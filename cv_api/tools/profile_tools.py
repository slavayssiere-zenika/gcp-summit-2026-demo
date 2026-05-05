# flake8: noqa: E501, E701, E302, F541, E306

import json
import httpx
from mcp.types import TextContent

async def handle_analyze_cv(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    url = arguments.get("url")
    source_tag = arguments.get("source_tag")
    folder_name = arguments.get("folder_name")
    if not url:
        return [TextContent(type="text", text="Error: Missing url argument.")]
    try:
        payload = {"url": url}
        if source_tag: payload["source_tag"] = source_tag
        if folder_name: payload["folder_name"] = folder_name
        response = await client.post(f"{api_base_url}/import", json=payload, headers=headers, timeout=60.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return [TextContent(type="text", text=f"CONFLIT (409) : {e.response.text}. Ne PAS réessayer l'outil avec les mêmes paramètres.")]
        return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Request failed: {str(e)}")]

async def handle_get_cv_status_bulk(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    user_ids = arguments.get("user_ids", [])
    if not user_ids:
        return [TextContent(type="text", text="[]")]
    import asyncio
    async def check_cv(uid):
        try:
            res = await client.get(f"{api_base_url}/{uid}", headers=headers, timeout=5.0)
            return {"user_id": uid, "has_cv": res.status_code == 200}
        except Exception:
            return {"user_id": uid, "has_cv": False}
    results = await asyncio.gather(*(check_cv(uid) for uid in user_ids))
    return [TextContent(type="text", text=json.dumps(results))]

async def handle_get_user_cv(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    user_id = arguments.get("user_id")
    skip = arguments.get("skip", 0)
    limit = arguments.get("limit", 50)
    if not user_id:
        return [TextContent(type="text", text="Error: Missing user_id argument.")]
    try:
        response = await client.get(f"{api_base_url}/user/{user_id}", params={"skip": skip, "limit": limit}, headers=headers, timeout=10.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return [TextContent(type="text", text=f"CONFLIT (409) : {e.response.text}. Ne PAS réessayer l'outil avec les mêmes paramètres.")]
        return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Request failed: {str(e)}")]

async def handle_get_user_missions(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    user_id = arguments.get("user_id")
    skip = arguments.get("skip", 0)
    limit = arguments.get("limit", 50)
    if not user_id:
        return [TextContent(type="text", text="Error: Missing user_id argument.")]
    try:
        response = await client.get(f"{api_base_url}/user/{user_id}/missions", params={"skip": skip, "limit": limit}, headers=headers, timeout=10.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Request failed: {str(e)}")]

async def handle_get_candidate_rag_context(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    user_id = arguments.get("user_id")
    if not user_id:
        return [TextContent(type="text", text="Error: Missing user_id argument.")]
    try:
        response = await client.get(f"{api_base_url}/user/{user_id}/details", headers=headers, timeout=20.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Request failed: {str(e)}")]
