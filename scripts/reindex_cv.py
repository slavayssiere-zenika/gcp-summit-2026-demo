#!/usr/bin/env python3
"""
reindex_cv.py — Déclenche et surveille la ré-indexation des CVs (embeddings globaux et/ou chunks de missions).

Modes disponibles :
  embeddings  (défaut) — re-calcule les vecteurs globaux via /reindex-embeddings
  chunks               — génère les chunk-level embeddings via /bulk-reanalyse/reindex-mission-chunks (RAG R7)
  both                 — enchaîne embeddings puis chunks

Usage:
    python3 scripts/reindex_cv.py [--mode embeddings|chunks|both] [--tag AGENCY] [--user-id ID]

Exemples:
    python3 scripts/reindex_cv.py                          # embeddings globaux, tous les CVs
    python3 scripts/reindex_cv.py --mode chunks            # chunks de missions uniquement
    python3 scripts/reindex_cv.py --mode both --tag Paris  # les deux, agence Paris
    python3 scripts/reindex_cv.py --mode chunks --no-logs  # déclencher sans surveiller

Pré-requis:
    uv add httpx pyyaml
    GCLOUD_BIN=/path/to/gcloud python3 scripts/reindex_cv.py
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

_antigravity_env = Path(__file__).parent / ".antigravity_env"
if _antigravity_env.exists():
    for _line in _antigravity_env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

BASE_URL = os.getenv("ZENIKA_BASE_URL", "https://prd.zenika.slavayssiere.fr")
GCLOUD_BIN = os.getenv("GCLOUD_BIN", "gcloud")
GCP_PROJECT = os.getenv("ZENIKA_GCP_PROJECT", "prod-ia-staffing")
CLOUD_RUN_SERVICE = os.getenv("ZENIKA_CV_API_SERVICE", "cv-api-prd")
CLOUD_RUN_REGION = os.getenv("ZENIKA_REGION", "europe-west1")

TOKEN_CACHE = Path.home() / ".cache" / "zenika_mcp_cli_token.json"
TOKEN_TTL = 3300  # 55 minutes

POLL_TIMEOUT_S = int(os.getenv("REINDEX_TIMEOUT_S", "5400"))   # 90 min (chunks plus long)
POLL_INTERVAL_S = int(os.getenv("REINDEX_POLL_S", "15"))

_ENVS_DIR = Path(__file__).parent.parent / "platform-engineering" / "envs"
_ENV_DEFAULTS = {
    "prd": {"service_suffix": "-prd"},
    "uat": {"service_suffix": "-uat"},
    "dev": {"service_suffix": "-dev"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Configuration env YAML
# ─────────────────────────────────────────────────────────────────────────────

def load_env_yaml(env: str) -> dict:
    yaml_path = _ENVS_DIR / f"{env}.yaml"
    if not yaml_path.exists():
        print(f"❌ Fichier env introuvable : {yaml_path}", file=sys.stderr)
        sys.exit(1)
    if not _YAML_AVAILABLE:
        result = {}
        for line in yaml_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and ":" in line:
                k, _, v = line.partition(":")
                result[k.strip()] = v.strip().strip('"')
        return result
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def configure_from_env(env: str) -> None:
    global BASE_URL, GCP_PROJECT, CLOUD_RUN_SERVICE, TOKEN_CACHE

    cfg = load_env_yaml(env)
    base_domain = cfg.get("base_domain", "zenika.slavayssiere.fr")
    suffix = _ENV_DEFAULTS.get(env, {}).get("service_suffix", f"-{env}")

    BASE_URL = f"https://prd.{base_domain}" if env == "prd" else f"https://{env}.{base_domain}"
    GCP_PROJECT = cfg.get("project_id", GCP_PROJECT)
    CLOUD_RUN_SERVICE = f"cv-api{suffix}"
    TOKEN_CACHE = Path.home() / ".cache" / f"zenika_mcp_cli_token_{env}.json"

    secret = os.getenv("ZENIKA_SECRET_NAME", f"admin-password{suffix}")
    os.environ.setdefault("ZENIKA_SECRET_NAME", secret)

    print(f"   Env      : {env}", file=sys.stderr)
    print(f"   URL      : {BASE_URL}", file=sys.stderr)
    print(f"   Projet   : {GCP_PROJECT}", file=sys.stderr)
    print(f"   Service  : {CLOUD_RUN_SERVICE}", file=sys.stderr)


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

def _gcloud_admin_password() -> str:
    secret_name = os.getenv("ZENIKA_SECRET_NAME", "admin-password-prd")
    result = subprocess.run(
        [GCLOUD_BIN, "secrets", "versions", "access", "latest",
         f"--secret={secret_name}", f"--project={GCP_PROJECT}"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    print(f"❌ Secret '{secret_name}' introuvable dans '{GCP_PROJECT}'.", file=sys.stderr)
    sys.exit(1)


def _login_admin() -> str:
    admin_email = os.getenv("ZENIKA_ADMIN_EMAIL", "admin@zenika.com")
    password = _gcloud_admin_password()
    print(f"🔐 Authentification sur {BASE_URL} ({admin_email})…", file=sys.stderr)
    resp = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"email": admin_email, "password": password},
        timeout=15.0,
    )
    if resp.status_code != 200:
        print(f"❌ Login échoué [{resp.status_code}]: {resp.text[:300]}", file=sys.stderr)
        sys.exit(1)
    token = resp.json().get("access_token")
    if not token:
        print(f"❌ Réponse login sans access_token : {resp.text[:200]}", file=sys.stderr)
        sys.exit(1)
    return token


def _load_cached_token() -> str | None:
    if not TOKEN_CACHE.exists():
        return None
    try:
        data = json.loads(TOKEN_CACHE.read_text())
        if time.time() < data.get("expires_at", 0):
            return data["token"]
    except Exception:
        pass
    return None


def _save_token(token: str) -> None:
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps({"token": token, "expires_at": time.time() + TOKEN_TTL}))


def get_jwt(no_cache: bool = False) -> str:
    if no_cache and TOKEN_CACHE.exists():
        TOKEN_CACHE.unlink()
    cached = _load_cached_token()
    if cached:
        return cached
    token = _login_admin()
    _save_token(token)
    print("✅ Token JWT obtenu et mis en cache.", file=sys.stderr)
    return token


# ─────────────────────────────────────────────────────────────────────────────
# Déclenchement
# ─────────────────────────────────────────────────────────────────────────────

def trigger_reindex_embeddings(token: str, tag: str | None, user_id: int | None) -> dict:
    """Déclenche POST /reindex-embeddings (vecteurs globaux)."""
    params = {}
    if tag:
        params["tag"] = tag
    if user_id:
        params["user_id"] = user_id
    url = f"{BASE_URL}/api/cv/reindex-embeddings"
    print(f"\n🚀 [embeddings] Déclenchement : POST {url}")
    if params:
        print(f"   Filtres : {params}")
    resp = httpx.post(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=30.0)
    if resp.status_code == 403:
        print("❌ Accès refusé — compte non-administrateur.", file=sys.stderr)
        sys.exit(1)
    if resp.status_code not in (200, 202):
        print(f"❌ Erreur HTTP [{resp.status_code}] : {resp.text[:400]}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


def trigger_reindex_chunks(token: str, tag: str | None, user_id: int | None, force: bool = False) -> dict:
    """Déclenche POST /bulk-reanalyse/reindex-mission-chunks (RAG R7).

    force=False (défaut) : skip les profils déjà indexés (reprise après restart).
    force=True : supprime et recrée tous les chunks.
    """
    params: dict = {"force": str(force).lower()}
    if tag:
        params["tag"] = tag
    if user_id:
        params["user_id"] = user_id
    url = f"{BASE_URL}/api/cv/bulk-reanalyse/reindex-mission-chunks"
    print(f"\n🚀 [chunks] Déclenchement : POST {url}")
    if params:
        print(f"   Filtres : {params}")
    resp = httpx.post(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=30.0)
    if resp.status_code == 403:
        print("❌ Accès refusé — compte non-administrateur.", file=sys.stderr)
        sys.exit(1)
    if resp.status_code not in (200, 202):
        print(f"❌ Erreur HTTP [{resp.status_code}] : {resp.text[:400]}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Polling Cloud Run Logs
# ─────────────────────────────────────────────────────────────────────────────

def _build_log_filter(since_ts: str, log_tag: str) -> str:
    """Filtre Cloud Logging pour les logs du cv_api.

    Les logs Python structurés (logger.info) arrivent en jsonPayload.message.
    On filtre sur la sous-chaîne du tag sans les crochets pour éviter
    l'ambiguïté RE2 ([] = classe de caractères en regex Cloud Logging).
    On exclut les health checks Uvicorn (textPayload /health).
    """
    bare = log_tag.strip("[]")  # ex: "CHUNK_REINDEX" ou "REINDEX"
    # Pour [REINDEX] on préfixe \[ pour ne pas capturer [CHUNK_REINDEX]
    # jsonPayload.message regex supporte \[ comme crochet littéral
    if bare == "REINDEX":
        pattern = r"\[REINDEX\]"
    else:
        pattern = bare
    return (
        f'resource.type="cloud_run_revision" '
        f'resource.labels.service_name="{CLOUD_RUN_SERVICE}" '
        f'resource.labels.location="{CLOUD_RUN_REGION}" '
        f'jsonPayload.message=~"{pattern}" '
        f'timestamp>="{since_ts}"'
    )


def fetch_logs(since_ts: str, log_tag: str) -> tuple[list[str], str | None]:
    """Récupère les logs Cloud Run contenant log_tag depuis since_ts.

    Retourne la liste des messages (textPayload ou jsonPayload.message),
    sans dupliquer les lignes vides ou sans contenu.
    """
    result = subprocess.run(
        [
            GCLOUD_BIN, "logging", "read",
            _build_log_filter(since_ts, log_tag),
            "--project", GCP_PROJECT,
            "--format", "json",
            "--limit", "300",
            "--order", "asc",
        ],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        err = (result.stderr or "").strip()[:200]
        return [], err or f"gcloud exit {result.returncode}"
    if not result.stdout.strip():
        return [], None
    try:
        entries = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [], "JSON invalide dans la réponse gcloud"
    lines = []
    for entry in entries:
        msg = (
            entry.get("textPayload")
            or (entry.get("jsonPayload") or {}).get("message")
            or ""
        )
        msg = msg.strip()
        if msg:
            lines.append(msg)
    return lines, None


def _progress_bar(pct: int, width: int = 30) -> str:
    filled = int(width * pct / 100)
    return "[" + "█" * filled + "░" * (width - filled) + f"] {pct:3d}%"


def _keepalive(token: str) -> None:
    """Ping l'endpoint data-quality pour éviter le scale-to-zero Cloud Run.

    Cloud Run coupe l'instance après quelques minutes sans requête entrante,
    tuant la background task. Ce ping léger maintient l'instance active.
    """
    try:
        httpx.get(
            f"{BASE_URL}/api/cv/bulk-reanalyse/data-quality",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
    except Exception:
        pass  # Non-bloquant : le keepalive ne doit jamais interrompre le polling


def poll_until_done(start_ts: str, log_tag: str, done_marker: str, token: str = "") -> tuple[bool, int, int]:
    """
    Surveille les logs Cloud Run jusqu'au marker de fin.
    Pinge l'API toutes les 30s pour maintenir l'instance Cloud Run active (anti scale-to-zero).

    Args:
        start_ts   : timestamp ISO8601 avant le déclenchement
        log_tag    : ex '[REINDEX]' ou '[CHUNK_REINDEX]'
        done_marker: chaîne signalant la fin (ex 'Terminé' ou 'terminée')
        token      : JWT pour les requêtes keepalive
    """
    print(f"\n⏳ Surveillance des logs Cloud Run ({log_tag})")
    print(f"   Service  : {CLOUD_RUN_SERVICE} ({CLOUD_RUN_REGION})")
    print(f"   Projet   : {GCP_PROJECT}")
    print(f"   Depuis   : {start_ts}")
    print(f"   Timeout  : {POLL_TIMEOUT_S // 60} min | Intervalle : {POLL_INTERVAL_S}s")
    print("   Keepalive: GET /api/cv/bulk-reanalyse/data-quality toutes les 30s\n")

    seen_lines: set[str] = set()
    elapsed = 0
    nb_success = 0
    nb_failed = 0
    gcloud_errors = 0
    total_expected = 0
    keepalive_counter = 0

    while elapsed < POLL_TIMEOUT_S:
        ts_now = time.strftime("%H:%M:%S")

        # Keepalive : toutes les 2 itérations (~30s) pour éviter le scale-to-zero
        keepalive_counter += 1
        if token and keepalive_counter % 2 == 0:
            _keepalive(token)

        logs, gcloud_err = fetch_logs(start_ts, log_tag)

        if gcloud_err:
            gcloud_errors += 1
            print(f"  [{ts_now}] ⚠️  gcloud erreur ({gcloud_errors}x) : {gcloud_err}")
        else:
            gcloud_errors = 0

        new_lines = [ln for ln in logs if ln not in seen_lines]

        if new_lines:
            for line in new_lines:
                seen_lines.add(line)
                print(f"  [{ts_now}] {line}")

                # Total attendu — log: "[CHUNK_REINDEX] 1461 profils à traiter"
                m_total = re.search(r"(\d+)\s+profils?\s+(?:à|a)\s+", line, re.IGNORECASE)
                if m_total:
                    total_expected = int(m_total.group(1))

                # Progression — log: "[CHUNK_REINDEX] 10% — 146/1461 (146 ok, 0 échecs, ...)"
                m_prog = re.search(
                    r"(\d+)%\s+[—\-]\s+(\d+)/(\d+).*?(\d+)\s+ok.*?(\d+)\s+[ée]chec",
                    line, re.IGNORECASE,
                )
                if m_prog:
                    pct = int(m_prog.group(1))
                    done_n, total_n = int(m_prog.group(2)), int(m_prog.group(3))
                    ok_n, fail_n = int(m_prog.group(4)), int(m_prog.group(5))
                    # Mise à jour des compteurs en temps réel depuis les logs
                    nb_success = ok_n
                    nb_failed = fail_n
                    if total_expected == 0:
                        total_expected = total_n
                    bar = _progress_bar(pct)
                    print(f"           {bar}  ({done_n}/{total_n} — ✅ {ok_n} ok  ❌ {fail_n} échecs)")

                # Fin
                if done_marker in line:
                    m_end = re.search(r"(\d+)\s+succ[eè]s.*?(\d+)\s+[eé]chec", line, re.IGNORECASE)
                    if m_end:
                        nb_success = int(m_end.group(1))
                        nb_failed = int(m_end.group(2))
                    return True, nb_success, nb_failed

                # Annulation
                if log_tag in line and "annul" in line.lower():
                    print("\n❌ Ré-indexation annulée (voir logs ci-dessus).")
                    return False, 0, 0
        else:
            if total_expected == 0:
                status = "⏳ En attente du démarrage de la background task…"
            else:
                pct_done = round(nb_success / total_expected * 100) if total_expected else 0
                bar = _progress_bar(pct_done)
                status = f"⏳ En cours  {bar}  ({nb_success}/{total_expected} ok, {nb_failed} échecs)"
            elapsed_str = f"{elapsed // 60}m{elapsed % 60:02d}s"
            print(f"  [{ts_now}] {status}  ({elapsed_str} écoulées)")

        time.sleep(POLL_INTERVAL_S)
        elapsed += POLL_INTERVAL_S

    print(f"\n⚠️  Timeout atteint ({POLL_TIMEOUT_S // 60} min) sans détection de fin.")
    return False, 0, 0


# ─────────────────────────────────────────────────────────────────────────────
# Rapport qualité (SQL via MCP monitoring)
# ─────────────────────────────────────────────────────────────────────────────

def _mcp_query(token: str, sql: str) -> list[dict]:
    mcp_url = f"{BASE_URL}/monitoring-mcp/mcp"
    try:
        resp = httpx.post(
            f"{mcp_url}/call",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"name": "execute_read_only_query", "arguments": {"query": sql}},
            timeout=30.0,
        )
        if resp.status_code != 200:
            return []
        raw = resp.json()
        results = raw.get("result", [])
        if not results:
            return []
        return json.loads(results[0].get("text", "[]"))
    except Exception:
        return []


def print_quality_report(token: str, tag: str | None, mode: str) -> None:
    print("\n" + "═" * 65)
    print("📊  RAPPORT QUALITÉ POST-RÉINDEXATION")
    print("═" * 65)
    tag_filter = f"AND source_tag ILIKE '%{tag}%'" if tag else ""

    # ── Embeddings globaux ────────────────────────────────────────────────────
    if mode in ("embeddings", "both"):
        stats = _mcp_query(token, f"""
            SELECT
                COUNT(*)                                             AS total_profils,
                COUNT(semantic_embedding)                            AS avec_embedding,
                COUNT(*) - COUNT(semantic_embedding)                 AS sans_embedding,
                ROUND(AVG(extraction_reliability_score)::numeric, 1) AS score_moyen,
                COUNT(CASE WHEN extraction_reliability_score >= 70 THEN 1 END) AS score_ok
            FROM cv_profiles WHERE 1=1 {tag_filter}
        """)
        if stats:
            s = stats[0]
            total = s.get("total_profils", 0)
            avec = s.get("avec_embedding", 0)
            sans = s.get("sans_embedding", 0)
            score_moy = s.get("score_moyen", "N/A")
            ok = s.get("score_ok", 0)
            coverage_pct = round(avec / total * 100, 1) if total else 0
            ok_pct = round(ok / total * 100, 1) if total else 0
            print("\n  📦 Embeddings globaux")
            print(f"  ├─ Corpus               : {total} profils{f' (filtre: {tag})' if tag else ''}")
            print(f"  ├─ Avec embedding       : {avec} / {total} ({coverage_pct}%)")
            print(f"  ├─ Sans embedding       : {sans}")
            print(f"  ├─ Score fiabilité moyen: {score_moy}%")
            print(f"  └─ Scores ≥ 70%         : {ok} ({ok_pct}%)")
        else:
            print("  ⚠️  Stats embeddings non disponibles (MCP indisponible).")

    # ── Chunks de missions (R7) ───────────────────────────────────────────────
    if mode in ("chunks", "both"):
        chunk_stats = _mcp_query(token, f"""
            SELECT
                COUNT(*)                  AS total_chunks,
                COUNT(DISTINCT user_id)   AS profils_indexes,
                ROUND(AVG(
                    sub.cnt
                )::numeric, 1)            AS avg_chunks_par_profil
            FROM (
                SELECT user_id, COUNT(*) AS cnt
                FROM cv_mission_embeddings
                WHERE chunk_embedding IS NOT NULL
                {('AND source_tag ILIKE ' + "'" + '%' + tag + '%' + "'") if tag else ''}
                GROUP BY user_id
            ) sub
        """)
        if chunk_stats and chunk_stats[0].get("total_chunks"):
            c = chunk_stats[0]
            total_c = c.get("total_chunks", 0)
            profils = c.get("profils_indexes", 0)
            avg = c.get("avg_chunks_par_profil", 0)
            print("\n  🧩 Chunks de missions (R7)")
            print(f"  ├─ Total chunks         : {total_c:,}")
            print(f"  ├─ Profils indexés      : {profils:,}")
            print(f"  └─ Chunks / profil      : {avg}")
        else:
            print("\n  ⚠️  Table cv_mission_embeddings vide — indexation incomplète ou non démarrée.")

    # ── Profils à surveiller ──────────────────────────────────────────────────
    problems = _mcp_query(token, f"""
        SELECT user_id, source_tag, current_role,
               COALESCE(extraction_reliability_score::text, 'SANS EMBEDDING') AS score
        FROM cv_profiles
        WHERE (extraction_reliability_score < 60 OR semantic_embedding IS NULL)
              {tag_filter}
        ORDER BY extraction_reliability_score ASC NULLS FIRST
        LIMIT 5
    """)
    if problems:
        print(f"\n  ⚠️  Top {len(problems)} profils à surveiller (score bas ou embedding manquant):")
        for p in problems:
            print(
                f"    user_id={p.get('user_id')} | {p.get('source_tag', 'N/A'):15s} | "
                f"{(p.get('current_role') or 'N/A')[:35]:35s} | score={p.get('score')}"
            )

    # ── FinOps ────────────────────────────────────────────────────────────────
    actions = "'reindex_embedding','reindex_chunk_embedding'"
    finops = _mcp_query(token, f"""
        SELECT action, SUM(input_tokens) AS tokens, COUNT(*) AS appels
        FROM ai_usage
        WHERE action IN ({actions})
          AND created_at >= NOW() - INTERVAL '3 hours'
        GROUP BY action
    """)
    if finops:
        print("\n  💰 FinOps (3 dernières heures):")
        for row in finops:
            tokens = row.get("tokens", 0) or 0
            appels = row.get("appels", 0)
            cout = round((tokens * 4 / 1000) * 0.000025, 4)
            print(f"    {row.get('action', '?'):35s} : {appels} appels | {tokens:,} tokens | ~${cout}")

    print("\n" + "═" * 65)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Déclenche et surveille la ré-indexation des CVs (vecteurs globaux et/ou chunks).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--env", default="prd", choices=["prd", "uat", "dev"],
        help="Environnement cible (défaut: prd).",
    )
    parser.add_argument(
        "--mode", default="embeddings", choices=["embeddings", "chunks", "both"],
        help=(
            "embeddings (défaut) : vecteurs globaux via /reindex-embeddings. "
            "chunks : chunks de missions via /bulk-reanalyse/reindex-mission-chunks. "
            "both : enchaîne les deux."
        ),
    )
    parser.add_argument("--tag", default=None, help="Filtre par agence (source_tag)")
    parser.add_argument("--user-id", type=int, default=None, help="Filtre par user_id")
    parser.add_argument("--no-cache", action="store_true", help="Forcer un nouveau login JWT")
    parser.add_argument("--no-logs", action="store_true",
                        help="Déclencher sans surveiller les logs Cloud Run (retour immédiat)")
    parser.add_argument("--force", action="store_true",
                        help="(mode chunks) Supprimer et recréer tous les chunks (défaut: skip déjà indexés)")
    args = parser.parse_args()

    configure_from_env(args.env)
    token = get_jwt(no_cache=args.no_cache)
    start_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    all_ok = True

    # ── Mode embeddings ou both ───────────────────────────────────────────────
    if args.mode in ("embeddings", "both"):
        resp = trigger_reindex_embeddings(token, args.tag, args.user_id)
        print(f"\n   ✅ Réponse API embeddings : {json.dumps(resp, ensure_ascii=False)}")

        if not args.no_logs:
            t0 = time.monotonic()
            done, nb_ok, nb_err = poll_until_done(start_ts, "[REINDEX]", "Terminé", token)
            elapsed = int(time.monotonic() - t0)
            mins, secs = divmod(elapsed, 60)
            if done:
                icon = "✅" if nb_err == 0 else "⚠️"
                print(f"\n{icon} Embeddings terminés en {mins}m{secs:02d}s — {nb_ok} succès, {nb_err} échecs")
            else:
                print("\n⚠️  Embeddings non confirmés (timeout).")
                all_ok = False

            # Rafraîchir le start_ts pour le prochain polling
            start_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # ── Mode chunks ou both ───────────────────────────────────────────────────
    if args.mode in ("chunks", "both"):
        resp = trigger_reindex_chunks(token, args.tag, args.user_id, getattr(args, 'force', False))
        print(f"\n   ✅ Réponse API chunks : {json.dumps(resp, ensure_ascii=False)}")

        if not args.no_logs:
            t0 = time.monotonic()
            done, nb_ok, nb_err = poll_until_done(start_ts, "[CHUNK_REINDEX]", "terminée", token)
            elapsed = int(time.monotonic() - t0)
            mins, secs = divmod(elapsed, 60)
            if done:
                icon = "✅" if nb_err == 0 else "⚠️"
                print(f"\n{icon} Chunks terminés en {mins}m{secs:02d}s — {nb_ok} succès, {nb_err} échecs")
            else:
                print("\n⚠️  Chunks non confirmés (timeout 90 min).")
                all_ok = False

    if args.no_logs:
        print("\n⚠️  --no-logs : surveillance désactivée. Vérifiez les logs Cloud Run.")
        sys.exit(0)

    # ── Rapport qualité ───────────────────────────────────────────────────────
    print_quality_report(token, args.tag, args.mode)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
