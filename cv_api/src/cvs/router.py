from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import httpx
import os
import re
import unicodedata
from typing import Optional, List
from google import genai
from google.genai import types
from opentelemetry.propagate import inject

from database import get_db
from src.auth import verify_jwt
from src.cvs.models import CVProfile
from src.cvs.schemas import CVImportRequest, CVResponse, SearchCandidateResponse, CVProfileResponse, UserMergeRequest

router = APIRouter(prefix="", tags=["CV Analysis"], dependencies=[Depends(verify_jwt)])

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")
COMPETENCIES_API_URL = os.getenv("COMPETENCIES_API_URL", "http://competencies_api:8003")
PROMPTS_API_URL = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")

# Initialize Gemini Client
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    print("WARNING: GOOGLE_API_KEY is missing. RAG embeddings will fail.")
    client = None
else:
    client = genai.Client(api_key=GEMINI_API_KEY)

import urllib.parse
import logging

logger = logging.getLogger(__name__)

async def _fetch_cv_content(url: str, google_token: Optional[str] = None) -> str:
    """Download the CV content. If Google Docs, map to raw export endpoint."""
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or ""
    
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Invalid URL scheme")
        
    forbidden_hosts = ["localhost", "127.0.0.1", "0.0.0.0"]
    if hostname in forbidden_hosts or hostname.endswith(".local") or hostname.endswith("_api"):
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
async def import_and_analyze_cv(req: CVImportRequest, request: Request, db: AsyncSession = Depends(get_db), token_payload: dict = Depends(verify_jwt)):
    # 1. Capture Authorization Context (Crucial per RULES[AGENTS.md])
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization via CV upload")
    
    headers = {"Authorization": auth_header}
    inject(headers)  # Mandatory Trace Span Propagation (Agent.md Rule 4)

    # 2. Fetch Text from CV Link
    try:
        logger.info(f"Downloading CV content from {req.url}")
        raw_text = await _fetch_cv_content(req.url, req.google_access_token)
    except HTTPException as he:
        logger.error(f"HTTPException while downloading CV: {he.detail}")
        raise
    except Exception as e:
        logger.error(f"Failed downloading CV content: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed downloading CV content: {e}")

    if not client:
        logger.error("GenAI Client not configured.")
        raise HTTPException(status_code=500, detail="GenAI Client not configured.")

    # 3. LLM Parsing Pass (Structured Output)
    try:
        logger.info("Fetching generic prompt for CV analysis")
        async with httpx.AsyncClient() as http_client:
            res_prompt = await http_client.get(f"{PROMPTS_API_URL.rstrip('/')}/cv_api.extract_cv_info", headers=headers, timeout=5.0)
            res_prompt.raise_for_status()
            prompt = res_prompt.json()["value"]
    except Exception as e:
        logger.error(f"Cannot fetch generic prompt: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cannot fetch generic prompt: {e}")
    
    try:
        logger.info("Calling Gemini to parse CV")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, f"RESUME:\n{raw_text[:8000]}"], # Cap length to avoid massive overload
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "is_cv": {"type": "boolean"},
                        "first_name": {"type": "string"},
                        "last_name": {"type": "string"},
                        "email": {"type": "string"},
                        "summary": {"type": "string"},
                        "current_role": {"type": "string"},
                        "years_of_experience": {"type": "integer"},
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
                    "required": ["is_cv", "first_name", "last_name", "email", "summary", "current_role", "years_of_experience", "competencies"]
                }
            )
        )
        parsed_data = response.text
        # LLM returns a JSON string matching schema
        import json
        structured_cv = json.loads(parsed_data)
        
        if not structured_cv.get("is_cv", False):
            logger.warning("Document is not recognized as a CV")
            raise HTTPException(status_code=400, detail="Not a CV: The document does not appear to be a resume.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"LLM Parsing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"LLM Parsing failed: {e}")    # 4. Synchronous Provisioning targeting Users API
    email = structured_cv["email"]
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        user_id = None
        importer_id = None

        # 1. Resolve target user by email (avoids pagination limits)
        search_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/search", params={"query": email, "limit": 10}, headers=headers)
        if search_res.status_code == 200:
            for u in search_res.json().get("items", []):
                if u.get("email", "").lower() == email.lower():
                    user_id = u["id"]
                    logger.info(f"User matched exactly by email: {email} -> ID: {user_id}")
                    break
        
        # 2. Semantic Fallback: if email wasn't found (e.g. personal vs pro email)
        if not user_id:
            first_n = structured_cv.get('first_name', '')
            last_n = structured_cv.get('last_name', '')
            if first_n and last_n:
                logger.info(f"Email {email} not found. Attempting semantic fallback on {first_n} {last_n}.")
                search_q = f"{first_n} {last_n}"
                name_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/search", params={"query": search_q, "limit": 10}, headers=headers)
                if name_res.status_code == 200:
                    def normalize_str(s: str) -> str:
                        if not s: return ""
                        return unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8').lower()
                    
                    for u in name_res.json().get("items", []):
                        if normalize_str(u.get("first_name")) == normalize_str(first_n) and normalize_str(u.get("last_name")) == normalize_str(last_n):
                            user_id = u["id"]
                            logger.info(f"User matched semantically by name -> ID: {user_id}")
                            break

        # 3. Resolve internal importer properly
        importer_username = token_payload.get("sub")
        if importer_username:
            importer_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/search", params={"query": importer_username, "limit": 10}, headers=headers)
            if importer_res.status_code == 200:
                for u in importer_res.json().get("items", []):
                    if u.get("username", "").lower() == importer_username.lower():
                        importer_id = u["id"]
                        break

        if not user_id:
            logger.info("User not found, creating new user...")
            # Create User
            new_u = {
                "username": f"{structured_cv['first_name'][0].lower()}{structured_cv['last_name'].lower()}",
                "email": email,
                "first_name": structured_cv['first_name'],
                "last_name": structured_cv['last_name'],
                "full_name": f"{structured_cv['first_name']} {structured_cv['last_name']}",
                "password": "zenikacv123"
            }
            create_res = await http_client.post(f"{USERS_API_URL.rstrip('/')}/", json=new_u, headers=headers)
            if create_res.status_code >= 400:
                logger.error(f"User creation failed: status={create_res.status_code}, detail={create_res.text}")
                raise HTTPException(status_code=500, detail=f"User creation failed: {create_res.text}")
            user_id = create_res.json()["id"]
            logger.info(f"User created with ID {user_id}")

        # 5. Provisioning Competencies API dependencies
        # Fetch current existing flat tree to avoid redundant insertions
        comp_res = await http_client.get(f"{COMPETENCIES_API_URL.rstrip('/')}/?limit=1000", headers=headers)
        comp_data = comp_res.json()
        all_comps = comp_data.get("items", []) if isinstance(comp_data, dict) else comp_data
        
        def find_comp_id(node_list, t_name):
            for n in node_list:
                if n['name'].lower() == t_name.lower(): return n['id']
                found = find_comp_id(n.get('sub_competencies', []), t_name)
                if found: return found
            return None

        assigned_count = 0
        logger.info(f"Processing {len(structured_cv.get('competencies', []))} competencies")
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
                        p_res = await http_client.post(f"{COMPETENCIES_API_URL.rstrip('/')}/", json={"name": parent, "description": "Auto-identified from CV"}, headers=headers)
                        if p_res.status_code < 400:
                            p_id = p_res.json()["id"]
                            all_comps.append(p_res.json()) # quick cache patch
                
                # Create leaf
                leaf_data = {"name": name, "description": "Candidate CV Skill"}
                if p_id: leaf_data["parent_id"] = p_id
                
                c_res = await http_client.post(f"{COMPETENCIES_API_URL.rstrip('/')}/", json=leaf_data, headers=headers)
                if c_res.status_code < 400:
                    c_id = c_res.json()["id"]
                    all_comps.append(c_res.json())
            
            # 6. Assign Node to User
            if c_id:
                assign_res = await http_client.post(f"{COMPETENCIES_API_URL.rstrip('/')}/user/{user_id}/assign/{c_id}", headers=headers)
                if assign_res.status_code < 400:
                    assigned_count += 1

    # 7. LLM Embedding Pass (Vector Dimension Matrix)
    comp_keywords = [c.get("name") for c in structured_cv.get("competencies", []) if c.get("name")]
    
    distilled_content = (
        f"Role: {structured_cv.get('current_role', 'Unknown')}\n"
        f"Experience: {structured_cv.get('years_of_experience', 0)} years\n"
        f"Summary: {structured_cv.get('summary', '')}\n"
        f"Competencies: {', '.join(comp_keywords)}\n"
    )
    
    try:
        emb_res = client.models.embed_content(
            model='gemini-embedding-001',
            contents=distilled_content
        )
        vector_data = emb_res.embeddings[0].values
    except Exception as e:
        logger.error(f"Embedding failed: {e}", exc_info=True)
        vector_data = None

    # 8. PostGreSQL Physical Save
    from sqlalchemy import delete
    await db.execute(delete(CVProfile).where(CVProfile.source_url == req.url).where(CVProfile.user_id == user_id))
    
    cv_record = CVProfile(
        user_id=user_id,
        source_url=req.url,
        source_tag=req.source_tag,
        extracted_competencies=structured_cv.get("competencies", []),
        current_role=structured_cv.get("current_role"),
        years_of_experience=structured_cv.get("years_of_experience"),
        summary=structured_cv.get("summary"),
        competencies_keywords=comp_keywords,
        raw_content=raw_text,
        semantic_embedding=vector_data,
        imported_by_id=importer_id
    )
    db.add(cv_record)
    await db.commit()

    logger.info(f"Successfully processed CV for {structured_cv.get('first_name')}, assigned {assigned_count} competencies.")
    return CVResponse(
        message=f"Success! Processed '{structured_cv['first_name']}' and mapped {assigned_count} RAG competencies.",
        user_id=user_id,
        competencies_assigned=assigned_count
    )

