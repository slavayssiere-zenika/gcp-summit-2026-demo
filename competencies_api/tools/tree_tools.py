# flake8: noqa: E501, E701, E302, F541, E306
import json
import httpx
from mcp.types import TextContent


async def handle_search_competencies(client, arguments: dict, headers: dict, api_base_url: str):

    response = await client.get(f"{api_base_url}/search", params=arguments)
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_get_competency(client, arguments: dict, headers: dict, api_base_url: str):

    response = await client.get(f"{api_base_url}/{arguments['competency_id']}/")
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_create_competency(client, arguments: dict, headers: dict, api_base_url: str):

    response = await client.post(f"{api_base_url}/", json=arguments)
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_update_competency(client, arguments: dict, headers: dict, api_base_url: str):

    comp_id = arguments["competency_id"]
    data = {k: v for k, v in arguments.items() if k != "competency_id" and v is not None}
    response = await client.put(f"{api_base_url}/{comp_id}", json=data)
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_delete_competency(client, arguments: dict, headers: dict, api_base_url: str):

    response = await client.delete(f"{api_base_url}/{arguments['competency_id']}")
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps({"message": "Competency deleted successfully"}))]


async def handle_list_competency_suggestions(client, arguments: dict, headers: dict, api_base_url: str):

    params = {}
    if "status" in arguments:
        params["status"] = arguments["status"]
    if "limit" in arguments:
        params["limit"] = arguments["limit"]
    response = await client.get(f"{api_base_url}/suggestions", params=params)
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_create_competency_suggestion(client, arguments: dict, headers: dict, api_base_url: str):

    response = await client.post(f"{api_base_url}/suggestions", json=arguments)
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_review_competency_suggestion(client, arguments: dict, headers: dict, api_base_url: str):

    suggestion_id = arguments.pop("suggestion_id")
    response = await client.patch(
        f"{api_base_url}/suggestions/{suggestion_id}/review",
        json=arguments
    )
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]


async def handle_list_competencies(client, arguments: dict, headers: dict, api_base_url: str):
    skip = arguments.get("skip", 0)
    limit = arguments.get("limit", 50)
    response = await client.get(
        f"{api_base_url}/",
        params={"skip": skip, "limit": limit},
        timeout=10.0,
    )
    response.raise_for_status()
    return [TextContent(type="text", text=json.dumps(response.json()))]
