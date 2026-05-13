# flake8: noqa: E501, E701, E302, F541, E306
import asyncio
import json
import random

import httpx
from mcp.types import TextContent


async def handle_bulk_import_tree(client, arguments: dict, headers: dict, api_base_url: str):

    response = await client.post(f"{api_base_url}/bulk_tree", json={"tree": arguments["tree"]})
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_batch_evaluate_competencies_search(client, arguments: dict, headers: dict, api_base_url: str):

    response = await client.post(f"{api_base_url}/evaluations/batch/search", json=arguments, timeout=30.0)
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_batch_evaluate_competencies_users(client, arguments: dict, headers: dict, api_base_url: str):

    response = await client.post(f"{api_base_url}/evaluations/batch/users", json=arguments, timeout=30.0)
    response.raise_for_status()
    raw = response.json()
    # Filtrer les paires sans score IA pour ne pas surcharger le contexte LLM
    evaluations = raw.get("evaluations", raw) if isinstance(raw, dict) else raw
    if isinstance(evaluations, dict):
        scored = {
            uid: eval_data
            for uid, eval_data in evaluations.items()
            if eval_data.get("ai_score") is not None
        }
        result = {
            "evaluations": scored,
            "scored_count": len(scored),
            "total_queried": len(evaluations),
            "note": f"{len(evaluations) - len(scored)} consultants sans score IA (CV non analysé) exclus du résultat."
        }
    else:
        result = raw
    return [TextContent(type="text", text=json.dumps(result))]


async def handle_assign_competencies_bulk(client, arguments: dict, headers: dict, api_base_url: str):
    """Assigne des compétences via MCP avec retry sur 429 (pool DB saturé).

    Retry avec backoff exponentiel : competencies_api retourne 429 quand son
    ASSIGN_BULK_SEMAPHORE est plein. L'agent peut retenter sans intervention.
    """
    user_id = arguments["user_id"]
    payload = {"competencies": arguments["competencies"]}
    url = f"{api_base_url}/user/{user_id}/assign/bulk"

    last_response: httpx.Response | None = None
    for attempt in range(3):
        try:
            last_response = await client.post(url, json=payload, timeout=60.0)
            if last_response.status_code not in (429, 500, 502, 503, 504):
                last_response.raise_for_status()
                return [TextContent(type="text", text=json.dumps(last_response.json()))]
            wait = min(2 ** attempt + random.uniform(0, 1), 15.0)
        except httpx.TimeoutException:
            wait = min(2 ** attempt + random.uniform(0, 1), 15.0)
            last_response = None
        if attempt < 2:
            await asyncio.sleep(wait)

    status = last_response.status_code if last_response is not None else "timeout"
    detail = last_response.text[:300] if last_response is not None else "timeout"
    return [TextContent(
        type="text",
        text=json.dumps({"success": False, "error": f"assign/bulk échoué après 3 tentatives (HTTP {status}): {detail}"}),
    )]


async def handle_bulk_scoring_all(client, arguments: dict, headers: dict, api_base_url: str):

    force = arguments.get("force", False)
    semaphore_limit = arguments.get("semaphore_limit", 2)
    response = await client.post(
        f"{api_base_url}/evaluations/bulk-scoring-all",
        params={"force": force, "semaphore_limit": semaphore_limit},
        timeout=15.0,
    )
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]