@router.get("/search", response_model=List[SearchCandidateResponse])
async def search_candidates(query: str, limit: int = 5, request: Request = None, db: AsyncSession = Depends(get_db)):
    """
    Recherche sémantique (RAG) du meilleur candidat via pgvector cosine distance.
    L'agent interroge cette route lorsqu'il cherche des consultants par mots-clés ou description de projet.
    """
    if not client:
        raise HTTPException(status_code=500, detail="GenAI Client not configured.")
        
    # 0. Pre-filtrage AI: Extract mandatory skills from query
    try:
        filter_prompt = f"Extract a JSON list of strictly required technical competencies from this search query. Return ONLY a JSON array of strings (e.g. ['Python', 'AWS']), or an empty array if none are strictly required.\nQuery: '{query}'"
        filter_res = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=filter_prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        import json
        required_skills = json.loads(filter_res.text)
        if not isinstance(required_skills, list):
            required_skills = []
    except Exception as e:
        logger.warning(f"Skill extraction failed, proceeding without pre-filter: {e}")
        required_skills = []

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
    stmt = select(
        CVProfile, 
        CVProfile.semantic_embedding.cosine_distance(search_vector).label('distance')
    ).filter(CVProfile.semantic_embedding.is_not(None))
    
    if required_skills:
        from sqlalchemy import cast, String
        for skill in required_skills:
            stmt = stmt.filter(cast(CVProfile.competencies_keywords, String).ilike(f'%{skill}%'))

    query_results = (await db.execute(stmt.order_by('distance').limit(limit * 2))).all()
                
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
                u_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{res['user_id']}", headers=headers_downstream)
                if u_res.status_code == 200:
                    u_data = u_res.json()
                    res["full_name"] = u_data.get("full_name")
                    res["email"] = u_data.get("email")
                    res["username"] = u_data.get("username")
                    res["is_active"] = u_data.get("is_active")
            except Exception as e:
                print(f"HTTP Enrichment failed for user {res['user_id']}: {e}")

    return mapped_results

