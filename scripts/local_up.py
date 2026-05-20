#!/usr/bin/env python3
"""
local_up.py — Déploiement local depuis les images GCP Artifact Registry.

Aucun rebuild local : pull la dernière version déployée par deploy.sh et
lance docker-compose up. Optionnellement enchâîne seed_data + Locust perf.

Usage :
    python3 scripts/local_up.py                    # pull + up
    python3 scripts/local_up.py --no-pull          # up sans re-pull
    python3 scripts/local_up.py --perf             # pull + up + seed perf + locust
    python3 scripts/local_up.py --seed             # seed standard (12 users) uniquement
    python3 scripts/local_up.py --seed-perf        # seed perf (400 users) uniquement
    python3 scripts/local_up.py --service users_api items_api  # pull/up partiel
"""
import argparse
import csv
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# seed_data.py est dans le même dossier scripts/
sys.path.insert(0, str(Path(__file__).parent))
import seed_data  # noqa: E402

# ── Configuration (miroir de deploy.sh) ────────────────────────────────────────
PROJECT_ID = "slavayssiere-sandbox-462015"
REGION = "europe-west1"
REGISTRY = "z-gcp-summit-services-dev"
AR_DOCKER_HOST = f"{REGION}-docker.pkg.dev"
AR_REPO = f"{AR_DOCKER_HOST}/{PROJECT_ID}/{REGISTRY}"
GCLOUD_BIN = os.getenv(
    "GCLOUD_BIN",
    "/Users/sebastien.lavayssiere/Apps/google-cloud-sdk/bin/gcloud"
)
ROOT = Path(__file__).parent.parent

# Services avec une image propre dans AR (buildés par deploy.sh)
AR_SERVICES = [
    "agent_hr_api",
    "agent_missions_api",
    "agent_ops_api",
    "agent_router_api",
    "analytics_mcp",
    "competencies_api",
    "cv_api",
    "db_migrations",
    "drive_api",
    "items_api",
    "missions_api",
    "monitoring_mcp",
    "missions_api",
    "prompts_api",
    "users_api",
    "drive_api",
]

# Bucket GCS contenant les archives du frontend (cf. deploy.sh)
FRONTEND_BUCKET = "z-gcp-summit-frontend"
FRONTEND_DIST = ROOT / "frontend" / "dist"
FRONTEND_VERSION_FILE = FRONTEND_DIST / ".local_version"

# Services buildés localement — vide depuis la migration vers GCS pour le frontend
LOCAL_BUILD_SERVICES: list = []

# Sidecars MCP qui partagent l'image de leur API parente.
# clé = nom sidecar dans docker-compose, valeur = service AR source
MCP_SIDECAR_ALIASES: dict = {
    "competencies_mcp": "competencies_api",
    "cv_mcp": "cv_api",
    "drive_mcp": "drive_api",
    "items_mcp": "items_api",
    "missions_mcp": "missions_api",
    "prompts_mcp": "prompts_api",
    "users_mcp": "users_api",
    "missions_mcp": "missions_api",
    "drive_mcp": "drive_api",
}

# Locust config
# Mode perf standard (--perf)
LOCUST_USERS = 50
LOCUST_SPAWN_RATE = 10
LOCUST_DURATION = "1m"

# Mode stress (--stress) : montee progressive vers 500 users, navigation pure sans ingestion CV
LOCUST_STRESS_USERS = 500
LOCUST_STRESS_SPAWN_RATE = 5   # 5/s -> 500 users atteints apres ~100s
LOCUST_STRESS_DURATION = "5m"
# Distributed : 1 master + N workers. Regle : 1 worker par 170 users.
# 500 / 170 ≈ 3 workers. Machine 12 CPUs, services ~6 CPUs → 3 workers sans contention.
LOCUST_STRESS_WORKERS = 3

RESULTS_DIR = ROOT / "locust" / "results"


# ── Helpers ──────────────────────────────────────────────────────────────────

