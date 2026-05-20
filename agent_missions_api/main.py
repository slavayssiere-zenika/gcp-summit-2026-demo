import logging
import os
import time
from contextlib import asynccontextmanager

import redis as _sync_redis  # noqa: F401 — compat import pour _get_hitl_redis
import httpx  # noqa: F401
import uvicorn
from agent import MISSIONS_TOOLS, run_agent_query
from agent_commons.a2a_utils import make_agent_card
from agent_commons.exception_handler import make_global_exception_handler
from agent_commons.mcp_client import auth_header_var  # noqa: F401
from agent_commons.schemas import (A2ARequest, A2AResponse, QueryRequest)  # noqa: F401
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response  # noqa: F401
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from hitl_router import hitl_create_entry, hitl_router  # noqa: F401
from metrics import QUERY_COUNT, QUERY_LATENCY
from opentelemetry import trace
from opentelemetry.propagate import extract, inject  # noqa: F401
from opentelemetry.trace import SpanKind
from pydantic import BaseModel  # noqa: F401
from session_router import session_router
from shared.auth.jwt import ALGORITHM  # noqa: F401
from shared.auth.jwt import verify_jwt_bearer, verify_jwt_request as verify_jwt
from shared.fastapi_utils import instrument_app, setup_tracing
from shared.observability import setup_logging
from agent_commons.session import RedisSessionService
from agent import _MISSIONS_CLIENTS_MAP, _MISSIONS_TOOLS_CACHE
from agent_commons.mcp_proxy import get_cached_tools

# Exposé pour les tests (import 'from main import SECRET_KEY')
SECRET_KEY = os.getenv("SECRET_KEY", "")

logger = logging.getLogger(__name__)

APP_VERSION = os.getenv("APP_VERSION", "v0.1.0")
ROOT_PATH = os.getenv("ROOT_PATH", "")

# JWT — validation de SECRET_KEY déléguée à shared.auth.jwt (fail-fast à l'import)

# ── Auth (JWT) — délégué à agent_commons.jwt_middleware.verify_jwt_request ──────
# verify_jwt = verify_jwt_request importé en tête de fichier


# ── Session service (lazy singleton) ──────────────────────────────────────────
_session_service = None


def get_session_service():
    global _session_service
    if _session_service is None:
        _session_service = RedisSessionService(
            redis_key_prefix="adk:missions:sessions",
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379/12"),
        )
    return _session_service


# ── Lifecycle ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[MISSIONS] 🚀 Starting agent_missions_api %s", APP_VERSION)
    try:

        tools = await get_cached_tools(_MISSIONS_CLIENTS_MAP, "[MISSIONS]", ttl=300, _cache=_MISSIONS_TOOLS_CACHE)
        logger.info("[MISSIONS] ✅ Pre-warmed %d MCP tools at startup.", len(tools))
    except Exception as e:
        logger.warning("[MISSIONS] Could not pre-warm tools cache: %s", e)
    yield
    logger.info("[MISSIONS] 🛑 Shutting down agent_missions_api.")


# ── FastAPI App ────────────────────────────────────────────────────────────────

# Leak Mitigation (Anti prompt-injection / introspection)
os.environ.pop("JWT_SECRET", None)
os.environ.pop("SECRET_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("ADMIN_SERVICE_PASSWORD", None)
app = FastAPI(
    title="Agent Missions API",
    description="Staffing Director — missions client & matching consultants (A2A Worker)",
    version=APP_VERSION,
    root_path=ROOT_PATH,
    lifespan=lifespan,
)

cors_origins_str = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:80,http://localhost:8080,"
    "https://dev.zenika.slavayssiere.fr,https://uat.zenika.slavayssiere.fr,"
    "https://zenika.slavayssiere.fr"
)
cors_origins = cors_origins_str.split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
instrument_app(
    app,
    service_name="agent-missions-api",
    register_exception_handler=False,
)
setup_tracing(service_name="agent-missions-api", app_version=APP_VERSION)
_tracer = trace.get_tracer("agent_missions_api")
setup_logging()  # Initialisation du logging JSON structuré

# ── Pydantic models — QueryRequest migré dans agent_commons.schemas ──────────