@router.get("/user/{user_id}", response_model=List[CVProfileResponse])
async def get_user_cv(user_id: int, request: Request = None, db: AsyncSession = Depends(get_db)):
    """
    Récupére le ou les liens source (Google Doc) originaux des CVs associés au collaborateur.
    """
    profiles = (await db.execute(select(CVProfile).filter(CVProfile.user_id == user_id).order_by(CVProfile.created_at.desc()))).scalars().all()
    if not profiles:
        raise HTTPException(status_code=404, detail="Aucun CV trouvé pour cet utilisateur.")
        
    return [
        CVProfileResponse(
            user_id=p.user_id,
            source_url=p.source_url,
            source_tag=p.source_tag,
            imported_by_id=p.imported_by_id
        ) for p in profiles
    ]

@router.get("/users/tag/{tag}", response_model=List[CVProfileResponse])
async def get_users_by_tag(tag: str, request: Request = None, db: AsyncSession = Depends(get_db)):
    """
    Récupère les profils CV (et user_ids) associés à un tag spécifique (ex: localisation 'Niort').
    Sans redondance par utilisateur (déduplication).
    """
    profiles = (await db.execute(select(CVProfile).filter(CVProfile.source_tag == tag).order_by(CVProfile.created_at.desc()))).scalars().all()
    
    seen_users = set()
    unique_profiles = []
    
    for p in profiles:
        if p.user_id not in seen_users:
            seen_users.add(p.user_id)
            unique_profiles.append(
                CVProfileResponse(
                    user_id=p.user_id,
                    source_url=p.source_url,
                    source_tag=p.source_tag,
                    imported_by_id=p.imported_by_id
                )
            )
            
    return unique_profiles

