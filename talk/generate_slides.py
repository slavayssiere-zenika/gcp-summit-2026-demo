import datetime
import json
import os.path
import time

import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google import genai
from google.genai import types

def extract_layouts_info(presentation):
    layouts_info = []
    for layout in presentation.get('layouts', []):
        placeholders = []
        for elem in layout.get('pageElements', []):
            ptype = elem.get('shape', {}).get('placeholder', {}).get('type')
            if ptype:
                placeholders.append(ptype)
        
        layouts_info.append({
            "layoutId": layout.get('objectId'),
            "name": layout.get('layoutProperties', {}).get('displayName', 'Unknown'),
            "placeholders": placeholders
        })
    return layouts_info

def update_presentation_plan(project, script_dir):
    print("📝 Génération/Mise à jour du plan de présentation à partir du prompt markdown...")
    try:
        client = genai.Client(vertexai=True, project=project, location="europe-west1")
        prompt_path = os.path.join(script_dir, "prompt_generate_plan.md")
        plan_path = os.path.join(script_dir, "presentation_plan.json")
        
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt = f.read()
            
        # Injection du contexte technique (AGENTS.md, README.md) pour éviter les hallucinations
        repo_root = os.path.dirname(script_dir)
        context = "\n\n--- CONTEXTE TECHNIQUE DU PROJET TEST-OPEN-CODE ---\n"
        
        agents_path = os.path.join(repo_root, "AGENTS.md")
        if os.path.exists(agents_path):
            with open(agents_path, "r", encoding="utf-8") as f:
                context += "\n# AGENTS.md\n" + f.read()
                
        readme_path = os.path.join(repo_root, "README.md")
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8") as f:
                context += "\n# README.md\n" + f.read()
                
        prompt += context
        
        print("🧠 Appel à Gemini pour concevoir le plan (avec le contexte du projet)...")
        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            ),
        )
        
        plan = json.loads(response.text)
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)
            
        print("✅ Plan de présentation mis à jour avec succès !")
        return plan
    except Exception as e:
        print(f"❌ Erreur lors de la mise à jour du plan : {e}")
        return None

