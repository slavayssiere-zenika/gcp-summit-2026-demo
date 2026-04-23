import os
import json
import time
import httpx
import google.auth
from google.auth.transport.requests import Request
import base64
import subprocess
import string
import random

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
        print("  -> Mot de passe admin lu depuis .antigravity_env")
        return os.environ["ADMIN_PASSWORD"]

    # Fallback : Secret Manager via ADC
    print("Fetching admin password from Secret Manager...")
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())

    url = f"https://secretmanager.googleapis.com/v1/projects/{PROJECT_ID}/secrets/admin-password-dev/versions/latest:access"
    response = httpx.get(
        url,
        headers={"Authorization": f"Bearer {credentials.token}"}
    )
    if response.status_code != 200:
        raise Exception(f"Failed to fetch secret: {response.text}")

    payload = response.json()["payload"]["data"]
    return base64.b64decode(payload).decode('utf-8')

def authenticate(password):
    print("Authenticating to users-api...")
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
    print("Ensuring sebastien.lavayssiere@zenika.com is admin...")
    with httpx.Client(base_url=DEV_API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=10.0) as client:
        # Check if user exists
        res = client.get("/api/users/search?query=sebastien.lavayssiere&limit=1")
        if res.status_code == 200 and res.json().get("total", 0) > 0:
            print("  -> sebastien.lavayssiere@zenika.com already exists.")
            return

        print("  -> Creating sebastien.lavayssiere@zenika.com as admin...")
        pwd = ''.join(random.choice(string.ascii_letters) for _ in range(16))
        payload = {
            "username": "slavayssiere",
            "email": "sebastien.lavayssiere@zenika.com",
            "first_name": "Sébastien",
            "last_name": "Lavayssière",
            "full_name": "Sébastien Lavayssière",
            "role": "admin",
            "password": pwd,
            "allowed_category_ids": [1,2,3,4,5],
            "is_active": True
        }
        res = client.post("/api/users/", json=payload)
        if res.status_code == 201:
            print("  -> Created successfully.")
        else:
            print(f"  -> Failed to create user: {res.text}")


def setup_drive_scanner(token, progress):
    with httpx.Client(base_url=DEV_API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=20.0) as client:
        print("Fetching currently tracked Drive folders...")
        res = client.get("/api/drive/folders")
        existing_folders = []
        if res.status_code == 200:
            existing_folders = res.json()
        
        # Clean up old root folder to avoid duplicate scanning
        for f in existing_folders:
            if f.get("folder_name") == "Fake Agencies" or f.get("tag") == "GCP Summit":
                print(f"  -> Deleting old root folder '{f.get('folder_name')}' from scanner...")
                client.delete(f"/api/drive/folders/{f.get('id')}")

        # Register each agency
        for agency_name in ["Saumur", "Sèvres", "Bizanos", "Paris"]:
            if agency_name not in progress:
                print(f"  -> Warning: {agency_name} not found in progress.json")
                continue
            
            folder_id = progress[agency_name].get("folder_id")
            if not folder_id:
                print(f"  -> No folder_id found for {agency_name}")
                continue
                
            # Check if already tracked
            if any(f.get("google_folder_id") == folder_id for f in existing_folders):
                print(f"  -> Folder '{agency_name}' is already tracked.")
                continue
                
            print(f"  -> Adding '{agency_name}' to Drive scanner...")
            res = client.post("/api/drive/folders", json={
                "google_folder_id": folder_id,
                "tag": agency_name,
                "folder_name": agency_name
            })
            if res.status_code == 200:
                print(f"  -> '{agency_name}' added successfully.")
            else:
                print(f"  -> Failed to add '{agency_name}': {res.text}")
        return True