@router.post("/recalculate_tree")
async def recalculate_competencies_tree(request: Request, db: AsyncSession = Depends(get_db)):
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

    profiles = (await db.execute(select(CVProfile))).scalars().all()
    if not profiles:
        raise HTTPException(status_code=404, detail="Aucun CV dans la base pour générer un arbre.")

    combined_text = "\n\n--- CV SUIVANT ---\n\n".join([p.raw_content for p in profiles])
    try:
        async with httpx.AsyncClient() as http_client:
            headers_downstream = {"Authorization": auth_header}
            res_prompt = await http_client.get(f"{PROMPTS_API_URL.rstrip('/')}/cv_api.generate_taxonomy_tree", headers=headers_downstream, timeout=5.0)
            res_prompt.raise_for_status()
            instruction = res_prompt.json()["value"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cannot fetch generic prompt: {e}")

    try:
        async with httpx.AsyncClient() as http_client:
            headers = {"Authorization": auth_header}
            comp_res = await http_client.get(f"{COMPETENCIES_API_URL.rstrip('/')}/?limit=1000", headers=headers)
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

@router.post("/internal/users/merge")
async def merge_users(req: UserMergeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Internal endpoint to merge user data.
    Updates cv_profiles.user_id = target_id where user_id = source_id.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization via CV merge")
        
    from sqlalchemy import update
    stmt = update(CVProfile).where(CVProfile.user_id == req.source_id).values(user_id=req.target_id)
    await db.execute(stmt)
    
    stmt2 = update(CVProfile).where(CVProfile.imported_by_id == req.source_id).values(imported_by_id=req.target_id)
    await db.execute(stmt2)

    await db.commit()
    return {"message": f"Successfully migrated CVs from user {req.source_id} to {req.target_id}"}
