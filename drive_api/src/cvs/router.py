from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import httpx
import os
import re
from typing import Optional, List
from google import genai
from google.genai import types
from opentelemetry.propagate import inject

from database import get_db
from src.auth import verify_jwt
from src.cvs.models import CVProfile
from src.cvs.schemas import CVImportRequest, CVResponse, SearchCandidateResponse, CVProfileResponse

router = APIRouter(prefix="/cvs", tags=["CV Analysis"], dependencies=[Depends(verify_jwt)])

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")
COMPETENCIES_API_URL = os.getenv("COMPETENCIES_API_URL", "http://competencies_api:8003")

# Initialize Gemini Client
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    print("WARNING: GOOGLE_API_KEY is missing. RAG embeddings will fail.")
    client = None
else:
    client = genai.Client(api_key=GEMINI_API_KEY)

import urllib.parse

async def _fetch_cv_content(url: str, google_token: Optional[str] = None) -> str:
    """Download the CV content. If Google Docs, map to raw export endpoint."""
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or ""
    
    if parsed.scheme not in ("http", "https"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid URL scheme")
        
    forbidden_hosts = ["localhost", "127.0.0.1", "0.0.0.0"]
    if hostname in forbidden_hosts or hostname.endswith(".local") or hostname.endswith("_api"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Internal URLs are not allowed")

    if "docs.google.com/document/d/" in url:
        # Map to export format if user pastes the browser URL
        doc_id = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
        if doc_id:
            url = f"https://docs.google.com/document/d/{doc_id.group(1)}/export?format=txt"
    
    req_headers = {}
    if google_token:
        req_headers["Authorization"] = f"Bearer {google_token}"

    async with httpx.AsyncClient() as http_client:
        resp = await http_client.get(url, headers=req_headers, follow_redirects=True)
        if resp.status_code == 401 or resp.status_code == 403:
            raise HTTPException(status_code=400, detail="Accès refusé par Google Docs. Veuillez vérifier que le document est public ou autoriser l'accès.")
        resp.raise_for_status()
        return resp.text

@router.post("/import", response_model=CVResponse)
async def import_and_analyze_cv(req: CVImportRequest, request: Request, db: Session = Depends(get_db), token_payload: dict = Depends(verify_jwt)):
    # 1. Capture Authorization Context (Crucial per RULES[AGENTS.md])
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization via CV upload")
    
    headers = {"Authorization": auth_header}
    inject(headers)  # Mandatory Trace Span Propagation (Agent.md Rule 4)

    # 2. Fetch Text from CV Link
    try:
        raw_text = await _fetch_cv_content(req.url, req.google_access_token)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed downloading CV content: {e}")

    if not client:
        raise HTTPException(status_code=500, detail="GenAI Client not configured.")

    # 3. LLM Parsing Pass (Structured Output)
    try:
        async with httpx.AsyncClient() as http_client:
            res_prompt = await http_client.get("http://prompts_api:8000/prompts/cv_api.extract_cv_info", headers=headers, timeout=5.0)
            res_prompt.raise_for_status()
            prompt = res_prompt.json()["value"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cannot fetch generic prompt: {e}")
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, f"RESUME:\n{raw_text[:8000]}"], # Cap length to avoid massive overload
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "first_name": {"type": "string"},
                        "last_name": {"type": "string"},
                        "email": {"type": "string"},
                        "competencies": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "parent": {"type": "string"}
                                },
                                "required": ["name"]
                            }
                        }
                    },
                    "required": ["first_name", "last_name", "email", "competencies"]
                }
            )
        )
        parsed_data = response.text
        # LLM returns a JSON string matching schema
        import json
        structured_cv = json.loads(parsed_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Parsing failed: {e}")    # 4. Synchronous Provisioning targeting Users API
    email = structured_cv["email"]
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        # Check if user exists
        user_res = await http_client.get(f"{USERS_API_URL}/users/", params={"skip":0, "limit": 100}, headers=headers)
        user_id = None
        importer_id = None
        importer_username = token_payload.get("sub")
        if user_res.status_code == 200:
            for u in user_res.json()["items"]:
                if u["email"].lower() == email.lower():
                    user_id = u["id"]
                
                u_username = u.get("username", "")
                if importer_username and u_username and u_username.lower() == importer_username.lower():
                    importer_id = u["id"]
                
                # Small optimization: If both are found, we don't need to break early since limit=100 is small.

        if not user_id:
            # Create User
            new_u = {
                "username": f"{structured_cv['first_name'][0].lower()}{structured_cv['last_name'].lower()}",
                "email": email,
                "first_name": structured_cv['first_name'],
                "last_name": structured_cv['last_name'],
                "full_name": f"{structured_cv['first_name']} {structured_cv['last_name']}",
                "password": "zenikacv123"
            }
            create_res = await http_client.post(f"{USERS_API_URL}/users/", json=new_u, headers=headers)
            if create_res.status_code >= 400:
                raise HTTPException(status_code=500, detail=f"User creation failed: {create_res.text}")
            user_id = create_res.json()["id"]

        # 5. Provisioning Competencies API dependencies
        # Fetch current existing flat tree to avoid redundant insertions
        comp_res = await http_client.get(f"{COMPETENCIES_API_URL}/competencies/?limit=1000", headers=headers)
        comp_data = comp_res.json()
        all_comps = comp_data.get("items", []) if isinstance(comp_data, dict) else comp_data
        
        def find_comp_id(node_list, t_name):
            for n in node_list:
                if n['name'].lower() == t_name.lower(): return n['id']
                found = find_comp_id(n.get('sub_competencies', []), t_name)
                if found: return found
            return None

        assigned_count = 0
        for comp in structured_cv.get("competencies", []):
            name = comp["name"]
            parent = comp.get("parent")
            
            c_id = find_comp_id(all_comps, name)
            if not c_id:
                p_id = None
                # Create parent if needed
                if parent:
                    p_id = find_comp_id(all_comps, parent)
                    if not p_id:
                        p_res = await http_client.post(f"{COMPETENCIES_API_URL}/competencies/", json={"name": parent, "description": "Auto-identified from CV"}, headers=headers)
                        if p_res.status_code < 400:
                            p_id = p_res.json()["id"]
                            all_comps.append(p_res.json()) # quick cache patch
                
                # Create leaf
                leaf_data = {"name": name, "description": "Candidate CV Skill"}
                if p_id: leaf_data["parent_id"] = p_id
                
                c_res = await http_client.post(f"{COMPETENCIES_API_URL}/competencies/", json=leaf_data, headers=headers)
                if c_res.status_code < 400:
                    c_id = c_res.json()["id"]
                    all_comps.append(c_res.json())
            
            # 6. Assign Node to User
            if c_id:
                assign_res = await http_client.post(f"{COMPETENCIES_API_URL}/competencies/user/{user_id}/assign/{c_id}", headers=headers)
                if assign_res.status_code < 400:
                    assigned_count += 1

    # 7. LLM Embedding Pass (Vector Dimension Matrix)
    try:
        emb_res = client.models.embed_content(
            model='gemini-embedding-001',
            contents=raw_text[:10000] # Cap 10k to prevent token limits on heavy CVs
        )
        vector_data = emb_res.embeddings[0].values
    except Exception as e:
        print(f"Embedding failed: {e}")
        vector_data = None

    # 8. PostGreSQL Physical Save
    cv_record = CVProfile(
        user_id=user_id,
        source_url=req.url,
        source_tag=req.source_tag,
        extracted_competencies=structured_cv.get("competencies", []),
        raw_content=raw_text,
        semantic_embedding=vector_data,
        imported_by_id=importer_id
    )
    db.add(cv_record)
    db.commit()

    return CVResponse(
        message=f"Success! Processed '{structured_cv['first_name']}' and mapped {assigned_count} RAG competencies.",
        user_id=user_id,
        competencies_assigned=assigned_count
    )

@router.get("/search", response_model=List[SearchCandidateResponse])
async def search_candidates(query: str, limit: int = 5, request: Request = None, db: Session = Depends(get_db)):
    """
    Recherche sémantique (RAG) du meilleur candidat via pgvector cosine distance.
    L'agent interroge cette route lorsqu'il cherche des consultants par mots-clés ou description de projet.
    """
    if not client:
        raise HTTPException(status_code=500, detail="GenAI Client not configured.")
        
    try:
        # 1. Convert Prompt Query into 3072-D Matrix
        emb_res = client.models.embed_content(
            model='gemini-embedding-001',
            contents=query
        )
        search_vector = emb_res.embeddings[0].values
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Embedding search query failed: {e}")

    # 2. Vector Postgres Search Operator (Cosine Distance <=>)
    query_results = db.query(
        CVProfile, 
        CVProfile.semantic_embedding.cosine_distance(search_vector).label('distance')
    ).filter(CVProfile.semantic_embedding.is_not(None))\
     .order_by('distance')\
     .limit(limit * 2).all()
                
    mapped_results = []
    seen_users = set()
    
    for row, distance in query_results:
        if row.user_id not in seen_users:
            seen_users.add(row.user_id)
            score = 1.0 - (distance if distance is not None else 0.0)
            mapped_results.append({
                "user_id": row.user_id,
                "similarity_score": round(score, 4)
            })
            if len(mapped_results) >= limit:
                break

    # 3. Enrich Candidates with Users API properties (Composition Pattern)
    auth_header = request.headers.get("Authorization") if request else None
    headers_downstream = {"Authorization": auth_header} if auth_header else {}
    inject(headers_downstream)  # Mandatory Trace Span Propagation (Agent.md Rule 4)
    
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        for res in mapped_results:
            try:
                u_res = await http_client.get(f"{USERS_API_URL}/users/{res['user_id']}", headers=headers_downstream)
                if u_res.status_code == 200:
                    u_data = u_res.json()
                    res["full_name"] = u_data.get("full_name")
                    res["email"] = u_data.get("email")
                    res["username"] = u_data.get("username")
                    res["is_active"] = u_data.get("is_active")
            except Exception as e:
                print(f"HTTP Enrichment failed for user {res['user_id']}: {e}")

    return mapped_results

@router.get("/user/{user_id}", response_model=CVProfileResponse)
async def get_user_cv(user_id: int, request: Request = None, db: Session = Depends(get_db)):
    """
    Récupére le lien source (Google Doc) original du CV associé au collaborateur.
    """
    profile = db.query(CVProfile).filter(CVProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Aucun CV trouvé pour cet utilisateur.")
        
    return CVProfileResponse(
        user_id=profile.user_id,
        source_url=profile.source_url
    )

@router.post("/recalculate_tree")
async def recalculate_competencies_tree(request: Request, db: Session = Depends(get_db)):
    """
    (Admin Only) Lit tous les CVs de la base et donne à Gemini la mission de synthétiser 
    le modèle hiérarchique optimal pour l'entreprise (Catégories -> Spécialités -> Compétences).
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=403, detail="Opération refusée: Authentification manquante.")
        
    token = auth_header.split(" ")[1]
    try:
        from jose import jwt
        from src.auth import SECRET_KEY, ALGORITHM
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Opération refusée: privilèges administrateur requis.")
    except Exception:
        raise HTTPException(status_code=403, detail="Token invalide pour cette opération protégée.")
             
    if not client:
        raise HTTPException(status_code=500, detail="Gemini SDK non configuré (Google API Key manquante).")

    profiles = db.query(CVProfile).all()
    if not profiles:
        raise HTTPException(status_code=404, detail="Aucun CV dans la base pour générer un arbre.")

    combined_text = "\n\n--- CV SUIVANT ---\n\n".join([p.raw_content for p in profiles])
    try:
        async with httpx.AsyncClient() as http_client:
            headers_downstream = {"Authorization": auth_header}
            res_prompt = await http_client.get("http://prompts_api:8000/prompts/cv_api.generate_taxonomy_tree", headers=headers_downstream, timeout=5.0)
            res_prompt.raise_for_status()
            instruction = res_prompt.json()["value"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cannot fetch generic prompt: {e}")

    try:
        async with httpx.AsyncClient() as http_client:
            headers = {"Authorization": auth_header}
            comp_res = await http_client.get(f"{COMPETENCIES_API_URL}/competencies/?limit=1000", headers=headers)
            comp_data = comp_res.json()
            all_comps = comp_data.get("items", []) if isinstance(comp_data, dict) else comp_data
            
            def get_all_names(nodes):
                names = []
                for n in nodes:
                    names.append(n["name"])
                    if "sub_competencies" in n and n["sub_competencies"]:
                        names.extend(get_all_names(n["sub_competencies"]))
                return names
            
            existing_names = get_all_names(all_comps)
            skills_str = ", ".join(existing_names) if existing_names else "Aucune compétence existante"
            instruction = instruction.replace("{{EXISTING_COMPETENCIES}}", skills_str)
    except Exception as e:
        print(f"WARNING: Failed to inject existing competencies: {e}")

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[instruction, combined_text],
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            )
        )
        # Parse JSON string from model implicitly as it's guaranteed to be valid by `response_mime_type`
        import json
        return {"tree": json.loads(response.text)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Gemini: {str(e)}")
