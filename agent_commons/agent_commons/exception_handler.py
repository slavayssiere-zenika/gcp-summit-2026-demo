"""
exception_handler.py — Reporting centralisé des exceptions vers prompts_api.

Fournit :
  - report_exception_to_prompts_api() : envoie l'erreur de manière non-bloquante
  - make_global_exception_handler()   : factory pour @app.exception_handler(Exception)

Ces fonctions étaient dupliquées à l'identique dans agent_hr_api, agent_ops_api,
agent_missions_api et agent_router_api. Cette extraction élimine ~200L de code dupliqué.

Usage :
    from agent_commons.exception_handler import make_global_exception_handler

    app = FastAPI()
    app.add_exception_handler(Exception, make_global_exception_handler("agent_hr_api"))
"""

import asyncio
import logging
import os
import traceback

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from opentelemetry.propagate import inject

logger = logging.getLogger(__name__)


async def report_exception_to_prompts_api(
    service_name: str,
    error_msg: str,
    trace_context: str,
    token: str,
) -> None:
    """Rapporte une exception non gérée à prompts_api (boucle de feedback).

    Envoi non-bloquant via asyncio.create_task — ne doit jamais faire planter le handler.

    Args:
        service_name: Nom du service qui a levé l'exception (ex: "agent_hr_api").
        error_msg: Message d'erreur court.
        trace_context: Stack trace complète (tronquée à 2000 chars).
        token: JWT Bearer token de l'utilisateur pour authentifier l'appel.
    """
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        inject(headers)
    except Exception as e:
        logger.warning(f"[exception_handler] inject OTel headers failed: {e}")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0)) as client:
            await client.post(
                f"{prompts_api_url}/errors/report",
                json={
                    "service_name": service_name,
                    "error_message": error_msg,
                    "context": trace_context[:2000],
                },
                headers=headers,
            )
    except Exception as e:
        logger.error(f"[exception_handler] Failed to report error to prompts_api: {e}")


def make_global_exception_handler(service_name: str):
    """Factory qui retourne un handler global d'exception FastAPI.

    Le handler :
    1. Capture le JWT de la requête entrante
    2. Envoie l'exception de manière non-bloquante à prompts_api
    3. Retourne une réponse HTTP 500 propre

    Args:
        service_name: Nom du service courant (injecté dans le rapport).

    Returns:
        Callable compatible avec @app.exception_handler(Exception).

    Usage:
        app.add_exception_handler(
            Exception,
            make_global_exception_handler("agent_hr_api")
        )
    """

    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        error_msg = str(exc)
        trace_context = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )

        auth_header = request.headers.get("Authorization", "")
        token = (
            auth_header.removeprefix("Bearer ").strip()
            if auth_header.startswith("Bearer ")
            else ""
        )

        if token:
            asyncio.create_task(
                report_exception_to_prompts_api(
                    service_name, error_msg, trace_context, token
                )
            )

        logger.error(
            f"[{service_name}] Unhandled exception on {request.method} {request.url.path}: "
            f"{error_msg}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "service": service_name},
        )

    return global_exception_handler
