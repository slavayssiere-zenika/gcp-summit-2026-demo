"""
finops.py — Logging FinOps vers Analytics MCP (BigQuery).

Ce module isole la fonction _log_finops() pour éviter sa duplication
dans cv_import_service.py et search_service.py.

Règle AGENTS.md §5 : Les calls FinOps ne doivent jamais bloquer le pipeline principal.
"""

import logging
from typing import Any

import httpx
from opentelemetry.propagate import inject

from src.services.config import ANALYTICS_MCP_URL

logger = logging.getLogger(__name__)


async def log_finops(
    user_email: str,
    action: str,
    model: str,
    usage_metadata: Any,
    metadata: dict = None,
    auth_token: str = None,
    is_batch: bool = False,
) -> None:
    """Enregistre une consommation IA dans BigQuery via Analytics MCP sidecar.

    Non-bloquant : les erreurs de connexion sont loguées en warning sans
    propager d'exception. Le pipeline principal n'est jamais interrompu.

    Args:
        user_email: Identifiant de l'appelant (sub du JWT ou email).
        action: Libellé de l'action IA (ex: "search_embedding", "bulk_reanalyse_apply").
        model: Nom du modèle utilisé (ex: "gemini-embedding-001").
        usage_metadata: Objet ou dict contenant prompt_token_count et candidates_token_count.
        metadata: Métadonnées additionnelles à loger (ex: {"query": "..."}).
        auth_token: Token JWT de l'appelant pour la propagation OTel.
        is_batch: True si l'appel a été réalisé via Vertex AI Batch.
    """
    if not usage_metadata:
        return

    try:
        # Extraction robuste des tokens (gère les objets Pydantic et les dicts)
        if hasattr(usage_metadata, "prompt_token_count"):
            input_tokens = getattr(usage_metadata, "prompt_token_count", 0)
        else:
            input_tokens = (
                usage_metadata.get("prompt_token_count", 0)
                if isinstance(usage_metadata, dict)
                else 0
            )

        if hasattr(usage_metadata, "candidates_token_count"):
            output_tokens = getattr(usage_metadata, "candidates_token_count", 0)
        else:
            output_tokens = (
                usage_metadata.get("candidates_token_count", 0)
                if isinstance(usage_metadata, dict)
                else 0
            )

        payload = {
            "name": "log_ai_consumption",
            "arguments": {
                "user_email": user_email,
                "action": action,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "is_batch": is_batch,
                "metadata": metadata or {},
            },
        }

        headers: dict = {}
        inject(headers)
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        async with httpx.AsyncClient() as http_client:
            try:
                await http_client.post(
                    f"{ANALYTICS_MCP_URL.rstrip('/')}/mcp/call",
                    json=payload,
                    headers=headers,
                    timeout=2.0,
                )
            except Exception as ex:
                logger.warning(f"Analytics MCP unreachable for FinOps: {ex}")

    except Exception as e:
        logger.error(f"FinOps logging analysis failed: {e}")
