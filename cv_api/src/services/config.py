"""
config.py — Variables d'environnement et constantes partagées du cv_api.

Ce module centralise TOUTES les variables d'environnement et constantes de
configuration consommées par les services cv_api. Il est importé par tous
les autres modules du service layer.

Règle AGENTS.md §4 : aucun modèle IA hardcodé — utiliser les variables d'environnement.
"""

import os
from datetime import datetime, timezone
from google import genai

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

# ── GCP / Gemini ────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "europe-west1")
BATCH_GCS_BUCKET = os.getenv("BATCH_GCS_BUCKET", "")

try:
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
    else:
        client = None
except Exception:
    client = None

try:
    if GCP_PROJECT_ID and VERTEX_LOCATION:
        vertex_batch_client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=VERTEX_LOCATION)
    else:
        vertex_batch_client = None
except Exception:
    vertex_batch_client = None

# ── Parallélisme du pipeline bulk-reanalyse (configurable via env) ────────────
# BULK_APPLY_SEMAPHORE : nombre de CVs appliqués simultanément (DB + HTTP).
#   Défaut 5 — safe pour AlloyDB avec pool_size=20 (5 workers × 3 conn max = 15).
# BULK_EMBED_SEMAPHORE : nombre d'appels Gemini Embedding API simultanés.
#   Défaut 10 — conservative vs quota Gemini Embedding (600 QPM Vertex AI).
BULK_APPLY_SEMAPHORE: int = int(os.getenv("BULK_APPLY_SEMAPHORE", "5"))
BULK_EMBED_SEMAPHORE: int = int(os.getenv("BULK_EMBED_SEMAPHORE", "10"))

# ── Scaling dynamique des Cloud Run cibles pendant le Bulk Apply ──────────────
# CLOUDRUN_WORKSPACE : workspace Terraform (ex: "prd", "dev") — injecté via cr_cv.tf.
# BULK_SCALE_SERVICES : noms logiques des services à scaler (sans workspace suffix).
CLOUDRUN_WORKSPACE: str = os.getenv("CLOUDRUN_WORKSPACE", "")
BULK_SCALE_SERVICES: list[str] = ["competencies-api", "items-api"]

# Nombre d'instances minimum à maintenir PENDANT la phase APPLY.
# Défaut 1 : évite les cold starts AlloyDB IAM (~15s) sans sur-provisionner.
BULK_SCALE_MIN_INSTANCES: int = int(os.getenv("BULK_SCALE_MIN_INSTANCES", "1"))

# ── Cache mémoire en process (TTL-based) ─────────────────────────────────────
# Partagé entre cv_import_service et bulk_service via ce module.
# Invalidation via force_invalidate_taxonomy_cache (endpoint POST /cache/invalidate-taxonomy).
_CV_CACHE: dict = {
    "prompt": {"value": None, "expires": datetime.min.replace(tzinfo=timezone.utc)},
    "tree_items": {"value": None, "expires": datetime.min.replace(tzinfo=timezone.utc)},
    "tree_context": {"value": None, "expires": datetime.min.replace(tzinfo=timezone.utc)},
    # Cache du rapport data quality (TTL 30s — aligné sur le polling frontend)
    "data_quality": {"value": None, "expires": datetime.min.replace(tzinfo=timezone.utc)},
}

