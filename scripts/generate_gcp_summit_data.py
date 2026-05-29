import os
import json
import time
import datetime
import httpx
import google.auth
from google.auth.transport.requests import Request
import base64
import subprocess
import string
import random
from logger_config import logger

# ─────────────────────────────────────────────────────────────────────────────
# Configuration — lue depuis .antigravity_env si disponible
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ID = "slavayssiere-sandbox-462015"
DEV_API_URL = os.getenv("DEV_API_URL", "https://api.dev.zenika.slavayssiere.fr")
PROGRESS_FILE = "reports/fake_profiles/progress.json"

# Charge les overrides depuis .antigravity_env (gitignore, jamais commité)
_env_file = os.path.join(os.path.dirname(__file__), "..", ".antigravity_env")
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and "=" in _line and not _line.startswith("#"):
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))

GCLOUD_BIN = os.getenv("GCLOUD_BIN", "gcloud")


def get_admin_password():
    """Lit le mot de passe admin depuis .antigravity_env ou Secret Manager en fallback."""
    # Priorité 1 : variable d'environnement (depuis .antigravity_env)
    if os.getenv("ADMIN_PASSWORD"):
        logger.info("  -> Mot de passe admin lu depuis .antigravity_env")
        return os.environ["ADMIN_PASSWORD"]

    # Fallback : Secret Manager via ADC
    logger.info("Fetching admin password from Secret Manager...")
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())

    url = (
        f"https://secretmanager.googleapis.com/v1/projects/{PROJECT_ID}"
        "/secrets/admin-password-dev/versions/latest:access"
    )
    response = httpx.get(
        url,
        headers={"Authorization": f"Bearer {credentials.token}"}
    )
    if response.status_code != 200:
        raise Exception(f"Failed to fetch secret: {response.text}")

    payload = response.json()["payload"]["data"]
    return base64.b64decode(payload).decode('utf-8')


def authenticate(password):
    logger.info("Authenticating to users-api...")
    response = httpx.post(
        f"{DEV_API_URL}/auth/login",
        json={
            "email": "admin@zenika.com",
            "password": password
        }
    )
    if response.status_code != 200:
        raise Exception(f"Login failed: {response.text}")

    return response.json()["access_token"]


def ensure_sebastien_admin(token):
    logger.info("Ensuring sebastien.lavayssiere@zenika.com is admin...")
    with httpx.Client(base_url=DEV_API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=10.0) as client:
        # Check if user exists
        res = client.get("/api/users/search?query=sebastien.lavayssiere&limit=1")
        if res.status_code == 200 and res.json().get("total", 0) > 0:
            user = res.json()["items"][0]
            if user.get("role") != "admin":
                logger.info(f"  -> Upgrading {user['email']} to admin role...")
                update_res = client.put(f"/api/users/{user['id']}", json={"role": "admin"})
                if update_res.status_code == 200:
                    logger.info("  -> Upgraded successfully.")
                else:
                    logger.error(f"  -> Failed to upgrade user: {update_res.text}")
            else:
                logger.info("  -> sebastien.lavayssiere@zenika.com already exists and is admin.")
            return

        logger.info("  -> Creating sebastien.lavayssiere@zenika.com as admin...")
        pwd = ''.join(random.choice(string.ascii_letters) for _ in range(16))
        payload = {
            "username": "slavayssiere",
            "email": "sebastien.lavayssiere@zenika.com",
            "first_name": "Sébastien",
            "last_name": "Lavayssière",
            "full_name": "Sébastien Lavayssière",
            "role": "admin",
            "password": pwd,
            "allowed_category_ids": [1, 2, 3, 4, 5],
            "is_active": True
        }
        res = client.post("/api/users/", json=payload)
        if res.status_code == 201:
            logger.info("  -> Created successfully. Upgrading to admin...")
            user_id = res.json()["id"]
            update_res = client.put(f"/api/users/{user_id}", json={"role": "admin"})
            if update_res.status_code == 200:
                logger.info("  -> Upgraded successfully.")
            else:
                logger.error(f"  -> Failed to upgrade user: {update_res.text}")
        else:
            logger.error(f"  -> Failed to create user: {res.text}")


def setup_drive_scanner(token, progress):
    with httpx.Client(base_url=DEV_API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=20.0) as client:
        logger.info("Fetching currently tracked Drive folders...")
        res = client.get("/api/drive/folders")
        existing_folders = []
        if res.status_code == 200:
            res_json = res.json()
            existing_folders = res_json.get("items", []) if isinstance(res_json, dict) else res_json

        # Clean up old root folder to avoid duplicate scanning
        for f in existing_folders:
            if f.get("folder_name") == "Fake Agencies" or f.get("tag") == "GCP Summit":
                logger.info(f"  -> Deleting old root folder '{f.get('folder_name')}' from scanner...")
                client.delete(f"/api/drive/folders/{f.get('id')}")

        # Register each agency
        for agency_name in ["Saumur", "Sèvres", "Bizanos", "Paris"]:
            if agency_name not in progress:
                logger.warning(f"  -> Warning: {agency_name} not found in progress.json")
                continue

            folder_id = progress[agency_name].get("folder_id")
            if not folder_id:
                logger.warning(f"  -> No folder_id found for {agency_name}")
                continue

            # Check if already tracked
            if any(f.get("google_folder_id") == folder_id for f in existing_folders):
                logger.info(f"  -> Folder '{agency_name}' is already tracked.")
                continue

            logger.info(f"  -> Adding '{agency_name}' to Drive scanner...")
            res = client.post("/api/drive/folders", json={
                "google_folder_id": folder_id,
                "tag": agency_name,
                "folder_name": agency_name
            })
            if res.status_code == 200:
                logger.info(f"  -> '{agency_name}' added successfully.")
            else:
                logger.error(f"  -> Failed to add '{agency_name}': {res.text}")
        return True


def trigger_drive_sync():
    logger.info("Triggering Drive sync via Cloud Scheduler...")
    res = subprocess.run([
        GCLOUD_BIN, "scheduler", "jobs", "run", "drive-sync-trigger-dev",
        "--location=europe-west1", "--project", PROJECT_ID
    ], capture_output=True, text=True)
    if res.returncode == 0:
        logger.info("  -> Sync triggered.")
    else:
        logger.error(f"  -> Failed to trigger sync: {res.stderr}")
        raise Exception(f"gcloud scheduler trigger failed: {res.stderr}")


def check_platform_health():
    """Vérifie que les services critiques sont up avant de lancer le workflow."""
    logger.info("\\n0. Vérification de la santé de la plateforme...")
    services = [
        ("users-api", f"{DEV_API_URL}/auth/health"),
        ("cv-api", f"{DEV_API_URL}/api/cv/health"),
        ("drive-api", f"{DEV_API_URL}/api/drive/health"),
        ("missions-api", f"{DEV_API_URL}/api/missions/health"),
    ]
    all_healthy = True
    for name, url in services:
        try:
            r = httpx.get(url, timeout=5)
            status = "✅" if r.status_code == 200 else "❌"
            logger.info(f"  {status} {name}: HTTP {r.status_code}")
            if r.status_code != 200:
                all_healthy = False
        except Exception as e:
            logger.error(f"  ❌ {name}: {e}")
            all_healthy = False
    if not all_healthy:
        raise Exception("Un ou plusieurs services sont unhealthy. Annulation du workflow.")
    logger.info("  -> Tous les services sont opérationnels.")


def wait_for_drive_ingestion(admin_password):
    logger.info("Waiting for Drive ingestion to complete...")
    logger.info("  -> Waiting 15 seconds for Cloud Scheduler sync to register in the queue...")
    time.sleep(15)
    token = authenticate(admin_password)
    with httpx.Client(base_url=DEV_API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=10.0) as client:
        while True:
            res = client.get("/api/drive/status")
            if res.status_code == 401:
                logger.warning("  -> JWT expired during polling. Re-authenticating...")
                token = authenticate(admin_password)
                client.headers["Authorization"] = f"Bearer {token}"
                continue

            if res.status_code == 200:
                data = res.json()
                pending = data.get("pending", 0)
                processing = data.get("processing", 0)
                queued = data.get("queued", 0)

                logger.info(
                    f"  -> Status: Pending={pending}, Queued={queued}, "
                    f"Processing={processing}, Imported={data.get('imported', 0)}"
                )

                if pending == 0 and processing == 0 and queued == 0:
                    logger.info("  -> Ingestion complete!")
                    break

                if pending > 0 and processing == 0 and queued == 0:
                    logger.info("  -> Backlog remaining but no active processing slots. Re-triggering sync...")
                    try:
                        trigger_drive_sync()
                    except Exception as trigger_err:
                        logger.warning(f"  -> Failed to re-trigger sync: {trigger_err}")
            else:
                logger.error(f"  -> Failed to check status: {res.text}")
            time.sleep(10)


def wait_for_missions_ingestion(admin_password):
    """Attend la fin de l'ingestion des missions.

    - Timeout : 10 min max.
    - Anti-zombie : si le même nombre de missions restent bloquées pendant 3 min
      consécutives → force leur statut vers STAFFED via PATCH et sort.
    """
    logger.info("Waiting for Missions ingestion to complete...")
    token = authenticate(admin_password)
    max_iterations = 60  # 60 x 10s = 10 min max
    iterations = 0
    stagnation_count = 0
    last_in_progress_count = -1
    stagnation_threshold = 18  # 18 x 10s = 3 min sans changement → force reset
    start_ts = time.time()

    with httpx.Client(
        base_url=DEV_API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    ) as client:
        while iterations < max_iterations:
            iterations += 1
            if client.headers.get("Authorization", "").split(" ")[-1] != token:
                client.headers["Authorization"] = f"Bearer {token}"

            res = client.get("/api/missions/missions?limit=200")
            if res.status_code == 401:
                logger.warning("  -> JWT expired during polling. Re-authenticating...")
                token = authenticate(admin_password)
                client.headers["Authorization"] = f"Bearer {token}"
                continue

            if res.status_code == 200:
                res_json = res.json()
                missions_list = (
                    res_json.get("items", []) if isinstance(res_json, dict) else res_json
                )
                in_progress = [
                    m for m in missions_list
                    if m.get("status") == "ANALYSIS_IN_PROGRESS"
                ]
                elapsed = int(time.time() - start_ts)
                elapsed_str = f"{elapsed // 60}m{elapsed % 60:02d}s"

                if len(in_progress) == 0:
                    logger.info(f"  -> [{elapsed_str}] Missions ingestion complete!")
                    break

                logger.info(
                    f"  -> [{elapsed_str}] {len(in_progress)} mission(s) still ANALYSIS_IN_PROGRESS"
                )

                # Détection de stagnation
                if len(in_progress) == last_in_progress_count:
                    stagnation_count += 1
                else:
                    stagnation_count = 0
                    last_in_progress_count = len(in_progress)

                if stagnation_count >= stagnation_threshold:
                    logger.warning(
                        f"  -> Stagnation détectée ({stagnation_threshold * 10}s sans changement). "
                        f"Force reset de {len(in_progress)} mission(s) zombie(s) → STAFFED..."
                    )
                    for m in in_progress:
                        mid = m.get("id")
                        patch_res = client.patch(
                            f"/api/missions/missions/{mid}/status",
                            json={
                                "status": "STAFFED",
                                "reason": "Auto-reset zombie ANALYSIS_IN_PROGRESS (timeout stagnation)",
                            },
                        )
                        if patch_res.status_code == 200:
                            logger.info(f"  -> Mission {mid} forcée → STAFFED ✓")
                        else:
                            logger.warning(
                                f"  -> Mission {mid} PATCH failed: "
                                f"HTTP {patch_res.status_code} {patch_res.text[:80]}"
                            )
                    break
            else:
                logger.error(f"  -> Failed to check missions: {res.text}")

            time.sleep(10)

        if iterations >= max_iterations:
            logger.warning(
                "  -> wait_for_missions_ingestion timeout (10 min). Continuing anyway."
            )


