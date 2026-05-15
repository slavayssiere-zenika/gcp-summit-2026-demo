import logging
import os
# flake8: noqa: E402  — warnings.filterwarnings must precede third-party imports
import warnings
from contextlib import asynccontextmanager

import httpx
import uvicorn
from agent import OPS_TOOLS, run_agent_query
from fastapi import (APIRouter, Depends, FastAPI, HTTPException, Request,
                     Response)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
# Routes /history (GET + DELETE) extraites dans history_routes.py (Golden Rule §14)
from history_routes import history_router as _history_router
from metrics import AGENT_QUERIES_TOTAL
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.sdk.resources import Resource, ResourceAttributes
from opentelemetry.trace import SpanKind

from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import SpanKind
from shared.fastapi_utils import instrument_app
from shared.observability import setup_logging

from agent_commons.exception_handler import make_global_exception_handler
from shared.auth.jwt import ALGORITHM
from shared.auth.jwt import verify_jwt_bearer as verify_jwt
from agent_commons.mcp_client import auth_header_var
from agent_commons.schemas import (A2ARequest, A2AResponse, QueryRequest,
                                   get_tool_metadata)

warnings.filterwarnings("ignore", message=".*authlib.jose module is deprecated.*")


if os.getenv("TRACE_EXPORTER", "grpc") == "http":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import \
        OTLPSpanExporter
elif os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
else:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import \
        OTLPSpanExporter


sampling_rate = float(os.getenv("TRACE_SAMPLING_RATE", "1.0"))
sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "agent-ops-api",
        ResourceAttributes.SERVICE_VERSION: os.getenv("APP_VERSION", "dev"),
    })
    ,
    sampler=sampler
)
if os.getenv("TRACE_EXPORTER", "grpc") == "gcp":
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
else:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter() if os.getenv("TRACE_EXPORTER", "grpc") == "http" else OTLPSpanExporter(insecure=True)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)
app_logger = logging.getLogger(__name__)


setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting ADK Web Agent with Gemini...")
    yield

app = FastAPI(
    title="ADK Ops Agent (A2A)",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    root_path=os.getenv("ROOT_PATH", "")
)
instrument_app(app, service_name="agent-ops-api", register_exception_handler=False)
RedisInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()


