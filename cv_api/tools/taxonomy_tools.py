# flake8: noqa: E501, E701, E302, F541, E306

import json
import httpx
from mcp.types import TextContent

async def handle_recalculate_competencies_tree(client: httpx.AsyncClient, headers: dict, api_base_url: str) -> list[TextContent]:
    try:
        response = await client.post(f"{api_base_url}/recalculate_tree", headers=headers, timeout=120.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return [TextContent(type="text", text=f"CONFLIT (409) : {e.response.text}. Ne PAS réessayer l'outil avec les mêmes paramètres.")]
        return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Request failed: {str(e)}")]

async def handle_get_recalculate_tree_status(client: httpx.AsyncClient, headers: dict, api_base_url: str) -> list[TextContent]:
    try:
        response = await client.get(f"{api_base_url}/recalculate_tree/status", headers=headers, timeout=10.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

async def handle_get_skills_coverage(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    try:
        params = {"top_n": arguments.get("top_n", 50)}
        if arguments.get("agency"): params["agency"] = arguments["agency"]
        response = await client.get(f"{api_base_url}/analytics/skills-coverage", params=params, headers=headers, timeout=15.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

async def handle_global_reanalyze_cvs(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    try:
        params = {}
        if arguments.get("tag"): params["tag"] = arguments["tag"]
        if arguments.get("user_id"): params["user_id"] = arguments["user_id"]
        response = await client.post(f"{api_base_url}/reanalyze", params=params, headers=headers, timeout=30.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Request failed: {str(e)}")]

async def handle_get_reanalyze_status(client: httpx.AsyncClient, headers: dict, api_base_url: str) -> list[TextContent]:
    try:
        response = await client.get(f"{api_base_url}/reanalyze/status", headers=headers, timeout=10.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

async def handle_reindex_cv_embeddings(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    try:
        params = {}
        if arguments.get("tag"): params["tag"] = arguments["tag"]
        if arguments.get("user_id"): params["user_id"] = arguments["user_id"]
        response = await client.post(f"{api_base_url}/reindex-embeddings", params=params, headers=headers, timeout=30.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

async def handle_start_bulk_cv_reanalyse(client: httpx.AsyncClient, headers: dict, api_base_url: str) -> list[TextContent]:
    try:
        response = await client.post(f"{api_base_url}/bulk-reanalyse/start", headers=headers, timeout=30.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return [TextContent(type="text", text=f"CONFLIT (409) : une ré-analyse est déjà en cours. Utiliser get_bulk_cv_reanalyse_status pour suivre.")]
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

async def handle_get_bulk_cv_reanalyse_status(client: httpx.AsyncClient, headers: dict, api_base_url: str) -> list[TextContent]:
    try:
        response = await client.get(f"{api_base_url}/bulk-reanalyse/status", headers=headers, timeout=15.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

async def handle_cancel_bulk_cv_reanalyse(client: httpx.AsyncClient, headers: dict, api_base_url: str) -> list[TextContent]:
    try:
        response = await client.post(f"{api_base_url}/bulk-reanalyse/cancel", headers=headers, timeout=15.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

async def handle_get_data_quality_report(client: httpx.AsyncClient, headers: dict, api_base_url: str) -> list[TextContent]:
    try:
        response = await client.get(f"{api_base_url}/bulk-reanalyse/data-quality", headers=headers, timeout=30.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_reindex_mission_chunks(client: httpx.AsyncClient, arguments: dict, headers: dict, api_base_url: str) -> list[TextContent]:
    """R7 — Handler MCP pour la ré-indexation des chunks de missions (RAG multi-vecteur)."""
    try:
        params = {}
        if arguments.get("tag"):
            params["tag"] = arguments["tag"]
        if arguments.get("user_id"):
            params["user_id"] = arguments["user_id"]
        response = await client.post(
            f"{api_base_url}/bulk-reanalyse/reindex-mission-chunks",
            params=params,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": f"API Error {e.response.status_code}: {e.response.text}"}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]