def run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    """Wrapper subprocess.run avec check=True par défaut."""
    kwargs.setdefault("check", True)
    return subprocess.run(cmd, **kwargs)


def ar_image(service: str, tag: str = "latest") -> str:
    """Retourne le nom complet de l'image dans Artifact Registry."""
    return f"{AR_REPO}/{service}:{tag}"


def local_image(service: str) -> str:
    """
    Retourne le nom de l'image local attendu par docker-compose.
    docker-compose nomme les images <project_dir>-<service>.
    """
    return f"test-open-code-{service}"


# ── Auth ──────────────────────────────────────────────────────────────────────

def authenticate_docker() -> None:
    """Configure Docker pour s'authentifier à l'Artifact Registry GCP."""
    print(f"🔑 Authentification Docker vers {AR_DOCKER_HOST}...")
    run([GCLOUD_BIN, "auth", "configure-docker", AR_DOCKER_HOST, "--quiet"])
    print("  ✅ Authentification réussie.")


# ── Pull + Tag ────────────────────────────────────────────────────────────────

def pull_and_tag(services: list) -> None:
    """Pull :latest depuis AR, re-tag pour docker-compose et alias les sidecars MCP."""
    print(f"\n📥 Pull de {len(services)} image(s) depuis Artifact Registry...")
    for service in services:
        src = ar_image(service)
        dst = local_image(service)
        print(f"\n  ↓ {src}")
        run(["docker", "pull", "--platform", "linux/amd64", src])
        run(["docker", "tag", src, dst])
        print(f"    → tagué : {dst}")

        # Tag également les sidecars MCP qui partagent cette image
        for sidecar, parent in MCP_SIDECAR_ALIASES.items():
            if parent == service:
                sidecar_dst = local_image(sidecar)
                run(["docker", "tag", src, sidecar_dst])
                print(f"    → alias sidecar : {sidecar_dst}")

    print(f"\n✅ {len(services)} image(s) (+ sidecars MCP) prêtes.")


def image_exists_locally(service: str) -> bool:
    """Vérifie si l'image locale existe dans le daemon Docker."""
    result = subprocess.run(
        ["docker", "image", "inspect", local_image(service)],
        capture_output=True,
    )
    return result.returncode == 0


def all_images_present(services: list) -> list:
    """
    Retourne la liste des services AR dont l'image locale est absente.
    Vérifie aussi les sidecars MCP associés.
    """
    missing = []
    for service in services:
        if not image_exists_locally(service):
            missing.append(service)
            continue
        # Vérifier aussi les sidecars de ce service
        for sidecar, parent in MCP_SIDECAR_ALIASES.items():
            if parent == service and not image_exists_locally(sidecar):
                # Le parent est présent mais le sidecar n'est pas tagé — on re-tag
                run(["docker", "tag", local_image(service), local_image(sidecar)])
                print(f"  🔁 Sidecar re-tagé : {local_image(sidecar)}")
    return missing


def ensure_images(services: list, force_pull: bool) -> None:
    """
    S'assure que toutes les images sont disponibles localement.
    - Si force_pull : pull tout depuis AR.
    - Sinon : pull uniquement les images manquantes (smart pull).
    """
    if force_pull:
        authenticate_docker()
        pull_and_tag(services)
        return

    missing = all_images_present(services)
    if missing:
        print(
            f"\n⚠️  {len(missing)} image(s) absente(s) localement, pull automatique :"
            f" {', '.join(missing)}"
        )
        authenticate_docker()
        pull_and_tag(missing)
    else:
        print("\n✅ Toutes les images sont déjà présentes localement.")


