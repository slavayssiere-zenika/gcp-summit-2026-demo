import logging
from typing import Any
import httpx
import os
from opentelemetry.propagate import inject

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
    """Enregistre une consommation IA dans BigQuery via Analytics MCP."""
    if not usage_metadata:
        return

    try:
        if hasattr(usage_metadata, "prompt_token_count"):
            input_tokens = getattr(usage_metadata, "prompt_token_count", 0)
        else:
            input_tokens = usage_metadata.get("prompt_token_count", 0) if isinstance(usage_metadata, dict) else 0

        if hasattr(usage_metadata, "candidates_token_count"):
            output_tokens = getattr(usage_metadata, "candidates_token_count", 0)
        else:
            output_tokens = usage_metadata.get("candidates_token_count", 0) if isinstance(usage_metadata, dict) else 0

        if input_tokens == 0 and output_tokens == 0:
            return

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
        elif headers.get("authorization"):
            pass

        analytics_url = os.getenv("ANALYTICS_MCP_URL", "http://analytics_mcp:8000")
        async with httpx.AsyncClient() as http_client:
            try:
                await http_client.post(
                    f"{analytics_url.rstrip('/')}/mcp/call",
                    json=payload,
                    headers=headers,
                    timeout=2.0,
                )
            except Exception as ex:
                logger.warning(f"Analytics MCP unreachable for FinOps: {ex}")

    except Exception as e:
        logger.error(f"FinOps logging failed: {e}")