def trigger_recalculate_tree(admin_password):
    logger.info("Triggering Competency Tree Recalculation...")
    token = authenticate(admin_password)
    with httpx.Client(
        base_url=DEV_API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=20.0
    ) as client:
        # Reset any zombie state in Redis first
        logger.info("  -> Resetting any previous stuck recalculation states in Redis...")
        reset_res = client.post("/api/cv/recalculate_tree/batch/reset")
        if reset_res.status_code == 401:
            logger.warning("  -> JWT expired during reset. Re-authenticating...")
            token = authenticate(admin_password)
            client.headers["Authorization"] = f"Bearer {token}"
            reset_res = client.post("/api/cv/recalculate_tree/batch/reset")
        logger.info(f"  -> Reset result: HTTP {reset_res.status_code}")

        res = client.post("/api/cv/recalculate_tree")
        if res.status_code == 401:
            logger.warning("  -> JWT expired. Re-authenticating...")
            token = authenticate(admin_password)
            client.headers["Authorization"] = f"Bearer {token}"
            res = client.post("/api/cv/recalculate_tree")

        if res.status_code in [200, 202]:
            logger.info("  -> Tree recalculation started in background.")
        else:
            logger.error(f"  -> Failed to start tree recalculation: HTTP {res.status_code} - {res.text}")


def wait_for_tree_recalculation(admin_password):
    logger.info("Polling Competency Tree Recalculation status...")
    token = authenticate(admin_password)
    displayed_logs = set()

    # Machine à états pour avancer automatiquement les étapes interactives
    next_steps = {
        "map": "deduplicate",
        "deduplicate": "reduce",
        "reduce": "sweep",
        "sweep": "apply"
    }

    with httpx.Client(
        base_url=DEV_API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15.0
    ) as client:
        while True:
            res = client.get("/api/cv/recalculate_tree/status")
            if res.status_code == 401:
                logger.warning("  -> JWT expired during polling. Re-authenticating...")
                token = authenticate(admin_password)
                client.headers["Authorization"] = f"Bearer {token}"
                continue

            if res.status_code == 200:
                data = res.json()
                status = data.get("status", "idle")
                batch_step = data.get("batch_step")
                logs = data.get("logs", [])
                for log in logs:
                    if log not in displayed_logs:
                        logger.info(f"    [Recalc] {log}")
                        displayed_logs.add(log)

                if status == "completed":
                    logger.info("  -> Competency Tree Recalculation completed!")
                    break
                if status == "error":
                    err = data.get("error", "Unknown error")
                    logger.error(f"  -> Competency Tree Recalculation failed: {err}")
                    break
                if status == "idle":
                    logger.info("  -> Competency Tree Recalculation idle. Exiting poll.")
                    break

                if status == "waiting_for_user" and batch_step in next_steps:
                    next_step = next_steps[batch_step]
                    logger.info(f"  -> Step '{batch_step}' finished. Auto-advancing to '{next_step}'...")

                    # Déclenche l'étape suivante
                    step_res = client.post(
                        "/api/cv/recalculate_tree/step",
                        json={"step": next_step}
                    )
                    if step_res.status_code == 401:
                        logger.warning("  -> JWT expired during step activation. Re-authenticating...")
                        token = authenticate(admin_password)
                        client.headers["Authorization"] = f"Bearer {token}"
                        step_res = client.post(
                            "/api/cv/recalculate_tree/step",
                            json={"step": next_step}
                        )

                    if step_res.status_code == 200:
                        logger.info(f"  -> Step '{next_step}' triggered successfully.")
                    else:
                        logger.error(f"  -> Failed to trigger step '{next_step}': {step_res.text}")
                        break
            else:
                logger.error(f"  -> Failed to check status: {res.text}")

            time.sleep(10)