def ensure_frontend(force: bool = False) -> None:
    """
    Smart-pull du frontend depuis le bucket GCS.

    Logique :
      1. Récupère la liste des archives du bucket (tri lexicographique → dernière = plus récente).
      2. Compare avec le marqueur .local_version dans frontend/dist/.
      3. Si identique et force=False → skip (aucun download).
      4. Sinon → gcloud storage cp + tar -xzf → frontend/dist/.
    """
    print("\n🌐 Vérification du frontend depuis GCS...")
    # 1. Dernière archive disponible
    result = subprocess.run(
        [GCLOUD_BIN, "storage", "ls", f"gs://{FRONTEND_BUCKET}/"],
        capture_output=True, text=True, check=True,
    )
    archives = sorted(line.strip() for line in result.stdout.splitlines() if line.strip().endswith(".tar.gz"))
    if not archives:
        print("  ⚠️  Aucune archive trouvée dans le bucket GCS. Frontend ignoré.")
        return
    latest_gcs = archives[-1]  # ex: gs://z-gcp-summit-frontend/frontend-20260516141607-v0.1.1.tar.gz
    latest_name = latest_gcs.split("/")[-1]  # ex: frontend-20260516141607-v0.1.1.tar.gz

    # 2. Version locale
    local_version = FRONTEND_VERSION_FILE.read_text().strip() if FRONTEND_VERSION_FILE.exists() else ""

    if not force and local_version == latest_name and FRONTEND_DIST.exists():
        print(f"  ✅ Frontend à jour ({latest_name}) — skip download.")
        return

    print(f"  ↓ Téléchargement : {latest_name}")
    tmp_archive = ROOT / latest_name
    run([GCLOUD_BIN, "storage", "cp", latest_gcs, str(tmp_archive)])

    # 3. Extraction → frontend/dist/ (l'archive contient frontend/dist/...)
    if FRONTEND_DIST.exists():
        shutil.rmtree(FRONTEND_DIST)
    # tar -xzf recrée frontend/dist/ à partir de la racine du projet
    run(["tar", "-xzf", str(tmp_archive), "-C", str(ROOT)], cwd=ROOT)
    tmp_archive.unlink(missing_ok=True)

    # 4. Marqueur de version
    FRONTEND_VERSION_FILE.write_text(latest_name)
    print(f"  ✅ Frontend extrait : {FRONTEND_DIST} ({latest_name})")


# ── Docker Compose ────────────────────────────────────────────────────────────

def compose_up(services: list) -> None:
    """Lance docker-compose up -d en reutilisant les images existantes (pas de rebuild).

    Le vrai build appartient exclusivement a deploy.sh.
    --remove-orphans assure que les nouveaux env vars (DB_POOL_SIZE, etc.) sont pris en
    compte en recreant les conteneurs si la config docker-compose a change.
    """
    cmd = ["docker-compose", "up", "-d", "--no-build", "--remove-orphans"]
    if services:
        cmd += services
    print(f"\n🚀 Démarrage : {' '.join(cmd)}")
    run(cmd, cwd=ROOT)


# ── Perf : Seed + Locust ──────────────────────────────────────────────────────

def run_seed(perf: bool = False) -> None:
    """
    Exécute le seed des données en important seed_data directement.
    - perf=False : 12 users, 50 items (mode développement)
    - perf=True  : 400 users, 2000 items (mode test de charge)
    """
    label = "perf (400 users, 2000 items)" if perf else "standard (12 users, 50 items)"
    print(f"\n📦 Ingestion des données [{label}]...")
    seed_data.main(perf=perf)
    print("  ✅ Seed terminé.")


def _build_locust_image() -> None:
    """Build l image locust (locustio/locust + pydantic). Cache Docker si inchange."""
    print("  🔨 Build image locust (cache Docker si inchange)...")
    run(["docker-compose", "--profile", "perf", "build", "locust"], cwd=ROOT)


