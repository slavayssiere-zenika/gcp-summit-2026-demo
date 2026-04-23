import json
import logging
import os
import re
import time

from contextlib import asynccontextmanager
from typing import Any, Optional

import jwt as pyjwt
import uvicorn
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

from agent import MISSIONS_TOOLS, run_agent_query
from logger import setup_logging, LoggingMiddleware
from agent_commons.metadata import extract_metadata_from_session
from agent_commons.schemas import A2ARequest, A2AResponse
from metrics import QUERY_COUNT, QUERY_LATENCY
from agent_commons.mcp_client import auth_header_var

logger = logging.getLogger(__name__)

APP_VERSION = os.getenv("APP_VERSION", "v0.1.0")
ROOT_PATH = os.getenv("ROOT_PATH", "")
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "agent-missions-api")
TRACE_EXPORTER = os.getenv("TRACE_EXPORTER", "none")

# JWT
SECRET_KEY = os.getenv("SECRET_KEY", "")
ALGORITHM = "HS256"
_raw_secret = SECRET_KEY
if not _raw_secret:
    logging.critical("[MISSIONS] FATAL: SECRET_KEY env var is not set. JWT validation will fail.")


# ── OTel Tracing — 3 modes : http (Tempo), gcp (Cloud Trace), none ────────────
def setup_tracing(app: FastAPI) -> TracerProvider:
    resource = Resource(attributes={"service.name": OTEL_SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    if TRACE_EXPORTER == "http":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        logger.info("[MISSIONS] OTLP HTTP exporter (Tempo) configured.")
    elif TRACE_EXPORTER == "gcp":
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
            provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
            logger.info("[MISSIONS] GCP Cloud Trace exporter configured.")
        except Exception as e:
            logger.warning("[MISSIONS] Could not init Cloud Trace exporter: %s", e)
    else:
        logger.info("[MISSIONS] No trace exporter configured (TRACE_EXPORTER=%s).", TRACE_EXPORTER)

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls="health,metrics")
    return provider


# ── Auth (JWT) — validation unique, payload retourné ──────────────────────────
def verify_jwt(request: Request) -> dict:
    """Validate Bearer JWT. Sets auth_header_var for MCP propagation. Raises 401 if invalid."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = auth_header.split(" ", 1)[1]
    try:
        payload = pyjwt.decode(token, _raw_secret, algorithms=[ALGORITHM])
        auth_header_var.set(auth_header)
        return payload
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="JWT token expired")
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid JWT: {e}")


# ── Session service (lazy singleton) ──────────────────────────────────────────
_session_service = None


def get_session_service():
    global _session_service
    if _session_service is None:
        from agent_commons.session import RedisSessionService
        _session_service = RedisSessionService(
            redis_key_prefix="adk:missions:sessions",
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379/12"),
        )
    return _session_service


# ── Lifecycle ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("[MISSIONS] 🚀 Starting agent_missions_api %s", APP_VERSION)
    try:
        from agent_commons.mcp_proxy import get_cached_tools
        from agent import _MISSIONS_CLIENTS_MAP, _MISSIONS_TOOLS_CACHE
        tools = await get_cached_tools(_MISSIONS_CLIENTS_MAP, "[MISSIONS]", ttl=300, _cache=_MISSIONS_TOOLS_CACHE)
        logger.info("[MISSIONS] ✅ Pre-warmed %d MCP tools at startup.", len(tools))
    except Exception as e:
        logger.warning("[MISSIONS] Could not pre-warm tools cache: %s", e)
    yield
    logger.info("[MISSIONS] 🛑 Shutting down agent_missions_api.")


# ── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Agent Missions API",
    description="Staffing Director — missions client & matching consultants (A2A Worker)",
    version=APP_VERSION,
    root_path=ROOT_PATH,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

_tracer_provider = setup_tracing(app)
_tracer = trace.get_tracer("agent_missions_api")

# Prometheus (Golden Rules §5 — obligatoire)
Instrumentator().instrument(app).expose(app)


# ── Pydantic models ────────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None  # None par défaut : le sub JWT est utilisé comme fallback


# ── Public endpoints (no JWT) ──────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "agent_missions_api", "version": APP_VERSION}


@app.get("/version")
async def version():
    return {"version": APP_VERSION}


# ── Protected router — JWT validé via Depends sur le routeur ────
protected_router = APIRouter(dependencies=[Depends(verify_jwt)])


async def _execute_query(request: QueryRequest, payload: dict) -> A2AResponse:
    """Logique partagée entre /query et /a2a/query."""
    start_time = time.time()
    user_id = request.user_id or payload.get("sub") or "unknown@zenika.com"

    QUERY_COUNT.labels(agent="missions", status="started").inc()
    logger.info("[MISSIONS] Query received user_id=%s session=%s", user_id, request.session_id)

    try:
        result = await run_agent_query(
            query=request.query,
            session_id=request.session_id,
            user_id=user_id,
        )
        QUERY_COUNT.labels(agent="missions", status="success").inc()
        return A2AResponse(
            response=result.get("response", ""),
            data=result.get("data"),
            steps=result.get("steps", []),
            thoughts=result.get("thoughts", ""),
            usage=result.get("usage", {}),
            source=result.get("source"),
            session_id=result.get("session_id"),
        )
    except Exception as e:
        QUERY_COUNT.labels(agent="missions", status="error").inc()
        logger.error("[MISSIONS] Agent error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal agent error: {e}")
    finally:
        elapsed = time.time() - start_time
        QUERY_LATENCY.labels(agent="missions").observe(elapsed)
        logger.info("[MISSIONS] Query completed in %.2fs", elapsed)


@protected_router.post("/query", response_model=A2AResponse)
async def query_agent(request: A2ARequest, payload: dict = Depends(verify_jwt)):
    """
    Point d'entrée direct — utilisé par le frontend ou pour les tests directs.
    Exécute le pipeline de staffing et retourne le résultat structuré.
    """
    return await _execute_query(request, payload)


@protected_router.post("/a2a/query", response_model=A2AResponse)
async def a2a_query_agent(
    request: A2ARequest,
    http_request: Request,
    payload: dict = Depends(verify_jwt),
):
    """
    Point d'entrée A2A — appelé exclusivement par agent_router_api.
    Valide le payload entrant (A2ARequest) et la réponse (A2AResponse) via le contrat Pydantic ADR12-4.
    Rattache le span OTel au contexte de trace propagé par le Router.
    """
    ctx = extract(http_request.headers)
    with _tracer.start_as_current_span("missions.a2a.query", context=ctx, kind=SpanKind.SERVER) as span:
        span.set_attribute("query.text", request.query[:100])
        user_id = request.user_id or payload.get("sub", "unknown")
        span.set_attribute("user.id", user_id)
        return await _execute_query(request, payload)


@protected_router.get("/history")
async def get_history(payload: dict = Depends(verify_jwt)):
    """Retourne l'historique de la session courante (par sub JWT)."""
    session_id = payload.get("sub")
    if not session_id:
        raise HTTPException(status_code=401, detail="Token invalide — sub manquant")
    user_id = session_id  # sub JWT = user_id pour la session ADK

    session_service = get_session_service()
    session = await session_service.get_session(
        app_name="zenika_missions_assistant",
        user_id=user_id,
        session_id=session_id,
    )
    if not session:
        return {"history": []}

    history = []
    current_assistant_msg = None

    for event in getattr(session, "events", []):
        author = getattr(event, "author", None)
        content = getattr(event, "content", "")
        role = getattr(content, "role", None) if content else None

        author_val = (author or "").lower()
        role_val = (role or "").lower()

        is_assistant = any(x in ["assistant", "model", "assistant_zenika_missions"] for x in [author_val, role_val])
        is_tool = any(x in ["tool", "function"] for x in [author_val, role_val])
        is_user = "user" in [author_val, role_val] and not is_tool and not is_assistant

        if hasattr(content, "parts"):
            content_text = "".join(getattr(p, "text", "") or "" for p in (content.parts or []) if hasattr(p, "text"))
        else:
            content_text = str(content)

        if is_user and content_text.strip():
            history.append({"role": "user", "content": content_text})
            current_assistant_msg = None

        elif is_assistant and current_assistant_msg is None:
            meta = extract_metadata_from_session(session)
            current_assistant_msg = {
                "role": "assistant",
                "content": content_text,
                "displayType": "text_only",
                "data": meta.get("data"),
                "parsedData": [],
                "steps": meta.get("steps", []),
                "thoughts": meta.get("thoughts", ""),
                "rawResponse": content_text,
                "activeTab": "preview",
                "pagination": {"currentPage": 1, "itemsPerPage": 10},
            }
            history.append(current_assistant_msg)

        if is_assistant and content_text and current_assistant_msg:
            full_raw = current_assistant_msg.get("_full_text_progress", "") + content_text
            current_assistant_msg["_full_text_progress"] = full_raw
            current_assistant_msg["rawResponse"] = full_raw
            try:
                json_match = re.search(r'\{[\s\S]*\}', full_raw)
                if json_match:
                    json_obj = json.loads(json_match.group(0))
                    if "reply" in json_obj and "display_type" in json_obj:
                        reply = json_obj.get("reply", "")
                        current_assistant_msg["content"] = full_raw.replace(json_match.group(0), reply).strip()
                        current_assistant_msg["displayType"] = json_obj["display_type"]
                        if json_obj.get("data"):
                            current_assistant_msg["data"] = json_obj["data"]
                    else:
                        current_assistant_msg["content"] = full_raw
                else:
                    current_assistant_msg["content"] = full_raw
            except Exception:
                current_assistant_msg["content"] = full_raw

            if current_assistant_msg.get("data"):
                d = current_assistant_msg["data"]
                if isinstance(d, dict) and d.get("dataType") == "mission":
                    current_assistant_msg["displayType"] = "cards"
                elif current_assistant_msg["displayType"] == "text_only":
                    current_assistant_msg["displayType"] = "cards"
                if isinstance(d, dict) and "items" in d:
                    current_assistant_msg["parsedData"] = d["items"]
                elif isinstance(d, list):
                    current_assistant_msg["parsedData"] = d
                else:
                    current_assistant_msg["parsedData"] = [d]

    final_history = []
    for msg in history:
        if isinstance(msg, dict):
            msg.pop("_full_text_progress", None)
            if msg.get("role") == "assistant" and not msg.get("content") and not msg.get("steps") and not msg.get("data"):
                continue
            final_history.append(msg)

    return {"history": final_history}


@protected_router.delete("/history")
async def delete_history(payload: dict = Depends(verify_jwt)):
    """Efface la session Redis de l'utilisateur courant."""
    session_id = payload.get("sub")
    if not session_id:
        raise HTTPException(status_code=401, detail="Token invalide — sub manquant")
    user_id = session_id  # sub JWT = user_id pour la session ADK

    session_service = get_session_service()
    session = await session_service.get_session(
        app_name="zenika_missions_assistant",
        user_id=user_id,
        session_id=session_id,
    )
    if session:
        session_service._delete_session_impl(
            app_name="zenika_missions_assistant",
            user_id=user_id,
            session_id=session_id,
        )
        return {"message": "Historique effacé"}
    return {"message": "Pas d'historique"}


@app.get("/spec")
async def get_spec():
    """Retourne la spécification métier de l'agent Missions."""
    try:
        with open("spec.md", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/markdown")
    except Exception:
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


app.include_router(protected_router)



import traceback
from fastapi.responses import JSONResponse
import httpx
import logging
import asyncio

async def report_exception_to_prompts_api(service_name: str, error_msg: str, trace_context: str, token: str):
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        from opentelemetry.propagate import inject
        inject(headers)
    except Exception: raise

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{prompts_api_url}/errors/report",
                json={
                    "service_name": service_name,
                    "error_message": error_msg,
                    "context": trace_context[:2000]
                },
                headers=headers
            )
        except Exception as e:
            logging.error(f"Failed to report error to prompts_api: {e}")
            raise e

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = str(exc)
    trace_context = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    
    if token:
        asyncio.create_task(report_exception_to_prompts_api("agent_missions_api", error_msg, trace_context, token))
    
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
