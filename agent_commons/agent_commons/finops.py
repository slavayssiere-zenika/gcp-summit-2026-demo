"""
finops.py — Async FinOps token logging shared across all agents.

Extracted from the ``run_agent_query`` functions in all three agent.py files.
The missions agent already used tenacity retries (best practice); this module
standardises that behaviour for all agents.

Key export:
  - log_tokens_to_bq(session_id, action, model, input_tokens, output_tokens,
                     query, market_url, auth_header)
      Fire-and-forget async task that logs AI consumption to BigQuery via the
      market_mcp ``log_ai_consumption`` tool.  Retries up to 3 times with
      exponential backoff via tenacity.
"""

import asyncio
import logging
import os

import httpx
from opentelemetry.propagate import inject
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_COST_PER_INPUT_TOKEN = 0.000000075   # USD — approximate Gemini Flash pricing
_COST_PER_OUTPUT_TOKEN = 0.0000003    # USD


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Return an estimated cost in USD for the given token counts."""
    return round(input_tokens * _COST_PER_INPUT_TOKEN + output_tokens * _COST_PER_OUTPUT_TOKEN, 6)


def log_tokens_to_bq(
    session_id: str | None,
    action: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    query: str,
    market_url: str | None = None,
    auth_header: str | None = None,
) -> None:
    """Schedule a fire-and-forget async task to log AI consumption to BigQuery.

    Must be called from within a running asyncio event loop (e.g. inside an
    async FastAPI handler or agent runner).  Uses ``asyncio.create_task()`` so
    the caller is never blocked.

    Args:
        session_id:    JWT sub or user email used as the billing identity.
        action:        Event label (e.g. ``"hr_agent_execution"``).
        model:         Gemini model name (e.g. ``"gemini-2.5-flash"``).
        input_tokens:  Total prompt token count for the request.
        output_tokens: Total response token count for the request.
        query:         First 100 chars of the user query (for BigQuery metadata).
        market_url:    Base URL of market_mcp (defaults to MARKET_MCP_URL env var).
        auth_header:   ``Authorization: Bearer <token>`` string for OTel propagation.
    """
    if input_tokens <= 0 and output_tokens <= 0:
        return

    _market_url = (market_url or os.getenv("MARKET_MCP_URL", "http://market_mcp:8008")).rstrip("/")
    user_email = session_id if "@" in str(session_id) else f"{session_id}@zenika.com"

    _headers: dict[str, str] = {}
    if auth_header:
        _headers["Authorization"] = auth_header
    inject(_headers)

    _payload = {
        "name": "log_ai_consumption",
        "arguments": {
            "user_email": user_email,
            "action": action,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "metadata": {"query": query[:100]},
        },
    }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type(Exception),
        reraise=False,
    )
    async def _log_with_retry() -> None:
        async with httpx.AsyncClient(timeout=10.0, headers=_headers) as c:
            await c.post(f"{_market_url}/mcp/call", json=_payload)

    async def _task() -> None:
        try:
            await _log_with_retry()
        except Exception as e:
            logger.warning("FinOps logging failed after retries: %s", e)

    asyncio.create_task(_task())
