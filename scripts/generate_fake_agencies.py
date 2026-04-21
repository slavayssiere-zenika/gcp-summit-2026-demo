import os
import random
import time
import google.auth
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from faker import Faker
from google import genai
from google.genai import types

# Configurations
AGENCIES = ["Sèvres", "Saumur", "Bizanos"]
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

fake = Faker('fr_FR')

def get_drive_service():
    print("Authentification Google Drive...")
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive.file"])
    service = build("drive", "v3", credentials=credentials)
    return service

def get_or_create_folder(service, folder_name, parent_id=None):
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    
    if items:
        # found
        return items[0]['id']
    else:
        # create
        metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            metadata['parents'] = [parent_id]
            
        folder = service.files().create(body=metadata, fields='id').execute()
        return folder.get('id')

def generate_profile_text(client: genai.Client, name: str, role: str, experience_years: int) -> str:
    prompt = f"""
Tu es un recruteur expert. Je te demande de générer un Curriculum Vitae au format texte clair et lisible.
Le consultant s'appelle {name}.
Son rôle est {role} et il a {experience_years} ans d'expérience.
Le CV doit impérativement contenir:
- Une phrase de présentation ou résumé.
- Ses compétences techniques et métiers détaillées.
- 2 à 3 expériences professionnelles expliquées avec le contexte technique et métier.
- Sa formation ou scolarité (invente si nécessaire).

Structure le tout avec des retours à la ligne propres, et un titre. Fais en sorte que ça semble naturel, professionnel.
    """
    
    # Using default model gemini-2.5-flash as it's quick and cost-effective
    # Make sure vertex is initialized properly. genai SDK uses Vertex implicitly if configured, or default project.
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"Erreur avec Gemini, utilisation d'un template par défaut: {e}")
        return f"# CV de {name}\n\n**Rôle**: {role}\n**Expérience**: {experience_years} ans\n\n## Résumé\nConsultant sur {role}.\n\n## Expériences\n- Mission 1: Développeur sur le projet X\n- Mission 2: Refonte de l'application Y\n\n## Compétences\n- Python, Java, JS"

def get_gemini_api_key():
    secrets_path = os.path.join(os.path.dirname(__file__), "..", "secrets.sh")
    try:
        with open(secrets_path, "r") as f:
            for line in f:
                if line.startswith("export GOOGLE_API_KEY="):
                    return line.split("=")[1].strip()
    except Exception:
        pass
    return os.getenv("GEMINI_API_KEY")

def main():
    service = get_drive_service()
    
    try:
        api_key = get_gemini_api_key()
        genai_client = genai.Client(api_key=api_key) if api_key else genai.Client()
    except Exception as e:
        print(f"Attention, initialisation GenAI échouée. Erreur: {e}")
        genai_client = None

    print("Création du dossier racine 'Fake Agencies'...")
    root_folder_id = get_or_create_folder(service, "Fake Agencies")
    
    for agency in AGENCIES:
        print(f"\n--- Agence : {agency} ---")
        agency_folder_id = get_or_create_folder(service, agency, root_folder_id)
        
        agency_local_dir = os.path.join(LOCAL_PROFILES_DIR, agency)
        os.makedirs(agency_local_dir, exist_ok=True)
        
        num_consultants = random.randint(10, 20)
        print(f"Génération de {num_consultants} consultants...")
        
        for i in range(num_consultants):
            first_name = fake.first_name()
            last_name = fake.last_name()
            full_name = f"{first_name} {last_name}"
            
            experience_years = random.randint(2, 15)
            role = random.choice(ROLES)
            
            print(f"  [{i+1}/{num_consultants}] {full_name} - {role} ({experience_years} ans)")
            
            # 1. Dossier Google Drive du consultant
            consultant_folder_id = get_or_create_folder(service, full_name, agency_folder_id)
            
            # 2. Générer le texte
            profile_text = generate_profile_text(genai_client, full_name, role, experience_years)
            
            # 3. Sauvegarde locale
            filename = f"{first_name.lower()}_{last_name.lower()}.md"
            filepath = os.path.join(agency_local_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(profile_text)
                
            # 4. Upload vers Google Drive (convertit en doc)
            file_metadata = {
                'name': f"CV_{first_name}_{last_name}",
                'parents': [consultant_folder_id],
                'mimeType': 'application/vnd.google-apps.document'  # Force Google Doc conversion
            }
            media = MediaFileUpload(filepath, mimetype='text/markdown', resumable=True)
            try:
                uploaded_file = service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                print(f"      -> CV Google Doc créé avec succès (ID: {uploaded_file.get('id')})")
            except Exception as e:
                print(f"      -> Erreur upload GDrive: {e}")
                
            time.sleep(1) # rate limit precaution

    print("\n✅ Génération terminée !")

if __name__ == "__main__":
    main()
