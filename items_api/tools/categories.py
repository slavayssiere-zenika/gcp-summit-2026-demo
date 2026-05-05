import json
from mcp.types import TextContent, Tool


def get_categories_tools() -> list[Tool]:
    return [
        Tool(
            name="list_categories",
            description="List all item categories with pagination",
            inputSchema={
                "type": "object",
                "properties": {
                    "skip": {"type": "integer", "description": "Number of categories to skip", "default": 0},
                    "limit": {"type": "integer", "description": "Maximum number of categories to return", "default": 50}
                }
            }
        ),
        Tool(
            name="create_category",
            description="Create a new item category",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Category name"},
                    "description": {"type": "string", "description": "Category description (optional)"}
                },
                "required": ["name"]
            }
        )
    ]


async def handle_categories_tool(name: str, arguments: dict, client, api_base_url: str) -> list[TextContent]:
    if name == "list_categories":
        skip = arguments.get("skip", 0)
        limit = arguments.get("limit", 50)
        response = await client.get(f"{api_base_url}/categories", params={"skip": skip, "limit": limit})
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json()))]

    elif name == "create_category":
        response = await client.post(f"{api_base_url}/categories", json={
            "name": arguments["name"],
            "description": arguments.get("description")
        })
        response.raise_for_status()
        return [TextContent(type="text", text=json.dumps(response.json()))]

    return None
