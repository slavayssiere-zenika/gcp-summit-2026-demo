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
import json
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.request
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
LOCUST_DURATION = "3m"  # 3 min : couverture suffisante pour valider les latences P95
# 13 workers ingestion × 180s / ~3s par pipeline (latence 1s) = ~780 CVs théoriques en 3 min
# Objectif affiché : conservatif (incl. overhead pipeline)
LOCUST_CV_TARGET_PERF = 120
LOCUST_MOCK_LATENCY_PERF = "1"  # 1s en perf : feedback rapide

# Phase d ingestion dédiée (--full, phase 2)
LOCUST_INGESTION_USERS = 30      # 30 workers d ingestion en parallèle
LOCUST_INGESTION_SPAWN = 5       # montée progressive
# Safety timeout : auto-stop bien avant via CV_TARGET
LOCUST_INGESTION_TIMEOUT = "20m"
LOCUST_CV_TARGET_INGESTION = 3000  # Arrêt automatique quand 3000 CVs ingeres
LOCUST_MOCK_LATENCY_INGESTION = "1"  # 1s pour maximiser le débit d ingestion

# Mode stress (--stress) : montée progressive vers 500 users, navigation pure sans ingestion CV
LOCUST_STRESS_USERS = 500
LOCUST_STRESS_SPAWN_RATE = 5   # 5/s -> 500 users atteints apres ~100s
LOCUST_STRESS_DURATION = "5m"
# 30 workers ingestion × 5min / ~6s par pipeline = ~1500 CVs, objectif 3000 avec latence 1s
LOCUST_CV_TARGET_STRESS = 3000
# Latence mock LLM réaliste en stress : simule la production (3s)
LOCUST_MOCK_LATENCY_STRESS = "3"
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
    archives = sorted(line.strip() for line in result.stdout.splitlines(
    ) if line.strip().endswith(".tar.gz"))
    if not archives:
        print("  ⚠️  Aucune archive trouvée dans le bucket GCS. Frontend ignoré.")
        return
    # ex: gs://z-gcp-summit-frontend/frontend-20260516141607-v0.1.1.tar.gz
    latest_gcs = archives[-1]
    # ex: frontend-20260516141607-v0.1.1.tar.gz
    latest_name = latest_gcs.split("/")[-1]

    # 2. Version locale
    local_version = FRONTEND_VERSION_FILE.read_text(
    ).strip() if FRONTEND_VERSION_FILE.exists() else ""

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