# ── Public endpoints (no JWT) ──────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "agent_missions_api", "version": APP_VERSION}


@app.get("/version")
async def version():
    return {"version": APP_VERSION}


@app.get("/.well-known/agent.json", include_in_schema=False)
async def agent_card():
    """A2A v2 — Service Discovery endpoint (google-adk 1.33+)."""
    return make_agent_card(
        name="Missions Agent (Staffing Director)",
        description=(
            "Sous-agent spécialisé missions client : listing, staffing IA, "
            "matching consultants/mission, cycle de vie et recommandations d'équipe. "
            "NE PAS utiliser pour la gestion des profils RH, l'import de CVs ou les coûts IA."
        ),
        url_env_var="AGENT_MISSIONS_API_URL",
        default_url="http://agent_missions_api:8080",
        skills=[
            {
                "id": "mission_listing",
                "name": "Listing des missions",
                "description": (
                    "Liste et filtre les missions client par statut, compétences requises ou équipe. "
                    "Retourne le détail d'une mission spécifique si un ID est fourni."
                ),
                "tags": ["missions", "liste", "filtre", "statut", "client"],
                "trigger_keywords": [
                    "mission", "missions", "projet", "appel d'offres", "client",
                    "liste des missions", "quelles missions", "quel projet",
                ],
            },
            {
                "id": "staffing",
                "name": "Staffing IA",
                "description": (
                    "Propose une équipe de consultants qualifiés pour une mission donnée "
                    "via recherche sémantique RAG. Analyse les compétences requises et "
                    "retourne les meilleurs profils disponibles avec un score de matching."
                ),
                "tags": ["staffing", "matching", "RAG", "équipe", "profils"],
                "trigger_keywords": [
                    "staff", "staffing", "propose une équipe", "qui peut faire",
                    "matching", "consultant pour cette mission", "recommande",
                    "quelle équipe", "meilleur profil pour",
                ],
            },
            {
                "id": "mission_lifecycle",
                "name": "Cycle de vie mission",
                "description": (
                    "Gère le cycle de vie d'une mission : changement de statut "
                    "(DRAFT → WON/NO_GO/CANCELLED), re-lancement de l'analyse IA, "
                    "clôture et archivage."
                ),
                "tags": ["statut", "cycle de vie", "analyse", "WON", "NO_GO"],
                "trigger_keywords": [
                    "statut", "changer le statut", "clôturer", "WON", "NO_GO",
                    "mission gagnée", "mission perdue", "archiver",
                ],
            },
            {
                "id": "mission_analysis",
                "name": "Analyse documentaire mission",
                "description": (
                    "Analyse les documents d'une mission (appel d'offres, cahier des charges) "
                    "pour en extraire les compétences requises, les délais et les contraintes."
                ),
                "tags": ["analyse", "document", "extraction", "compétences requises"],
                "trigger_keywords": [
                    "analyser cette mission", "extraire les compétences", "cahier des charges",
                    "appel d'offres", "que demande cette mission",
                ],
            },
        ],
        routing_hints={
            "do_use_when": [
                "L'utilisateur parle de missions CLIENT (appels d'offres, projets, contrats)",
                "L'utilisateur veut stafter une mission ou trouver une équipe pour un projet",
                "L'utilisateur veut voir la liste ou le détail d'une mission",
                "L'utilisateur veut changer le statut d'une mission (WON, NO_GO, etc.)",
            ],
            "do_not_use_when": [
                "L'utilisateur cherche un consultant nommé ou son profil RH → utiliser hr_agent",
                "L'utilisateur parle de CVs, de compétences individuelles → utiliser hr_agent",
                "L'utilisateur parle de coûts IA ou de santé système → utiliser ops_agent",
            ],
        },
        examples=[
            {"query": "Liste les missions en cours", "skill": "mission_listing"},
            {"query": "Propose une équipe pour la mission #42", "skill": "staffing"},
            {"query": "Marque la mission Alpha comme WON", "skill": "mission_lifecycle"},
            {"query": "Quelles compétences sont requises pour la mission Société Générale ?",
             "skill": "mission_analysis"},
        ],
    )

# ── Protected router — JWT validé via Depends sur le routeur ────
protected_router = APIRouter(dependencies=[Depends(verify_jwt)])


