"""
config.py — Variables d'environnement et constantes partagées du cv_api.

Ce module centralise TOUTES les variables d'environnement et constantes de
configuration consommées par les services cv_api. Il est importé par tous
les autres modules du service layer.

Règle AGENTS.md §4 : aucun modèle IA hardcodé — utiliser les variables d'environnement.
"""

import logging
import os

from google import genai
from google.genai.types import HttpOptions

logger = logging.getLogger(__name__)

# ── URLs des microservices internes ──────────────────────────────────────────
USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8000")
COMPETENCIES_API_URL = os.getenv("COMPETENCIES_API_URL", "http://competencies_api:8003")
PROMPTS_API_URL = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
DRIVE_API_URL = os.getenv("DRIVE_API_URL", "http://drive_api:8006")
ITEMS_API_URL = os.getenv("ITEMS_API_URL", "http://items_api:8001")
MISSIONS_API_URL = os.getenv("MISSIONS_API_URL", "http://missions_api:8000")
ANALYTICS_MCP_URL = os.getenv("ANALYTICS_MCP_URL", "http://analytics_mcp:8008")

# ── Credentials service account (tâches de fond longue durée) ────────────────
# AGENTS.md §4 : les tâches longues doivent utiliser un compte de service dédié.
# Ces variables permettent d'obtenir un service-token via /internal/service-token.
ADMIN_SERVICE_USERNAME = os.getenv("ADMIN_SERVICE_USERNAME", "")
ADMIN_SERVICE_PASSWORD = os.getenv("ADMIN_SERVICE_PASSWORD", "")
os.environ.pop("ADMIN_SERVICE_PASSWORD", None)

# ── GCP / Gemini ────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY", "")
os.environ.pop("GOOGLE_API_KEY", None)
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "europe-west1")
BATCH_GCS_BUCKET = os.getenv("BATCH_GCS_BUCKET", "")

# Redirection vers mock_gemini si GEMINI_API_BASE_URL est défini (mode perf local)
GEMINI_API_BASE_URL: str = os.getenv("GEMINI_API_BASE_URL", "")
_http_opts = HttpOptions(baseUrl=GEMINI_API_BASE_URL) if GEMINI_API_BASE_URL else None
try:
    if GEMINI_API_KEY or GEMINI_API_BASE_URL:
        # PRD : clé réelle. Perf-test local : mock-key-local + baseUrl mock_gemini.
        client = genai.Client(
            api_key=GEMINI_API_KEY or "mock-key-local",
            http_options=_http_opts,
        )
    else:
        # Comportement original préservé : client=None si aucune config Gemini.
        # Produit un 503 explicite au lieu d'un 401 opaque.
        client = None
except Exception as e:
    logger.warning("[config] Gemini client init failed (api_key mode): %s — cv_extraction disabled", e)
    client = None

try:
    # VERTEX_API_BASE_URL : redirection vers mock_gemini pour les batch jobs (mode perf local).
    # En PRD : absent → None → appels Vertex AI normaux (ADC / service account).
    VERTEX_API_BASE_URL: str = os.getenv("VERTEX_API_BASE_URL", "")
    _vertex_http_opts = HttpOptions(baseUrl=VERTEX_API_BASE_URL) if VERTEX_API_BASE_URL else None
    if GCP_PROJECT_ID and VERTEX_LOCATION:
        vertex_batch_client = genai.Client(
            vertexai=True,
            project=GCP_PROJECT_ID,
            location=VERTEX_LOCATION,
            http_options=_vertex_http_opts,
        )
    else:
        vertex_batch_client = None
except Exception as e:
    logger.warning("[config] Vertex batch client init failed: %s — bulk re-analyse disabled", e)
    vertex_batch_client = None

# ── Parallélisme du pipeline bulk-reanalyse (configurable via env) ────────────
# BULK_APPLY_SEMAPHORE : nombre de CVs appliqués simultanément (DB + HTTP).
#   Défaut 5 — safe pour AlloyDB avec pool_size=20 (5 workers × 3 conn max = 15).
# BULK_EMBED_SEMAPHORE : nombre d'appels Gemini Embedding API simultanés.
#   Défaut 10 — conservative vs quota Gemini Embedding (600 QPM Vertex AI).
BULK_APPLY_SEMAPHORE: int = int(os.getenv("BULK_APPLY_SEMAPHORE", "5"))
BULK_EMBED_SEMAPHORE: int = int(os.getenv("BULK_EMBED_SEMAPHORE", "10"))
# ITEMS_DELETE_SEMAPHORE : limite la concurrence des DELETE /user/{id}/items vers items-api-prd.
# Le pipeline bulk-apply lance BULK_APPLY_SEMAPHORE workers simultanés, chacun faisant un DELETE
# items en parallèle. Sans sémaphore dédié, cela sature le pool AlloyDB de items-api → 500.
# Défaut 2 : conservatif vs items-api pool_size=10 (laisse de la marge aux requêtes API normales).
ITEMS_DELETE_SEMAPHORE: int = int(os.getenv("ITEMS_DELETE_SEMAPHORE", "2"))

# ── Scaling dynamique des Cloud Run cibles pendant le Bulk Apply ──────────────
# CLOUDRUN_WORKSPACE : workspace Terraform (ex: "prd", "dev") — injecté via cr_cv.tf.
# BULK_SCALE_SERVICES : noms logiques des services à scaler (sans workspace suffix).
CLOUDRUN_WORKSPACE: str = os.getenv("CLOUDRUN_WORKSPACE", "")
BULK_SCALE_SERVICES: list[str] = ["competencies-api", "items-api"]

# Nombre d'instances minimum à maintenir PENDANT la phase APPLY.
# Défaut 1 : évite les cold starts AlloyDB IAM (~15s) sans sur-provisionner.
BULK_SCALE_MIN_INSTANCES: int = int(os.getenv("BULK_SCALE_MIN_INSTANCES", "1"))

# Le cache en mémoire (ancien _CV_CACHE) a été supprimé.
# Veuillez utiliser la librairie partagée `shared.cache` pour un cache Redis distribué
# (respect de la Golden Rule §6 — namespaces DB isolés, un DB par service).
