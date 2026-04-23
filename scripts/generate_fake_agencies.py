import json
import os
import random
import time
import shutil

import google.auth
from faker import Faker
from google import genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from logger_config import logger

# Configurations
AGENCIES = ["Sèvres", "Saumur", "Bizanos", "Paris"]
ROLES = [
    "Développeur Fullstack React/Node",
    "Ingénieur Data GCP",
    "Architecte Cloud AWS",
    "Coach Agile",
    "Développeur Java Spring",
    "Ingénieur DevSecOps",
    "Développeur Mobile Flutter",
    "Consultant Green IT"
]

LOCAL_PROFILES_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "fake_profiles")
os.makedirs(LOCAL_PROFILES_DIR, exist_ok=True)

PROGRESS_FILE = os.path.join(LOCAL_PROFILES_DIR, "progress.json")

fake = Faker('fr_FR')


def get_drive_service():
    logger.info("Authentification Google Drive...")
    # drive scope (not drive.file) is required to delete folders that may
    # contain files created by a different app session.
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])
    service = build("drive", "v3", credentials=credentials)
    return service


def get_or_create_folder(service, folder_name, parent_id=None):
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])

    if items:
        return items[0]['id']
    else:
        metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            metadata['parents'] = [parent_id]

        folder = service.files().create(body=metadata, fields='id').execute()
        return folder.get('id')


def _delete_file_recursive(service, file_id: str):
    """Recursively delete all children of a Drive file/folder, then delete it."""
    # List children (works for folders)
    page_token = None
    while True:
        response = service.files().list(
            q=f"'{file_id}' in parents and trashed=false",
            spaces='drive',
            fields='nextPageToken, files(id, mimeType)',
            pageToken=page_token
        ).execute()
        for child in response.get('files', []):
            _delete_file_recursive(service, child['id'])
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    try:
        service.files().delete(fileId=file_id).execute()
    except Exception as e:
        logger.error(f"      -> Erreur suppression fichier {file_id}: {e}")


def delete_folder(service, folder_name):
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    for item in items:
        try:
            _delete_file_recursive(service, item['id'])
            logger.info(f"Dossier Drive '{folder_name}' supprimé.")
        except Exception as e:
            logger.error(f"Erreur suppression Drive: {e}")


