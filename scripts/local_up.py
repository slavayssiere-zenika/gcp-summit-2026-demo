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
import datetime
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
LOCUST_INGESTION_USERS = 15      # 15 workers d ingestion en parallèle (aligné avec ASSIGN_BULK_SEMAPHORE=15)
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
RESULTS_HISTORY_DIR = RESULTS_DIR / "history"

# ── Session logger ───────────────────────────────────────────────────────────
_SESSION_LOG_FILE = None


def _init_session_log(mode: str) -> None:
    """Initialise le fichier de log de session dans locust/results/."""
    global _SESSION_LOG_FILE
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = RESULTS_DIR / f"session_{ts}.log"
    _SESSION_LOG_FILE = log_path.open("w", encoding="utf-8")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = (
        f"# local_up.py session — {now_str}\n"
        f"# PID={os.getpid()}  CMD={'  '.join(sys.argv[1:])}\n\n"
    )
    _SESSION_LOG_FILE.write(header)
    _SESSION_LOG_FILE.flush()
    log(f"Mode : {mode}")


def log(msg: str) -> None:
    """Print horodaté vers stdout ET fichier de session."""
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if _SESSION_LOG_FILE and not _SESSION_LOG_FILE.closed:
        _SESSION_LOG_FILE.write(line + "\n")
        _SESSION_LOG_FILE.flush()