@app.get("/.well-known/agent.json", include_in_schema=False)
async def agent_card():
    """A2A v2 — Service Discovery endpoint (google-adk 1.33+)."""
    from agent_commons.a2a_utils import make_agent_card
    return make_agent_card(
        name="Ops Agent (Platform & FinOps)",
        description=(
            "Sous-agent spécialisé Ops : santé système GCP, FinOps IA, "
            "logs Grafana/Loki, synchronisation Drive, gestion des system prompts. "
            "NE PAS utiliser pour les sujets RH (consultants, CVs) ou les missions client."
        ),
        url_env_var="AGENT_OPS_API_URL",
        default_url="http://agent_ops_api:8080",
        skills=[
            {
                "id": "finops",
                "name": "FinOps & Coûts IA",
                "description": (
                    "Analyse la consommation de tokens, les coûts d'inférence et les anomalies FinOps. "
                    "Retourne des rapports journaliers, hebdomadaires ou mensuels par utilisateur."
                ),
                "tags": ["FinOps", "coûts", "tokens", "BigQuery", "budget"],
                "trigger_keywords": [
                    "coût", "coûts", "dépense", "token", "budget", "FinOps",
                    "combien ça coûte", "consommation IA", "facture", "anomalie",
                ],
            },
            {
                "id": "system_health",
                "name": "Santé système GCP",
                "description": (
                    "Vérifie l'état des services Cloud Run, les métriques de performance "
                    "et l'infrastructure GCP. Fournit des logs, des alertes et l'état des pods."
                ),
                "tags": ["GCP", "Cloud Run", "santé", "infrastructure", "logs", "Loki", "Grafana"],
                "trigger_keywords": [
                    "santé", "erreur 500", "logs", "service down", "infrastructure",
                    "Cloud Run", "GCP", "monitoring", "alerte", "panne",
                ],
            },
            {
                "id": "drive_management",
                "name": "Gestion Drive",
                "description": (
                    "Configure les dossiers Google Drive synchronisés pour l'ingestion des CVs. "
                    "Permet d'ajouter, modifier ou supprimer les sources Drive surveillées."
                ),
                "tags": ["Drive", "sync", "configuration", "ingestion", "CV"],
                "trigger_keywords": [
                    "drive", "dossier", "synchronisation", "ingestion", "source de CVs",
                ],
            },
            {
                "id": "prompt_management",
                "name": "Gestion des System Prompts",
                "description": (
                    "Crée, modifie et optimise les instructions des agents Gemini. "
                    "Permet de personnaliser le comportement de chaque agent sans redéploiement."
                ),
                "tags": ["prompts", "configuration", "agents", "personnalisation"],
                "trigger_keywords": [
                    "prompt", "instruction", "comportement", "personnaliser", "modifier l'agent",
                    "system prompt", "changer la réponse",
                ],
            },
            {
                "id": "market_intelligence",
                "name": "Intelligence marché",
                "description": (
                    "Analyse les tendances du marché tech (compétences demandées, volume d'offres). "
                    "Utile pour le benchmark salarial et l'alignement des compétences Zenika."
                ),
                "tags": ["marché", "compétences", "tendances", "benchmark"],
                "trigger_keywords": [
                    "marché", "tendance", "demandé", "benchmark", "salaire", "offres d'emploi",
                ],
            },
        ],
        routing_hints={
            "do_use_when": [
                "L'utilisateur demande des informations sur les coûts, tokens ou budget IA",
                "L'utilisateur parle de la santé du système, des erreurs, des logs ou de l'infrastructure GCP",
                "L'utilisateur veut configurer Drive ou les system prompts",
                "L'utilisateur demande des tendances de marché ou un benchmark tech",
            ],
            "do_not_use_when": [
                "L'utilisateur cherche des consultants ou des profils RH → utiliser hr_agent",
                "L'utilisateur parle de missions client ou de staffing → utiliser missions_agent",
            ],
        },
        examples=[
            {"query": "Quel est le coût IA cette semaine ?", "skill": "finops"},
            {"query": "Y a-t-il des erreurs 500 sur cv_api ?", "skill": "system_health"},
            {"query": "Ajoute le dossier Drive /CVs/Paris à la synchronisation",
             "skill": "drive_management"},
            {"query": "Modifie le prompt de l'agent RH pour qu'il réponde en anglais",
             "skill": "prompt_management"},
        ],
    )



@app.get("/")
async def root():
    return {"message": "Ops Agent API - Use /a2a/query for interactions"}


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
                "CRITICAL: Exception in /query (Ops) — %s: %s",
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
                "CRITICAL: Exception in /a2a/query (Ops) — %s: %s",
                type(e).__name__,
                str(e) or repr(e),
                exc_info=True,
            )
            raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# NOTE: Les endpoints /login, /me, /logout ont été supprimés.
# Le frontend s'authentifie directement via /auth/ → users_api (LB prio 30).
# agent_ops_api est un worker A2A : il n'est appelé que par agent_router_api
# via le LB interne (http://api.internal.zenika/api/agent-ops/).


@protected_router.get("/mcp/registry")
async def mcp_registry():
    return {
        "services": [
            {
                "id": "ops",
                "name": "Ops Agent (Platform & FinOps)",
                "tools": get_tool_metadata(OPS_TOOLS)
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
    # Synchronisation avec les noms Terraform (market -> ANALYTICS_MCP_URL, drive -> DRIVE_MCP_URL, etc.)
    target_url_env = f"{server_name.upper()}_URL"
    base_url = os.getenv(target_url_env)

    if not base_url:
        target_url_env_mcp = f"{server_name.upper()}_MCP_URL"
        base_url = os.getenv(target_url_env_mcp)

    if not base_url:
        raise HTTPException(status_code=404, detail=f"MCP Server {server_name} introuvable (Tried {target_url_env} and {target_url_env_mcp if 'target_url_env_mcp' in locals() else 'N/A'})")

    auth_header = f"{auth.scheme} {auth.credentials}"
    headers = {"Authorization": auth_header}
    inject(headers)

    body = await request.body()
    target_path = f"{base_url.rstrip('/')}/{path}"
    query_params = request.url.query
    if query_params:
        target_path += "?" + query_params

    async with httpx.AsyncClient() as client:
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


app.add_exception_handler(Exception, make_global_exception_handler("agent_ops_api"))

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
