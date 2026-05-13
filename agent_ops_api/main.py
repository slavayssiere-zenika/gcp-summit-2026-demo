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
from jose import jwt
from logger import LoggingMiddleware, setup_logging
from metrics import AGENT_QUERIES_TOTAL
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace import SpanKind
from prometheus_fastapi_instrumentator import Instrumentator
from shared.middlewares import ContentLengthSanitizerASGIMiddleware

from agent_commons.exception_handler import make_global_exception_handler
from agent_commons.jwt_middleware import ALGORITHM
from agent_commons.jwt_middleware import verify_jwt_bearer as verify_jwt
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
app.add_middleware(LoggingMiddleware)
Instrumentator().instrument(app).expose(app)
app.add_middleware(ContentLengthSanitizerASGIMiddleware)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready,metrics,version")
RedisInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()


@app.get("/")
async def root():
    return {"message": "Ops Agent API - Use /a2a/query for interactions"}


security = HTTPBearer()

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in environment variables")
os.environ.pop("SECRET_KEY", None)

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
async def query(request: QueryRequest, http_request: Request, auth: HTTPAuthorizationCredentials = Depends(security)):
    auth_header = f"{auth.scheme} {auth.credentials}"
    auth_header_var.set(auth_header)

    try:
        payload = jwt.decode(auth.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        computed_session_id = payload.get("sub")
        if not computed_session_id:
            raise HTTPException(status_code=401, detail="Token invalide")
    except Exception:
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
async def a2a_query(request: A2ARequest, http_request: Request, auth: HTTPAuthorizationCredentials = Depends(security)):
    """Point d'entrée A2A — appelé exclusivement par agent_router_api.
    Valide le payload entrant (A2ARequest) et la réponse (A2AResponse) via le contrat Pydantic ADR12-4.
    """
    # Standard A2A Entrypoint
    auth_header = f"{auth.scheme} {auth.credentials}"
    auth_header_var.set(auth_header)

    try:
        payload = jwt.decode(auth.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        computed_session_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")

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