def _close_session_log() -> None:
    """Ferme proprement le fichier de session."""
    if _SESSION_LOG_FILE and not _SESSION_LOG_FILE.closed:
        if hasattr(_SESSION_LOG_FILE, 'name'):
            log(f"Log de session complet : {_SESSION_LOG_FILE.name}")
        _SESSION_LOG_FILE.close()


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
    max_retries: int = 3,
    retry_delay_s: float = 10.0,
) -> bool:
    """Retourne True si le seed peut être ignoré — vérifie la DB via l'API.

    Stratégie (fail-safe à 2 niveaux) :
      1. Tentative de login admin (admin@zenika.com / admin) avec RETRY sur erreur réseau.
         • Erreur connexion (timeout, refused) → service encore en démarrage → on retente.
         • HTTP 4xx (401, 403) → admin n'existe pas → DB vide → seed requis immédiatement.
         • Après max_retries tentatives sans succès → seed requis.
      2. Lecture de seeded_ids.json + probe aléatoire de 10 user IDs avec le JWT.
         Si >= threshold (80%) répondent HTTP 200 → données confirmées → seed ignoré.

    Cas typique de faux négatif évité : compose_up redémarre les containers, le sleep(15)
    n'est pas toujours suffisant. Sans retry, la probe échoue et le seed est rellancé
    inutilement, écrasant les données existantes.
    """
    # Étape 1 : login admin avec retry sur erreur réseau
    token = ""
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                f"{users_url}/login",
                data=json.dumps({"email": "admin@zenika.com",
                                "password": "admin"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                if r.status == 200:
                    token = json.loads(r.read()).get("access_token", "")
                    break  # succes
                # HTTP 4xx = service up mais admin absent -> DB vide -> seed requis
                print(f"  >> Login admin HTTP {r.status} (tentative {attempt}/{max_retries})"
                      f" -> seed requis.")
                return False
        except urllib.error.HTTPError as e:
            # 4xx = fail-fast (admin absent en DB)
            if 400 <= e.code < 500:
                print(f"  >> Login admin HTTP {e.code} -> admin absent en DB -> seed requis.")
                return False
            # 5xx = service instable -> retry
            print(f"  >> Login admin HTTP {e.code} (tentative {attempt}/{max_retries})"
                  f" -> on retente dans {retry_delay_s:.0f}s...")
        except Exception as e:
            # Erreur reseau (ConnectionRefused, Timeout) -> service pas encore pret -> retry
            print(f"  >> Login admin erreur reseau ({type(e).__name__}: {e})"
                  f" (tentative {attempt}/{max_retries}) -> on retente dans {retry_delay_s:.0f}s...")
        if attempt < max_retries:
            time.sleep(retry_delay_s)

    if not token:
        print(f"  >> Login admin echoue apres {max_retries} tentatives -> seed requis.")
        return False
    print(f"  >> Login admin OK (tentative {attempt}/{max_retries}).")

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
                      autostart: bool = True,
                      cv_target: int = LOCUST_CV_TARGET_PERF,
                      mock_latency: str = LOCUST_MOCK_LATENCY_PERF,
                      csv_prefix: str = "perf_stats") -> list:
    """Arguments communs aux modes standalone et distribué.

    autostart=True (défaut) : --autostart, web UI accessible sur :8089 en temps réel.
    csv_prefix : préfixe des fichiers CSV générés — permet d'isoler les résultats par phase.
    cv_target / mock_latency : acceptés pour homogénéité des appels — transmis en -e par
    les appelants (_run_locust_standalone, _run_locust_distributed, _run_locust_ingestion).
    """
    start_mode = "--autostart" if autostart else "--headless"
    return [
        "-f", "/locust/locustfile.py",
        start_mode,
        # quitte 5s après la fin du test (requis avec --autostart)
        "--autoquit", "5",
        "-u", str(users),
        "-r", str(spawn),
        "-t", duration,
        "--csv", f"/locust/results/{csv_prefix}",
        "--html", f"/locust/results/{csv_prefix}.html",
        "--host", "http://localhost",
    ]


def _run_locust_standalone(users: int, spawn: int, duration: str, scenario: str,
                           cv_target: int = LOCUST_CV_TARGET_PERF,
                           mock_latency: str = LOCUST_MOCK_LATENCY_PERF,
                           csv_prefix: str = "perf_stats") -> bool:
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
                          cv_target=cv_target, mock_latency=mock_latency,
                          csv_prefix=csv_prefix)
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
                            mock_latency: str = LOCUST_MOCK_LATENCY_STRESS,
                            csv_prefix: str = "perf_stats") -> bool:
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
                                    cv_target=cv_target, mock_latency=mock_latency,
                                    csv_prefix=csv_prefix) + [
        "--master",
        f"--expect-workers={n_workers}",
    ]
    print(f"  ℹ️  CV_TARGET={cv_target} | Mock LLM latency={mock_latency}s")

    # Master : docker run direct (pas docker-compose run qui génère un nom auto et ignore
    # container_name, cassant docker wait / docker logs / docker cp).
    # Le volume ./locust:/locust est monté → les CSVs apparaissent directement sur l'hôte.
    master_cmd = [
        "docker", "run", "-d",
        "--name", "locust-master",
        "--hostname", "locust-master",
        "--network", "monitoring_net",
        "-v", f"{ROOT}/locust:/locust",
        "-v", f"{ROOT}/shared:/shared:ro",
        "-p", "8089:8089",
        "-e", f"LOCUST_SCENARIO={scenario}",
        "-e", f"LOCUST_CV_TARGET={cv_target}",
        "-e", f"MOCK_LLM_LATENCY_MAX_S={mock_latency}",
        "-e", "PYTHONPATH=/",
        "-e", "MISSIONS_API_URL=http://missions_api:8009",
        "-e", "DRIVE_API_URL=http://drive_api:8006",
        "-e", "PROMPTS_API_URL=http://prompts_api:8000",
        "test-open-code-locust-master:latest",
    ] + master_args
    run(master_cmd, cwd=ROOT)
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
    # Workers : ~3s démarrage + ~10s connexion au master + expect-workers handshake.
    # Avec --autostart, le master attend N workers AVANT de démarrer le test.
    # Si les workers prennent plus de 8s à s'enregistrer, le master peut quitter.
    # On attend 20s pour laisser le temps aux workers de se connecter.
    time.sleep(20)
    # Vérifier que le master est encore actif avant de conclure que le test démarre
    inspect = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Status}}", "locust-master"],
        cwd=ROOT, capture_output=True, text=True,
    )
    master_status = inspect.stdout.strip()
    if master_status != "running":
        print(f"  ⚠️  Master locust sorti prématurément (status={master_status}) — workers trop lents ?")
        print("       Relancez avec --stress seul pour diagnostiquer.")
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


def _run_locust_ingestion(csv_prefix: str = "perf_stats_ingestion") -> bool:
    """Phase d'ingestion dédiée (scenario=ingestion) : 30 workers, auto-stop à CV_TARGET.

    Lance uniquement CVIngestionPipelineUser. Le runner s'arrête automatiquement
    via environment.runner.quit() dans locustfile.py quand CV_TARGET est atteint.
    Safety timeout : LOCUST_INGESTION_TIMEOUT (20 min) pour éviter les boucles infinies.
    L'image locust est supposée déjà buildée par la phase précédente.
    """
    print(
        f"\n[+] Phase ingestion : {LOCUST_INGESTION_USERS} workers -> {LOCUST_CV_TARGET_INGESTION} CVs")
    print(
        f"  (i) Mock LLM latency={LOCUST_MOCK_LATENCY_INGESTION}s | Timeout safety={LOCUST_INGESTION_TIMEOUT}")
    # Pas de _build_locust_image() ici — buildée une seule fois en début de run_full_suite()
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
        csv_prefix=csv_prefix,
    )
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode not in (0, 1):
        print(
            f"  ❌ Phase ingestion échouée (code {result.returncode}) — fail-fast.")
        return False
    print("  ✅ Phase ingestion terminée.")
    return True


