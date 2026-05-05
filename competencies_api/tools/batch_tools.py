# flake8: noqa: E501, E701, E302, F541, E306
import json
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

    user_id = arguments["user_id"]
    payload = {"competencies": arguments["competencies"]}
    response = await client.post(
        f"{api_base_url}/user/{user_id}/assign/bulk",
        json=payload,
        timeout=60.0,
    )
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


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
