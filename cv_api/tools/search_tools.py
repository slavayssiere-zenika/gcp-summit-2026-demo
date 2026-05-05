# flake8: noqa: E501, E701, E302, F541, E306

import json
import httpx
from mcp.types import TextContent

async def handle_search_best_candidates(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    query = arguments.get("query")
    limit = arguments.get("limit", 5)
    skip = arguments.get("skip", 0)
    agency = arguments.get("agency")
    if not query:
        return [TextContent(type="text", text="Error: Missing query argument.")]
    try:
        params = {"query": query, "limit": limit, "skip": skip}
        if agency: params["agency"] = agency
        response = await client.get(f"{api_base_url}/search", params=params, headers=headers, timeout=60.0)
        response.raise_for_status()
        data = response.json()
        if not data:
            return [TextContent(type="text", text=f"Aucun candidat ne correspond à la recherche sémantique '{query}' dans la base de CVs.")]
        return [TextContent(type="text", text=json.dumps(data, indent=2))]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return [TextContent(type="text", text=f"CONFLIT (409) : {e.response.text}. Ne PAS réessayer l'outil avec les mêmes paramètres.")]
        return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Request failed: {str(e)}")]

async def handle_get_users_by_tag(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    tag = arguments.get("tag")
    skip = arguments.get("skip", 0)
    limit = arguments.get("limit", 50)
    if not tag:
        return [TextContent(type="text", text="Error: Missing tag argument.")]
    try:
        response = await client.get(f"{api_base_url}/users/tag/{tag}", params={"skip": skip, "limit": limit}, headers=headers, timeout=10.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Request failed: {str(e)}")]

async def handle_get_most_experienced_consultants(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    limit = arguments.get("limit", 5)
    agency = arguments.get("agency")
    params = {"limit": limit}
    if agency: params["agency"] = agency
    try:
        response = await client.get(f"{api_base_url}/ranking/experience", params=params, headers=headers, timeout=20.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Request failed: {str(e)}")]

async def handle_get_tags_map(client: httpx.AsyncClient, headers: dict, api_base_url: str) -> list[TextContent]:
    try:
        response = await client.get(f"{api_base_url}/users/tags/map", headers=headers, timeout=10.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

async def handle_find_similar_consultants(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    user_id = arguments.get("user_id")
    if not user_id:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": "user_id requis"}))]
    try:
        params = {"limit": arguments.get("limit", 5)}
        if arguments.get("agency"): params["agency"] = arguments["agency"]
        response = await client.get(f"{api_base_url}/user/{user_id}/similar", params=params, headers=headers, timeout=15.0)
        response.raise_for_status()
        data = response.json()
        if not data:
            return [TextContent(type="text", text=f"Aucun consultant similaire trouvé pour user_id={user_id}.")]
        return [TextContent(type="text", text=json.dumps(data, indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

async def handle_search_candidates_multi_criteria(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    queries = arguments.get("queries")
    if not queries:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": "queries requis (liste de critères)"}))]
    try:
        payload = {"queries": queries, "limit": arguments.get("limit", 10)}
        if arguments.get("weights"): payload["weights"] = arguments["weights"]
        if arguments.get("agency"): payload["agency"] = arguments["agency"]
        response = await client.post(f"{api_base_url}/search/multi-criteria", json=payload, headers=headers, timeout=60.0)
        response.raise_for_status()
        data = response.json()
        if not data:
            return [TextContent(type="text", text=f"Aucun candidat correspondant à ces critères combinés.")]
        return [TextContent(type="text", text=json.dumps(data, indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

async def handle_get_rag_snippet(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    user_id = arguments.get("user_id")
    query = arguments.get("query")
    if not user_id or not query:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": "user_id et query requis"}))]
    try:
        response = await client.get(f"{api_base_url}/user/{user_id}/rag-snippet", params={"query": query, "top_k": arguments.get("top_k", 3)}, headers=headers, timeout=45.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

async def handle_match_mission_to_candidates(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    mission_id = arguments.get("mission_id")
    if not mission_id:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": "mission_id requis"}))]
    try:
        params = {"mission_id": mission_id, "limit": arguments.get("limit", 10)}
        if arguments.get("agency"): params["agency"] = arguments["agency"]
        response = await client.post(f"{api_base_url}/search/mission-match", params=params, headers=headers, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        if not data:
            return [TextContent(type="text", text=f"Aucun candidat correspondant à la mission {mission_id}.")]
        return [TextContent(type="text", text=json.dumps(data, indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]