def run_validate_pubsub() -> None:
    """Valide le pipeline Pub/Sub si l'émulateur est actif (PUBSUB_EMULATOR_HOST défini).

    Appelée après la phase d'ingestion pour vérifier que des messages ont transité.
    Silencieuse si l'émulateur n'est pas configuré.
    """
    emulator = os.getenv("PUBSUB_EMULATOR_HOST", "")
    if not emulator:
        log("  ℹ️  PUBSUB_EMULATOR_HOST non défini — validation Pub/Sub ignorée.")
        return
    validate_script = Path(__file__).parent / "validate_pubsub_emulator.py"
    if not validate_script.exists():
        log("  ⚠️  validate_pubsub_emulator.py introuvable — validation ignorée.")
        return
    log("\n🔌 Validation du pipeline Pub/Sub...")
    result = subprocess.run(
        [sys.executable, str(validate_script)],
        cwd=ROOT,
    )
    if result.returncode != 0:
        log(f"  ⚠️  validate_pubsub_emulator.py retourné {result.returncode}.")


def run_full_suite() -> None:
    """Enchaîne les 3 phases du cycle complet de test :

    Phase 1 — Perf standard    : 50 users, 3 min, scénario full (nav + ingestion partielle)
    Phase 2 — Ingestion dédiée : 30 workers, auto-stop à 3000 CVs (~10-15 min à 1s latence)
    Phase 3 — Stress           : 500 users, 5 min, navigation pure (ZenikaPerfUser uniquement)

    Chaque phase écrit ses résultats dans un fichier CSV distinct pour éviter l'écrasement.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    sep = "=" * 70

    print(f"\n{sep}")
    print("PHASE 1/3 — Perf standard (50 users / 3 min)")
    print(sep)
    _build_locust_image()
    ok1 = _run_locust_standalone(
        LOCUST_USERS, LOCUST_SPAWN_RATE, LOCUST_DURATION, "full",
        cv_target=LOCUST_CV_TARGET_PERF, mock_latency=LOCUST_MOCK_LATENCY_PERF,
        csv_prefix="perf_stats_perf",
    )
    if ok1:
        display_results(csv_prefix="perf_stats_perf")
        archive_results(csv_prefix="perf_stats_perf")
        run_compare()
    else:
        print("  ⛔ Phase 1 échouée — abandon du cycle complet.")
        return

    print(f"\n{sep}")
    print(
        f"PHASE 2/3 — Ingestion dédiée ({LOCUST_CV_TARGET_INGESTION} CVs)")
    print(sep)
    ok2 = _run_locust_ingestion(csv_prefix="perf_stats_ingestion")
    if ok2:
        display_results(csv_prefix="perf_stats_ingestion")
        archive_results(csv_prefix="perf_stats_ingestion")
    else:
        print("  ⚠️  Phase 2 échouée — on continue quand même vers le stress test.")
    run_validate_pubsub()

    print(f"\n{sep}")
    print("PHASE 3/3 — Stress test (500 users / 5 min)")
    print(sep)
    ok3 = _run_locust_distributed(
        LOCUST_STRESS_USERS, LOCUST_STRESS_SPAWN_RATE, LOCUST_STRESS_DURATION, "navigation",
        cv_target=LOCUST_CV_TARGET_STRESS, mock_latency=LOCUST_MOCK_LATENCY_STRESS,
        csv_prefix="perf_stats_stress",
    )
    if ok3:
        display_results(csv_prefix="perf_stats_stress")
        archive_results(csv_prefix="perf_stats_stress")
        run_compare()
    else:
        print("  ⛔ Phase 3 (stress) échouée.")


def run_locust(stress: bool = False) -> bool:
    """Lance Locust : standalone (--perf, 50 users) ou distribué (--stress, 500 users).

    Les deux modes génèrent :
      - CSV : /locust/results/{prefix}_stats.csv
      - HTML : /locust/results/{prefix}.html
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
            csv_prefix="perf_stats_stress",
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
            csv_prefix="perf_stats_perf",
        )


def display_results(csv_prefix: str = "perf_stats") -> None:
    """Affiche les résultats CSV de Locust + rapport d analyse copiable."""
    stats_file = RESULTS_DIR / f"{csv_prefix}_stats.csv"
    failures_file = RESULTS_DIR / f"{csv_prefix}_failures.csv"

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
    sep = "=" * 80
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

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


