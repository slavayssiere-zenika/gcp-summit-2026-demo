#!/usr/bin/env python3
"""
sre_report_runner.py — Génère un rapport SRE depuis les erreurs loggées dans prompts_api.

Usage : python3 sre_report_runner.py

Étapes :
  1. S'authentifie sur la prd via mcp_cli.get_jwt()
  2. Récupère tous les prompts commençant par 'error_correction:' depuis prompts_api
  3. Génère sre_report.md avec analyse et plan de remédiation
  4. Supprime les erreurs obsolètes (DELETE /prompts/{key})
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import httpx

# ── Configuration ──────────────────────────────────────────────────────────────
BASE_URL = os.getenv("ZENIKA_BASE_URL", "https://prd.zenika.slavayssiere.fr")
REPORT_FILE = Path("sre_report.md")

# Réutilise l'auth de mcp_cli pour ne pas dupliquer la logique
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from mcp_cli import get_jwt  # noqa: E402


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def fetch_error_prompts(token: str) -> list[dict]:
    """Récupère tous les prompts error_correction:* depuis prompts_api."""
    resp = httpx.get(
        f"{BASE_URL}/api/prompts/",
        headers=_headers(token),
        timeout=60.0,
    )
    if resp.status_code == 401:
        # Token cache périmé → forcer un nouveau login
        from pathlib import Path
        TOKEN_CACHE = Path.home() / ".cache" / "zenika_mcp_cli_token.json"
        TOKEN_CACHE.unlink(missing_ok=True)
        from mcp_cli import get_jwt as _get_fresh_jwt
        token = _get_fresh_jwt()
        resp = httpx.get(f"{BASE_URL}/api/prompts/",
                         headers=_headers(token), timeout=60.0)
    if resp.status_code != 200:
        print(
            f"❌ GET /api/prompts/ → {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    # prompts_api retourne {"prompts": [...], "total": N, "skip": N, "limit": N}
    prompts = data.get("prompts", data.get("items", data)
                       ) if isinstance(data, dict) else data
    if not isinstance(prompts, list):
        print(f"❌ Format inattendu : {type(data)}", file=sys.stderr)
        sys.exit(1)

    errors = [p for p in prompts if str(
        p.get("key", "")).startswith("error_correction:")]
    print(f"📋 {len(errors)} erreur(s) error_correction trouvée(s) sur {len(prompts)} prompts total.")
    return errors


def delete_prompt(key: str, token: str) -> bool:
    """Supprime un prompt par sa clé."""
    resp = httpx.delete(
        f"{BASE_URL}/api/prompts/{key}",
        headers=_headers(token),
        timeout=10.0,
    )
    return resp.status_code in (200, 204, 404)


def fetch_cloud_500_errors(token: str, hours: int = 24, limit: int = 15) -> list[dict]:
    """Récupère les erreurs 500 récentes depuis monitoring_mcp via son API call."""
    mcp_url = f"{BASE_URL.rstrip('/')}/monitoring-mcp/mcp/call"
    try:
        resp = httpx.post(
            mcp_url,
            headers=_headers(token),
            json={
                "name": "get_recent_500_errors",
                "arguments": {"hours_lookback": hours, "limit": limit}
            },
            timeout=30.0
        )
        if resp.status_code == 200:
            raw_result = resp.json()
            results = raw_result.get("result", [])
            if results:
                text_content = results[0].get("text", "")
                import json
                data = json.loads(text_content)
                errors = data if isinstance(
                    data, list) else data.get("errors", [])
                return errors
            else:
                print("⚠️ Réponse MCP vide ou sans résultat.", file=sys.stderr)
        else:
            print(
                f"⚠️ Échec appel monitoring_mcp ({resp.status_code}): {resp.text[:300]}", file=sys.stderr)
    except Exception as e:
        print(
            f"⚠️ Erreur lors de la récupération des erreurs 500 : {e}", file=sys.stderr)
    return []


def generate_report(error_prompts: list[dict], cloud_errors: list[dict]) -> str:
    """Génère le contenu Markdown du rapport SRE."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Rapport SRE — {now}",
        "",
        f"**Source** : `prompts_api` & `monitoring_mcp` (Cloud Logging) | **Total Anomalies** : {len(error_prompts) + len(cloud_errors)}",
        "",
    ]

    # --- Section 1: Erreurs applicatives (prompts) ---
    lines += ["## 🤖 Erreurs Applicatives (Agents)", ""]
    if not error_prompts:
        lines += ["*Aucune erreur d'agent active (prompts).* ", ""]
    else:
        for i, err in enumerate(error_prompts, 1):
            key = err.get("key", "?")
            value = err.get("value", "")
            parts = key.split(":")
            service = parts[1] if len(parts) > 1 else "inconnu"
            lines += [
                f"### [{i}] `{key}`",
                "",
                f"**Service** : `{service}`",
                "",
                "**Message d'erreur** :",
                "```",
                value[:2000] if value else "(vide)",
                "```",
                "",
            ]

    # --- Section 2: Erreurs HTTP 5xx (Cloud Logging) ---
    lines += [
        "## 🚨 Erreurs HTTP 5xx Récentes (Infrastructure / Pipelines)", ""]
    if not cloud_errors:
        lines += ["*Aucune erreur HTTP 5xx récente détectée dans les logs.*", ""]
    else:
        for i, err in enumerate(cloud_errors, 1):
            timestamp = err.get("timestamp", "?")
            service = err.get("service", "inconnu")
            req = err.get("request", {})
            method = req.get("method", "?")
            url = req.get("url", "?")
            status = req.get("status", 500)
            trace_id = err.get("trace_id", "inconnu")
            msg = err.get("message") or "Erreur HTTP 5xx"

            lines += [
                f"### [{i}] `{service}` — HTTP {status} sur `{method} {url}`",
                "",
                f"**Date** : `{timestamp}` | **Trace ID** : `{trace_id}`",
                "",
                "**Message d'erreur / Contexte** :",
                "```",
                msg[:2000],
                "```",
                "",
            ]

    # --- Section 3: Plan de remédiation ---
    lines += [
        "## Plan de remédiation",
        "",
        "> Analyse des erreurs ci-dessus et propositions de correction.",
        "",
    ]

    # Analyse automatique des prompts d'agents (dédupliquée par catégorie)
    analyzed_prompts = set()
    for err in error_prompts:
        key = err.get("key", "")
        value = err.get("value", "")
        parts = key.split(":")
        service = parts[1] if len(parts) > 1 else "inconnu"

        sig = None
        if "string indices must be integers" in value:
            sig = "string_indices"
        elif "401" in value or "Unauthorized" in value:
            sig = "auth_401"
        elif "404" in value or "Not Found" in value:
            sig = "not_found_404"

        if sig and sig in analyzed_prompts:
            continue
        if sig:
            analyzed_prompts.add(sig)

        if "string indices must be integers" in value:
            lines += [
                f"#### `{service}` — TypeError: string indices must be integers",
                "",
                "**Cause probable** : itération sur une chaîne au lieu d'un dict/list.",
                "Souvent dû à un `.get()` ou `for x in response` où `response` est une `str`",
                "plutôt qu'un objet JSON parsé.",
                "",
                "**Actions** :",
                f"- Vérifier les parsings JSON dans `{service}/` (réponses httpx non `.json()`-ées)",
                "- Chercher les `for item in data` sans vérification de type préalable",
                "- Vérifier que `response.json()` n'est pas appelé sur une erreur HTTP",
                "",
            ]
        elif "401" in value or "Unauthorized" in value:
            lines += [
                f"#### `{service}` — Erreur d'authentification 401",
                "",
                f"**Actions** : Vérifier la propagation JWT dans `{service}/`.",
                "",
            ]
        elif "404" in value or "Not Found" in value:
            lines += [
                f"#### `{service}` — Ressource introuvable 404",
                "",
                f"**Actions** : Vérifier les routes et les IDs dans `{service}/`.",
                "",
            ]
        else:
            lines += [
                f"#### `{service}` — Erreur générique",
                "",
                f"**Actions** : Analyser manuellement le message d'erreur dans `{service}/`.",
                "",
            ]

    # Analyse automatique des erreurs 500 (dédupliquée par catégorie)
    analyzed_cloud = set()
    for err in cloud_errors:
        service = err.get("service", "")
        req = err.get("request", {})
        url = req.get("url", "")
        msg = err.get("message", "") or ""

        sig = None
        if "pubsub/import-cv" in url:
            sig = "pubsub_jwt"
        elif "connection refused" in msg.lower() or "dial tcp" in msg.lower():
            sig = "conn_refused"

        if sig and sig in analyzed_cloud:
            continue
        if sig:
            analyzed_cloud.add(sig)

        if "pubsub/import-cv" in url:
            lines += [
                f"#### `{service}` — Échec d'authentification sur pubsub/import-cv",
                "",
                "**Cause probable** : Validation de token JWT échouée lors du push Pub/Sub.",
                "Vérifier si SECRET_KEY est vide suite à une purge de sécurité (main.py) ou si les secrets",
                "ne correspondent pas entre users-api et cv-api.",
                "",
                "**Actions** :",
                "- Importer la SECRET_KEY depuis `shared.auth.jwt` au lieu de `os.getenv`.",
                "- Relancer la remédiation en remettant en `PENDING` les fichiers impactés.",
                "",
            ]
        elif "connection refused" in msg.lower() or "dial tcp" in msg.lower():
            lines += [
                f"#### `{service}` — Connexion réseau refusée",
                "",
                "**Cause probable** : Le service cible est arrêté, en cours de redémarrage ou inaccessible.",
                "",
                "**Actions** : Vérifier si le service cible est sain et répond sur le port attendu.",
                "",
            ]

    return "\n".join(lines)


