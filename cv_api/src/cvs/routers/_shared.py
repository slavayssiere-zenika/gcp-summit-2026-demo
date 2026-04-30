"""
Shared constants, logger, and CV response schema for all cv_api sub-routers.
Single source of truth — imported by profile_router, search_router, taxonomy_router,
bulk_router and analytics_router to avoid duplication.
"""
import logging
import os
from datetime import datetime

# ── Logger ────────────────────────────────────────────────────────────────────
logger = logging.getLogger("src.cvs")

# ── URL constants ─────────────────────────────────────────────────────────────
USERS_API_URL        = os.getenv("USERS_API_URL",        "http://users_api:8000")
COMPETENCIES_API_URL = os.getenv("COMPETENCIES_API_URL", "http://competencies_api:8003")
PROMPTS_API_URL      = os.getenv("PROMPTS_API_URL",      "http://prompts_api:8000")
DRIVE_API_URL        = os.getenv("DRIVE_API_URL",        "http://drive_api:8006")
ITEMS_API_URL        = os.getenv("ITEMS_API_URL",        "http://items_api:8001")
MISSIONS_API_URL     = os.getenv("MISSIONS_API_URL",     "http://missions_api:8000")
ANALYTICS_MCP_URL    = os.getenv("ANALYTICS_MCP_URL",   "http://analytics_mcp:8008")
GCP_PROJECT_ID       = os.getenv("GCP_PROJECT_ID",      "")
VERTEX_LOCATION      = os.getenv("VERTEX_LOCATION",      "europe-west1")
BATCH_GCS_BUCKET     = os.getenv("BATCH_GCS_BUCKET",    "")
CLOUDRUN_WORKSPACE   = os.getenv("CLOUDRUN_WORKSPACE",  "")
BULK_SCALE_SERVICES: list[str] = ["competencies-api", "items-api"]

# Admin credentials for long-running background tasks (AGENTS.md §4)
ADMIN_SERVICE_USERNAME = os.getenv("ADMIN_SERVICE_USERNAME", "")
ADMIN_SERVICE_PASSWORD = os.getenv("ADMIN_SERVICE_PASSWORD", "")

# Parallelism config
BULK_APPLY_SEMAPHORE:     int = int(os.getenv("BULK_APPLY_SEMAPHORE",     "5"))
BULK_EMBED_SEMAPHORE:     int = int(os.getenv("BULK_EMBED_SEMAPHORE",     "10"))
BULK_SCALE_MIN_INSTANCES: int = int(os.getenv("BULK_SCALE_MIN_INSTANCES", "1"))

# ── Schéma JSON partagé entre route unitaire ET batch Vertex ─────────────────
# Toute modification ici s'applique automatiquement aux deux pipelines.
CV_RESPONSE_SCHEMA: dict = {
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
                    "parent": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "practiced": {
                        "type": "boolean",
                        "description": "True if the consultant has actively used this skill in at least one mission."
                    }
                },
                "required": ["name", "practiced"]
            }
        },
        "missions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "company": {"type": "string"},
                    "description": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM or YYYY, null if unknown"},
                    "end_date": {"type": "string", "description": "YYYY-MM, YYYY, 'present', or null"},
                    "duration": {"type": "string", "description": "Explicit duration from CV text, null if not stated"},
                    "mission_type": {"type": "string", "description": "One of: audit, conseil, accompagnement, formation, expertise, build"},
                    "is_sensitive": {"type": "boolean"},
                    "competencies": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["title", "competencies", "is_sensitive", "mission_type"]
            }
        },
        "educations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "degree": {"type": "string"},
                    "school": {"type": "string"}
                }
            }
        },
        "is_anonymous": {"type": "boolean"},
        "trigram": {"type": "string"}
    },
    "required": ["is_cv", "first_name", "last_name", "email", "summary", "current_role",
                 "years_of_experience", "competencies", "missions", "educations", "is_anonymous"]
}

# Backward-compat alias (used in some older service code)
_CV_RESPONSE_SCHEMA = CV_RESPONSE_SCHEMA

# ── Pydantic models shared between sub-routers ─────────────────────────────
# These were defined inline in the original monolithic router.py.
# Centralised here so that both taxonomy_router and search_router can import them.
from typing import Optional, List
from pydantic import BaseModel


class RecalculateStepRequest(BaseModel):
    """Request body for POST /recalculate_tree/step."""
    step: str
    target_pillar: Optional[str] = None


class MultiCriteriaSearchRequest(BaseModel):
    """Request body for POST /search/multi-criteria."""
    queries: List[str]
    weights: Optional[List[float]] = None
    limit: int = 10
    agency: Optional[str] = None