def generate_smart_plan(plan, layouts_info, project):
    print("🧠 Appel à Gemini (Vertex AI) pour mapper intelligemment le contenu...")
    try:
        client = genai.Client(vertexai=True, project=project, location="europe-west1")
        
        prompt = f"""
        Tu es un expert "Slide Designer" pour Zenika. Ton rôle est de mapper le contenu brut d'une présentation vers les "Layouts" d'un template Google Slides.
        
        RÈGLE ABSOLUE : Tu n'as pas le droit de modifier le texte fourni. Tu dois réutiliser le texte EXACT.
        
        # 1. TEMPLATE (Layouts disponibles)
        {json.dumps(layouts_info, indent=2)}
        
        # 2. CONTENU À PLACER
        {json.dumps(plan['slides'], indent=2)}
        
        # CONSIGNES DE MAPPING
        - Chaque slide doit utiliser le 'layoutId' d'un Layout disponible.
        - Respecte les indices 'slide_type' et 'preferred_color' pour choisir le bon Layout :
          * 'cover' ou 'chapter' -> utiliser un layout de type "header"
          * 'text_image' -> utiliser un layout de type "text+img"
          * 'customer_story' -> utiliser le layout "customer story"
        - Mappe le champ 'title' dans "TITLE".
        - Mappe le champ 'subtitle' dans "SUBTITLE".
        - Si la slide contient du 'content' (liste à puces), joins les lignes avec un saut de ligne '\\n' et mappe-les UNIQUEMENT dans "BODY".
        - Si le layout choisi n'a pas de "BODY" (ex: un header), n'essaie surtout pas de forcer le 'content' dans le SUBTITLE. Ignore le 'content' ou choisis un layout de type "text".
        
        # FORMAT DE SORTIE (STRICTEMENT JSON)
        Retourne uniquement un JSON valide contenant une liste 'slides'.
        Exemple :
        {{
            "slides": [
                {{
                    "slide_number": 1,
                    "layoutId": "ID_DU_LAYOUT",
                    "placeholders_mapping": [
                        {{ "placeholder_type": "TITLE", "text": "Titre exact" }},
                        {{ "placeholder_type": "SUBTITLE", "text": "Sous-titre exact" }},
                        {{ "placeholder_type": "BODY", "text": "Point 1\\nPoint 2" }}
                    ]
                }}
            ]
        }}
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0
            ),
        )
        
        smart_plan = json.loads(response.text)
        return smart_plan.get("slides", smart_plan)
    except Exception as e:
        print(f"❌ Erreur lors de la génération avec Vertex AI : {e}")
        return None

def main():
    print("Chargement des credentials...")
    SCOPES = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/presentations"
    ]
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        creds_path = os.path.join(script_dir, "credentials.json")
        token_path = os.path.join(script_dir, "token.json")
        
        if os.path.exists(creds_path):
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.oauth2.credentials import Credentials
            creds = None
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            if not creds or not creds.valid:
                from google.auth.transport.requests import Request
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                with open(token_path, "w") as token:
                    token.write(creds.to_json())
            
            try:
                _, project = google.auth.default()
                if not project:
                    project = "prod-ia-staffing"
            except Exception:
                project = "prod-ia-staffing"
        else:
            creds, project = google.auth.default(scopes=SCOPES)
    except Exception as e:
        print(f"Erreur lors du chargement des credentials: {e}")
        return

    try:
        drive_service = build("drive", "v3", credentials=creds)
        slides_service = build("slides", "v1", credentials=creds)
        
        # 0. Générer puis charger le plan
        plan = update_presentation_plan(project, script_dir)
        if not plan:
            print("⚠️ Impossible de générer le plan, tentative de lecture depuis le fichier existant...")
            plan_path = os.path.join(script_dir, "presentation_plan.json")
            with open(plan_path, "r", encoding="utf-8") as f:
                plan = json.load(f)
            
        template_id = "1pxgzUdmW2Nx5G7mVj5tbP69fBaGblZ1v9EhZh_1lE8o"
        print(f"📄 Utilisation du template ciblé (ID: {template_id})")
        
        # 1. Création d'une copie du template
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        new_presentation_title = f"{today} - Au-delà du PoC"
        
        print(f"⏳ Création d'une copie du template...")
        presentation_copy = drive_service.files().copy(
            fileId=template_id, 
            body={"name": new_presentation_title}
        ).execute()
        
        new_presentation_id = presentation_copy.get("id")
        print(f"✅ Nouvelle présentation créée (ID: {new_presentation_id})")
        
        # 2. Analyse de la copie pour récupérer les Layouts et les Slides existants
        presentation = slides_service.presentations().get(presentationId=new_presentation_id).execute()
        existing_slides_ids = [s.get('objectId') for s in presentation.get('slides', [])]
        layouts_info = extract_layouts_info(presentation)
        
        # 3. Génération du Smart Plan via Gemini
        smart_slides = generate_smart_plan(plan, layouts_info, project)
        if not smart_slides:
            print("Échec de la génération de la structure. Arrêt.")
            return
            
        # 4. Suppression des slides du template + Création des nouveaux slides
        requests_structure = []
        
        # A. On supprime les slides d'exemple du template
        for slide_id in existing_slides_ids:
            requests_structure.append({"deleteObject": {"objectId": slide_id}})
            
        # B. On crée les nouveaux slides selon les ordres de l'IA
        new_slide_ids = []
        for slide in smart_slides:
            new_id = f"slide_{slide['slide_number']}_{int(time.time()*1000)}"
            new_slide_ids.append((new_id, slide))
            requests_structure.append({
                "createSlide": {
                    "objectId": new_id,
                    "slideLayoutReference": {
                        "layoutId": slide["layoutId"]
                    }
                }
            })
            
        print("🗑️ Nettoyage des slides d'exemple et création de la nouvelle structure...")
        slides_service.presentations().batchUpdate(
            presentationId=new_presentation_id, 
            body={"requests": requests_structure}
        ).execute()
        
        # 5. Injection du texte dans les placeholders des nouveaux slides
        print("✍️  Injection du contenu et mise en page...")
        # On refetch la présentation pour obtenir les ID des placeholders générés sur les nouveaux slides
        presentation = slides_service.presentations().get(presentationId=new_presentation_id).execute()
        
        requests_text = []
        requests_bullets = []
        requests_images = []
        
        for slide_id, slide_data in new_slide_ids:
            page = next((p for p in presentation.get("slides", []) if p.get("objectId") == slide_id), None)
            if not page:
                continue
                
            for mapping in slide_data.get("placeholders_mapping", []):
                ptype = mapping.get("placeholder_type")
                text = mapping.get("text")
                if not ptype or not text:
                    continue
                    
                shape_id = None
                for element in page.get("pageElements", []):
                    placeholder = element.get("shape", {}).get("placeholder", {})
                    api_ptype = placeholder.get("type", "")
                    
                    if ptype == "TITLE" and api_ptype in ["TITLE", "CENTERED_TITLE"]:
                        shape_id = element["objectId"]
                        break
                    elif ptype == "BODY" and api_ptype == "BODY":
                        shape_id = element["objectId"]
                        break
                    elif ptype == "SUBTITLE" and api_ptype == "SUBTITLE":
                        shape_id = element["objectId"]
                        break
                        
                if shape_id:
                    # Injecte le texte brut
                    requests_text.append({
                        "insertText": {
                            "objectId": shape_id,
                            "text": text
                        }
                    })
                    
                    # Si c'est le BODY, on applique les vraies puces Google Slides
                    if ptype == "BODY":
                        requests_bullets.append({
                            "createParagraphBullets": {
                                "objectId": shape_id,
                                "textRange": {
                                    "type": "ALL"
                                },
                                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
                            }
                        })
                        
            # Gestion des images via Imagen 3
            # L'image originale est uploadée sur Drive et liée à la présentation
            image_prompt = next((s.get("image_prompt") for s in plan.get("slides", []) if s.get("slide_number") == slide_data.get("slide_number")), None)
            if image_prompt:
                print(f"🎨 Génération de l'image avec Imagen 3 pour la slide {slide_id} : {image_prompt}")
                try:
                    img_client = genai.Client(vertexai=True, project=project, location="europe-west1")
                    img_response = img_client.models.generate_images(
                        model='imagen-3.0-generate-002',
                        prompt=image_prompt,
                        config=types.GenerateImagesConfig(
                            number_of_images=1,
                            output_mime_type="image/jpeg",
                            aspect_ratio="4:3"
                        )
                    )
                    image_bytes = img_response.generated_images[0].image.image_bytes
                    
                    # Upload sur Drive
                    from googleapiclient.http import MediaIoBaseUpload
                    import io
                    file_metadata = {'name': f'img_{slide_id}.jpg'}
                    media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype='image/jpeg')
                    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                    img_file_id = file.get('id')
                    
                    # Rend le fichier public pour que Slides puisse l'importer
                    drive_service.permissions().create(fileId=img_file_id, body={'type': 'anyone', 'role': 'reader'}).execute()
                    img_url = f"https://drive.google.com/uc?id={img_file_id}"
                    
                    requests_images.append({
                        "createImage": {
                            "url": img_url,
                            "elementProperties": {
                                "pageObjectId": slide_id,
                                "size": {
                                    "height": {"magnitude": 4000000, "unit": "EMU"},
                                    "width": {"magnitude": 4000000, "unit": "EMU"}
                                },
                                "transform": {
                                    "scaleX": 1, "scaleY": 1, "translateX": 4800000, "translateY": 800000, "unit": "EMU"
                                }
                            }
                        }
                    })
                except Exception as img_err:
                    print(f"⚠️ Erreur lors de la génération ou de l'insertion de l'image: {img_err}")
                    
        # On applique le texte d'abord
        if requests_text:
            slides_service.presentations().batchUpdate(
                presentationId=new_presentation_id, 
                body={"requests": requests_text}
            ).execute()
            
        # Puis on formate en puces
        if requests_bullets:
            slides_service.presentations().batchUpdate(
                presentationId=new_presentation_id, 
                body={"requests": requests_bullets}
            ).execute()
            
        # Puis on insère les images
        if requests_images:
            slides_service.presentations().batchUpdate(
                presentationId=new_presentation_id, 
                body={"requests": requests_images}
            ).execute()
            
        print(f"🎉 Présentation finalisée ! URL : https://docs.google.com/presentation/d/{new_presentation_id}/edit")

    except HttpError as error:
        print(f"❌ Une erreur est survenue avec l'API Google : {error}")
    except Exception as e:
        print(f"❌ Erreur inattendue : {e}")

if __name__ == "__main__":
    main()
