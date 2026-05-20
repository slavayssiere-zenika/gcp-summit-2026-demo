"""
mock_gemini/main.py — Mock du service Google Generative AI (google-genai >= 2.0.0).

Implémente les endpoints REST consommés par le SDK côté cv_api :
  POST /{version}/models/{model}:generateContent      → extraction structurée CV
  POST /{version}/models/{model}:embedContent         → embedding unitaire
  POST /{version}/models/{model}:batchEmbedContents   → batch embeddings
  GET  /{version}/models                              → liste des modèles (SDK health)
  GET  /{version}/models/{model}                      → info modèle

Comportement :
  - Charge mock_responses.json au démarrage (pool de 20 CV extractions + vecteurs)
  - Sélectionne une réponse par hash MD5 du texte d'entrée (prédictif / reproductible)
  - Injecte un délai uniforme aléatoire [0, MOCK_LLM_LATENCY_MAX_S] secondes
  - Embedding dimension : MOCK_LLM_EMBEDDING_DIM (défaut 3072, aligné sur gemini-embedding-001)
"""

import asyncio
import hashlib
import json
import logging
import math
import os
import random
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("mock_gemini")
logging.basicConfig(level=logging.INFO)

# ── Configuration ─────────────────────────────────────────────────────────────
LATENCY_MAX_S: float = float(os.getenv("MOCK_LLM_LATENCY_MAX_S", "3"))
EMBEDDING_DIM: int = int(os.getenv("MOCK_LLM_EMBEDDING_DIM", "3072"))
DATA_FILE: Path = Path(os.getenv("MOCK_DATA_FILE", "/data/mock_responses.json"))

# ── Pool de réponses ──────────────────────────────────────────────────────────
_POOL: dict = {"cv_extractions": [], "embeddings_pool": []}


def _load_pool() -> None:
    """Charge mock_responses.json depuis le volume monté.

    Accepte deux formats :
    - Dict  : {"cv_extractions": [...], "embeddings_pool": [...]}  (format canonique)
    - Liste : [extraction1, extraction2, ...]  (format compact — mock_cv_pool.json)
    """
    global _POOL
    if DATA_FILE.exists():
        try:
            with DATA_FILE.open() as f:
                raw = json.load(f)
            if isinstance(raw, list):
                # Format liste : traiter comme cv_extractions directement
                _POOL = {"cv_extractions": raw, "embeddings_pool": []}
            elif isinstance(raw, dict):
                _POOL = raw
            else:
                logger.warning("[mock_gemini] Format JSON inattendu (%s) — pool vide", type(raw))
                return
            logger.info(
                "[mock_gemini] Pool chargé : %d CV, %d vecteurs",
                len(_POOL.get("cv_extractions", [])),
                len(_POOL.get("embeddings_pool", [])),
            )
        except Exception as e:
            logger.warning("[mock_gemini] Impossible de charger %s : %s — pool vide", DATA_FILE, e)
    else:
        logger.warning("[mock_gemini] %s introuvable — réponses synthétiques utilisées", DATA_FILE)


def _pick_by_hash(pool: list, text: str):
    """Sélectionne un élément du pool de façon déterministe par hash MD5."""
    if not pool:
        return None
    idx = int(hashlib.md5(text.encode()).hexdigest(), 16) % len(pool)
    return pool[idx]


def _random_unit_vector(dim: int) -> list[float]:
    """Génère un vecteur unitaire aléatoire de dimension `dim` (embeddings synthétiques)."""
    v = [random.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def _get_embedding(text: str) -> list[float]:
    """Retourne un vecteur depuis le pool (ou synthétique) selon le hash du texte."""
    pool = _POOL.get("embeddings_pool", [])
    vec = _pick_by_hash(pool, text)
    if vec and len(vec) == EMBEDDING_DIM:
        return vec
    # Génère un vecteur synthétique reproductible via seed fixé sur le hash
    random.seed(int(hashlib.md5(text.encode()).hexdigest(), 16))
    result = _random_unit_vector(EMBEDDING_DIM)
    random.seed()
    return result


async def _inject_latency() -> None:
    """Délai aléatoire uniforme [0, LATENCY_MAX_S] pour simuler le temps LLM."""
    if LATENCY_MAX_S > 0:
        await asyncio.sleep(random.uniform(0, LATENCY_MAX_S))


# ── Application ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_pool()
    logger.info(
        "[mock_gemini] Démarré — LATENCY_MAX_S=%.1f, EMBEDDING_DIM=%d",
        LATENCY_MAX_S,
        EMBEDDING_DIM,
    )
    yield


app = FastAPI(title="Mock Gemini API", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "pool_size": len(_POOL.get("cv_extractions", []))}


# ── Models list (SDK health check) ────────────────────────────────────────────
@app.get("/{version}/models")
async def list_models(version: str):
    return {
        "models": [
            {"name": f"models/{m}", "displayName": m, "supportedGenerationMethods": ["generateContent"]}
            for m in ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro",
                      "text-embedding-004", "gemini-embedding-001"]
        ]
    }


