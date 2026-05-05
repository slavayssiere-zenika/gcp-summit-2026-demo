import json
from mcp.types import TextContent, Tool


def get_items_tools() -> list[Tool]:
    return [
        Tool(
            name="list_items",
            description="List all items with pagination",
            inputSchema={
                "type": "object",
                "properties": {
                    "skip": {"type": "integer", "description": "Number of items to skip", "default": 0},
                    "limit": {"type": "integer", "description": "Maximum number of items to return", "default": 10}
                }
            },
            meta={"ui": {"resourceUri": "ui://items"}}
        ),
        Tool(
            name="get_item",
            description="Get an item by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "The item ID"}
                },
                "required": ["item_id"]
            }
        ),
        Tool(
            name="create_item",
            description="Create a new item (requires valid user_id)",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Item name"},
                    "description": {"type": "string", "description": "Item description (optional)"},
                    "user_id": {"type": "integer", "description": "ID of the user who owns this item"},
                    "category_ids": {"type": "array", "items": {"type": "integer"}, "description": "List of category IDs"},
                    "metadata_json": {"type": "object", "description": "Rich metadata (JSONB) for missions, etc."}
                },
                "required": ["name", "user_id", "category_ids"]
            }
        ),
        Tool(
            name="get_item_with_user",
            description="Get an item with user information",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "The item ID"}
                },
                "required": ["item_id"]
            }
        ),
        Tool(
            name="health_check",
            description="Check if the API is healthy",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="update_item",
            description="Update an existing item",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "The item ID"},
                    "name": {"type": "string", "description": "New name (optional)"},
                    "description": {"type": "string", "description": "New description (optional)"},
                    "category_ids": {"type": "array", "items": {"type": "integer"}, "description": "New category IDs (optional)"},
                    "metadata_json": {"type": "object", "description": "New metadata (optional)"}
                },
                "required": ["item_id"]
            }
        ),
        Tool(
            name="delete_item",
            description="Delete an item",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "The item ID"}
                },
                "required": ["item_id"]
            }
        ),
        Tool(
            name="search_items",
            description="Search items by name or description",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Maximum number of results", "default": 10}
                },
                "required": ["query"]
            },
            meta={"ui": {"resourceUri": "ui://items"}}
        ),
        Tool(
            name="get_items_by_user",
            description="Get all items for a specific user",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "The user ID"}
                },
                "required": ["user_id"]
            },
            meta={"ui": {"resourceUri": "ui://items"}}
        ),
        Tool(
            name="get_item_stats",
            description="Get statistics about items",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="bulk_create_items",
            description=(
                "Crée plusieurs items en une seule requête (bulk). "
                "Très performant pour l'ingestion de CVs (création de profils consultants en masse). "
                "Chaque item doit avoir un nom, un user_id et au moins une catégorie. "
                "Idémpotent : les items existants sont mis à jour plutôt que dupliqués."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "Liste des items à créer",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Nom de l'item"},
                                "description": {"type": "string", "description": "Description (optionnel)"},
                                "user_id": {"type": "integer", "description": "ID de l'utilisateur propriétaire"},
                                "category_ids": {"type": "array", "items": {"type": "integer"}, "description": "IDs des catégories"},
                                "metadata_json": {"type": "object", "description": "Métadonnées riches (JSONB)"}
                            },
                            "required": ["name", "user_id", "category_ids"]
                        }
                    }
                },
                "required": ["items"]
            }
        ),
        Tool(
            name="delete_user_items",
            description=(
                "(Admin / Service Account only) Supprime tous les items (missions) d'un utilisateur. "
                "Utilisé par le pipeline de ré-analyse globale (Vertex AI Batch) avant la "
                "ré-indexation complète des missions extraites du nouveau prompt LLM."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "L'ID de l'utilisateur dont les items doivent être supprimés"}
                },
                "required": ["user_id"]
            }
        )
    ]


async def handle_items_tool(name: str, arguments: dict, client, api_base_url: str, users_api_url: str) -> list[TextContent]:
    if name == "list_items":
        skip = arguments.get("skip", 0)
        limit = arguments.get("limit", 10)
        response = await client.get(f"{api_base_url}/", params={"skip": skip, "limit": limit})
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json()))]

    elif name == "get_item":
        response = await client.get(f"{api_base_url}/{arguments['item_id']}/")
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json()))]

    elif name == "create_item":
        payload = {
            "name": arguments["name"],
            "description": arguments.get("description"),
            "user_id": arguments["user_id"],
            "category_ids": arguments.get("category_ids", []),
            "metadata_json": arguments.get("metadata_json")
        }
        response = await client.post(f"{api_base_url}/", json=payload)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json()))]

    elif name == "get_item_with_user":
        item_response = await client.get(f"{api_base_url}/{arguments['item_id']}/")
        item_response.raise_for_status()
        item_data = item_response.json()

        user_response = await client.get(f"{users_api_url.rstrip('/')}/{item_data.get('user_id')}")
        if user_response.status_code == 200:
            item_data["user"] = user_response.json()

        return [TextContent(type="text", text=json.dumps(item_data))]

    elif name == "health_check":
        response = await client.get(f"{api_base_url}/health")
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json()))]

    elif name == "update_item":
        item_id = arguments["item_id"]
        data = {k: v for k, v in arguments.items() if k not in ["item_id"] and v is not None}
        response = await client.put(f"{api_base_url}/{item_id}", json=data)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json()))]

    elif name == "delete_item":
        item_id = arguments["item_id"]
        response = await client.delete(f"{api_base_url}/{item_id}")
        response.raise_for_status()
        return [TextContent(type="text", text="Item deleted successfully")]

    elif name == "search_items":
        query = arguments.get("query", "")
        limit = arguments.get("limit", 10)
        response = await client.get(f"{api_base_url}/search/query", params={"query": query, "limit": limit})
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json()))]

    elif name == "get_items_by_user":
        try:
            user_id = int(arguments["user_id"])
        except Exception:
            return [TextContent(type="text", text=f"Error: user_id must be an integer, got {arguments.get('user_id')}")]
        
        response = await client.get(f"{api_base_url}/user/{user_id}", params={"skip": 0, "limit": 100})
        response.raise_for_status()
        data = response.json()
        
        return [TextContent(type="text", text=json.dumps(data))]

    elif name == "get_item_stats":
        response = await client.get(f"{api_base_url}/stats")
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json()))]

    elif name == "bulk_create_items":
        items_payload = arguments.get("items", [])
        if not items_payload:
            return [TextContent(type="text", text=json.dumps({"success": False, "error": "Paramètre 'items' manquant ou vide."}))]
        response = await client.post(f"{api_base_url}/bulk", json={"items": items_payload}, timeout=60.0)
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json()))]

    elif name == "delete_user_items":
        user_id = arguments["user_id"]
        response = await client.delete(f"{api_base_url}/user/{user_id}/items")
        response.raise_for_status()
        return [TextContent(type="text", text=f"All items deleted for user {user_id}")]

    return None
