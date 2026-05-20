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
  - Deux latences distinctes :
      MOCK_LLM_LATENCY_MAX_S      → generateContent (simulation d'inférence LLM, défaut 3s)
      MOCK_LLM_EMBED_LATENCY_MAX_S → embedContent/batchEmbedContents (lookup O(1), défaut 0s)
  - Embedding dimension : MOCK_LLM_EMBEDDING_DIM (défaut 3072, aligné sur gemini-embedding-001)
  - 256 vecteurs unitaires pré-générés au démarrage → réponse embedding en O(1) par hash MD5
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
# Latence pour generateContent (simulation d'inférence LLM)
LATENCY_MAX_S: float = float(os.getenv("MOCK_LLM_LATENCY_MAX_S", "3"))
# Latence pour embedContent / batchEmbedContents (lookup O(1) dans le pool pré-généré)
# Défaut 0s : les vecteurs sont servis depuis le pool en mémoire, aucune raison d'attendre.
EMBED_LATENCY_MAX_S: float = float(os.getenv("MOCK_LLM_EMBED_LATENCY_MAX_S", "0"))
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
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"[mock_gemini] Critical: JSON pool file {DATA_FILE} is missing!")

    try:
        with DATA_FILE.open(encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list):
            # Format liste : traiter comme cv_extractions directement
            _POOL = {"cv_extractions": raw, "embeddings_pool": []}
        elif isinstance(raw, dict):
            _POOL = raw
        else:
            raise ValueError(f"[mock_gemini] Format JSON inattendu : {type(raw)}")
        logger.info(
            "[mock_gemini] Pool chargé : %d CV, %d vecteurs",
            len(_POOL.get("cv_extractions", [])),
            len(_POOL.get("embeddings_pool", [])),
        )
    except Exception as e:
        logger.error("[mock_gemini] Échec critique du chargement de %s : %s", DATA_FILE, e)
        raise


def _pick_by_hash(pool: list, text: str):
    """Sélectionne un élément du pool de façon déterministe par hash MD5."""
    if not pool:
        return None
    idx = int(hashlib.md5(text.encode()).hexdigest(), 16) % len(pool)
    return pool[idx]


# Pool de vecteurs aléatoires pré-générés pour éviter les calculs CPU intensifs en cours de test
_PREGENERATED_VECTORS: list[list[float]] = []


def _pregenerate_vectors(count: int = 256, dim: int = 3072) -> None:
    """Pré-génère un ensemble de vecteurs unitaires pour éviter les boucles CPU-bound sous charge."""
    logger.info("[mock_gemini] Pré-génération de %d vecteurs de dimension %d...", count, dim)
    random.seed(42)  # Fixer le seed pour avoir des vecteurs reproductibles au démarrage
    for _ in range(count):
        v = [random.gauss(0, 1) for _ in range(dim)]
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        _PREGENERATED_VECTORS.append([x / norm for x in v])
    random.seed()  # reset seed
    logger.info("[mock_gemini] Pré-génération de %d vecteurs terminée.", count)


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
    # Si le pool d'embeddings est vide ou incomplet, retourner un vecteur pré-généré déterministe
    if _PREGENERATED_VECTORS:
        idx = int(hashlib.md5(text.encode()).hexdigest(), 16) % len(_PREGENERATED_VECTORS)
        return _PREGENERATED_VECTORS[idx]
    # Fallback de sécurité (normalement jamais atteint)
    random.seed(int(hashlib.md5(text.encode()).hexdigest(), 16))
    result = _random_unit_vector(EMBEDDING_DIM)
    random.seed()
    return result


async def _inject_latency(max_s: float | None = None) -> None:
    """Délai aléatoire uniforme [0, max_s] pour simuler le temps de réponse.

    - generateContent  → max_s=LATENCY_MAX_S  (défaut 3s, simule l'inférence LLM)
    - embedContent     → max_s=EMBED_LATENCY_MAX_S (défaut 0s, lookup O(1) depuis pool)
    """
    effective = LATENCY_MAX_S if max_s is None else max_s
    if effective > 0:
        await asyncio.sleep(random.uniform(0, effective))


# ── Application ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_pool()
    _pregenerate_vectors(count=256, dim=EMBEDDING_DIM)
    logger.info(
        "[mock_gemini] Démarré — LATENCY_MAX_S=%.1fs / EMBED_LATENCY_MAX_S=%.1fs / EMBEDDING_DIM=%d",
        LATENCY_MAX_S,
        EMBED_LATENCY_MAX_S,
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
    # Latence embedding : 0s par défaut (lookup O(1) depuis pool pré-généré)
    await _inject_latency(max_s=EMBED_LATENCY_MAX_S)

    body = await request.json()
    text = ""
    content = body.get("content", {})
    for part in content.get("parts", []):
        text += part.get("text", "")

    return JSONResponse({"embedding": {"values": _get_embedding(text)}})


# ── batchEmbedContents ─────────────────────────────────────────────────────────
@app.post("/{version}/models/{model_id}:batchEmbedContents")
async def batch_embed_contents(version: str, model_id: str, request: Request):
    # Latence embedding : 0s par défaut (lookups O(1) depuis pool pré-généré)
    await _inject_latency(max_s=EMBED_LATENCY_MAX_S)

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