def trigger_drive_sync():
    print("Triggering Drive sync via Cloud Scheduler...")
    res = subprocess.run([
        GCLOUD_BIN, "scheduler", "jobs", "run", "drive-sync-trigger-dev",
        "--location=europe-west1", "--project", PROJECT_ID
    ], capture_output=True, text=True)
    if res.returncode == 0:
        print("  -> Sync triggered.")
    else:
        print(f"  -> Failed to trigger sync: {res.stderr}")
        raise Exception(f"gcloud scheduler trigger failed: {res.stderr}")


def check_platform_health():
    """Vérifie que les services critiques sont up avant de lancer le workflow."""
    print("\n0. Vérification de la santé de la plateforme...")
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
            print(f"  {status} {name}: HTTP {r.status_code}")
            if r.status_code != 200:
                all_healthy = False
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            all_healthy = False
    if not all_healthy:
        raise Exception("Un ou plusieurs services sont unhealthy. Annulation du workflow.")
    print("  -> Tous les services sont opérationnels.")

def wait_for_drive_ingestion(token):
    print("Waiting for Drive ingestion to complete...")
    with httpx.Client(base_url=DEV_API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=10.0) as client:
        while True:
            res = client.get("/api/drive/status")
            if res.status_code == 200:
                data = res.json()
                pending = data.get("pending", 0)
                processing = data.get("processing", 0)
                queued = data.get("queued", 0)
                
                print(f"  -> Status: Pending={pending}, Queued={queued}, Processing={processing}, Imported={data.get('imported', 0)}")
                
                if pending == 0 and processing == 0 and queued == 0:
                    print("  -> Ingestion complete!")
                    break
            else:
                print(f"  -> Failed to check status: {res.text}")
            time.sleep(10)

def wait_for_missions_ingestion(token):
    print("Waiting for Missions ingestion to complete...")
    with httpx.Client(base_url=DEV_API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=10.0) as client:
        while True:
            res = client.get("/api/missions/missions")
            if res.status_code == 200:
                missions = res.json()
                in_progress = [m for m in missions if m.get("status") == "ANALYSIS_IN_PROGRESS"]
                
                print(f"  -> Status: {len(in_progress)} missions still in ANALYSIS_IN_PROGRESS...")
                
                if len(in_progress) == 0:
                    print("  -> Missions ingestion complete!")
                    break
            else:
                print(f"  -> Failed to check missions: {res.text}")
            time.sleep(10)

def main():
    print("=== GCP Summit Data Generation Workflow ===")
    print(f"   API URL : {DEV_API_URL}")
    print(f"   gcloud  : {GCLOUD_BIN}")

    check_platform_health()

    print("\n1. Running generate_fake_agencies.py...")
    subprocess.run(["python3", "scripts/generate_fake_agencies.py"], check=True)

    if not os.path.exists(PROGRESS_FILE):
        raise Exception("Error: progress.json not found. generate_fake_agencies failed?")

    with open(PROGRESS_FILE, "r") as f:
        progress = json.load(f)

    root_folder_id = progress.get("root_folder_id")
    if not root_folder_id:
        raise Exception("Error: root_folder_id not found in progress.json.")

    print(f"\n2. Found root folder ID: {root_folder_id}")

    admin_password = get_admin_password()
    token = authenticate(admin_password)

    print("\n3. Adding Sebastien as admin...")
    ensure_sebastien_admin(token)

    print("\n4. Registering folders with Drive Scanner...")
    if setup_drive_scanner(token, progress):
        print("\n5. Triggering Drive Sync...")
        trigger_drive_sync()

        print("\n6. Polling Drive Ingestion...")
        wait_for_drive_ingestion(token)

    print("\n7. Generating fake missions...")
    subprocess.run(["python3", "scripts/generate_fake_missions.py"], check=True)

    print("\n8. Polling Missions Ingestion...")
    wait_for_missions_ingestion(token)

    print("\n=== Workflow Completed Successfully ===")
    print(f"   Données générées sur : {DEV_API_URL}")
    print("   Prochaine étape : /analyse-prompt pour valider les agents")


if __name__ == "__main__":
    main()