def _locust_base_args(users: int, spawn: int, duration: str, scenario: str,
                      autostart: bool = True) -> list:
    """Arguments communs aux modes standalone et distributed.

    autostart=True (defaut) : --autostart, web UI accessible sur :8089 en temps reel.
    """
    start_mode = "--autostart" if autostart else "--headless"
    return [
        "-f", "/locust/locustfile.py",
        start_mode,
        "--autoquit", "5",   # quitte 5s apres la fin du test (requis avec --autostart)
        "-u", str(users),
        "-r", str(spawn),
        "-t", duration,
        "--csv", "/locust/results/perf_stats",
        "--html", "/locust/results/perf_report.html",
        "--host", "http://localhost",
    ]


def _run_locust_standalone(users: int, spawn: int, duration: str, scenario: str) -> bool:
    """Mode standalone (--perf, 50 users) : 1 seul process Locust, web UI sur :8089."""
    cmd = [
        "docker-compose", "--profile", "perf",
        "run", "--rm",
        "-p", "8089:8089",
        "-e", f"LOCUST_SCENARIO={scenario}",
        "locust",
    ] + _locust_base_args(users, spawn, duration, scenario, autostart=True)
    print("  🟡 Web UI disponible sur http://localhost:8089")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode not in (0, 1):
        print(f"  ❌ Locust standalone echoue (code {result.returncode}) — fail-fast.")
        return False
    print("  ✅ Test Locust standalone termine.")
    return True