async def _execute_query(request: QueryRequest, http_request: Request, payload: dict) -> A2AResponse:
    """Logique partagée entre /query et /a2a/query."""
    start_time = time.time()
    user_id = request.user_id or payload.get("sub") or "unknown@zenika.com"
    auth_header = http_request.headers.get("Authorization")

    QUERY_COUNT.labels(agent="missions", status="started").inc()
    logger.info("[MISSIONS] Query received user_id=%s session=%s", user_id, request.session_id)

    try:
        result = await run_agent_query(
            query=request.query,
            session_id=request.session_id,
            auth_token=auth_header,
            user_id=user_id,
        )
        QUERY_COUNT.labels(agent="missions", status="success").inc()
        return A2AResponse(
            response=result.get("response", ""),
            data=result.get("data"),
            display_type=result.get("display_type"),
            steps=result.get("steps", []),
            thoughts=result.get("thoughts", ""),
            usage=result.get("usage", {}),
            source=result.get("source"),
            session_id=result.get("session_id"),
        )
    except Exception as e:
        QUERY_COUNT.labels(agent="missions", status="error").inc()
        logger.error("[MISSIONS] Agent error: %s", e, exc_info=True)
        # ADK v2 — réponse dégradée plutôt qu'un HTTP 500 non géré.
        # Bénéficie à /query et /a2a/query via ce handler partagé.
        return A2AResponse(
            response=f"⚠️ L'agent Missions a rencontré une erreur technique : {type(e).__name__}.",
            source="error",
            steps=[{"type": "warning", "tool": "_execute_query", "args": {"message": str(e)}}],
        )
    finally:
        elapsed = time.time() - start_time
        QUERY_LATENCY.labels(agent="missions").observe(elapsed)
        logger.info("[MISSIONS] Query completed in %.2fs", elapsed)


@protected_router.post("/query", response_model=A2AResponse)
async def query_agent(request: A2ARequest, http_request: Request, payload: dict = Depends(verify_jwt)):
    """
    Point d'entrée direct — utilisé par le frontend ou pour les tests directs.
    Exécute le pipeline de staffing et retourne le résultat structuré.
    """
    return await _execute_query(request, http_request, payload)


@protected_router.post("/a2a/query", response_model=A2AResponse)
async def a2a_query_agent(
    request: A2ARequest,
    http_request: Request,
    auth: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    payload: dict = Depends(verify_jwt_bearer),
):
    """
    Point d'entrée A2A — appelé exclusivement par agent_router_api (service-to-service).
    Exige un Bearer token strict (via HTTPBearer) — pas de cookie accepté.
    Valide le payload entrant (A2ARequest) et la réponse (A2AResponse) via le contrat Pydantic ADR12-4.
    Rattache le span OTel au contexte de trace propagé par le Router.
    """
    ctx = extract(http_request.headers)
    with _tracer.start_as_current_span("missions.a2a.query", context=ctx, kind=SpanKind.SERVER) as span:
        span.set_attribute("query.text", request.query[:100])
        user_id = request.user_id or payload.get("sub", "unknown")
        span.set_attribute("user.id", user_id)
        return await _execute_query(request, http_request, payload)


app.include_router(session_router)


@app.get("/spec")
async def get_spec():
    """Retourne la spécification métier de l'agent Missions."""
    try:
        with open("spec.md", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/markdown")
    except Exception as e:
        logger.debug("[spec] spec.md not found or unreadable: %s: %s", type(e).__name__, e)
        return Response(
            content="# Agent Missions API\n\nStaffing Director — gestion des missions client et matching consultants.",
            media_type="text/markdown",
        )


@protected_router.get("/mcp/registry")
async def mcp_registry(_payload: dict = Depends(verify_jwt)):
    """Liste les outils MCP disponibles pour cet agent (debug/introspection)."""
    return {
        "agent": "agent_missions_api",
        "tools": [
            {"name": fn.__name__, "description": fn.__doc__ or ""}
            for fn in MISSIONS_TOOLS
        ],
        "count": len(MISSIONS_TOOLS),
    }


app.include_router(hitl_router)
app.include_router(protected_router)

app.add_exception_handler(Exception, make_global_exception_handler("agent_missions_api"))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
