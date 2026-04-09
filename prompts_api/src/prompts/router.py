import os
import json
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
        except Exception:
            pass

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
        except Exception:
            pass

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

from .analyzer import generate_test_cases, run_promptfoo_analysis, improve_prompt_with_gemini

@router.post("/{key}/analyze", response_model=schemas.AnalysisResponse)
async def analyze_prompt(key: str, db: AsyncSession = Depends(get_db), admin: dict = Depends(verify_admin)):
    prompt = (await db.execute(select(models.Prompt).filter(models.Prompt.key == key))).scalars().first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
        
    original = prompt.value
    
    try:
        # 1. Generate test cases
        test_cases = generate_test_cases(original)
        if not test_cases:
            raise HTTPException(status_code=500, detail="Failed to generate test cases.")
            
        # 2. Run promptfoo eval
        eval_results = run_promptfoo_analysis(original, test_cases)
        
        # 3. Generate improved prompt
        improved = improve_prompt_with_gemini(original, eval_results)
        
        return schemas.AnalysisResponse(
            original_prompt=original,
            improved_prompt=improved,
            promptfoo_report=eval_results
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