def _run_locust_distributed(users: int, spawn: int, duration: str, scenario: str) -> bool:
    """Mode distributed (--stress, 500 users) : 1 master + LOCUST_STRESS_WORKERS workers.

    Architecture :
      - Master demarre via "docker-compose up -d locust-master" avec container_name=locust-master.
        Hostname DNS fixe → workers peuvent resoudre "locust-master" sur monitoring_net.
      - Workers demarres en background (docker-compose up --scale N).
      - Script attend l exit du master via "docker wait locust-master" (bloquant).
      - Workers stoppes apres exit du master.
    Rapport HTML genere par le master dans /locust/results/perf_report.html.
    """
    n_workers = LOCUST_STRESS_WORKERS
    print("  🔨 Build images locust-master/worker (cache Docker si inchange)...")
    run(["docker-compose", "--profile", "perf-stress", "build", "locust-master", "locust-worker"], cwd=ROOT)

    # Nettoyage preventif du master precedent (container_name fixe → conflit si existe deja)
    subprocess.run(
        ["docker", "rm", "-f", "locust-master"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    # Master : run -d avec port 8089 expose + --autostart (web UI accessible en temps reel)
    master_args = _locust_base_args(users, spawn, duration, scenario, autostart=True) + [
        "--master",
        f"--expect-workers={n_workers}",
    ]
    env_args = ["-e", f"LOCUST_SCENARIO={scenario}"]
    run(
        [
            "docker-compose", "--profile", "perf-stress",
            "run", "-d", "--name", "locust-master",
            "-p", "8089:8089",
        ] + env_args + [
            "locust-master",
        ] + master_args,
        cwd=ROOT,
    )
    print("  🟡 Master demarre. Web UI disponible sur http://localhost:8089")
    print(f"     Demarrage {n_workers} workers...")

    # Workers : up --scale (se connectent a locust-master par DNS container_name)
    # Workers : up -d (detache) — sans --no-deps car depends_on est retire du compose
    run(
        [
            "docker-compose", "--profile", "perf-stress",
            "up", "-d", "--scale", f"locust-worker={n_workers}",
            "locust-worker",
        ],
        cwd=ROOT,
    )
    time.sleep(8)  # Workers : ~3s demarrage + ~5s connexion au master avant autostart
    print(f"  🔥 Test en cours ({n_workers} workers connectes au master)...")

    # Attente bloquante de la fin du master
    wait_result = subprocess.run(["docker", "wait", "locust-master"], cwd=ROOT, capture_output=True, text=True)
    exit_code = int(wait_result.stdout.strip()) if wait_result.stdout.strip().isdigit() else 2

    print("  🛑 Arret des workers...")
    subprocess.run(
        ["docker-compose", "--profile", "perf-stress", "stop", "locust-worker"],
        cwd=ROOT, stdout=subprocess.DEVNULL,
    )
    # Copier les resultats depuis le master avant de le supprimer
    subprocess.run(
        ["docker", "cp", "locust-master:/locust/results/.", str(RESULTS_DIR)],
        cwd=ROOT,
    )
    subprocess.run(["docker", "rm", "-f", "locust-master"], cwd=ROOT, stdout=subprocess.DEVNULL)

    if exit_code not in (0, 1):
        print(f"  ❌ Locust master echoue (code {exit_code}) — fail-fast.")
        return False
    print(f"  ✅ Test Locust distribue termine ({n_workers} workers).")
    return True


def run_locust(stress: bool = False) -> bool:
    """Lance Locust : standalone (--perf, 50 users) ou distribue (--stress, 500 users).

    Les deux modes generent :
      - CSV : /locust/results/perf_stats_*.csv
      - HTML : /locust/results/perf_report.html (graphiques latence/throughput)
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if stress:
        users, spawn, duration = LOCUST_STRESS_USERS, LOCUST_STRESS_SPAWN_RATE, LOCUST_STRESS_DURATION
        scenario = "navigation"
        label = f"STRESS distribue {users} users ({LOCUST_STRESS_WORKERS} workers), {duration}"
        print(f"\n🔥 Lancement Locust ({label})...")
        return _run_locust_distributed(users, spawn, duration, scenario)
    else:
        users, spawn, duration = LOCUST_USERS, LOCUST_SPAWN_RATE, LOCUST_DURATION
        scenario = "full"
        label = f"{users} users standalone, {duration}"
        print(f"\n🔥 Lancement Locust ({label})...")
        _build_locust_image()
        return _run_locust_standalone(users, spawn, duration, scenario)


def display_results() -> None:
    """Affiche les résultats CSV de Locust + rapport d analyse copiable."""
    stats_file = RESULTS_DIR / "perf_stats_stats.csv"
    failures_file = RESULTS_DIR / "perf_stats_failures.csv"

    sep = "=" * 80
    print(f"\n{sep}")
    print("RESULTATS DE PERFORMANCE")
    print(sep)

    if not stats_file.exists():
        print(f"Fichier de stats introuvable : {stats_file}")
        return

    with open(stats_file, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    detail_rows = [r for r in rows if r.get("Name") != "Aggregated"]
    agg_rows = [r for r in rows if r.get("Name") == "Aggregated"]

    col_w = [38, 8, 8, 10, 10, 10, 10, 8]
    headers = ["Endpoint", "Req/s", "Fail%", "Median(ms)", "95%(ms)", "99%(ms)", "Max(ms)", "Errors"]
    print("".join(h.ljust(col_w[i]) for i, h in enumerate(headers)))
    print("-" * sum(col_w))

    def fmt(r: dict) -> str:
        cols = [
            r.get("Name", "")[:36],
            r.get("Requests/s", "-"),
            r.get("Failure %", "-"),
            r.get("50%", "-"),
            r.get("95%", "-"),
            r.get("99%", "-"),
            r.get("Max", "-"),
            r.get("Failure Count", "-"),
        ]
        return "".join(str(c).ljust(col_w[i]) for i, c in enumerate(cols))

    for row in sorted(detail_rows, key=lambda r: float(r.get("95%", 0) or 0), reverse=True):
        print(fmt(row))

    if agg_rows:
        print("-" * sum(col_w))
        print(fmt(agg_rows[0]) + "  TOTAL")

    failures: list = []
    if failures_file.exists():
        with open(failures_file, newline="", encoding="utf-8") as f:
            failures = list(csv.DictReader(f))
        if failures:
            print(f"\n{len(failures)} type(s) d erreur detectes :")
            for fail in failures:
                m = fail.get("Method", "?")
                n = fail.get("Name", "?")
                e = fail.get("Error", "?")
                o = fail.get("Occurrences", "?")
                print(f"  - [{m}] {n} -> {e} ({o} fois)")
        else:
            print("\nAucune erreur HTTP detectee.")
    else:
        print("\nAucune erreur HTTP detectee.")

    print(sep)
    print(f"Resultats complets : {RESULTS_DIR}")
    _print_analysis_report(detail_rows, agg_rows, failures)


# Seuils d alerte
_P95_WARN_MS = 1_000
_P95_CRIT_MS = 5_000
_FAIL_WARN_PCT = 5.0
_FAIL_CRIT_PCT = 15.0


def _print_analysis_report(detail_rows: list, agg_rows: list, failures: list) -> None:
    """Genere un rapport d analyse Markdown copiable."""
    import datetime as _dt
    sep = "=" * 80
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    conn_refused = [f for f in failures if "ConnectionRefused" in f.get("Error", "")]
    not_found = [f for f in failures if "404" in f.get("Error", "") or "Not Found" in f.get("Error", "")]
    other_errors = [f for f in failures if f not in conn_refused and f not in not_found]

    crit_latency, warn_latency = [], []
    for r in detail_rows:
        try:
            p95 = int(r.get("95%", 0) or 0)
        except ValueError:
            continue
        name = r.get("Name", "?")
        if p95 >= _P95_CRIT_MS:
            crit_latency.append((name, p95))
        elif p95 >= _P95_WARN_MS:
            warn_latency.append((name, p95))

    agg = agg_rows[0] if agg_rows else {}
    try:
        fail_pct = float(agg.get("Failure %", 0) or 0)
    except ValueError:
        fail_pct = 0.0
    total_req = agg.get("Request Count", "?")
    total_fail = agg.get("Failure Count", "?")
    rps = agg.get("Requests/s", "?")
    fail_icon = "[CRIT]" if fail_pct >= _FAIL_CRIT_PCT else ("[WARN]" if fail_pct >= _FAIL_WARN_PCT else "[OK]")

    print(f"\n{sep}")
    print("RAPPORT D ANALYSE -- copiable en Markdown")
    print(sep)
    print(f"\n## Rapport Locust -- {now}\n")
    print("### Vue d ensemble\n")
    print("| Metrique          | Valeur |")
    print("|---|---|")
    print(f"| Requetes totales  | {total_req} |")
    print(f"| Requetes/s        | {rps} |")
    print(f"| Echecs            | {total_fail} ({fail_pct:.1f}%) {fail_icon} |")
    print(f"| Duree / Users     | {LOCUST_DURATION} / {LOCUST_USERS} users |")

    if conn_refused:
        print("\n### [CRIT] Services injoignables (ConnectionRefused)\n")
        print("> Cause : reseau Docker manquant ou service non demarre.\n")
        for f in conn_refused:
            print(f"- **{f.get(chr(78)+'ame', '?')}** -- {f.get('Occurrences', '?')} echecs")
            print(f"  - Erreur : `{f.get('Error', '?')}`")
            print("  - Action : docker-compose logs <service> + verifier monitoring_net")

    if not_found:
        print("\n### [WARN] Erreurs 404\n")
        for f in not_found:
            print(f"- **{f.get('Name', '?')}** -- {f.get('Occurrences', '?')} fois")
        print("\n> Les user_id aleatoires 1-400 n ont pas tous un profil dans cv_api.")
        print("> Action : utiliser les IDs reellement crees par le seed.")

    if other_errors:
        print("\n### [CRIT] Autres erreurs HTTP\n")
        for f in other_errors:
            print(f"- **{f.get('Name', '?')}** -> `{f.get('Error', '?')}` ({f.get('Occurrences', '?')} fois)")

    if crit_latency:
        print("\n### [CRIT] Latences critiques (P95 > 5s)\n")
        for name, p95 in sorted(crit_latency, key=lambda x: x[1], reverse=True):
            print(f"- **{name}** -> P95 = **{p95} ms**")
            if "items" in name.lower():
                print("  - Cause probable : scan full-table -- index manquant sur user_id/category_ids")
                print("  - Action : EXPLAIN ANALYZE + ajout d index B-tree ou GIN")
            elif "users" in name.lower():
                print("  - Cause probable : N+1 resolution permissions ou cache absent")
                print("  - Action : verifier query plan + activer cache Redis")
            elif "login" in name.lower():
                print("  - Cause probable : bcrypt CPU-bound lors du spawn simultane")
                print("  - Action : cache de session Redis ou pré-login partage")

    if warn_latency:
        print("\n### [WARN] Latences elevees (P95 entre 1s et 5s)\n")
        for name, p95 in sorted(warn_latency, key=lambda x: x[1], reverse=True):
            print(f"- **{name}** -> P95 = {p95} ms")

    if not crit_latency and not warn_latency:
        print("\n### [OK] Latences : toutes P95 < 1s\n")

    print("\n### Actions prioritaires\n")
    prio = 1
    if conn_refused:
        svcs = sorted({f.get("Name", "").split("[")[-1].split("]")[0] for f in conn_refused})
        print(f"{prio}. **Reseau Docker** : ajouter `network: monitoring_net` au service locust")
        print(f"   Services touches : {', '.join(svcs)}")
        prio += 1
    for name, p95 in sorted(crit_latency, key=lambda x: x[1], reverse=True):
        print(f"{prio}. **Optimiser `{name}`** (P95={p95}ms) -- voir diagnostics ci-dessus")
        prio += 1
    if not_found:
        print(f"{prio}. **Corriger les 404 CV** : utiliser user_id du pool seed")
        prio += 1
    if fail_pct >= _FAIL_WARN_PCT:
        print(f"{prio}. **Taux echec global {fail_pct:.1f}%** -- voir erreurs ci-dessus")
        prio += 1
    if prio == 1:
        print("Aucun point bloquant detecte.")

    print(f"\n{sep}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pull les images depuis AR et lance docker-compose en local."
    )
    parser.add_argument(
        "--no-pull", action="store_true",
        help="Ne pas re-puller les images (utilise celles déjà présentes localement).",
    )
    parser.add_argument(
        "--perf", action="store_true",
        help="Enchâîne seed perf (400 users) + Locust + affichage des résultats.",
    )
    parser.add_argument(
        "--seed", action="store_true",
        help="Exécute uniquement le seed standard (12 users, 50 items) sans docker-compose.",
    )
    parser.add_argument(
        "--seed-perf", action="store_true", dest="seed_perf",
        help="Exécute uniquement le seed perf (400 users, 2000 items) sans docker-compose.",
    )
    parser.add_argument(
        "--service", nargs="+", metavar="SERVICE",
        help="Limite le pull/up à certains services (ex: --service users_api items_api).",
    )
    parser.add_argument(
        "--stress", action="store_true",
        help=(
            "Mode stress : 500 users progressifs sur 5 min, navigation pure (ZenikaPerfUser). "
            "Seed perf lancé avant le test. Pas d ingestion CV."
        ),
    )
    parsed = parser.parse_args()

    # Modes seed standalone (sans docker-compose up)
    if parsed.seed or parsed.seed_perf:
        run_seed(perf=parsed.seed_perf)
        print("\n✨ local_up.py terminé.")
        return

    services = parsed.service or AR_SERVICES

    ensure_images(services, force_pull=not parsed.no_pull)
    ensure_frontend(force=not parsed.no_pull)
    compose_up(parsed.service or [])

    if parsed.perf or parsed.stress:
        print("\n⏳ Attente du démarrage des services (15s)...")
        time.sleep(15)
        run_seed(perf=True)
        locust_ok = run_locust(stress=parsed.stress)
        if locust_ok:
            display_results()
        else:
            print("\n⛔ Locust a echoue — resultats precedents non affiches (fail-fast).")

    print("\n✨ local_up.py terminé.")


if __name__ == "__main__":
    main()
