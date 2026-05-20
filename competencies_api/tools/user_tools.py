# flake8: noqa: E501, E701, E302, F541, E306
import json
from mcp.types import TextContent


async def handle_assign_competency_to_user(client, arguments: dict, headers: dict, api_base_url: str):

    user_id = arguments["user_id"]
    comp_id = arguments["competency_id"]
    response = await client.post(f"{api_base_url}/user/{user_id}/assign/{comp_id}", timeout=10.0)
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_remove_competency_from_user(client, arguments: dict, headers: dict, api_base_url: str):

    user_id = arguments["user_id"]
    comp_id = arguments["competency_id"]
    response = await client.delete(f"{api_base_url}/user/{user_id}/remove/{comp_id}", timeout=10.0)
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps({"message": "Competency removed from user"}))]


async def handle_list_user_competencies(client, arguments: dict, headers: dict, api_base_url: str):

    skip = arguments.get("skip", 0)
    limit = arguments.get("limit", 100)
    response = await client.get(f"{api_base_url}/user/{arguments['user_id']}", params={"skip": skip, "limit": limit}, timeout=10.0)
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_list_competency_users(client, arguments: dict, headers: dict, api_base_url: str):

    response = await client.get(f"{api_base_url}/{arguments['competency_id']}/users", timeout=10.0)
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_clear_user_competencies(client, arguments: dict, headers: dict, api_base_url: str):

    user_id = arguments["user_id"]
    response = await client.delete(f"{api_base_url}/user/{user_id}/clear", timeout=10.0)
    response.raise_for_status()
    return [TextContent(type="text", text=f"All competencies cleared for user {user_id}")]


async def handle_get_competency_stats(client, arguments: dict, headers: dict, api_base_url: str):

    response = await client.post(f"{api_base_url}/stats/counts", json=arguments, timeout=10.0)
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_get_agency_competency_coverage(client, arguments: dict, headers: dict, api_base_url: str):

    params = {}
    if "min_count" in arguments:
        params["min_count"] = arguments["min_count"]
    if "limit" in arguments:
        params["limit"] = arguments["limit"]
    response = await client.get(f"{api_base_url}/analytics/agency-coverage", params=params, timeout=10.0)
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_find_similar_consultants(client, arguments: dict, headers: dict, api_base_url: str):

    user_id = arguments["user_id"]
    top_n = arguments.get("top_n", 5)
    response = await client.get(
        f"{api_base_url}/analytics/similar-consultants/{user_id}",
        params={"top_n": top_n},
        timeout=10.0,
    )
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]