def main():
    print(f"🔐 Authentification sur {BASE_URL}...")
    token = get_jwt()
    print("✅ Token obtenu.\n")

    # Étape 1 : Récupérer les erreurs interactives (prompts)
    error_prompts = fetch_error_prompts(token)

    # Étape 2 : Récupérer les erreurs 500 (Cloud Logging)
    print("🚨 Récupération des erreurs 500 récentes depuis Cloud Logging...")
    cloud_errors = fetch_cloud_500_errors(token, hours=24, limit=15)
    print(f"📋 {len(cloud_errors)} erreur(s) 500 trouvée(s) dans Cloud Logging.")

    # Étape 3 : Générer le rapport
    report = generate_report(error_prompts, cloud_errors)
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(f"\n📄 Rapport généré : {REPORT_FILE}")

    # Étape 4 : Afficher le résumé
    total_anomalies = len(error_prompts) + len(cloud_errors)
    if total_anomalies > 0:
        if error_prompts:
            print("\n🤖 Erreurs d'Agents actives :")
            for e in error_prompts:
                key = e.get("key", "?")
                val_preview = str(e.get("value", ""))[:120].replace("\n", " ")
                print(f"  • {key}")
                print(f"    → {val_preview}")
        if cloud_errors:
            print("\n🚨 Erreurs HTTP 5xx récentes (Cloud Logging) :")
            for e in cloud_errors:
                service = e.get("service", "?")
                req = e.get("request", {})
                print(
                    f"  • {service} : {req.get('method')} {req.get('url')} -> {req.get('status')}")
        print(
            f"\n⚠️  {total_anomalies} anomalie(s) à corriger — voir {REPORT_FILE}")
    else:
        print("✅ Aucune erreur active — plateforme stable.")

    # Étape 5 : Nettoyage optionnel (erreurs déjà traitées)
    if error_prompts:
        print("\n💡 Pour supprimer une erreur d'agent traitée :")
        print(
            f"   curl -X DELETE {BASE_URL}/api/prompts/<key> -H 'Authorization: Bearer $TOKEN'")


if __name__ == "__main__":
    main()