@app.get("/{version}/models/{model_id}")
async def get_model(version: str, model_id: str):
    return {
        "name": f"models/{model_id}",
        "displayName": model_id,
        "supportedGenerationMethods": ["generateContent", "embedContent"],
    }


# ── generateContent ────────────────────────────────────────────────────────────
@app.post("/{version}/models/{model_id}:generateContent")
async def generate_content(version: str, model_id: str, request: Request):
    await _inject_latency()

    body = await request.json()
    # Extraire le texte de la requête pour le hash déterministe
    input_text = ""
    for content in body.get("contents", []):
        for part in content.get("parts", []):
            input_text += part.get("text", "")

    # Sélectionner une extraction CV du pool
    cv_pool = _POOL.get("cv_extractions", [])
    extraction = _pick_by_hash(cv_pool, input_text) if cv_pool else None

    if extraction is None:
        # Extraction synthétique minimale si pool vide
        extraction = {
            "is_cv": True,
            "first_name": "Perf",
            "last_name": "Test",
            "email": f"perf.{hashlib.md5(input_text.encode()).hexdigest()[:8]}@mock.local",
            "summary": "Consultant senior simulé par le mock Gemini pour les tests de performance.",
            "current_role": "Senior Consultant",
            "years_of_experience": 7,
            "competencies": [
                {"name": "Python", "parent": "Langages", "aliases": [], "practiced": True},
                {"name": "FastAPI", "parent": "Frameworks", "aliases": [], "practiced": True},
                {"name": "PostgreSQL", "parent": "Bases de données", "aliases": [], "practiced": True},
            ],
            "missions": [
                {
                    "title": "Mission Perf Test",
                    "company": "Mock Corp",
                    "description": "Mission simulée par le mock Gemini.",
                    "start_date": "2022-01",
                    "end_date": "present",
                    "duration": "3 ans",
                    "mission_type": "build",
                    "is_sensitive": False,
                    "competencies": ["Python", "FastAPI"],
                }
            ],
            "educations": [{"degree": "Ingénieur", "school": "École Mock"}],
            "is_anonymous": False,
            "trigram": "PTU",
        }

    response_text = json.dumps(extraction, ensure_ascii=False)
    prompt_tokens = max(100, len(input_text) // 4)
    candidate_tokens = max(50, len(response_text) // 4)

    return JSONResponse({
        "candidates": [{
            "content": {
                "parts": [{"text": response_text}],
                "role": "model",
            },
            "finishReason": "STOP",
            "index": 0,
        }],
        "usageMetadata": {
            "promptTokenCount": prompt_tokens,
            "candidatesTokenCount": candidate_tokens,
            "totalTokenCount": prompt_tokens + candidate_tokens,
        },
        "modelVersion": model_id,
    })


# ── embedContent ───────────────────────────────────────────────────────────────
@app.post("/{version}/models/{model_id}:embedContent")
async def embed_content(version: str, model_id: str, request: Request):
    await _inject_latency()

    body = await request.json()
    text = ""
    content = body.get("content", {})
    for part in content.get("parts", []):
        text += part.get("text", "")

    return JSONResponse({"embedding": {"values": _get_embedding(text)}})


# ── batchEmbedContents ─────────────────────────────────────────────────────────
@app.post("/{version}/models/{model_id}:batchEmbedContents")
async def batch_embed_contents(version: str, model_id: str, request: Request):
    await _inject_latency()

    body = await request.json()
    embeddings = []
    for req_item in body.get("requests", []):
        text = ""
        for part in req_item.get("content", {}).get("parts", []):
            text += part.get("text", "")
        embeddings.append({"values": _get_embedding(text)})

    return JSONResponse({"embeddings": embeddings})


# ── Vertex AI Batch Prediction Jobs (competencies_api) ────────────────────────
_batch_jobs: dict = {}


@app.post("/v1/projects/{project}/locations/{location}/batchPredictionJobs")
async def create_batch_job(project: str, location: str, request: Request):
    """Mock Vertex AI Batch Prediction Job — retourne SUCCEEDED après LATENCY_MAX_S."""
    body = await request.json()
    job_id = hashlib.md5(json.dumps(body).encode()).hexdigest()[:12]
    _batch_jobs[job_id] = {"state": "JOB_STATE_RUNNING", "created": asyncio.get_event_loop().time()}
    return JSONResponse({
        "name": f"projects/{project}/locations/{location}/batchPredictionJobs/{job_id}",
        "state": "JOB_STATE_RUNNING",
        "displayName": body.get("displayName", "mock-batch"),
    }, status_code=200)


@app.get("/v1/projects/{project}/locations/{location}/batchPredictionJobs/{job_id}")
async def get_batch_job(project: str, location: str, job_id: str):
    """Poll status — SUCCEEDED dès que LATENCY_MAX_S est écoulé depuis la création."""
    job = _batch_jobs.get(job_id, {})
    now = asyncio.get_event_loop().time()
    elapsed = now - job.get("created", now)
    state = "JOB_STATE_SUCCEEDED" if elapsed >= LATENCY_MAX_S else "JOB_STATE_RUNNING"
    return JSONResponse({
        "name": f"projects/{project}/locations/{location}/batchPredictionJobs/{job_id}",
        "state": state,
    })
