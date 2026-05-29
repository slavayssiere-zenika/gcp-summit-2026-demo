import os
import base64
import subprocess
import httpx
import google.auth
from google.auth.transport.requests import Request
from logger_config import logger

PROJECT_ID = "slavayssiere-sandbox-462015"
DEV_API_URL = os.getenv("DEV_API_URL", "https://api.dev.zenika.slavayssiere.fr")

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
    if os.getenv("ADMIN_PASSWORD"):
        logger.info("  -> Mot de passe admin lu depuis .antigravity_env")
        return os.environ["ADMIN_PASSWORD"]

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


def purge_drive_folders(client):
    logger.info("\n1. Purging Tracked Drive Folders...")
    try:
        res = client.get("/api/drive/folders")
        if res.status_code == 200:
            res_json = res.json()
            existing_folders = res_json.get("items", []) if isinstance(res_json, dict) else res_json
            for f in existing_folders:
                folder_id = f.get("id")
                folder_name = f.get("folder_name", "Unknown")
                logger.info(f"  -> Deleting tracked folder '{folder_name}' (ID: {folder_id})...")
                del_res = client.delete(f"/api/drive/folders/{folder_id}")
                logger.info(f"     * Deleted: HTTP {del_res.status_code}")
        else:
            logger.error(f"  -> Failed to list drive folders: {res.text}")
    except Exception as e:
        logger.error(f"  -> Error purging drive folders: {e}")


def purge_non_admin_users(client):
    logger.info("\n2. Purging Non-Admin Users and their competencies/items...")
    skip = 0
    limit = 100
    all_users = []

    while True:
        res = client.get(f"/api/users/?skip={skip}&limit={limit}")
        if res.status_code != 200:
            logger.error(f"  -> Failed to fetch users: {res.text}")
            break
        data = res.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        all_users.extend(items)
        if len(items) < limit:
            break
        skip += limit

    non_admins = [u for u in all_users if u.get("role") != "admin"]
    logger.info(f"  -> Found {len(non_admins)} non-admin users to purge.")

    for u in non_admins:
        user_id = u["id"]
        email = u.get("email", f"ID {user_id}")
        logger.info(f"  -> Purging user: {email} (ID: {user_id})...")

        try:
            eval_res = client.delete(f"/api/competencies/user/{user_id}/evaluations")
            logger.info(f"     * Competency evaluations cleared: HTTP {eval_res.status_code}")
        except Exception as e:
            logger.warning(f"     * Failed to clear competency evaluations: {e}")

        try:
            comp_res = client.delete(f"/api/competencies/user/{user_id}/clear")
            logger.info(f"     * Competencies cleared: HTTP {comp_res.status_code}")
        except Exception as e:
            logger.warning(f"     * Failed to clear competencies: {e}")

        try:
            items_res = client.delete(f"/api/items/user/{user_id}/items")
            logger.info(f"     * Items cleared: HTTP {items_res.status_code}")
        except Exception as e:
            logger.warning(f"     * Failed to clear items: {e}")

        try:
            user_del = client.delete(f"/api/users/{user_id}")
            logger.info(f"     * User deleted: HTTP {user_del.status_code}")
        except Exception as e:
            logger.error(f"     * Failed to delete user {user_id}: {e}")


def purge_missions(client):
    logger.info("\n3. Purging All Missions...")
    try:
        res = client.delete("/api/missions/missions")
        logger.info(f"  -> Purge missions result: HTTP {res.status_code} - {res.text}")
    except Exception as e:
        logger.error(f"  -> Error purging missions: {e}")


def purge_suggestions(client):
    logger.info("\n2b. Purging Competency Suggestions...")
    try:
        res = client.delete("/api/competencies/suggestions")
        logger.info(f"  -> Purge suggestions result: HTTP {res.status_code}")
    except Exception as e:
        logger.error(f"  -> Error purging competency suggestions: {e}")


def purge_cvs(client):
    logger.info("\n4. Purging CV Profiles and Embeddings...")
    try:
        res = client.delete("/api/cv/admin/purge-data")
        logger.info(f"  -> Purge CVs result: HTTP {res.status_code} - {res.text}")
    except Exception as e:
        logger.error(f"  -> Error purging CV profiles: {e}")


def main():
    logger.info("=== Zenika Platform Reset & Reprocessing Pipeline ===")
    logger.info(f"   API URL : {DEV_API_URL}")

    admin_password = get_admin_password()
    token = authenticate(admin_password)

    # Clean the environment
    with httpx.Client(base_url=DEV_API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=60.0) as client:
        # A. Tracked Drive Folders
        purge_drive_folders(client)

        # B. Non-admin users and their data (competencies & items)
        purge_non_admin_users(client)

        # B2. Competency suggestions
        purge_suggestions(client)

        # C. Missions
        purge_missions(client)

        # D. CV Profiles & Embeddings
        purge_cvs(client)

    logger.info("\n=== Database Purged Successfully! ===")

    # B. Trigger the generation of fake agencies CV files in Google Drive
    logger.info("\n5. Running generate_fake_agencies.py...")
    subprocess.run(["python3", "scripts/generate_fake_agencies.py"], check=True)

    # C. Trigger the ingestion pipeline (GCP Summit data workflow)
    logger.info("\n6. Running generate_gcp_summit_data.py to reprocess all...")
    subprocess.run(["python3", "scripts/generate_gcp_summit_data.py"], check=True)

    logger.info("\n=== All Reprocessing Operations Completed Successfully! ===")


if __name__ == "__main__":
    main()