def generate_profile_text(client: genai.Client, name: str, role: str, experience_years: int, agency: str) -> str:
    """Generate a CV text. Always returns a non-None string."""
    prompt = f"""
Tu es un recruteur expert. Je te demande de générer un Curriculum Vitae au format texte clair et lisible.
Ne fais AUCUNE phrase d'introduction de type "Absolument ! Voici un Curriculum Vitae...". Renvoie directement le CV.

Le consultant s'appelle {name}.
Son rôle est {role} et il a {experience_years} ans d'expérience.
Il est rattaché à l'agence de {agency} et habite dans cette ville.

Le CV doit impérativement contenir:
- Une phrase de présentation ou résumé.
- Ses compétences techniques et métiers détaillées. Assure-toi d'inclure une grande diversité de technologies sur l'ensemble du profil (Java, Node.js, TypeScript, Data Engineering, Agilité, etc.), MAIS la compétence centrale et le fil conducteur du CV DOIT ÊTRE GCP (Google Cloud Platform, Vertex AI, AgentSpace). Les mentions à GCP doivent être les plus visibles et les plus développées.
  Pense aussi à ajouter quelques compétences liées au contexte de l'entreprise "Zenika".
- 3 expériences professionnelles (missions) expliquées avec le contexte technique et métier, en respectant STRICTEMENT ces règles :
  1. Chaque mission doit avoir une DATE DE DÉBUT et une DATE DE FIN (ex: "Janvier 2021 - Mars 2023").
  2. Chaque mission doit IMPÉRATIVEMENT préciser la DURÉE EXPLICITE en toutes lettres (ex: "Durée : 24 mois" ou "Durée : 2 ans").
  3. Varie les TYPES DE MISSIONS : inclut au moins une mission d'"Audit / Conseil", une mission d'"Accompagnement / Formation" ou d'"Expertise", en plus des missions de "Développement / Build". Utilise ces mots-clés dans les titres.
  4. Pour CHAQUE mission, liste précisément l'environnement technique ou les compétences spécifiquement utilisées pendant cette mission.
- Sa formation ou scolarité (invente si nécessaire).

Structure le tout avec des retours à la ligne propres, et un titre. Fais en sorte que ça semble naturel, professionnel.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        # response.text can be None if content is filtered or empty
        text = response.text
        if text:
            return text
        logger.warning(f"      -> Avertissement: réponse vide de Gemini, utilisation du template par défaut.")
    except Exception as e:
        logger.warning(f"      -> Erreur avec Gemini, utilisation d'un template par défaut: {e}")

    # Fallback template — always a valid string
    return (
        f"# CV de {name}\n\n"
        f"**Rôle** : {role}\n"
        f"**Agence** : {agency}\n"
        f"**Expérience** : {experience_years} ans\n\n"
        "## Résumé\n"
        f"Consultant expérimenté en {role}, spécialisé sur GCP avec un focus sur l'audit et l'architecture cloud.\n\n"
        "## Compétences\n"
        "- Google Cloud Platform (GCP), Vertex AI, AgentSpace\n"
        "- Python, Java, Node.js, TypeScript\n"
        "- Data Engineering, Agilité\n\n"
        "## Expériences\n"
        "### Mission 1 : Audit d'Architecture Cloud sur GCP\n"
        "**Janvier 2022 - Décembre 2023** | **Durée : 24 mois**\n"
        "Réalisation d'un audit complet de l'infrastructure d'un client grand compte. Conseil et recommandations stratégiques.\n"
        "**Environnement technique** : Google Cloud Platform, Terraform, Kubernetes.\n\n"
        "### Mission 2 : Expert technique et Accompagnement Data\n"
        "**Janvier 2020 - Décembre 2021** | **Durée : 24 mois**\n"
        "Accompagnement et formation des équipes de développement sur la refonte du pipeline data.\n"
        "**Environnement technique** : BigQuery, Dataflow, Python.\n\n"
        "### Mission 3 : Développement d'application de gestion\n"
        "**Janvier 2018 - Décembre 2019** | **Durée : 24 mois**\n"
        "Mission de build et réalisation d'une application interne métier.\n"
        "**Environnement technique** : Java, Spring Boot, PostgreSQL.\n\n"
        "## Formation\n"
        "- Ingénieur informatique, Grande École d'Ingénieurs (fictif)\n"
    )


def get_gemini_api_key():
    secrets_path = os.path.join(os.path.dirname(__file__), "..", "secrets.sh")
    try:
        with open(secrets_path, "r") as f:
            for line in f:
                if line.startswith("export GOOGLE_API_KEY="):
                    return line.split("=")[1].strip()
    except Exception: raise
    return os.getenv("GEMINI_API_KEY")


def load_progress() -> dict:
    """Load the progress tracker. Returns a dict with agency data."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Avertissement: impossible de lire le fichier de progression ({e}). Repartons de zéro.")
    return {}


