from agent_commons.schemas import (A2ARequest, A2AResponse, QueryRequest,
                                   get_tool_metadata)
from agent_commons.mcp_client import auth_header_var
import logging
import os
# flake8: noqa: E402  — warnings.filterwarnings must precede third-party imports
import warnings
from contextlib import asynccontextmanager

import httpx
import uvicorn
from agent import HR_TOOLS, run_agent_query
from agent_commons.a2a_utils import make_agent_card
from fastapi import (APIRouter, Depends, FastAPI, HTTPException, Request,
                     Response)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
# Routes /history (GET + DELETE) extraites dans history_routes.py (Golden Rule §14)
from history_routes import history_router as _history_router
from metrics import AGENT_QUERIES_TOTAL
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.propagate import extract, inject
from shared.mcp_server_utils import setup_mcp_tracer_provider

from shared.fastapi_utils import instrument_app
from shared.observability import setup_logging

from agent_commons.exception_handler import make_global_exception_handler
from shared.auth.jwt import verify_jwt_bearer as verify_jwt

# Exposé pour les tests (import 'from main import SECRET_KEY, ALGORITHM')
import os as _os
SECRET_KEY = _os.getenv("SECRET_KEY", "")


warnings.filterwarnings("ignore", message=".*authlib.jose module is deprecated.*")

security = HTTPBearer()


if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter  # noqa: F401

tracer = trace.get_tracer(__name__)
setup_mcp_tracer_provider("agent-hr-api")

app_logger = logging.getLogger(__name__)

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting ADK Web Agent with Gemini...")
    yield

app = FastAPI(
    title="ADK HR Agent (A2A)",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    root_path=os.getenv("ROOT_PATH", "")
)
instrument_app(app, service_name="agent-hr-api", register_exception_handler=False)
RedisInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()


@app.get("/.well-known/agent.json", include_in_schema=False)
async def agent_card():
    """A2A v2 — Service Discovery endpoint (google-adk 1.33+)."""
    return make_agent_card(
        name="HR Agent (Talent & Compétences)",
        description=(
            "Sous-agent spécialisé RH : recherche de profils consultants, "
            "analyse de CVs, compétences, évaluation Gemini, disponibilité. "
            "NE PAS utiliser pour lister des missions client ou proposer une équipe de staffing."
        ),
        url_env_var="AGENT_HR_API_URL",
        default_url="http://agent_hr_api:8080",
        skills=[
            {
                "id": "consultant_search",
                "name": "Recherche de consultants",
                "description": (
                    "Trouve les consultants correspondant à des critères de compétences "
                    "ou de disponibilité. Supporte la recherche sémantique (RAG multi-critères)."
                ),
                "tags": ["consultant", "profil", "recherche", "RAG", "sémantique"],
                "trigger_keywords": [
                    "consultant", "profil", "trouver", "cherche", "disponible",
                    "qui a la compétence", "expert en", "liste des consultants",
                ],
            },
            {
                "id": "cv_analysis",
                "name": "Analyse de CV",
                "description": (
                    "Analyse un CV (Google Doc, PDF) et extrait les compétences, "
                    "missions passées et formations. Utiliser quand l'utilisateur "
                    "partage un lien Google Drive ou demande l'analyse d'un profil spécifique."
                ),
                "tags": ["CV", "extraction", "gemini", "google-doc", "drive"],
                "trigger_keywords": ["CV", "curriculum", "profil", "analyse", "google doc", "drive"],
            },
            {
                "id": "competency_scoring",
                "name": "Scoring de compétences",
                "description": (
                    "Évalue et score les compétences d'un consultant via l'IA Gemini. "
                    "Utile pour l'évaluation RH, le coaching CV, ou le scoring d'arbre taxonomique."
                ),
                "tags": ["scoring", "compétences", "AI", "taxonomie", "évaluation"],
                "trigger_keywords": [
                    "score", "niveau", "évaluer", "compétence", "taxonomie",
                    "coaching", "arbre de compétences",
                ],
            },
            {
                "id": "consultant_history",
                "name": "Historique missions consultant",
                "description": (
                    "Récupère l'historique des missions passées d'un consultant nommé. "
                    "NE PAS utiliser pour lister les missions client — utiliser missions_agent."
                ),
                "tags": ["historique", "missions", "consultant", "passé"],
                "trigger_keywords": ["quelles missions a fait", "historique de", "parcours de"],
            },
            {
                "id": "availability",
                "name": "Disponibilité consultant",
                "description": "Consulte les indisponibilités déclarées d'un consultant spécifique.",
                "tags": ["disponibilité", "planning", "RH", "congé"],
                "trigger_keywords": ["disponible", "indisponible", "congé", "planning"],
            },
        ],
        routing_hints={
            "do_use_when": [
                "L'utilisateur cherche des consultants par compétence ou disponibilité",
                "L'utilisateur mentionne un CV, un profil ou un lien Google Drive",
                "L'utilisateur veut connaître les compétences ou l'historique d'un consultant nommé",
                "L'utilisateur demande une évaluation ou un scoring de compétences",
            ],
            "do_not_use_when": [
                "L'utilisateur parle de missions CLIENT → utiliser missions_agent",
                "L'utilisateur demande un staffing ou une recommandation d'équipe → utiliser missions_agent",
                "L'utilisateur parle de la santé du système ou des coûts IA → utiliser ops_agent",
            ],
        },
        examples=[
            {"query": "Trouve-moi des consultants experts en Kubernetes disponibles en juin",
             "skill": "consultant_search"},
            {"query": "Analyse ce CV : https://docs.google.com/...", "skill": "cv_analysis"},
            {"query": "Quelles missions a faites Jean Dupont ?", "skill": "consultant_history"},
            {"query": "Quelle est la disponibilité de Marie Martin ?", "skill": "availability"},
        ],
    )


