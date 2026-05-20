# flake8: noqa: E501, E701, E302, F541, E306
import json
from mcp.types import TextContent


async def handle_set_user_competency_score(client, arguments: dict, headers: dict, api_base_url: str):

    user_id = arguments["user_id"]
    competency_id = arguments["competency_id"]
    body = {"score": arguments["score"]}
    if arguments.get("comment"):
        body["comment"] = arguments["comment"]
    response = await client.post(
        f"{api_base_url}/evaluations/user/{user_id}/competency/{competency_id}/user-score",
        json=body,
        timeout=10.0,
    )
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_trigger_ai_scoring(client, arguments: dict, headers: dict, api_base_url: str):

    user_id = arguments["user_id"]
    response = await client.post(
        f"{api_base_url}/evaluations/user/{user_id}/ai-score-all",
        timeout=30.0,
    )
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_get_user_competency_evaluations(client, arguments: dict, headers: dict, api_base_url: str):

    user_id = arguments["user_id"]
    skip = arguments.get("skip", 0)
    limit = arguments.get("limit", 500)
    response = await client.get(f"{api_base_url}/evaluations/user/{user_id}", params={"skip": skip, "limit": limit}, timeout=10.0)
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_clear_user_evaluations(client, arguments: dict, headers: dict, api_base_url: str):

    user_id = arguments["user_id"]
    response = await client.delete(
        f"{api_base_url}/user/{user_id}/evaluations",
        timeout=10.0,
    )
    response.raise_for_status()
    return [TextContent(type="text", text=f"All evaluations cleared for user {user_id}")]


async def handle_find_skill_gaps(client, arguments: dict, headers: dict, api_base_url: str):

    params = {"user_ids": arguments["user_ids"]}
    if "competency_ids" in arguments and arguments["competency_ids"]:
        params["competency_ids"] = arguments["competency_ids"]
    if "min_coverage" in arguments:
        params["min_coverage"] = arguments["min_coverage"]
    response = await client.get(f"{api_base_url}/analytics/skill-gaps", params=params, timeout=10.0)
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]