def save_progress(progress: dict):
    """Persist the progress tracker to disk."""
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def main():
    service = get_drive_service()

    try:
        api_key = get_gemini_api_key()
        genai_client = genai.Client(api_key=api_key) if api_key else genai.Client()
    except Exception as e:
        logger.error(f"Attention, initialisation GenAI échouée. Erreur: {e}")
        genai_client = None

    # --- Resume logic ---
    progress = load_progress()
    is_resume = bool(progress)

    if is_resume:
        logger.info(f"✔  Fichier de progression détecté — reprise en cours (sans suppression de l'historique).")
        root_folder_id = progress.get("root_folder_id")
        if not root_folder_id:
            logger.error("Erreur: root_folder_id manquant dans progress.json. Relancez sans le fichier.")
            return
    else:
        logger.info("Nettoyage de l'existant...")
        logger.info("- Suppression des anciens profils locaux...")
        if os.path.exists(LOCAL_PROFILES_DIR):
            shutil.rmtree(LOCAL_PROFILES_DIR)
        os.makedirs(LOCAL_PROFILES_DIR, exist_ok=True)

        logger.info("- Suppression de l'ancien dossier 'Fake Agencies' sur Google Drive...")
        delete_folder(service, "Fake Agencies")

        logger.info("\\nCréation du dossier racine 'Fake Agencies'...")
        root_folder_id = get_or_create_folder(service, "Fake Agencies")
        progress["root_folder_id"] = root_folder_id
        save_progress(progress)

    for agency in AGENCIES:
        agency_progress = progress.get(agency, {})

        # Consultants already done for this agency
        done_consultants: list = agency_progress.get("done", [])
        # Planned consultants list (fixed at first run so resume is consistent)
        planned: list = agency_progress.get("planned", [])
        agency_folder_id: str = agency_progress.get("folder_id", "")

        if not planned:
            # First time we visit this agency → plan the full list deterministically
            num_consultants = random.randint(10, 20)
            planned = []
            for _ in range(num_consultants):
                planned.append({
                    "first_name": fake.first_name(),
                    "last_name": fake.last_name(),
                    "experience_years": random.randint(2, 15),
                    "role": random.choice(ROLES),
                })
            agency_progress["planned"] = planned
            agency_progress["done"] = done_consultants
            progress[agency] = agency_progress
            save_progress(progress)

        num_consultants = len(planned)
        logger.info(f"\\n--- Agence : {agency} ---")

        if not agency_folder_id:
            agency_folder_id = get_or_create_folder(service, agency, root_folder_id)
            agency_progress["folder_id"] = agency_folder_id
            progress[agency] = agency_progress
            save_progress(progress)

        agency_local_dir = os.path.join(LOCAL_PROFILES_DIR, agency)
        os.makedirs(agency_local_dir, exist_ok=True)

        done_names = {f"{c['first_name']} {c['last_name']}" for c in done_consultants}
        
        # Copie du CV réel pour l'agence de Paris
        if agency == "Paris":
            user_cv_name = "Sébastien Lavayssière"
            if user_cv_name not in done_names:
                logger.info(f"  -> Copie du CV réel de Sébastien dans l'agence Paris...")
                try:
                    user_folder_id = get_or_create_folder(service, user_cv_name, agency_folder_id)
                    service.files().copy(
                        fileId="1SxWW-HN-cxGXBFerPRtvQpzfFKhKkKov",
                        body={"name": f"CV_{user_cv_name.replace(' ', '_')}", "parents": [user_folder_id]}
                    ).execute()
                    done_names.add(user_cv_name)
                    done_consultants.append({
                        "first_name": "Sébastien",
                        "last_name": "Lavayssière",
                        "role": "Expert GCP",
                        "experience_years": 15
                    })
                    agency_progress["done"] = done_consultants
                    progress[agency] = agency_progress
                    save_progress(progress)
                except Exception as e:
                    logger.error(f"  -> Erreur lors de la copie du CV réel: {e}")
        
        remaining = [c for c in planned if f"{c['first_name']} {c['last_name']}" not in done_names]

        if not remaining:
            already_done = len(done_consultants)
            logger.info(f"  (déjà complété : {already_done}/{num_consultants} consultants — passage à la suite)")
            continue

        logger.info(f"Génération de {num_consultants} consultants... ({len(done_consultants)} déjà traités)")

        for consultant in planned:
            first_name = consultant["first_name"]
            last_name = consultant["last_name"]
            full_name = f"{first_name} {last_name}"
            experience_years = consultant["experience_years"]
            role = consultant["role"]

            idx = planned.index(consultant) + 1

            # Skip already processed consultants
            if full_name in done_names:
                logger.info(f"  [{idx}/{num_consultants}] {full_name} — déjà traité, saut.")
                continue

            logger.info(f"  [{idx}/{num_consultants}] {full_name} - {role} ({experience_years} ans)")

            # 1. Dossier Google Drive du consultant
            consultant_folder_id = get_or_create_folder(service, full_name, agency_folder_id)

            # 2. Générer le texte (guaranteed non-None)
            profile_text = generate_profile_text(genai_client, full_name, role, experience_years, agency)

            # 3. Sauvegarde locale
            filename = f"{first_name.lower()}_{last_name.lower()}.md"
            filepath = os.path.join(agency_local_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(profile_text)

            # 4. Upload vers Google Drive (convertit en doc)
            file_metadata = {
                'name': f"CV_{first_name}_{last_name}",
                'parents': [consultant_folder_id],
                'mimeType': 'application/vnd.google-apps.document'
            }
            media = MediaFileUpload(filepath, mimetype='text/markdown', resumable=True)
            try:
                uploaded_file = service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                logger.info(f"      -> CV Google Doc créé avec succès (ID: {uploaded_file.get('id')})")
            except Exception as e:
                logger.error(f"      -> Erreur upload GDrive: {e}")

            # 5. Mark as done and persist immediately
            done_consultants.append(consultant)
            done_names.add(full_name)
            agency_progress["done"] = done_consultants
            progress[agency] = agency_progress
            save_progress(progress)

            time.sleep(1)  # rate limit precaution

    logger.info("\\n✅ Génération terminée !")


if __name__ == "__main__":
    main()
