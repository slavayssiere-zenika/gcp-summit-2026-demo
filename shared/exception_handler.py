"""Gestionnaire d'exceptions global pour les APIs data Zenika.

Usage (dans main.py) :
    from shared.exception_handler import register_global_exception_handler
    register_global_exception_handler(app, service_name="users-api")

Le handler :
1. Préserve les codes HTTP natifs FastAPI (401, 404, 422...).
2. Tente de reporter l'erreur à prompts_api pour l'amélioration continue des prompts.
3. Loggue la stack trace complète.
4. Retourne toujours HTTP 500 pour les exceptions non prévues.
"""
import logging
import os
import traceback

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry.propagate import inject
from starlette.exceptions import HTTPException as StarletteHTTPException


async def _get_service_token_fallback() -> str:
    """Tente d'obtenir un token via OIDC Metadata Server (Cloud Run) ou DEV_SERVICE_TOKEN."""
    dev_token = os.getenv("DEV_SERVICE_TOKEN")
    if dev_token:
        return dev_token

    try:
        users_api_url = os.getenv("USERS_API_URL", "http://users_api:8000")
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.0, connect=1.0)) as client:
            res_meta = await client.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/"
                "service-accounts/default/identity?audience=users_api",
                headers={"Metadata-Flavor": "Google"},
                timeout=2.0,
            )
            if res_meta.status_code == 200:
                id_token = res_meta.text
                res = await client.post(
                    f"{users_api_url}/auth/service-account/login",
                    json={"id_token": id_token},
                )
                if res.status_code == 200:
                    return res.json().get("access_token", "")
    except Exception:
        pass
    return ""


async def _report_to_prompts_api(service_name: str, error_msg: str, trace_context: str, token: str) -> None:
    """Envoie le rapport d'erreur à prompts_api (best-effort, non bloquant)."""
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    headers = {"Authorization": f"Bearer {token}"}
    inject(headers)  # Propagation OTel trace context

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
        try:
            await client.post(
                f"{prompts_api_url}/errors/report",
                json={
                    "service_name": service_name,
                    "error_message": error_msg,
                    "context": trace_context[-2000:] if len(trace_context) > 2000 else trace_context,
                },
                headers=headers,
            )
        except Exception as e:
            # Best-effort : ne jamais relancer pour ne pas masquer l'erreur originale.
            logging.error("Failed to report error to prompts_api: %s", e)


def register_global_exception_handler(app: FastAPI, service_name: str) -> None:
    """Enregistre le gestionnaire d'exceptions global sur l'instance FastAPI.

    Args:
        app: L'instance FastAPI cible.
        service_name: Nom du service (ex: "users-api") — utilisé dans le rapport prompts_api.
    """

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # Guard : préserver les codes HTTP natifs FastAPI (401, 404, 422...)
        if isinstance(exc, StarletteHTTPException):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        if isinstance(exc, RequestValidationError):
            return JSONResponse(status_code=422, content={"detail": exc.errors()})

        error_msg = str(exc)
        trace_context = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""

        try:
            if not token:
                token = await _get_service_token_fallback()
            if token:
                await _report_to_prompts_api(service_name, error_msg, trace_context, token)
        except Exception as fallback_e:
            logging.error("Failed to process exception reporting: %s", fallback_e)

        logging.error(
            "[%s] Unhandled exception on %s %s: %s\n%s",
            service_name,
            request.method,
            request.url.path,
            error_msg,
            trace_context,
        )
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
