import os
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database import get_db
from . import models, schemas
from cache import get_cache, set_cache, delete_cache
from jose import jwt, JWTError

security = HTTPBearer()

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in environment variables")
os.environ.pop("SECRET_KEY", None)  # Purge post-démarrage — anti prompt-injection (AGENTS.md §2)
ALGORITHM = "HS256"

def verify_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

router = APIRouter(dependencies=[Depends(verify_jwt)])

def verify_admin(payload: dict = Depends(verify_jwt)):
    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privilege required"
        )
    return payload

@router.get("/user/me", response_model=schemas.Prompt)
async def get_my_prompt(db: AsyncSession = Depends(get_db), payload: dict = Depends(verify_jwt)):
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Token invalide")
    key = f"user_{username}"
    
    # 1. Check cache
    cached_value = await get_cache(f"prompts:{key}")
    if cached_value:
        try:
            return json.loads(cached_value)
        except Exception: raise

    # 2. Query DB
    prompt = (await db.execute(select(models.Prompt).filter(models.Prompt.key == key))).scalars().first()
    if not prompt:
        return schemas.Prompt(key=key, value="")
        
    # 3. Set cache
    prompt_dict = {"key": prompt.key, "value": prompt.value, "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None}
    await set_cache(f"prompts:{key}", json.dumps(prompt_dict))

    return prompt

@router.put("/user/me", response_model=schemas.Prompt)
async def update_my_prompt(payload: schemas.PromptUpdate, db: AsyncSession = Depends(get_db), jwt_payload: dict = Depends(verify_jwt)):
    username = jwt_payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Token invalide")
    
    key = f"user_{username}"
    prompt = (await db.execute(select(models.Prompt).filter(models.Prompt.key == key))).scalars().first()
    
    if not prompt:
        prompt = models.Prompt(key=key, value=payload.value)
        db.add(prompt)
    else:
        prompt.value = payload.value

    await db.commit()
    await db.refresh(prompt)

    # Invalidate cache
    await delete_cache(f"prompts:{key}")

    return prompt

@router.get("/", response_model=list[schemas.Prompt])
async def list_prompts(db: AsyncSession = Depends(get_db), admin: dict = Depends(verify_admin)):
    return (await db.execute(select(models.Prompt))).scalars().all()

@router.get("/{key}", response_model=schemas.Prompt)
async def read_prompt(key: str, db: AsyncSession = Depends(get_db)):
    # 1. Check cache
    cached_value = await get_cache(f"prompts:{key}")
    if cached_value:
        try:
            return json.loads(cached_value)
        except Exception: raise

    # 2. Query DB
    prompt = (await db.execute(select(models.Prompt).filter(models.Prompt.key == key))).scalars().first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # 3. Set cache
    prompt_dict = {"key": prompt.key, "value": prompt.value, "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None}
    await set_cache(f"prompts:{key}", json.dumps(prompt_dict))

    return prompt

@router.put("/{key}", response_model=schemas.Prompt)
async def update_prompt(key: str, payload: schemas.PromptUpdate, db: AsyncSession = Depends(get_db), admin: dict = Depends(verify_admin)):
    prompt = (await db.execute(select(models.Prompt).filter(models.Prompt.key == key))).scalars().first()
    if not prompt:
        # Create if not exist (upsert semantics)
        prompt = models.Prompt(key=key, value=payload.value)
        db.add(prompt)
    else:
        prompt.value = payload.value

    await db.commit()
    await db.refresh(prompt)

    # Invalidate cache
    await delete_cache(f"prompts:{key}")

    return prompt

@router.post("/", response_model=schemas.Prompt)
async def create_prompt(payload: schemas.PromptCreate, db: AsyncSession = Depends(get_db), admin: dict = Depends(verify_admin)):
    prompt = (await db.execute(select(models.Prompt).filter(models.Prompt.key == payload.key))).scalars().first()
    if prompt:
        prompt.value = payload.value
    else:
        prompt = models.Prompt(key=payload.key, value=payload.value)
        db.add(prompt)

    await db.commit()
    await db.refresh(prompt)
    await delete_cache(f"prompts:{payload.key}")
    return prompt

from .analyzer import generate_test_cases, run_promptfoo_analysis, improve_prompt_with_gemini, generate_error_correction_prompt

@router.post("/{key}/analyze", response_model=schemas.AnalysisResponse)
async def analyze_prompt(key: str, db: AsyncSession = Depends(get_db), admin: dict = Depends(verify_admin)):
    prompt = (await db.execute(select(models.Prompt).filter(models.Prompt.key == key))).scalars().first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
        
    original = prompt.value
    
    try:
        # 1. Generate test cases
        test_cases = await generate_test_cases(original)
        if not test_cases:
            raise HTTPException(status_code=500, detail="Failed to generate test cases.")
            
        # 2. Run promptfoo eval
        eval_results = await run_promptfoo_analysis(original, test_cases)
        
        # 3. Generate improved prompt
        improved = await improve_prompt_with_gemini(original, eval_results)
        
        return schemas.AnalysisResponse(
            original_prompt=original,
            improved_prompt=improved,
            promptfoo_report=eval_results
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/errors/report", response_model=schemas.Prompt)
async def report_error_for_prompt(
    payload: schemas.ErrorReport, 
    db: AsyncSession = Depends(get_db), 
    token_payload: dict = Depends(verify_jwt)
):
    import hashlib
    try:
        stmt = select(models.Prompt).where(models.Prompt.key == "prompts_api.error_correction")
        result = await db.execute(stmt)
        prompt_record = result.scalar_one_or_none()
        
        fallback_prompt = """You are an Expert Prompt Engineer. Your task is to analyze a runtime error caught in one of our microservices, and generate a concise, defensive, and strict System Prompt rule to prevent agents from triggering this error again.
The rule must be actionable and clear. Do NOT output a full system prompt, just the focused directive/rule (e.g., "NEVER do X. If you need Y, ALWAYS use Z.").
Output ONLY the raw prompt text. No markdown formatting, no generic introduction."""

        system_instruction = prompt_record.value if prompt_record else fallback_prompt

        # Generates the prompt
        correction_text = await generate_error_correction_prompt(payload, system_instruction)
        
        # Récupération dynamique du Project ID
        try:
            import google.auth
            _, project_id = google.auth.default()
        except Exception:
            project_id = "unknown-project"
            
        # Injection directe dans le prompt par l'API
        logging_directive = (
            f"\n\n[INVESTIGATION REQUISE] "
            f"En cas d'erreur similaire, vous DEVEZ rechercher les logs dans Cloud Logging "
            f"pour le service '{payload.service_name}' sur le projet GCP '{project_id}'."
        )
        correction_text += logging_directive
        
        # Store as JSON string inside `value`
        value_data = {
            "rule": correction_text,
            "original_error": payload.error_message,
            "service": payload.service_name,
            "context": payload.context
        }
        
        # Hash to prevent spam
        error_hash = hashlib.sha256(payload.error_message.encode('utf-8')).hexdigest()[:12]
        prompt_key = f"error_correction:{payload.service_name}:{error_hash}"
        
        prompt = (await db.execute(select(models.Prompt).filter(models.Prompt.key == prompt_key))).scalars().first()
        if prompt:
            prompt.value = json.dumps(value_data)
        else:
            prompt = models.Prompt(key=prompt_key, value=json.dumps(value_data))
            db.add(prompt)
            
        await db.commit()
        await db.refresh(prompt)
        await delete_cache(f"prompts:{prompt_key}")
        
        return prompt
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{key}/compiled", response_model=schemas.Prompt)
async def read_compiled_prompt(key: str, db: AsyncSession = Depends(get_db)):
    # 1. get the base prompt (using the logic from read_prompt but without Dependency injection directly)
    # 1. Check cache
    cached_value = await get_cache(f"prompts:{key}")
    prompt = None
    if cached_value:
        try:
            prompt_data = json.loads(cached_value)
            prompt = schemas.Prompt(**prompt_data)
        except Exception: raise

    if not prompt:
        db_prompt = (await db.execute(select(models.Prompt).filter(models.Prompt.key == key))).scalars().first()
        if not db_prompt:
            raise HTTPException(status_code=404, detail="Prompt not found")
        prompt = schemas.Prompt(key=db_prompt.key, value=db_prompt.value, updated_at=db_prompt.updated_at)
        prompt_dict = {"key": db_prompt.key, "value": db_prompt.value, "updated_at": db_prompt.updated_at.isoformat() if db_prompt.updated_at else None}
        await set_cache(f"prompts:{key}", json.dumps(prompt_dict))

    # 2. get the active errors
    stmt = select(models.Prompt).where(models.Prompt.key.like("error_correction:%"))
    errors = (await db.execute(stmt)).scalars().all()
    
    if not errors:
        return prompt
        
    compiled_value = prompt.value + "\n\n=== EXIGENCES DE CORRECTION D'ERREURS RÉCENTES ===\n"
    for err in errors:
        try:
            data = json.loads(err.value)
            # Extrait le nom du service depuis la clé (ex: error_correction:users_api:1234)
            parts = err.key.split(':')
            service_name = parts[1] if len(parts) > 1 else "Système"
            compiled_value += f"- [{service_name}] {data.get('rule', '')}\n"
        except Exception:
            # Rétrocompatibilité si d'anciens enregistrements en texte brut existent
            compiled_value += f"- {err.value}\n"
            
    compiled_prompt = schemas.Prompt(key=prompt.key, value=compiled_value)
    return compiled_prompt