def trigger_bulk_reanalyse(admin_password):
    """Lance le pipeline Bulk Reanalyse (map→reduce→apply) pour lier les compétences à la taxonomie.

    Stratégie idempotente :
    1. Si status=completed → skip (résultats déjà en base).
    2. Si status=batch_running/applying → poll sans relancer (job Vertex déjà en cours).
    3. Si status=idle → lance un nouveau job seulement si nécessaire.
    """
    logger.info("Triggering Bulk Reanalyse (competency_assignment pipeline)...")
    token = authenticate(admin_password)

    with httpx.Client(
        base_url=DEV_API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as client:

        # ── Étape 0 : Vérifier le status existant ──────────────────────────
        status_res = client.get("/api/cv/bulk-reanalyse/status")
        if status_res.status_code == 200:
            st = status_res.json()
            current_status = st.get("status", "idle")
            applying_current = st.get("applying_current", 0)
            total_cvs = st.get("total_cvs", 0)
            error_count = st.get("error_count", 0)

            if current_status == "completed" and error_count == 0:
                logger.info(
                    f"  -> Bulk reanalyse déjà completed ({applying_current}/{total_cvs} CVs). "
                    "Skip — résultats déjà en base."
                )
                return

            if current_status in ("batch_running", "applying", "building"):
                logger.info(
                    f"  -> Bulk reanalyse déjà en cours (status={current_status}). "
                    "Poll sans relancer le job Vertex."
                )
                return

        # ── Étape 1 : Lancer un nouveau job ────────────────────────────────
        res = client.post("/api/cv/bulk-reanalyse/start", json={})
        if res.status_code == 401:
            logger.warning("  -> JWT expired. Re-authenticating...")
            token = authenticate(admin_password)
            client.headers["Authorization"] = f"Bearer {token}"
            res = client.post("/api/cv/bulk-reanalyse/start", json={})

        if res.status_code in [200, 202]:
            logger.info(f"  -> Bulk reanalyse started: {res.json().get('message', '')}")
        elif res.status_code == 409:
            logger.info("  -> Bulk reanalyse already running — will poll existing pipeline.")
        else:
            logger.error(
                f"  -> Failed to start bulk reanalyse: HTTP {res.status_code} - {res.text}"
            )


def wait_for_bulk_reanalyse(admin_password):
    """Attend la fin du pipeline Bulk Reanalyse en interrogeant /bulk-reanalyse/status.

    Le pipeline passe par les phases : building → batch_running → applying → completed.
    On attend que status soit 'completed' ou 'error'/'cancelled'.
    """
    logger.info("Polling Bulk Reanalyse status...")
    token = authenticate(admin_password)
    with httpx.Client(base_url=DEV_API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=15.0) as client:
        while True:
            res = client.get("/api/cv/bulk-reanalyse/status")
            if res.status_code == 401:
                logger.warning("  -> JWT expired during polling. Re-authenticating...")
                token = authenticate(admin_password)
                client.headers["Authorization"] = f"Bearer {token}"
                continue

            if res.status_code == 200:
                data = res.json()
                status = data.get("status", "idle")
                processed = data.get("processed", 0)
                total = data.get("total_cvs", 0)
                errors = data.get("errors", 0)

                logger.info(
                    f"  -> Bulk reanalyse status={status} | processed={processed}/{total} | errors={errors}"
                )

                if status == "completed":
                    logger.info("  -> Bulk reanalyse completed!")
                    break
                if status in ("error", "cancelled"):
                    logger.error(f"  -> Bulk reanalyse ended with status={status}. Continuing anyway.")
                    break
                if status == "idle":
                    logger.info("  -> Bulk reanalyse idle (may have completed). Exiting poll.")
                    break
            else:
                logger.error(f"  -> Failed to check bulk reanalyse status: {res.text}")

            time.sleep(15)


def trigger_bulk_scoring(admin_password):
    """Lance le Bulk Scoring IA pour scorer les compétences de tous les consultants.

    Alimente la métrique `ai_scoring` du Data Quality Dashboard.
    Stratégie idempotente :
    1. Si status=batch_running et batch_job_id connu → appelle /resume/manual
       qui détecte Vertex SUCCEEDED et déclenche l'apply depuis GCS
       (évite de relancer un job Vertex coûteux si le résultat est déjà en GCS).
    2. Si status=completed/idle → lance un nouveau job (delta_only=True).
    3. Si status=409 (déjà en cours) → poll l'existant.
    """
    logger.info("Triggering Bulk Scoring IA (ai_scoring pipeline)...")
    token = authenticate(admin_password)

    with httpx.Client(
        base_url=DEV_API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as client:

        # ── Étape 0 : Vérifier si un job batch est déjà en état batch_running ──
        status_res = client.get("/api/competencies/bulk-scoring-all/status")
        if status_res.status_code == 200:
            st = status_res.json()
            current_status = st.get("status", "idle")
            batch_job_id = st.get("batch_job_id")

            if current_status == "batch_running" and batch_job_id:
                # Un job Vertex existe déjà. On appelle resume/manual :
                # - Si Vertex est SUCCEEDED → apply depuis GCS (pas de nouveau job)
                # - Si Vertex est encore RUNNING → retourne "polling" et on attend
                logger.info(
                    f"  -> Status={current_status}, batch_job_id trouvé. "
                    "Appel resume/manual pour détecter Vertex SUCCEEDED..."
                )
                resume_res = client.post(
                    "/api/competencies/bulk-scoring-all/resume/manual"
                )
                if resume_res.status_code == 200:
                    action = resume_res.json().get("action", "?")
                    logger.info(f"  -> resume/manual → action={action}")
                    if action == "apply_triggered":
                        logger.info(
                            "  -> Vertex SUCCEEDED détecté — apply depuis GCS lancé. "
                            "Polling en attente de completed..."
                        )
                    elif action == "polling":
                        state = resume_res.json().get("state", "?")
                        logger.info(
                            f"  -> Vertex encore en cours (state={state}). "
                            "Poursuite du polling..."
                        )
                    elif action == "error":
                        logger.error(
                            f"  -> Vertex job en erreur : {resume_res.json()}. "
                            "Continuing anyway."
                        )
                    # Dans tous les cas, on passe au polling — pas de nouveau job
                    return
                else:
                    logger.warning(
                        f"  -> resume/manual HTTP {resume_res.status_code} — "
                        "fallback : poursuite du polling sans relancer le job."
                    )
                    return

            elif current_status == "completed":
                logger.info(
                    "  -> Bulk scoring déjà completed (scores présents). "
                    "Skip trigger — nothing to do."
                )
                return

            elif current_status == "applying":
                logger.info(
                    "  -> Apply déjà en cours (status=applying). "
                    "Polling en attente de completed..."
                )
                return

        # ── Étape 1 : Pas de job en cours → lancer un nouveau job ───────────
        res = client.post(
            "/api/competencies/evaluations/bulk-scoring-all",
            params={"delta_only": "true", "force": "false", "min_scored_threshold": 10},
        )
        if res.status_code == 401:
            logger.warning("  -> JWT expired. Re-authenticating...")
            token = authenticate(admin_password)
            client.headers["Authorization"] = f"Bearer {token}"
            res = client.post(
                "/api/competencies/evaluations/bulk-scoring-all",
                params={
                    "delta_only": "true",
                    "force": "false",
                    "min_scored_threshold": 10,
                },
            )

        if res.status_code in [200, 202]:
            data = res.json()
            logger.info(
                f"  -> Bulk scoring started: {data.get('triggered', 0)} consultant(s) à scorer. "
                f"{data.get('message', '')}"
            )
        elif res.status_code == 409:
            logger.info("  -> Bulk scoring already running — will poll existing job.")
        else:
            logger.error(
                f"  -> Failed to start bulk scoring: HTTP {res.status_code} - {res.text}"
            )


def wait_for_bulk_scoring(admin_password):
    """Attend la fin du Bulk Scoring en interrogeant /bulk-scoring-all/status.

    Le scoring passe par les phases : running/batch_running → applying → completed.
    Timeout : 480 itérations × 15s = 2h max (cohérent avec les jobs Vertex à 2000+ paires).
    """
    logger.info("Polling Bulk Scoring status...")
    token = authenticate(admin_password)
    max_iterations = 480  # 480 x 15s = 2h max
    iterations = 0
    start_ts = time.time()
    with httpx.Client(base_url=DEV_API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=15.0) as client:
        while iterations < max_iterations:
            iterations += 1
            res = client.get("/api/competencies/bulk-scoring-all/status")
            if res.status_code == 401:
                logger.warning("  -> JWT expired during polling. Re-authenticating...")
                token = authenticate(admin_password)
                client.headers["Authorization"] = f"Bearer {token}"
                continue

            if res.status_code == 200:
                data = res.json()
                status = data.get("status", "idle")
                # NOTE : l'API retourne "success" (pas "success_count")
                success = data.get("success", data.get("success_count", 0))
                errors = data.get("error_count", 0)
                total = data.get("total_users", 0)
                elapsed = int(time.time() - start_ts)
                elapsed_str = f"{elapsed // 60}m{elapsed % 60:02d}s"

                # Afficher le dernier log Vertex pour suivre la progression
                logs = data.get("logs", [])
                last_vertex_log = ""
                for entry in reversed(logs):
                    if "[Poll #" in entry or "sous-tâches" in entry or "terminées" in entry:
                        # Extraire juste la partie utile après le timestamp
                        last_vertex_log = entry.split("] ", 1)[-1] if "] " in entry else entry
                        break

                log_suffix = f" | {last_vertex_log}" if last_vertex_log else ""
                logger.info(
                    f"  -> [{elapsed_str}] Bulk scoring status={status}"
                    f" | success={success}/{total} | errors={errors}{log_suffix}"
                )

                if status == "completed":
                    logger.info(f"  -> Bulk scoring completed! ({elapsed_str} elapsed)")
                    break
                if status in ("error", "cancelled"):
                    logger.error(
                        f"  -> Bulk scoring ended with status={status}. Continuing anyway."
                    )
                    break
                if status == "idle":
                    logger.info(
                        "  -> Bulk scoring idle (may have completed or not started). Exiting poll."
                    )
                    break
            else:
                logger.error(f"  -> Failed to check bulk scoring status: {res.text}")

            time.sleep(15)

        if iterations >= max_iterations:
            logger.warning("  -> Bulk scoring polling timeout (2h). Continuing anyway.")


def declare_consultant_unavailabilities(admin_password):
    logger.info("Declaring unavailability periods for 70% of consultants...")
    token = authenticate(admin_password)
    with httpx.Client(base_url=DEV_API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=10.0) as client:
        # 1. Fetch all users
        skip = 0
        limit = 100
        all_users = []
        while True:
            res = client.get(f"/api/users/?skip={skip}&limit={limit}")
            if res.status_code != 200:
                logger.error(f"  -> Failed to fetch users: {res.text}")
                return
            data = res.json()
            items = data.get("items", [])
            all_users.extend(items)
            if len(items) < limit:
                break
            skip += limit

        # 2. Filter for consultants (role == "user")
        consultants = [u for u in all_users if u.get("role") == "user"]
        if not consultants:
            logger.warning("  -> No consultants found to declare unavailabilities.")
            return

        # 3. Select 70% of them randomly
        num_to_select = int(len(consultants) * 0.7)
        selected_consultants = random.sample(consultants, num_to_select)
        logger.info(f"  -> Selecting {num_to_select} out of {len(consultants)} consultants (70%).")

        # 4. Generate and PUT unavailabilities
        today = datetime.date.today()
        unavailability_types = ["Congé", "Formation", "Autre"]

        updated_count = 0
        for user in selected_consultants:
            # Generate 1 period: start date within the next 6 months (180 days)
            start_offset = random.randint(1, 180)
            duration = random.randint(3, 5)  # 3 to 5 days max

            start_date = today + datetime.timedelta(days=start_offset)
            end_date = start_date + datetime.timedelta(days=duration - 1)

            period = {
                "type": random.choice(unavailability_types),
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d")
            }

            # Put update to users_api
            user_id = user["id"]
            update_payload = {
                "unavailability_periods": [period]
            }

            res = client.put(f"/api/users/{user_id}", json=update_payload)
            if res.status_code == 200:
                updated_count += 1
            else:
                logger.error(f"  -> Failed to update user {user_id}: {res.text}")

        logger.info(f"  -> Successfully declared unavailabilities for {updated_count} consultants.")


def main():
    logger.info("=== GCP Summit Data Generation Workflow ===")
    logger.info(f"   API URL : {DEV_API_URL}")
    logger.info(f"   gcloud  : {GCLOUD_BIN}")

    check_platform_health()

    admin_password = get_admin_password()
    token = authenticate(admin_password)

    logger.info("\\n1. Adding Sebastien as admin (Early Injection)...")
    ensure_sebastien_admin(token)

    logger.info("\\n2. Running generate_fake_agencies.py...")
    subprocess.run(["python3", "scripts/generate_fake_agencies.py"], check=True)

    if not os.path.exists(PROGRESS_FILE):
        raise Exception("Error: progress.json not found. generate_fake_agencies failed?")

    with open(PROGRESS_FILE, "r") as f:
        progress = json.load(f)

    root_folder_id = progress.get("root_folder_id")
    if not root_folder_id:
        raise Exception("Error: root_folder_id not found in progress.json.")

    logger.info(f"\\n3. Found root folder ID: {root_folder_id}")

    logger.info("\\n4. Registering folders with Drive Scanner...")
    if setup_drive_scanner(token, progress):
        logger.info("\\n5. Triggering Drive Sync...")
        logger.info("\n5. Triggering Drive Sync...")
        trigger_drive_sync()

        logger.info("\n6. Polling Drive Ingestion...")
        wait_for_drive_ingestion(admin_password)

        logger.info("\n6b. Triggering Competency Tree Recalculation...")
        trigger_recalculate_tree(admin_password)
        wait_for_tree_recalculation(admin_password)

        logger.info("\n6c. Declaring Unavailability Periods...")
        declare_consultant_unavailabilities(admin_password)

        logger.info("\n6d. Triggering Bulk Reanalyse (competency_assignment)...")
        trigger_bulk_reanalyse(admin_password)
        wait_for_bulk_reanalyse(admin_password)

        logger.info("\n6e. Triggering Bulk Scoring IA (ai_scoring)...")
        trigger_bulk_scoring(admin_password)
        wait_for_bulk_scoring(admin_password)

    logger.info("\n7. Generating fake missions...")
    subprocess.run(["python3", "scripts/generate_fake_missions.py"], check=True)

    logger.info("\n8. Polling Missions Ingestion...")
    wait_for_missions_ingestion(admin_password)

    logger.info("\n9. Calibrating RAG parameters...")
    try:
        subprocess.run(
            ["python3", "platform-engineering/manage_env.py", "rag-calibrate", "--env", "dev"],
            check=True
        )
        logger.info("  -> RAG calibration completed successfully.")
    except Exception as e:
        logger.warning(f"  -> RAG calibration failed (non-blocking): {e}")

    logger.info("\n10. Seeding mcp-claude-memory with demo memories...")
    seed_mcp_claude_memory()

    logger.info("\n=== Workflow Completed Successfully ===")
    logger.info(f"   Données générées sur : {DEV_API_URL}")
    logger.info("   Prochaine étape : /analyse-prompt pour valider les agents")


# ─────────────────────────────────────────────────────────────────────────────
# Étape 10 : Injection de mémoires de démo dans mcp-claude-memory
# ─────────────────────────────────────────────────────────────────────────────

MCP_MEMORY_URL = os.getenv(
    "MCP_MEMORY_URL",
    "https://api.dev.zenika.slavayssiere.fr/mcp-claude-memory"
)

# Répertoire contenant les fichiers JSON de mémoires de démo.
# Chaque fichier JSON est une liste de dicts compatibles avec store_memory.
# Ajouter ou éditer les JSON pour enrichir le dataset sans toucher au script.
_DEMO_MEMORIES_DIR = os.path.join(os.path.dirname(__file__), "demo_memories")


def _load_demo_memories() -> list:
    """Charge toutes les mémoires de démo depuis scripts/demo_memories/.

    Supporte deux formats :
    - *.json  : tableau JSON [ {...}, {...}, ... ]
    - *.jsonl : une mémoire par ligne (JSON Lines)

    Les fichiers sont chargés dans l'ordre alphabétique.
    Retourne une liste plate de dicts compatibles avec store_memory.
    """
    memories = []
    if not os.path.isdir(_DEMO_MEMORIES_DIR):
        logger.warning(
            f"  [memory] Répertoire demo_memories introuvable : {_DEMO_MEMORIES_DIR}"
        )
        return memories

    all_files = sorted(
        f for f in os.listdir(_DEMO_MEMORIES_DIR)
        if f.endswith(".json") or f.endswith(".jsonl")
    )
    if not all_files:
        logger.warning("  [memory] Aucun fichier JSON/JSONL trouvé dans demo_memories/")
        return memories

    for fname in all_files:
        fpath = os.path.join(_DEMO_MEMORIES_DIR, fname)
        try:
            if fname.endswith(".jsonl"):
                batch = []
                with open(fpath, encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            batch.append(json.loads(line))
                        except json.JSONDecodeError as je:
                            logger.warning(
                                f"  [memory] {fname}:{lineno} JSON invalide — ignoré ({je})"
                            )
                logger.info(
                    f"  [memory] JSONL chargé : {len(batch)} mémoires depuis {fname}"
                )
            else:
                with open(fpath, encoding="utf-8") as fh:
                    batch = json.load(fh)
                if not isinstance(batch, list):
                    logger.warning(f"  [memory] {fname} : format invalide (attendu list)")
                    continue
                logger.info(
                    f"  [memory] JSON chargé  : {len(batch)} mémoires depuis {fname}"
                )
            memories.extend(batch)
        except Exception as exc:
            logger.warning(f"  [memory] Erreur lecture {fname} : {exc}")

    logger.info(f"  [memory] Total chargé : {len(memories)} mémoires de démo")
    return memories


DEMO_MEMORIES = [
    # ── Projet test-open-code ──────────────────────────────────────────────
    {
        "content": (
            "L'architecture multi-agents de la plateforme Zenika repose sur le protocole A2A (Agent-to-Agent) "
            "via HTTP REST stateless. L'agent_router_api délègue aux sous-agents (agent_hr_api, agent_ops_api, "
            "agent_missions_api) en fonction de la nature de la requête RH ou opérationnelle. "
            "Les sous-agents ne s'exposent pas en MCP — seules les APIs data le font."
        ),
        "summary": "Architecture multi-agents A2A : router + sous-agents spécialisés",
        "category": "decision",
        "tags": ["architecture", "adk", "a2a", "multi-agents", "cloud-run"],
        "importance": 0.95,
        "project": "test-open-code",
    },
    {
        "content": (
            "Le pattern Zero-Trust de la plateforme impose que chaque service vérifie le JWT HS256 "
            "localement via verify_jwt() avant tout traitement. Les agents propagent le token via "
            "inject(headers) d'OpenTelemetry et auth_header_var (contextvars) pour tous les appels "
            "httpx sortants. Aucun endpoint protégé ne retourne 200 sans Authorization valide."
        ),
        "summary": "Zero-Trust inter-services : propagation JWT via inject(headers)",
        "category": "pattern",
        "tags": ["zero-trust", "jwt", "security", "opentelemetry"],
        "importance": 0.9,
        "project": "test-open-code",
    },
    {
        "content": (
            "Le bulk-scoring Vertex AI Batch traite 1851 paires (user × compétence) en une seule "
            "soumission JSONL sur GCS. Le job batchPredictionJobs/{id} tourne en région europe-west1 "
            "avec gemini-2.5-flash. La résumption est gérée par un Cloud Scheduler keepalive sur "
            "/bulk-scoring-all/resume toutes les 15 min pour survivre au scale-to-zero Cloud Run."
        ),
        "summary": "Vertex AI Batch scoring : 1851 inférences, keepalive Cloud Scheduler",
        "category": "feature",
        "tags": ["vertex-ai", "batch", "scoring", "cloud-scheduler", "gcs"],
        "importance": 0.85,
        "project": "test-open-code",
    },
    {
        "content": (
            "La recalcul de l'arbre taxonomique suit une machine à états Redis : "
            "map → deduplicate → reduce → sweep → apply. "
            "Chaque étape est déclenchée automatiquement par le script via POST /taxonomy/batch/next-step. "
            "Le reset Redis préalable (/batch/reset) est indispensable pour éviter les états zombies "
            "qui bloquent la progression."
        ),
        "summary": "State machine Redis pour le recalcul de l'arbre taxonomique (5 étapes)",
        "category": "feature",
        "tags": ["redis", "state-machine", "taxonomy", "competencies"],
        "importance": 0.8,
        "project": "test-open-code",
    },
    {
        "content": (
            "Le RAG calibration génère automatiquement les top-10 IDs de consultants pour chaque "
            "golden query et les injecte dans golden_queries.json. Le snapshot est poussé vers "
            "analytics_mcp BigQuery (table ai_usage, location europe-west1). "
            "Les 8 cas de test couvrent : GCP DevOps, Data Engineer, Fullstack React, Cloud Architect, "
            "Security Zero Trust, Agile Coach, MLOps, Node Backend."
        ),
        "summary": "RAG calibration : 8 golden queries, snapshot BigQuery europe-west1",
        "category": "feature",
        "tags": ["rag", "calibration", "bigquery", "golden-dataset"],
        "importance": 0.75,
        "project": "test-open-code",
    },
    {
        "content": (
            "Correction du bug de containment word-match dans competencies_router.py. "
            "Le check 1 (nouveau) détecte les expansions de marque via regex word-boundary : "
            "'Google Kubernetes Engine' → résout vers 'Kubernetes' existant. "
            "CONTAINMENT_MIN_LEN=6 évite les faux positifs sur les mots courts (Cloud=5, Agile=5). "
            "La fonction _auto_alias() centralise l'ajout d'alias pour éviter la duplication de code."
        ),
        "summary": "Fix containment word-match : GKE → Kubernetes, _auto_alias()",
        "category": "bugfix",
        "tags": ["competencies", "fuzzy-match", "regex", "deduplication"],
        "importance": 0.7,
        "project": "test-open-code",
    },
    {
        "content": (
            "La pagination obligatoire (AGENTS.md §3) impose skip/limit + total sur tous les endpoints "
            "liste. Une hard limit silencieuse est un bug qui masque des données. "
            "Le pattern correct : fetch_all_users() boucle sur skip/limit jusqu'à len(batch) < limit. "
            "Les tools MCP exposant des listes DOIVENT transmettre skip/limit à la requête SQL."
        ),
        "summary": "Pagination obligatoire : skip/limit + total, jamais de hard limit silencieuse",
        "category": "pattern",
        "tags": ["pagination", "api-design", "mcp", "golden-rules"],
        "importance": 0.7,
        "project": "test-open-code",
    },
    {
        "content": (
            "Le FinOps tracking est centralisé dans analytics_mcp via log_ai_consumption(). "
            "La table BigQuery ai_usage est partitionnée par jour en europe-west1. "
            "Tous les agents DOIVENT appeler log_ai_consumption après chaque inférence LLM. "
            "Le dashboard Grafana AIOps charge les métriques via /api/analytics/metrics/aiops."
        ),
        "summary": "FinOps : log_ai_consumption → BigQuery ai_usage partitionnée par jour",
        "category": "learning",
        "tags": ["finops", "bigquery", "analytics", "grafana", "aiops"],
        "importance": 0.65,
        "project": "test-open-code",
    },
    {
        "content": (
            "Les contrats d'interface inter-services DOIVENT utiliser Model.model_validate() "
            "avec gestion explicite de ValidationError. L'utilisation de .get('clé', []) est "
            "formellement interdite pour les réponses structurées (ADR-0015). "
            "Les schémas partagés sont dans shared/schemas/ : PaginationResponse[T], "
            "MissionsResponse, UsersResponse, McpToolResult."
        ),
        "summary": "Contrats d'interface : model_validate() obligatoire, .get() interdit (ADR-0015)",
        "category": "decision",
        "tags": ["pydantic", "contracts", "adr", "validation", "fail-fast"],
        "importance": 0.8,
        "project": "test-open-code",
    },
    {
        "content": (
            "La commande reprocess_all.py orchestre la purge complète + regénération des données "
            "de démo : purge Drive → purge users → purge compétences/suggestions → "
            "ingestion 65 CVs → recalcul arbre taxonomique → bulk reanalyse → bulk scoring → "
            "génération 20 missions → calibration RAG. Durée totale : ~45-60 min."
        ),
        "summary": "reprocess_all.py : pipeline complet purge + regénération (45-60 min)",
        "category": "feature",
        "tags": ["reprocessing", "demo", "idempotent", "pipeline"],
        "importance": 0.75,
        "project": "test-open-code",
    },
    # ── Projet MCP-Claude-mem-local ───────────────────────────────────────
    {
        "content": (
            "La connexion AlloyDB IAM Auth utilise le connecteur Python google-cloud-alloydb-connector "
            "avec enable_iam_auth=True et IPTypes.PRIVATE. Le Service Account Cloud Run est "
            "sa-mcp-claude-memory-dev@{project_id}.iam.gserviceaccount.com. "
            "Aucun mot de passe en clair — authentication par token ADC."
        ),
        "summary": "AlloyDB IAM Auth : connecteur Python, SA Cloud Run, zéro mot de passe",
        "category": "feature",
        "tags": ["alloydb", "iam-auth", "cloud-run", "security"],
        "importance": 0.9,
        "project": "MCP-Claude-mem-local",
    },
    {
        "content": (
            "La recherche hybride combine vectorielle (pgvector cosine) + trigramme (pg_trgm) "
            "avec Reciprocal Rank Fusion pour fusionner les résultats. "
            "Le scoring ACT-R (Adaptive Control of Thought-Rational) pondère par récence d'accès "
            "et activation cognitive. Les mémoires oubliées (activation < -2) sont exclues par défaut."
        ),
        "summary": "Recherche hybride : pgvector + pg_trgm + RRF + scoring ACT-R cognitif",
        "category": "feature",
        "tags": ["hybrid-search", "pgvector", "actr", "rrf", "cognitive"],
        "importance": 0.85,
        "project": "MCP-Claude-mem-local",
    },
    {
        "content": (
            "Le déploiement GCP utilise Cloud Run derrière IAP Google. "
            "L'auth se fait via identity token (OIDC) généré par gcloud auth print-identity-token "
            "--audiences={iap_client_id} où l'audience est lue depuis Secret Manager google-secret-id. "
            "Pour les user accounts, on impersonne le SA via gcloud auth print-identity-token "
            "--impersonate-service-account=sa-mcp-claude-memory-dev@..."
        ),
        "summary": "IAP Cloud Run : identity token OIDC + impersonation SA pour user accounts",
        "category": "feature",
        "tags": ["iap", "cloud-run", "oidc", "impersonation", "secret-manager"],
        "importance": 0.85,
        "project": "MCP-Claude-mem-local",
    },
    {
        "content": (
            "L'embedding utilise text-embedding-004 de Vertex AI (768 dimensions) en production GCP. "
            "Le fallback local utilise nomic-embed-text via Ollama. "
            "La variable EMBEDDING_PROVIDER='vertexai' switche entre les deux modes. "
            "Les index HNSW pgvector utilisent vector_cosine_ops pour la similarité cosinus."
        ),
        "summary": "Embeddings : text-embedding-004 (Vertex) vs nomic-embed-text (Ollama local)",
        "category": "decision",
        "tags": ["embeddings", "vertex-ai", "ollama", "pgvector", "hnsw"],
        "importance": 0.8,
        "project": "MCP-Claude-mem-local",
    },
    {
        "content": (
            "La CLI gcp/cli.py est le proxy stdio-to-HTTP pour les IDEs (Antigravity, Claude Code). "
            "Elle traduit les requêtes JSON-RPC MCP stdio vers les appels HTTP IAP-protégés. "
            "Le cache token est stocké dans ~/.cache/mcp_iap_token_{project_id}.json "
            "avec expiration 50 min (tokens Google : 1h)."
        ),
        "summary": "CLI proxy stdio-to-HTTP : JSON-RPC MCP → HTTP IAP, cache token 50 min",
        "category": "feature",
        "tags": ["cli", "mcp", "stdio", "proxy", "token-cache"],
        "importance": 0.7,
        "project": "MCP-Claude-mem-local",
    },
    {
        "content": (
            "Le cycle d'oubli ACT-R recalcule l'activation de toutes les mémoires : "
            "active (A > 0), dormant (-2 < A ≤ 0), forgotten (A ≤ -2). "
            "Les mémoires forgotten restent en base mais sont exclues des résultats par défaut. "
            "access_timestamps est un ring buffer (max 1000 entrées) pour le calcul de récence."
        ),
        "summary": "Cycle d'oubli ACT-R : active/dormant/forgotten, ring buffer access_timestamps",
        "category": "learning",
        "tags": ["actr", "forgetting", "cognitive", "memory-management"],
        "importance": 0.75,
        "project": "MCP-Claude-mem-local",
    },
    {
        "content": (
            "Row-Level Security (RLS) PostgreSQL isole les mémoires par user_id. "
            "La session variable app.current_user_id est injectée via _init_connection() "
            "sur chaque nouvelle connexion du pool asyncpg. "
            "Les mémoires avec user_id IS NULL sont accessibles à tous (mémoires partagées)."
        ),
        "summary": "RLS PostgreSQL : user_id isolation via app.current_user_id par connexion",
        "category": "feature",
        "tags": ["rls", "postgresql", "user-isolation", "security", "asyncpg"],
        "importance": 0.8,
        "project": "MCP-Claude-mem-local",
    },
    {
        "content": (
            "Correction du crash KeyError dans la génération de viewer_demo.html. "
            "L'utilisation originelle de str.format() sur HTML_TEMPLATE levait KeyError "
            "à cause des accolades CSS (ex: {display: flex}). "
            "Solution : chaînage de .replace() ciblés qui préserve la syntaxe CSS standard."
        ),
        "summary": "Fix KeyError viewer_demo.html : .replace() au lieu de .format() (accolades CSS)",
        "category": "bugfix",
        "tags": ["bugfix", "css", "python", "template"],
        "importance": 0.6,
        "project": "MCP-Claude-mem-local",
    },
    # ── Projet gcp-summit-2026-demo ────────────────────────────────────────
    {
        "content": (
            "Le GCP Summit 2026 démo montre une plateforme de staffing IA complète : "
            "ingestion CV Drive → analyse Gemini → arbre de compétences → scoring Vertex AI → "
            "matching missions → recommandation d'équipes. "
            "65 consultants fictifs sur 4 agences (Paris, Sèvres, Saumur, Bizanos). "
            "20 missions RFP avec analyse IA et proposition d'équipes."
        ),
        "summary": "GCP Summit 2026 : démo staffing IA end-to-end (65 consultants, 20 missions)",
        "category": "discovery",
        "tags": ["gcp-summit", "demo", "staffing", "zenika"],
        "importance": 0.95,
        "project": "gcp-summit-2026-demo",
    },
    {
        "content": (
            "Le Google Cloud SDK (ADC) est utilisé pour toutes les authentifications GCP : "
            "Secret Manager, Vertex AI, BigQuery, AlloyDB IAM. "
            "La commande gcloud auth application-default login configure les credentials locaux. "
            "En Cloud Run, les credentials ADC sont automatiques via le Service Account du runtime."
        ),
        "summary": "ADC (Application Default Credentials) : local gcloud login, Cloud Run automatique",
        "category": "learning",
        "tags": ["adc", "gcloud", "credentials", "cloud-run", "gcp"],
        "importance": 0.8,
        "project": "gcp-summit-2026-demo",
    },
    {
        "content": (
            "Vertex AI Batch Prediction est plus économique que l'inférence en streaming pour "
            "les workloads bulk (> 100 requêtes). Le JSONL est uploadé sur GCS, le job soumis "
            "via client.batches.create(), et les résultats lus depuis GCS après completion. "
            "Région obligatoire : europe-west1 pour la conformité RGPD."
        ),
        "summary": "Vertex AI Batch vs streaming : économique pour bulk > 100 req, RGPD europe-west1",
        "category": "decision",
        "tags": ["vertex-ai", "batch", "cost", "rgpd", "gcs"],
        "importance": 0.85,
        "project": "gcp-summit-2026-demo",
    },
    {
        "content": (
            "Cloud Run scale-to-zero économise les coûts en dehors des démos. "
            "Le cold start est géré par un warmup endpoint et le Cloud Scheduler keepalive. "
            "Min-instances=0 en dev, min-instances=1 en production pour les services critiques. "
            "Le timeout max Cloud Run est 3600s (1h) pour les jobs longs (bulk scoring)."
        ),
        "summary": "Cloud Run scale-to-zero : warmup, keepalive, min-instances selon env",
        "category": "preference",
        "tags": ["cloud-run", "scale-to-zero", "cost", "warmup"],
        "importance": 0.7,
        "project": "gcp-summit-2026-demo",
    },
    {
        "content": (
            "Google Drive est utilisé comme source de vérité pour les CVs. "
            "drive_api synchronise les fichiers PDF/DOCX via l'API Drive v3 avec pagination "
            "(pageSize=100, nextPageToken en boucle). "
            "Un Cloud Scheduler déclenche la sync toutes les heures. "
            "Les CVs sont analysés par Gemini via cv_api avec extraction structurée."
        ),
        "summary": "Google Drive → CVs : sync drive_api paginée, analyse Gemini cv_api",
        "category": "feature",
        "tags": ["google-drive", "cv", "gemini", "sync", "pagination"],
        "importance": 0.75,
        "project": "gcp-summit-2026-demo",
    },
    {
        "content": (
            "AlloyDB PostgreSQL avec l'extension pgvector permet la recherche vectorielle native. "
            "Les embeddings de 768 dimensions sont stockés dans la colonne vector(768). "
            "L'index HNSW (vector_cosine_ops) garantit des requêtes de similarité < 10ms. "
            "pgvector est disponible nativement sur AlloyDB sans installation additionnelle."
        ),
        "summary": "AlloyDB + pgvector : embeddings 768d, HNSW index, similarité < 10ms",
        "category": "learning",
        "tags": ["alloydb", "pgvector", "embeddings", "hnsw", "performance"],
        "importance": 0.8,
        "project": "gcp-summit-2026-demo",
    },
    {
        "content": (
            "Le frontend Vue.js utilise un proxy Nginx qui route /api/ vers agent_router_api. "
            "L'agent router analyse la requête utilisateur et délègue au sous-agent approprié "
            "via A2A HTTP. La réponse est streamée en SSE vers le frontend pour l'affichage "
            "progressif. Le cache sémantique Redis évite les appels LLM redondants."
        ),
        "summary": "Frontend Vue.js → Nginx → agent_router → A2A → SSE stream + cache sémantique",
        "category": "discovery",
        "tags": ["frontend", "vue", "nginx", "sse", "semantic-cache", "redis"],
        "importance": 0.75,
        "project": "gcp-summit-2026-demo",
    },
    # ── Projet test-open-code (suite) ─────────────────────────────────────
    {
        "content": (
            "Le Dockerfile multi-stage de chaque service suit 3 étapes : "
            "builder (installation deps), runtime (image slim), et expose uniquement le port 8080. "
            "USER non-root obligatoire (USER appuser), CMD sans shell (forme JSON array). "
            "Le .dockerignore exclut .git, __pycache__, *.pyc, .env, tests/. "
            "L'image de base est python:3.12-slim pour minimiser la surface d'attaque."
        ),
        "summary": "Dockerfile multi-stage : builder/runtime, USER non-root, CMD JSON array",
        "category": "pattern",
        "tags": ["docker", "security", "multi-stage", "cloud-run", "best-practices"],
        "importance": 0.75,
        "project": "test-open-code",
    },
    {
        "content": (
            "Les migrations de base de données utilisent Liquibase avec des changelogs XML. "
            "Chaque changeset DOIT inclure une section rollback. "
            "Le deploy.sh exécute les migrations AVANT le déploiement du service. "
            "Les migrations sont versionnées dans db_migrations/changelogs/ "
            "et s'exécutent via le container Liquibase en mode CI (--fail-on-error=true)."
        ),
        "summary": "Liquibase : changelogs XML avec rollback, exécution pré-déploiement",
        "category": "pattern",
        "tags": ["liquibase", "migrations", "postgresql", "ci-cd", "rollback"],
        "importance": 0.8,
        "project": "test-open-code",
    },
    {
        "content": (
            "Redis est utilisé avec des namespaces DB isolés — un DB par service — "
            "pour éviter les collisions de clés. Le cache est invalidé sur toutes les mutations "
            "(POST, PUT, DELETE) via delete_cache() et clear_namespace(). "
            "Le TTL par défaut est 300s. Les clés de tree suivent le pattern 'competencies:tree:{id}'. "
            "La connexion Redis utilise les variables REDIS_HOST et REDIS_PORT."
        ),
        "summary": "Redis namespaces isolés par service, invalidation sur mutations, TTL 300s",
        "category": "pattern",
        "tags": ["redis", "cache", "namespaces", "invalidation", "performance"],
        "importance": 0.75,
        "project": "test-open-code",
    },
    {
        "content": (
            "Prometheus + Grafana surveillent tous les services via PrometheusInstrumentator. "
            "FastAPIInstrumentor est configuré avec excluded_urls='health,metrics'. "
            "Les dashboards Grafana sont provisionnés automatiquement depuis grafana/dashboards/. "
            "Les alertes Cloud Monitoring sont configurées pour les erreurs 5xx (seuil > 5/min) "
            "et la latence P95 (seuil > 2s). Loki centralise les logs structurés JSON."
        ),
        "summary": "Observabilité : Prometheus/Grafana/Loki, alertes 5xx et latence P95",
        "category": "feature",
        "tags": ["prometheus", "grafana", "loki", "monitoring", "alerting"],
        "importance": 0.8,
        "project": "test-open-code",
    },
    {
        "content": (
            "Le test_zero_trust.py est obligatoire dans chaque service. "
            "Il vérifie : (1) 401 sans token, (2) 401 avec token expiré, "
            "(3) 401 avec token signature invalide, (4) 200 avec token valide. "
            "Les tests MCP (test_mcp_tools.py) vérifient le contrat de chaque tool. "
            "pytest.ini configure markers et coverage minimum 80%."
        ),
        "summary": "Tests obligatoires : test_zero_trust.py + test_mcp_tools.py, coverage 80%",
        "category": "pattern",
        "tags": ["tests", "zero-trust", "mcp", "pytest", "coverage"],
        "importance": 0.75,
        "project": "test-open-code",
    },
    {
        "content": (
            "Le router.py de chaque API data est maintenu sous un seuil de complexité cyclomatique. "
            "La logique métier est déléguée à des services (services/). "
            "Le fichier main.py ne doit contenir que : app init, middleware, routers include, "
            "health/ready endpoints, MCP proxy route. "
            "Tout endpoint avec plus de 50 lignes doit être refactorisé en service."
        ),
        "summary": "Architecture clean : router.py < seuil, logique dans services/, main.py minimal",
        "category": "decision",
        "tags": ["architecture", "clean-code", "refactor", "complexity"],
        "importance": 0.7,
        "project": "test-open-code",
    },
    {
        "content": (
            "Pub/Sub est utilisé pour les événements asynchrones entre services. "
            "La Dead Letter Queue (DLQ) capture les messages non traités après 5 tentatives. "
            "monitoring_mcp expose un tool inspect_pubsub_dlq pour diagnostiquer les messages bloqués. "
            "Le pattern d'abonnement utilise des push subscriptions vers Cloud Run "
            "avec authentification OIDC (service account subscriber)."
        ),
        "summary": "Pub/Sub avec DLQ, push subscriptions OIDC vers Cloud Run, monitoring via MCP",
        "category": "feature",
        "tags": ["pubsub", "dlq", "async", "event-driven", "oidc"],
        "importance": 0.7,
        "project": "test-open-code",
    },
    {
        "content": (
            "La data quality est évaluée via un score Grade A/B/C/D sur 4 critères : "
            "complétude des CVs (> 80%), couverture scoring (> 70% des compétences scorées), "
            "fraîcheur des données (< 30 jours), et diversité taxonomique (> 5 piliers). "
            "La dégradation de grade déclenche une alerte Slack via webhook. "
            "tenacity (retry avec backoff exponentiel) protège les appels Gemini contre les timeouts."
        ),
        "summary": "Data quality Grade A-D : complétude, scoring, fraîcheur, diversité taxonomique",
        "category": "feature",
        "tags": ["data-quality", "scoring", "monitoring", "tenacity", "gemini"],
        "importance": 0.75,
        "project": "test-open-code",
    },
    # ── Projet ia-staffing-agent (nouveau) ────────────────────────────────
    {
        "content": (
            "L'agent missions utilise le tool get_rfp_details pour extraire les compétences "
            "requises d'un RFP (Request for Proposal) en langage naturel. "
            "Il appelle ensuite search_consultants_by_skills pour scorer les consultants "
            "selon leur pertinence (score 0-100). Le résultat inclut une recommandation "
            "d'équipe avec justification par compétence et disponibilité."
        ),
        "summary": "Agent missions : RFP → extraction compétences → scoring consultants → équipe",
        "category": "feature",
        "tags": ["agent", "missions", "rag", "staffing", "rfp"],
        "importance": 0.9,
        "project": "ia-staffing-agent",
    },
    {
        "content": (
            "Le prompt engineering pour l'extraction RFP utilise le few-shot prompting avec 3 exemples. "
            "Les system prompts sont stockés dans prompts_api (clé missions_api.extract_mission_info). "
            "La température est fixée à 0.1 pour maximiser la reproductibilité. "
            "Les hallucinations sont réduites par une contrainte de format JSON strict "
            "avec validation Pydantic sur la réponse de Gemini."
        ),
        "summary": "Prompt engineering RFP : few-shot, température 0.1, JSON strict + validation Pydantic",
        "category": "learning",
        "tags": ["prompt-engineering", "few-shot", "gemini", "pydantic", "temperature"],
        "importance": 0.85,
        "project": "ia-staffing-agent",
    },
    {
        "content": (
            "Le cache sémantique de agent_router_api évite les appels LLM redondants. "
            "Il calcule un embedding de la requête utilisateur et cherche dans Redis "
            "les réponses précédentes avec similarité cosinus > 0.92. "
            "TTL du cache : 3600s. Invalidation manuelle via DELETE /cache/semantic. "
            "Économie estimée : 40% des appels Gemini sur des requêtes répétitives."
        ),
        "summary": "Cache sémantique : embedding + cosinus > 0.92, TTL 3600s, économie 40% LLM",
        "category": "feature",
        "tags": ["semantic-cache", "redis", "embeddings", "cost", "performance"],
        "importance": 0.85,
        "project": "ia-staffing-agent",
    },
    {
        "content": (
            "Les guardrails de l'agent bloquent les requêtes hors-scope (non liées au staffing). "
            "Un classifier Gemini évalue le score de pertinence (0-1) avant de router. "
            "Les requêtes avec score < 0.3 reçoivent une réponse standard de refus. "
            "Les sessions sont maintenues 30 min en Redis avec un historique de 10 échanges. "
            "Le guardrail log toutes les tentatives de jailbreak dans Cloud Logging."
        ),
        "summary": "Guardrails : classifier pertinence 0-1, refus < 0.3, logs jailbreak Cloud Logging",
        "category": "feature",
        "tags": ["guardrails", "classifier", "security", "sessions", "logging"],
        "importance": 0.9,
        "project": "ia-staffing-agent",
    },
    {
        "content": (
            "Le mode streaming SSE (Server-Sent Events) permet l'affichage progressif "
            "des réponses de l'agent dans le frontend Vue.js. "
            "Le agent_router_api streame via yield de tokens Gemini. "
            "Le frontend utilise EventSource API avec reconnection automatique. "
            "Les chunks sont formattés en Markdown et rendus via marked.js."
        ),
        "summary": "Streaming SSE : tokens Gemini → frontend Vue.js via EventSource + Markdown",
        "category": "feature",
        "tags": ["sse", "streaming", "frontend", "gemini", "markdown"],
        "importance": 0.75,
        "project": "ia-staffing-agent",
    },
    {
        "content": (
            "L'agent HR construit dynamiquement sa liste de tools MCP au démarrage "
            "en interrogeant les sidecars MCP de users_api, competencies_api et cv_api. "
            "Les docstrings des tools sont critiques : le LLM s'en sert pour décider quand les appeler. "
            "Un tool mal documenté cause des hallucinations ou des appels incorrects. "
            "Les tools sont enregistrés dans ADK via FunctionTool(func=...) avec description enrichie."
        ),
        "summary": "ADK tools : docstrings critiques pour le routing LLM, enregistrement FunctionTool",
        "category": "learning",
        "tags": ["adk", "tools", "docstrings", "llm", "function-calling"],
        "importance": 0.85,
        "project": "ia-staffing-agent",
    },
    # ── Projet infra-ops ──────────────────────────────────────────────────
    {
        "content": (
            "Terraform gère l'infrastructure GCP (Cloud Run, AlloyDB, Redis, Pub/Sub, IAM). "
            "Le state est stocké dans un bucket GCS avec verrouillage DynamoDB-style. "
            "Les secrets sont provisionnés via google_secret_manager_secret_version. "
            "Les IPs sont réservées statiquement pour le Load Balancer. "
            "terraform apply est INTERDIT manuellement — seul deploy.sh est autorisé."
        ),
        "summary": "Terraform GCP : state GCS, secrets Secret Manager, LB IP statique, deploy.sh only",
        "category": "decision",
        "tags": ["terraform", "gcp", "iac", "secret-manager", "load-balancer"],
        "importance": 0.85,
        "project": "infra-ops",
    },
    {
        "content": (
            "Le Load Balancer GCP route les requêtes selon le path prefix : "
            "/api/* → agent_router_api (Cloud Run), "
            "/mcp-claude-memory/* → mcp-claude-memory (Cloud Run, projet externe), "
            "/monitoring-mcp/* → monitoring_mcp. "
            "Les extra-projects injectent leurs routes LB via lb-routes dans manage_env.py. "
            "Les health checks LB se font sur /health avec interval 10s, threshold 2."
        ),
        "summary": "LB GCP : routing par path prefix, extra-projects injectent leurs routes",
        "category": "feature",
        "tags": ["load-balancer", "routing", "cloud-run", "health-check", "gcp"],
        "importance": 0.8,
        "project": "infra-ops",
    },
    {
        "content": (
            "Le deploy.sh orchestre le cycle complet : "
            "1. Détection des services modifiés (hash build), "
            "2. Build Docker et push Artifact Registry, "
            "3. Bump de version (semver patch automatique), "
            "4. Exécution migrations Liquibase, "
            "5. Déploiement Cloud Run via terraform apply, "
            "6. Sanity checks post-déploiement. "
            "Seul deploy.sh est autorisé à bumper les versions dans envs/*.yaml."
        ),
        "summary": "deploy.sh : détection changements → build → bump version → migrations → Terraform → sanity",
        "category": "feature",
        "tags": ["deploy", "ci-cd", "terraform", "semver", "automation"],
        "importance": 0.9,
        "project": "infra-ops",
    },
    {
        "content": (
            "Artifact Registry (europe-west1) stocke toutes les images Docker. "
            "Le nommage suit : europe-west1-docker.pkg.dev/{project_id}/{registry}/{service}:{version}. "
            "Les images inutilisées sont nettoyées automatiquement (retention policy 30 versions). "
            "La signature des images n'est pas encore activée (roadmap Q3 2026). "
            "Le scan de vulnérabilités Artifact Analysis tourne à chaque push."
        ),
        "summary": "Artifact Registry europe-west1 : nommage, retention 30 versions, vulnerability scan",
        "category": "feature",
        "tags": ["artifact-registry", "docker", "security", "vulnerability-scan", "gcp"],
        "importance": 0.7,
        "project": "infra-ops",
    },
    {
        "content": (
            "AlloyDB est configuré en mode HA (High Availability) avec une replica en europe-west1-b. "
            "Le failover automatique prend < 60s. "
            "Les connexions passent par le connecteur AlloyDB Python (Private IP uniquement). "
            "Le backup automatique est configuré à 2h du matin avec rétention 7 jours. "
            "Les extensions activées : pgvector, pg_trgm, uuid-ossp, pg_stat_statements."
        ),
        "summary": "AlloyDB HA : replica europe-west1-b, failover < 60s, backup 2h, extensions pgvector/trgm",
        "category": "feature",
        "tags": ["alloydb", "ha", "backup", "pgvector", "pg-trgm"],
        "importance": 0.8,
        "project": "infra-ops",
    },
    {
        "content": (
            "Le VPC est configuré avec des sous-réseaux privés pour Cloud Run et AlloyDB. "
            "Le Cloud Run peut accéder à AlloyDB via Private Service Connect (PSC). "
            "Aucun service n'a d'IP publique directe — tout passe par le Load Balancer. "
            "Les règles de firewall n'autorisent que les ports 443 (LB) et 5432 (AlloyDB interne). "
            "VPC Flow Logs est activé pour l'audit de trafic."
        ),
        "summary": "VPC privé : PSC pour AlloyDB, pas d'IP publique, firewall 443+5432, VPC Flow Logs",
        "category": "decision",
        "tags": ["vpc", "network", "security", "psc", "firewall"],
        "importance": 0.75,
        "project": "infra-ops",
    },
    # ── Projet data-platform ──────────────────────────────────────────────
    {
        "content": (
            "Le pipeline d'ingestion CV passe par 4 états : PENDING → QUEUED → PROCESSING → IMPORTED. "
            "Un webhook Drive notifie drive_api à chaque nouveau fichier. "
            "Le service Cloud Scheduler relance la sync toutes les heures comme fallback. "
            "Les CVs mal formés (> 20 Mo, format non supporté) passent en FAILED avec log détaillé. "
            "L'idempotence est assurée par hash SHA256 du contenu du fichier Drive."
        ),
        "summary": "Pipeline CV : PENDING→QUEUED→PROCESSING→IMPORTED, idempotence SHA256, webhook Drive",
        "category": "feature",
        "tags": ["pipeline", "cv", "drive", "state-machine", "idempotent"],
        "importance": 0.85,
        "project": "data-platform",
    },
    {
        "content": (
            "La taxonomie des compétences Zenika est organisée en 6 piliers principaux : "
            "Cloud & DevOps, Data & AI, Software Engineering, Cybersecurity, "
            "Agile & Management, Architecture. "
            "Chaque pilier contient des domaines (niveau 2) et des compétences feuilles (niveau 3). "
            "L'arbre est recalculé automatiquement après chaque ingestion batch de CVs "
            "pour intégrer les nouvelles compétences détectées par Gemini."
        ),
        "summary": "Taxonomie Zenika : 6 piliers, 3 niveaux, recalcul post-ingestion via Gemini",
        "category": "discovery",
        "tags": ["taxonomy", "competencies", "gemini", "nlp", "knowledge-graph"],
        "importance": 0.9,
        "project": "data-platform",
    },
    {
        "content": (
            "Gemini extrait les compétences des CVs via extraction structurée (JSON mode). "
            "Le prompt inclut le contenu textuel du CV + le contexte de l'arbre taxonomique existant. "
            "La déduplication floue (SequenceMatcher + containment word-boundary) "
            "empêche la création de doublons (ex: 'GKE' et 'Google Kubernetes Engine'). "
            "Les nouvelles compétences non reconnues sont soumises comme 'suggestions' pour review admin."
        ),
        "summary": "Extraction compétences : Gemini JSON mode + dédup floue + suggestions admin",
        "category": "feature",
        "tags": ["gemini", "extraction", "nlp", "deduplication", "suggestions"],
        "importance": 0.9,
        "project": "data-platform",
    },
    {
        "content": (
            "Le scoring ACT-R des compétences utilise Vertex AI pour évaluer "
            "le niveau de maîtrise (0-5) de chaque consultant sur chaque compétence. "
            "Le prompt fournit : (1) les missions du consultant, (2) la compétence évaluée, "
            "(3) une grille d'évaluation par niveau. "
            "Le score est arrondi au demi-point le plus proche et stocké dans ai_score. "
            "La justification (max 500 chars) explique le score attribué."
        ),
        "summary": "Scoring compétences : Vertex AI, prompt missions+grille, score 0-5 demi-point, justification",
        "category": "feature",
        "tags": ["scoring", "vertex-ai", "competencies", "evaluation", "justification"],
        "importance": 0.85,
        "project": "data-platform",
    },
    {
        "content": (
            "Les missions sont analysées par Gemini via missions_api pour extraire : "
            "technologies, rôles, durée, budget, niveau d'expérience requis. "
            "Le document RFP (PDF/DOCX) est converti en texte via document AI ou textract. "
            "L'extraction retourne un JSON structuré avec champs obligatoires validés par Pydantic. "
            "Les compétences extraites des missions alimentent aussi la taxonomie (suggestions)."
        ),
        "summary": "Analyse missions : Gemini extraction RFP, document AI, JSON Pydantic, feed taxonomie",
        "category": "feature",
        "tags": ["missions", "gemini", "extraction", "pydantic", "document-ai"],
        "importance": 0.8,
        "project": "data-platform",
    },
    {
        "content": (
            "Le golden dataset RAG contient 8 requêtes de référence avec leurs top-10 consultants attendus. "
            "La calibration recalcule ces top-10 en live et compare avec les résultats précédents. "
            "Un delta > 3 consultants sur une requête déclenche une alerte (dérive RAG). "
            "Le snapshot est poussé en BigQuery pour tracking historique de la qualité RAG. "
            "La précision@10 moyenne est l'indicateur clé (objectif : > 0.80)."
        ),
        "summary": "Golden dataset RAG : 8 requêtes, précision@10 > 0.80, dérive alertée, BigQuery tracking",
        "category": "feature",
        "tags": ["rag", "golden-dataset", "precision", "drift", "bigquery"],
        "importance": 0.8,
        "project": "data-platform",
    },
    # ── Projet client-portail-rh ──────────────────────────────────────────
    {
        "content": (
            "Le portail RH Vue.js permet aux managers de créer des missions, "
            "consulter les propositions d'équipes de l'IA, et valider/rejeter les staffings. "
            "L'interface affiche un profil consultant avec : photo, compétences scorées (radar chart), "
            "historique missions, disponibilité, et score de pertinence pour la mission courante. "
            "Les notifications en temps réel utilisent WebSocket pour alerter des nouvelles propositions."
        ),
        "summary": "Portail RH Vue.js : missions, propositions IA, profil consultant, radar chart, WebSocket",
        "category": "feature",
        "tags": ["frontend", "vue", "ux", "websocket", "radar-chart"],
        "importance": 0.8,
        "project": "client-portail-rh",
    },
    {
        "content": (
            "L'accessibilité WCAG 2.1 niveau AA est requise pour le portail RH. "
            "Les contrastes de couleur respectent le ratio 4.5:1 (texte normal) et 3:1 (grand texte). "
            "Tous les composants interactifs ont des attributs aria-label. "
            "La navigation clavier est complète (Tab, Enter, Escape). "
            "Les tests d'accessibilité automatiques utilisent axe-core dans la CI."
        ),
        "summary": "Accessibilité WCAG 2.1 AA : contraste 4.5:1, aria-label, navigation clavier, axe-core CI",
        "category": "decision",
        "tags": ["wcag", "accessibility", "a11y", "aria", "frontend"],
        "importance": 0.7,
        "project": "client-portail-rh",
    },
    {
        "content": (
            "Les performances du portail sont optimisées via : "
            "lazy loading des composants Vue (defineAsyncComponent), "
            "pagination côté serveur (skip/limit), "
            "skeleton screens pendant les chargements, "
            "debounce 300ms sur les champs de recherche, "
            "et virtualisation des listes longues (vue-virtual-scroller). "
            "Le LCP (Largest Contentful Paint) cible < 2.5s sur connexion 4G."
        ),
        "summary": "Perf portail : lazy loading, pagination serveur, skeleton, debounce 300ms, LCP < 2.5s",
        "category": "feature",
        "tags": ["performance", "vue", "lcp", "lazy-loading", "ux"],
        "importance": 0.75,
        "project": "client-portail-rh",
    },
    {
        "content": (
            "L'authentification du portail utilise OAuth2 PKCE avec Google comme provider. "
            "Le JWT est stocké en mémoire (pas localStorage) pour éviter les attaques XSS. "
            "Le refresh token est en httpOnly cookie avec SameSite=Strict. "
            "La déconnexion révoque le token côté serveur (users_api /auth/logout). "
            "La durée de session est 8h avec refresh automatique toutes les 55 min."
        ),
        "summary": "Auth portail : OAuth2 PKCE Google, JWT en mémoire, httpOnly cookie, session 8h",
        "category": "feature",
        "tags": ["oauth2", "pkce", "security", "jwt", "session"],
        "importance": 0.85,
        "project": "client-portail-rh",
    },
    {
        "content": (
            "L'export des propositions d'équipes se fait en PDF via jsPDF côté client. "
            "Le PDF inclut : résumé de la mission, profils consultants (photo + compétences top-5), "
            "score de pertinence global, planning de disponibilité. "
            "La génération prend < 3s pour une équipe de 5 personnes. "
            "Le nom de fichier suit le pattern : Proposition_{mission_id}_{date}.pdf."
        ),
        "summary": "Export PDF équipe : jsPDF, profils + scores + planning, < 3s pour 5 personnes",
        "category": "feature",
        "tags": ["pdf", "export", "jspdf", "frontend", "reporting"],
        "importance": 0.65,
        "project": "client-portail-rh",
    },
    # ── MCP-Claude-mem-local (suite) ──────────────────────────────────────
    {
        "content": (
            "La table user_prompts stocke l'historique des prompts utilisateur "
            "avec embedding vectoriel pour la recherche de contexte similaire. "
            "Le prompt_number est incrémental par session. "
            "La corrélation entre prompts et mémoires créées permet d'analyser "
            "quels types de tâches génèrent le plus de connaissances persistantes. "
            "Retention des prompts : 90 jours (RGPD)."
        ),
        "summary": "user_prompts : historique + embeddings, corrélation tâches/mémoires, retention 90j RGPD",
        "category": "feature",
        "tags": ["prompts", "history", "embeddings", "rgpd", "analytics"],
        "importance": 0.65,
        "project": "MCP-Claude-mem-local",
    },
    {
        "content": (
            "La visibilité des mémoires ('personal', 'team', 'organization') permet la collaboration. "
            "Les mémoires 'team' sont partagées entre les membres du même team_id. "
            "Les mémoires 'organization' sont accessibles à tous les users de la base. "
            "La RLS PostgreSQL filtre automatiquement selon le user_id de la session. "
            "Cette feature est prévue pour Q2 2026 (actuellement toutes les mémoires sont 'personal')."
        ),
        "summary": "Visibilité mémoires : personal/team/organization, RLS PostgreSQL, roadmap Q2 2026",
        "category": "discovery",
        "tags": ["collaboration", "rls", "team", "roadmap", "visibility"],
        "importance": 0.6,
        "project": "MCP-Claude-mem-local",
    },
    {
        "content": (
            "Les métriques de santé de la base de mémoires incluent : "
            "activation moyenne (cible > 1.5), ratio mémoires actives/dormantes/forgotten, "
            "taux d'accès par catégorie, et distribution des importance_scores. "
            "Un score < 0.2 sur une mémoire importante (importance > 0.8) déclenche une recommandation "
            "de mise à jour. Le cycle d'oubli est planifié toutes les semaines via Cloud Scheduler."
        ),
        "summary": "Health mémoires : activation moyenne, ratio statuts, cycle d'oubli hebdomadaire",
        "category": "feature",
        "tags": ["health", "metrics", "actr", "scheduler", "maintenance"],
        "importance": 0.65,
        "project": "MCP-Claude-mem-local",
    },
]

# Fusionner les mémoires inline avec celles des fichiers JSON
# (les JSON sont prioritaires pour l'enrichissement, les inline sont la base)
DEMO_MEMORIES = _load_demo_memories() or DEMO_MEMORIES


def _get_iap_token_for_memory() -> str:
    """Génère un identity token IAP pour mcp-claude-memory (même pattern que gcp/cli.py).

    1. Lit l'audience (IAP Client ID) depuis Secret Manager google-secret-id
    2. Tente gcloud auth print-identity-token --audiences={audience}
    3. Fallback : impersonation SA sa-mcp-claude-memory-dev@{project_id}...
    Retourne le token ou chaîne vide en cas d'erreur.
    """
    try:
        # Résoudre la dernière version "enabled" (évite les versions DESTROYED)
        list_res = subprocess.run(
            [GCLOUD_BIN, "secrets", "versions", "list", "google-secret-id",
             f"--project={PROJECT_ID}", "--filter=state=enabled",
             "--format=value(name)", "--sort-by=~name"],
            capture_output=True, text=True, timeout=15,
        )
        enabled_versions = [v.strip() for v in list_res.stdout.strip().splitlines() if v.strip()]
        if not enabled_versions:
            logger.warning("  [iap] Aucune version enabled trouvée pour google-secret-id.")
            return ""
        # Prendre la version avec le numéro le plus élevé (première après --sort-by=~name)
        latest_enabled = enabled_versions[0]
        res = subprocess.run(
            [GCLOUD_BIN, "secrets", "versions", "access", latest_enabled,
             "--secret=google-secret-id", f"--project={PROJECT_ID}"],
            capture_output=True, text=True, timeout=15,
        )
        if res.returncode != 0 or not res.stdout.strip():
            logger.warning(
                f"  [iap] Impossible de lire google-secret-id@{latest_enabled} : "
                f"{res.stderr.strip()}"
            )
            return ""
        audience = res.stdout.strip()
        logger.info(f"  [iap] Audience IAP lue depuis google-secret-id@{latest_enabled}.")
    except Exception as exc:
        logger.warning(f"  [iap] Erreur lecture secret google-secret-id : {exc}")
        return ""

    # Tentative 1 : token natif (fonctionne si le compte actif est un SA)
    try:
        res = subprocess.run(
            [GCLOUD_BIN, "auth", "print-identity-token", f"--audiences={audience}"],
            capture_output=True, text=True, timeout=15,
        )
        if res.returncode == 0 and res.stdout.strip():
            logger.info("  [iap] ✓ Identity token IAP obtenu (natif).")
            return res.stdout.strip()

        # Tentative 2 : impersonation SA (pour les user accounts)
        sa_email = f"sa-mcp-claude-memory-dev@{PROJECT_ID}.iam.gserviceaccount.com"
        logger.info(f"  [iap] Fallback impersonation SA '{sa_email}'...")
        res_imp = subprocess.run(
            [GCLOUD_BIN, "auth", "print-identity-token",
             f"--impersonate-service-account={sa_email}",
             f"--audiences={audience}",
             "--include-email"],
            capture_output=True, text=True, timeout=15,
        )
        if res_imp.returncode == 0 and res_imp.stdout.strip():
            logger.info("  [iap] ✓ Identity token IAP obtenu via impersonation SA.")
            return res_imp.stdout.strip().splitlines()[-1]

        logger.warning(f"  [iap] Impersonation SA échouée : {res_imp.stderr.strip()}")
        return ""
    except Exception as exc:
        logger.warning(f"  [iap] Erreur génération identity token : {exc}")
        return ""


def seed_mcp_claude_memory() -> None:
    """Injecte les mémoires de démo dans mcp-claude-memory via le MCP tool store_memory.

    Idempotent : vérifie le nombre de mémoires existantes avant d'injecter.
    Skip si déjà >= 20 mémoires (signe que la seed a déjà été faite).
    Auth : IAP identity token uniquement (pas de X-API-Key séparée).
    """
    iap_token = _get_iap_token_for_memory()
    if not iap_token:
        logger.warning("  [memory] Token IAP indisponible — seed mcp-claude-memory ignoré.")
        return

    headers = {
        "Authorization": f"Bearer {iap_token}",
        "Content-Type": "application/json",
    }

    # Vérification idempotente : compte les mémoires existantes
    try:
        with httpx.Client(timeout=15.0) as client:
            stats_res = client.get(f"{MCP_MEMORY_URL}/api/stats", headers=headers)
        if stats_res.status_code == 200:
            existing_count = stats_res.json().get("total_memories", 0)
            if existing_count >= 20:
                logger.info(
                    f"  [memory] Déjà {existing_count} mémoires en base — seed ignoré (idempotent)."
                )
                return
            logger.info(
                f"  [memory] {existing_count} mémoires existantes"
                f" — injection de {len(DEMO_MEMORIES)} mémoires..."
            )
        else:
            logger.warning(f"  [memory] /api/stats HTTP {stats_res.status_code} — tentative d'injection quand même.")
    except Exception as exc:
        logger.warning(f"  [memory] Impossible de vérifier les stats : {exc} — tentative d'injection quand même.")

    # Injection séquentielle avec throttle anti-429
    # Le rate limit de mcp-claude-memory est ~10 req/s → on vise ~5 req/s (200ms entre chaque)
    success_count = 0
    error_count = 0
    DELAY_BETWEEN_REQUESTS = 0.2   # 200ms = ~5 req/s, bien en dessous du rate limit
    MAX_RETRIES_429 = 3

    for i, mem in enumerate(DEMO_MEMORIES, 1):
        retries = 0
        injected = False
        while retries <= MAX_RETRIES_429:
            try:
                with httpx.Client(timeout=30.0) as client:
                    res = client.post(
                        f"{MCP_MEMORY_URL}/mcp/call",
                        headers=headers,
                        json={"name": "store_memory", "arguments": mem},
                    )
                if res.status_code == 429:
                    wait = (2 ** retries) * 1.0  # 1s, 2s, 4s
                    retries += 1
                    if retries <= MAX_RETRIES_429:
                        time.sleep(wait)
                        continue
                    else:
                        error_count += 1
                        logger.warning(
                            f"  [memory] [{i}/{len(DEMO_MEMORIES)}] "
                            f"429 persistant après {MAX_RETRIES_429} retries — skip."
                        )
                        break
                elif res.status_code == 200:
                    result_text = res.json().get("result", [{}])
                    if result_text and isinstance(result_text, list):
                        text = result_text[0].get("text", "")
                    else:
                        text = str(result_text)
                    if "Memoire stockee" in text or "ID:" in text:
                        success_count += 1
                        injected = True
                        if i % 50 == 0 or i == len(DEMO_MEMORIES):
                            logger.info(
                                f"  [memory] [{i}/{len(DEMO_MEMORIES)}] "
                                f"{success_count} injectées, {error_count} erreurs..."
                            )
                    else:
                        error_count += 1
                        logger.warning(
                            f"  [memory] [{i}/{len(DEMO_MEMORIES)}] "
                            f"Réponse inattendue : {text[:100]}"
                        )
                    break
                else:
                    error_count += 1
                    logger.warning(
                        f"  [memory] [{i}/{len(DEMO_MEMORIES)}] "
                        f"HTTP {res.status_code} : {res.text[:100]}"
                    )
                    break
            except Exception as exc:
                error_count += 1
                logger.warning(f"  [memory] [{i}/{len(DEMO_MEMORIES)}] Erreur : {exc}")
                break

        if not injected or retries > 0:
            pass  # already logged above
        time.sleep(DELAY_BETWEEN_REQUESTS)

    logger.info(
        f"  [memory] Seed terminé — {success_count}/{len(DEMO_MEMORIES)} mémoires injectées"
        f", {error_count} erreurs."
    )


if __name__ == "__main__":
    main()