def wait_for_services(max_wait_s: int = 90) -> None:
    """Attend que les services critiques soient prêts (healthcheck par polling).

    Poll users_api, cv_api et items_api toutes les 3s jusqu'au succès ou timeout.
    """
    health_endpoints = [
        ("users_api", "http://localhost:8000/health"),
        ("cv_api", "http://localhost:8004/health"),
        ("items_api", "http://localhost:8001/health"),
    ]
    log(f"Attente de la disponibilité des services (max {max_wait_s}s)...")
    start = time.monotonic()
    pending = list(health_endpoints)
    while pending and (time.monotonic() - start) < max_wait_s:
        still_pending = []
        for name, url in pending:
            try:
                with urllib.request.urlopen(url, timeout=3) as r:
                    if r.status == 200:
                        log(f"  {name} prêt ✅")
                        continue
            except Exception:
                pass
            still_pending.append((name, url))
        pending = still_pending
        if pending:
            names = ", ".join(n for n, _ in pending)
            log(f"  En attente : {names} — retry dans 3s...")
            time.sleep(3)
    elapsed = int(time.monotonic() - start)
    if pending:
        names = ", ".join(n for n, _ in pending)
        log(f"  ⚠️  Services toujours indisponibles après {max_wait_s}s : {names}")
    else:
        log(f"  ✅ Tous les services sont prêts ({elapsed}s écoulées).")


def archive_results(csv_prefix: str = "perf_stats") -> None:
    """Archive les CSVs et le rapport JSON du dernier run dans history/.

    Format : YYYYMMDD_HHMM_{csv_prefix}_stats.csv (préfixe horodaté + label phase).
    """
    RESULTS_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    prefix = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    archived = []
    for suffix in ("_stats.csv", "_failures.csv", "_exceptions.csv"):
        src = RESULTS_DIR / f"{csv_prefix}{suffix}"
        if src.exists():
            dst = RESULTS_HISTORY_DIR / f"{prefix}_{csv_prefix}{suffix}"
            shutil.copy2(src, dst)
            archived.append(f"{csv_prefix}{suffix}")
    # Archiver aussi le JSON si présent (nom fixe perf_report.json)
    json_src = RESULTS_DIR / "perf_report.json"
    if json_src.exists():
        shutil.copy2(json_src, RESULTS_HISTORY_DIR / f"{prefix}_{csv_prefix}.json")
        archived.append("perf_report.json")
    if archived:
        log(f"  ✅ Résultats archivés dans {RESULTS_HISTORY_DIR} (préfixe {prefix}_{csv_prefix})")
    else:
        log("  ℹ️  Aucun fichier CSV à archiver (run non terminé ?).")


def run_compare() -> None:
    """Lance compare_runs.py pour afficher le diff avec le run précédent."""
    compare_script = Path(__file__).parent / "compare_runs.py"
    if not compare_script.exists():
        log("  ⚠️  compare_runs.py introuvable — comparaison ignorée.")
        return
    log("\n📊 Comparaison avec le run précédent...")
    result = subprocess.run(
        [sys.executable, str(compare_script)],
        cwd=ROOT,
    )
    if result.returncode != 0:
        log(f"  ⚠️  compare_runs.py retourné {result.returncode}.")


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

    # Détecter le mode pour le log de session
    if parsed.seed or parsed.seed_perf:
        _mode = "seed"
    elif parsed.full:
        _mode = "full"
    elif parsed.perf:
        _mode = "perf"
    elif parsed.stress:
        _mode = "stress"
    else:
        _mode = "up"
    _init_session_log(_mode)

    # Modes seed standalone (sans docker-compose up)
    if parsed.seed or parsed.seed_perf:
        run_seed(perf=parsed.seed_perf)
        log("\n✨ local_up.py terminé.")
        _close_session_log()
        return

    services = parsed.service or AR_SERVICES

    ensure_images(services, force_pull=not parsed.no_pull)
    ensure_frontend(force=not parsed.no_pull)
    compose_up(parsed.service or [])

    if parsed.full or parsed.perf or parsed.stress:
        wait_for_services(max_wait_s=90)
        run_seed(perf=True, skip_if_present=not parsed.erase)

        if parsed.full:
            run_full_suite()
        else:
            locust_ok = run_locust(stress=parsed.stress)
            _csv_prefix = "perf_stats_stress" if parsed.stress else "perf_stats_perf"
            if locust_ok:
                display_results(csv_prefix=_csv_prefix)
                archive_results(csv_prefix=_csv_prefix)
                run_compare()
            else:
                log(
                    "\n⛔ Locust a echoue — resultats precedents non affiches (fail-fast).")

    log("\n✨ local_up.py terminé.")
    _close_session_log()


if __name__ == "__main__":
    main()
