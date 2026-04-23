import os
import json
import time
import httpx
import google.auth
from google.auth.transport.requests import Request
import base64
from google import genai

# ─────────────────────────────────────────────────────────────────────────────
# Configuration — lue depuis .env puis .antigravity_env
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ID = "slavayssiere-sandbox-462015"
DEV_API_URL = os.getenv("DEV_API_URL", "https://api.dev.zenika.slavayssiere.fr")


def _load_env_file(path):
    """Charge les variables KEY=VALUE d'un fichier dans os.environ (sans écraser)."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


# Priorité 1 : .env à la racine (contient GOOGLE_API_KEY)
_load_env_file(os.path.join(os.path.dirname(__file__), "..", ".env"))
# Priorité 2 : .antigravity_env (contient ADMIN_PASSWORD, GCLOUD_BIN)
_load_env_file(os.path.join(os.path.dirname(__file__), "..", ".antigravity_env"))

# Base mission topics
MISSION_TOPICS = [
    "Migration massive de AWS vers GCP",
    "Développement Cloud Native sur GCP",
    "Accompagnement et Coaching Agile",
    "Création d'une Landing Zone GCP",
    "Refonte d'Application et Dev sur GCP",
    "Développement Mobile Flutter et Backend GCP",
    "Audit Green IT et Optimisation GCP",
    "Déploiement d'un Data Lakehouse sur GCP",
    "Migration On-Premise vers Cloud Hybride",
    "Transformation Agile et DevSecOps",
    "Application Interne Zenika - Portail Consultants",
    "Intégration Vertex AI dans un CRM",
    "Refonte Front-end React et Hébergement GCP",
    "Sécurisation des pipelines CI/CD Cloud",
    "Développement d'une app Mobile e-Santé",
    "Coach Agile pour équipe Data",
    "Audit d'Architecture Cloud AWS",
    "Modernisation Java Spring Boot sur Kubernetes",
    "Dashboarding et Data Visualisation sur GCP",
    "Stratégie Numérique Responsable (Green IT)"
]

def get_admin_password():
    """Lit le mot de passe admin depuis .antigravity_env ou Secret Manager en fallback."""
    if os.getenv("ADMIN_PASSWORD"):
        print("  -> Mot de passe admin lu depuis .antigravity_env")
        return os.environ["ADMIN_PASSWORD"]

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

def clear_existing_missions(token):
    print("Clearing existing missions in the database...")
    with httpx.Client(base_url=DEV_API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=20.0) as client:
        res = client.delete("/api/missions/missions")
        if res.status_code in [200, 204]:
            print("  -> Missions cleared successfully.")
        elif res.status_code == 404:
            print("  -> DELETE endpoint not found. Make sure to deploy missions_api first.")
        else:
            print(f"  -> Failed to clear missions: {res.text}")

def generate_missions(token):
    clear_existing_missions(token)

    print(f"Generating fake missions with LLM (2-4 pages per mission)...")
    # Utilise la GOOGLE_API_KEY depuis .env (Gemini AI Studio)
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise Exception(
            "GOOGLE_API_KEY manquante. Ajoute-la dans .env : GOOGLE_API_KEY=<ta_clé>"
        )
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    client = genai.Client(api_key=api_key)
    
    prompt_template = """Tu es un directeur de projet de haut niveau. Rédige un appel d'offre (Request For Proposal) extrêment complet et détaillé (environ 2 à 4 pages) pour la mission : "{topic}".
    
Inclus obligatoirement les sections suivantes :
1. Contexte de l'entreprise (invente une grande entreprise cliente fictive pertinente, son marché, ses défis).
2. L'existant technique (architecture legacy, problèmes actuels).
3. Les enjeux technologiques, de sécurité et d'organisation.
4. L'architecture cible sur Google Cloud Platform (GCP) détaillée (services utilisés, flux de données).
5. Les profils recherchés (Architectes, Data Engineers, DevOps, etc.) et le niveau d'expertise attendu.
6. Les livrables attendus et le planning global.

Le document doit être structuré, professionnel et très exhaustif."""

    with httpx.Client(base_url=DEV_API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=60.0) as http_client:
        for i, topic in enumerate(MISSION_TOPICS, 1):
            print(f"[{i}/{len(MISSION_TOPICS)}] Generating RFP for: {topic}")
            
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt_template.format(topic=topic)
                )
                long_description = response.text
                
                print(f"  -> Generated {len(long_description)} characters. Submitting to API...")
                
                api_response = http_client.post(
                    "/api/missions/missions",
                    data={
                        "title": f"Appel d'offre : {topic}",
                        "description": long_description
                    }
                )
                
                if api_response.status_code == 202:
                    task_id = api_response.json().get("task_id")
                    print(f"  -> Accepted (Task ID: {task_id}). Waiting for Gemini backend processing...")
                    time.sleep(5)  # Let the backend process it
                else:
                    print(f"  -> API Error: {api_response.status_code} - {api_response.text}")
            except Exception as e:
                print(f"  -> Generation failed for '{topic}': {e}")
                
if __name__ == "__main__":
    try:
        admin_password = get_admin_password()
        token = authenticate(admin_password)
        generate_missions(token)
        print("✅ Finished generating long-form fake missions.")
    except Exception as e:
        print(f"❌ Script failed: {e}")