@app.get("/")
async def root():
    return {"message": "HR Agent API - Use /a2a/query for interactions"}


protected_router = APIRouter(dependencies=[Depends(verify_jwt)])


@app.get("/spec")
async def get_spec():
    try:
        with open("spec.md", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/markdown")
    except Exception as e:
        app_logger.debug("[spec] spec.md not found or unreadable: %s: %s", type(e).__name__, e)
        return Response(content="# Specification introuvable", media_type="text/markdown")


@protected_router.post("/query")
async def query(request: QueryRequest, http_request: Request,
                auth: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
                payload: dict = Depends(verify_jwt)):
    auth_header = f"{auth.scheme} {auth.credentials}"
    auth_header_var.set(auth_header)

    computed_session_id = payload.get("sub")
    if not computed_session_id:
        raise HTTPException(status_code=401, detail="Token invalide")

    ctx = extract(http_request.headers)

    with tracer.start_as_current_span("query.process", context=ctx, kind=SpanKind.SERVER) as span:
        trace_id = format(span.get_span_context().trace_id, '032x')
        span.set_attribute("trace.id", trace_id)
        span.set_attribute("query.text", request.query)
        span.set_attribute("session.id", computed_session_id)

        try:
            AGENT_QUERIES_TOTAL.inc()
            # Propager le sub JWT comme user_id pour le tracking FinOps
            jwt_user_id = payload.get("sub") or "unknown@zenika.com"
            result = await run_agent_query(request.query, computed_session_id, auth_token=auth_header, user_id=jwt_user_id)
            span.set_attribute("agent.source", result.get("source", "unknown"))
            return result

        except Exception as e:
            app_logger.error(
                "CRITICAL: Exception in /query — %s: %s",
                type(e).__name__,
                str(e) or repr(e),
                exc_info=True,
            )
            return {"response": f"Erreur: {str(e)}", "source": "error"}


@protected_router.post("/a2a/query", response_model=A2AResponse)
async def a2a_query(request: A2ARequest, http_request: Request,
                    auth: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
                    payload: dict = Depends(verify_jwt)):
    """Point d'entrée A2A — appelé exclusivement par agent_router_api."""
    auth_header = f"{auth.scheme} {auth.credentials}"
    auth_header_var.set(auth_header)

    computed_session_id = payload.get("sub")

    # Prb 7: Use the user_id propagated from Router if available, else fall back to JWT sub
    effective_user_id = request.user_id or computed_session_id or "user_1"

    ctx = extract(http_request.headers)
    with tracer.start_as_current_span("a2a.query", context=ctx, kind=SpanKind.SERVER) as span:
        try:
            result = await run_agent_query(request.query, computed_session_id, auth_token=auth_header, user_id=effective_user_id)
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
            app_logger.error(
                "CRITICAL: Exception in /a2a/query — %s: %s",
                type(e).__name__,
                str(e) or repr(e),
                exc_info=True,
            )
            raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# NOTE: Les endpoints /login, /me, /logout ont été supprimés.
# Le frontend s'authentifie directement via /auth/ → users_api (LB prio 30).
# agent_hr_api est un worker A2A : il n'est appelé que par agent_router_api
# via le LB interne (http://api.internal.zenika/api/agent-hr/).


@protected_router.get("/mcp/registry")
async def mcp_registry():
    return {
        "services": [
            {
                "id": "hr",
                "name": "HR Agent (Staffing & Talent)",
                "tools": get_tool_metadata(HR_TOOLS)
            }
        ]
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/version")
async def get_version():
    return {"version": os.getenv("APP_VERSION", "unknown")}


@protected_router.api_route("/mcp/proxy/{server_name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_mcp(server_name: str, path: str, request: Request, auth: HTTPAuthorizationCredentials = Depends(security)):
    target_url_env = f"{server_name.upper()}_URL"
    base_url = os.getenv(target_url_env)

    if not base_url:
        raise HTTPException(status_code=404, detail=f"MCP Server {server_name} introuvable")

    auth_header = f"{auth.scheme} {auth.credentials}"
    headers = {"Authorization": auth_header}
    inject(headers)

    body = await request.body()
    target_path = f"{base_url.rstrip('/')}/{path}"
    query_params = request.url.query
    if query_params:
        target_path += "?" + query_params

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
        try:
            res = await client.request(
                method=request.method,
                url=target_path,
                headers=headers,
                content=body,
                timeout=300.0
            )
            return Response(content=res.content, status_code=res.status_code, media_type=res.headers.get("content-type"))
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Erreur de communication avec {server_name}: {str(exc)}")


app.include_router(_history_router)
app.include_router(protected_router)


app.add_exception_handler(Exception, make_global_exception_handler("agent_hr_api"))

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