def _should_skip_seed(
    users_url: str = "http://localhost:8000",
    threshold: float = 0.80,
) -> bool:
    """Retourne True si le seed peut être ignoré — vérifie la DB via l'API.

    Stratégie (fail-safe à 2 niveaux) :
      1. Tentative de login admin (admin@zenika.com / admin).
         Si échec → la table users est vide ou le service ne répond pas → seed requis.
      2. Lecture de seeded_ids.json + probe aléatoire de 10 user IDs avec le JWT.
         Si ≥ threshold (80%) répondent HTTP 200 → données confirmées → seed ignoré.

    Cette probe est la seule preuve fiable que la DB est peuplée : le fichier
    seeded_ids.json est persistant sur le filesystem et peut exister même après
    une purge du volume Docker.
    """
    # Étape 1 : login admin pour obtenir un JWT
    try:
        req = urllib.request.Request(
            f"{users_url}/login",
            data=json.dumps({"email": "admin@zenika.com",
                            "password": "admin"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            if r.status != 200:
                print(f"  🔄 Login admin HTTP {r.status} — seed requis.")
                return False
            token = json.loads(r.read()).get("access_token", "")
    except Exception as e:
        print(
            f"  🔄 Login admin échoué ({e}) — service indisponible ou DB vide — seed requis.")
        return False

    # Étape 2 : vérifier la présence des users seedés
    seeded_path = ROOT / "locust" / "data" / "seeded_ids.json"
    if not seeded_path.exists():
        print("  ℹ️  seeded_ids.json absent — login admin OK mais pas de référentiel — seed requis.")
        return False

    try:
        with seeded_path.open() as f:
            ids = json.load(f)
        user_ids = ids.get("user_ids", [])
    except Exception as e:
        print(f"  ⚠️  Lecture seeded_ids.json échouée ({e}) — seed requis.")
        return False

    if not user_ids:
        print("  ℹ️  seeded_ids.json vide (pas d'IDs) — seed requis.")
        return False

    sample = random.sample(user_ids, min(10, len(user_ids)))
    auth_header = f"Bearer {token}"
    ok, total = 0, len(sample)
    for uid in sample:
        try:
            req = urllib.request.Request(
                f"{users_url}/users/{uid}",
                headers={"Authorization": auth_header},
            )
            with urllib.request.urlopen(req, timeout=3) as r:
                if r.status == 200:
                    ok += 1
        except Exception:
            pass

    ratio = ok / total if total > 0 else 0
    if ratio >= threshold:
        print(
            f"  ⏭️  DB confirmée ({ok}/{total} users OK ≥ {threshold*100:.0f}%) — seed ignoré.")
        return True
    print(
        f"  🔄 DB incomplète ({ok}/{total} users OK < {threshold*100:.0f}%) — seed requis.")
    return False


def run_seed(perf: bool = False, skip_if_present: bool = False) -> None:
    """
    Exécute le seed des données en important seed_data directement.
    - perf=False : 12 users, 50 items (mode développement)
    - perf=True  : 400 users, 2000 items (mode test de charge)
    - skip_if_present=True : probe l'API (login admin + spot-check users) avant de seeder.
    """
    if skip_if_present and _should_skip_seed():
        return
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
        # quitte 5s apres la fin du test (requis avec --autostart)
        "--autoquit", "5",
        "-u", str(users),
        "-r", str(spawn),
        "-t", duration,
        "--csv", "/locust/results/perf_stats",
        "--html", "/locust/results/perf_report.html",
        "--host", "http://localhost",
    ]


def _run_locust_standalone(users: int, spawn: int, duration: str, scenario: str,
                           cv_target: int = LOCUST_CV_TARGET_PERF,
                           mock_latency: str = LOCUST_MOCK_LATENCY_PERF) -> bool:
    """Mode standalone (--perf, 50 users) : 1 seul process Locust, web UI sur :8089."""
    cmd = [
        "docker-compose", "--profile", "perf",
        "run", "--rm",
        "-p", "8089:8089",
        "-e", f"LOCUST_SCENARIO={scenario}",
        "-e", f"LOCUST_CV_TARGET={cv_target}",
        "-e", f"MOCK_LLM_LATENCY_MAX_S={mock_latency}",
        "locust",
    ] + _locust_base_args(users, spawn, duration, scenario, autostart=True,
                          cv_target=cv_target, mock_latency=mock_latency)
    print("  🟡 Web UI disponible sur http://localhost:8089")
    print(f"  ℹ️  CV_TARGET={cv_target} | Mock LLM latency={mock_latency}s")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode not in (0, 1):
        print(
            f"  ❌ Locust standalone echoue (code {result.returncode}) — fail-fast.")
        return False
    print("  ✅ Test Locust standalone termine.")
    return True


def _run_locust_distributed(users: int, spawn: int, duration: str, scenario: str,
                            cv_target: int = LOCUST_CV_TARGET_STRESS,
                            mock_latency: str = LOCUST_MOCK_LATENCY_STRESS) -> bool:
    """Mode distributed (--stress, 500 users) : 1 master + LOCUST_STRESS_WORKERS workers.

    Architecture :
      - Master démarré via "docker-compose up -d locust-master" avec container_name=locust-master.
        Hostname DNS fixe → workers peuvent résoudre "locust-master" sur monitoring_net.
      - Workers démarrés en background (docker-compose up --scale N).
      - Script attend l'exit du master via "docker wait locust-master" (bloquant).
      - Workers stoppés après exit du master.
    Rapport HTML généré par le master dans /locust/results/perf_report.html.
    """
    n_workers = LOCUST_STRESS_WORKERS
    print("  🔨 Build images locust-master/worker (cache Docker si inchange)...")
    run(["docker-compose", "--profile", "perf-stress",
        "build", "locust-master", "locust-worker"], cwd=ROOT)

    # Nettoyage préventif du master précédent (container_name fixe → conflit si existe déjà)
    subprocess.run(
        ["docker", "rm", "-f", "locust-master"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    # Master : run -d avec port 8089 exposé + --autostart (web UI accessible en temps réel)
    master_args = _locust_base_args(users, spawn, duration, scenario, autostart=True,
                                    cv_target=cv_target, mock_latency=mock_latency) + [
        "--master",
        f"--expect-workers={n_workers}",
    ]
    env_args = [
        "-e", f"LOCUST_SCENARIO={scenario}",
        "-e", f"LOCUST_CV_TARGET={cv_target}",
        "-e", f"MOCK_LLM_LATENCY_MAX_S={mock_latency}",
    ]
    print(f"  ℹ️  CV_TARGET={cv_target} | Mock LLM latency={mock_latency}s")
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
    print("  🟡 Master démarré. Web UI disponible sur http://localhost:8089")
    print(f"     Démarrage {n_workers} workers...")

    # Workers : up --scale (se connectent à locust-master par DNS container_name)
    # Passer les mêmes env vars aux workers via --env pour cohérence du CV_TARGET
    run(
        [
            "docker-compose", "--profile", "perf-stress",
            "up", "-d", "--scale", f"locust-worker={n_workers}",
            "locust-worker",
        ],
        cwd=ROOT,
    )
    # Workers : ~3s démarrage + ~5s connexion au master avant autostart
    time.sleep(8)
    print(f"  🔥 Test en cours ({n_workers} workers connectés au master)...")

    # Attente bloquante de la fin du master
    wait_result = subprocess.run(
        ["docker", "wait", "locust-master"], cwd=ROOT, capture_output=True, text=True)
    exit_code = int(wait_result.stdout.strip()
                    ) if wait_result.stdout.strip().isdigit() else 2

    print("  🛑 Arrêt des workers...")
    subprocess.run(
        ["docker-compose", "--profile", "perf-stress", "stop", "locust-worker"],
        cwd=ROOT, stdout=subprocess.DEVNULL,
    )
    # Copier les résultats depuis le master avant de le supprimer
    subprocess.run(
        ["docker", "cp", "locust-master:/locust/results/.", str(RESULTS_DIR)],
        cwd=ROOT,
    )
    subprocess.run(["docker", "rm", "-f", "locust-master"],
                   cwd=ROOT, stdout=subprocess.DEVNULL)

    if exit_code not in (0, 1):
        print(f"  ❌ Locust master échoué (code {exit_code}) — fail-fast.")
        return False
    print(f"  ✅ Test Locust distribué terminé ({n_workers} workers).")
    return True


def _run_locust_ingestion() -> bool:
    """Phase d'ingestion d\u00e9di\u00e9e (scenario=ingestion) : 30 workers, auto-stop \u00e0 CV_TARGET.

    Lance uniquement CVIngestionPipelineUser. Le runner s'arr\u00eate automatiquement
    via environment.runner.quit() dans locustfile.py quand CV_TARGET est atteint.
    Safety timeout : LOCUST_INGESTION_TIMEOUT (20 min) pour \u00e9viter les boucles infinies.
    """
    print(
        f"\\n\ud83d\udce5 Phase ingestion : {LOCUST_INGESTION_USERS} workers \u2192 {LOCUST_CV_TARGET_INGESTION} CVs")
    print(
        f"  \u2139\ufe0f  Mock LLM latency={LOCUST_MOCK_LATENCY_INGESTION}s | Timeout safety={LOCUST_INGESTION_TIMEOUT}")
    _build_locust_image()
    cmd = [
        "docker-compose", "--profile", "perf",
        "run", "--rm",
        "-p", "8089:8089",
        "-e", "LOCUST_SCENARIO=ingestion",
        "-e", f"LOCUST_CV_TARGET={LOCUST_CV_TARGET_INGESTION}",
        "-e", f"MOCK_LLM_LATENCY_MAX_S={LOCUST_MOCK_LATENCY_INGESTION}",
        "locust",
    ] + _locust_base_args(
        LOCUST_INGESTION_USERS, LOCUST_INGESTION_SPAWN, LOCUST_INGESTION_TIMEOUT,
        "ingestion", autostart=True,
        cv_target=LOCUST_CV_TARGET_INGESTION,
        mock_latency=LOCUST_MOCK_LATENCY_INGESTION,
    )
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode not in (0, 1):
        print(
            f"  \u274c Phase ingestion \u00e9chou\u00e9e (code {result.returncode}) \u2014 fail-fast.")
        return False
    print("  \u2705 Phase ingestion termin\u00e9e.")
    return True


def run_full_suite() -> None:
    """Encha\u00eene les 3 phases du cycle complet de test :

    Phase 1 \u2014 Perf standard    : 50 users, 3 min, sc\u00e9nario full (nav + ingestion partielle)
    Phase 2 \u2014 Ingestion d\u00e9di\u00e9e : 30 workers, auto-stop \u00e0 3000 CVs (~10-15 min \u00e0 1s latence)
    Phase 3 \u2014 Stress           : 500 users, 5 min, navigation pure (ZenikaPerfUser uniquement)
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    sep = "=" * 70

    print(f"\\n{sep}")
    print("PHASE 1/3 \u2014 Perf standard (50 users / 3 min)")
    print(sep)
    _build_locust_image()
    ok1 = _run_locust_standalone(
        LOCUST_USERS, LOCUST_SPAWN_RATE, LOCUST_DURATION, "full",
        cv_target=LOCUST_CV_TARGET_PERF, mock_latency=LOCUST_MOCK_LATENCY_PERF,
    )
    if ok1:
        display_results()
    else:
        print("  \u26d4 Phase 1 \u00e9chou\u00e9e \u2014 abandon du cycle complet.")
        return

    print(f"\\n{sep}")
    print(
        f"PHASE 2/3 \u2014 Ingestion d\u00e9di\u00e9e ({LOCUST_CV_TARGET_INGESTION} CVs)")
    print(sep)
    ok2 = _run_locust_ingestion()
    if not ok2:
        print("  \u26a0\ufe0f  Phase 2 \u00e9chou\u00e9e \u2014 on continue quand m\u00eame vers le stress test.")

    print(f"\\n{sep}")
    print("PHASE 3/3 \u2014 Stress test (500 users / 5 min)")
    print(sep)
    ok3 = _run_locust_distributed(
        LOCUST_STRESS_USERS, LOCUST_STRESS_SPAWN_RATE, LOCUST_STRESS_DURATION, "navigation",
        cv_target=LOCUST_CV_TARGET_STRESS, mock_latency=LOCUST_MOCK_LATENCY_STRESS,
    )
    if ok3:
        display_results()
    else:
        print("  \u26d4 Phase 3 (stress) \u00e9chou\u00e9e.")


def run_locust(stress: bool = False) -> bool:
    """Lance Locust : standalone (--perf, 50 users) ou distribué (--stress, 500 users).

    Les deux modes génèrent :
      - CSV : /locust/results/perf_stats_*.csv
      - HTML : /locust/results/perf_report.html (graphiques latence/throughput)
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if stress:
        users, spawn, duration = LOCUST_STRESS_USERS, LOCUST_STRESS_SPAWN_RATE, LOCUST_STRESS_DURATION
        scenario = "navigation"
        label = f"STRESS distribué {users} users ({LOCUST_STRESS_WORKERS} workers), {duration}"
        print(f"\n🔥 Lancement Locust ({label})...")
        return _run_locust_distributed(
            users, spawn, duration, scenario,
            cv_target=LOCUST_CV_TARGET_STRESS,
            mock_latency=LOCUST_MOCK_LATENCY_STRESS,
        )
    else:
        users, spawn, duration = LOCUST_USERS, LOCUST_SPAWN_RATE, LOCUST_DURATION
        scenario = "full"
        label = f"{users} users standalone, {duration}"
        print(f"\n🔥 Lancement Locust ({label})...")
        _build_locust_image()
        return _run_locust_standalone(
            users, spawn, duration, scenario,
            cv_target=LOCUST_CV_TARGET_PERF,
            mock_latency=LOCUST_MOCK_LATENCY_PERF,
        )


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
    headers = ["Endpoint", "Req/s", "Fail%",
               "Median(ms)", "95%(ms)", "99%(ms)", "Max(ms)", "Errors"]
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

    conn_refused = [
        f for f in failures if "ConnectionRefused" in f.get("Error", "")]
    not_found = [f for f in failures if "404" in f.get(
        "Error", "") or "Not Found" in f.get("Error", "")]
    other_errors = [
        f for f in failures if f not in conn_refused and f not in not_found]

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
    fail_icon = "[CRIT]" if fail_pct >= _FAIL_CRIT_PCT else (
        "[WARN]" if fail_pct >= _FAIL_WARN_PCT else "[OK]")

    print(f"\n{sep}")
    print("RAPPORT D ANALYSE -- copiable en Markdown")
    print(sep)
    print(f"\n## Rapport Locust -- {now}\n")
    print("### Vue d ensemble\n")
    print("| Metrique          | Valeur |")
    print("|---|---|")
    print(f"| Requetes totales  | {total_req} |")
    print(f"| Requetes/s        | {rps} |")
    print(
        f"| Echecs            | {total_fail} ({fail_pct:.1f}%) {fail_icon} |")
    print(f"| Duree / Users     | {LOCUST_DURATION} / {LOCUST_USERS} users |")

    if conn_refused:
        print("\n### [CRIT] Services injoignables (ConnectionRefused)\n")
        print("> Cause : reseau Docker manquant ou service non demarre.\n")
        for f in conn_refused:
            print(
                f"- **{f.get(chr(78)+'ame', '?')}** -- {f.get('Occurrences', '?')} echecs")
            print(f"  - Erreur : `{f.get('Error', '?')}`")
            print("  - Action : docker-compose logs <service> + verifier monitoring_net")

    if not_found:
        print("\n### [WARN] Erreurs 404\n")
        for f in not_found:
            print(
                f"- **{f.get('Name', '?')}** -- {f.get('Occurrences', '?')} fois")
        print("\n> Les user_id aleatoires 1-400 n ont pas tous un profil dans cv_api.")
        print("> Action : utiliser les IDs reellement crees par le seed.")

    if other_errors:
        print("\n### [CRIT] Autres erreurs HTTP\n")
        for f in other_errors:
            print(
                f"- **{f.get('Name', '?')}** -> `{f.get('Error', '?')}` ({f.get('Occurrences', '?')} fois)")

    if crit_latency:
        print("\n### [CRIT] Latences critiques (P95 > 5s)\n")
        for name, p95 in sorted(crit_latency, key=lambda x: x[1], reverse=True):
            print(f"- **{name}** -> P95 = **{p95} ms**")
            if "items" in name.lower():
                print(
                    "  - Cause probable : scan full-table -- index manquant sur user_id/category_ids")
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
        svcs = sorted({f.get("Name", "").split(
            "[")[-1].split("]")[0] for f in conn_refused})
        print(
            f"{prio}. **Reseau Docker** : ajouter `network: monitoring_net` au service locust")
        print(f"   Services touches : {', '.join(svcs)}")
        prio += 1
    for name, p95 in sorted(crit_latency, key=lambda x: x[1], reverse=True):
        print(
            f"{prio}. **Optimiser `{name}`** (P95={p95}ms) -- voir diagnostics ci-dessus")
        prio += 1
    if not_found:
        print(f"{prio}. **Corriger les 404 CV** : utiliser user_id du pool seed")
        prio += 1
    if fail_pct >= _FAIL_WARN_PCT:
        print(
            f"{prio}. **Taux echec global {fail_pct:.1f}%** -- voir erreurs ci-dessus")
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
        help="Seed perf (skip si DB peuplee) + Locust 50 users 3 min.",
    )
    parser.add_argument(
        "--full", action="store_true",
        help=(
            "Cycle complet en 3 phases : "
            "(1) Perf 50 users 3 min — "
            "(2) Ingestion 3000 CVs (auto-stop) — "
            "(3) Stress 500 users 5 min."
        ),
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
            "Seed perf lance avant le test (skip si DB peuplee)."
        ),
    )
    parser.add_argument(
        "--erase", action="store_true",
        help="Force le reseed complet meme si la DB est deja peuplee (probe API ignoree).",
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

    if parsed.full or parsed.perf or parsed.stress:
        print("\n⏳ Attente du démarrage des services (15s)...")
        time.sleep(15)
        run_seed(perf=True, skip_if_present=not parsed.erase)

        if parsed.full:
            run_full_suite()
        else:
            locust_ok = run_locust(stress=parsed.stress)
            if locust_ok:
                display_results()
            else:
                print(
                    "\n⛔ Locust a echoue — resultats precedents non affiches (fail-fast).")

    print("\n✨ local_up.py terminé.")


if __name__ == "__main__":
    main()
