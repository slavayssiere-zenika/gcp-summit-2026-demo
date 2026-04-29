import json
import logging
import asyncio
import os
import httpx
from mcp.types import TextContent

API_BASE_URL = os.getenv("USERS_API_URL", "http://localhost:8000")

async def handle_tool_call(name: str, arguments: dict, headers: dict, client: httpx.AsyncClient) -> list[TextContent]:
    """Exécute l'outil MCP demandé via l'API Users."""
    try:
        if name == "list_users":
            skip = arguments.get("skip", 0)
            limit = arguments.get("limit", 10)
            response = await client.get(f"{API_BASE_URL}/", params={"skip": skip, "limit": limit})
            response.raise_for_status()
            return [TextContent(type="text", text=json.dumps(response.json()))]

        elif name == "get_user":
            response = await client.get(f"{API_BASE_URL}/{arguments['user_id']}/")
            response.raise_for_status()
            return [TextContent(type="text", text=json.dumps(response.json()))]

        elif name == "get_users_bulk":
            user_ids = arguments.get("user_ids", [])
            if not user_ids:
                return [TextContent(type="text", text="[]")]
            response = await client.post(f"{API_BASE_URL}/bulk", json=user_ids)
            response.raise_for_status()
            return [TextContent(type="text", text=json.dumps(response.json()))]

        elif name == "create_user":
            response = await client.post(f"{API_BASE_URL}/", json={
                "username": arguments["username"],
                "email": arguments["email"],
                "password": arguments.get("password", ""),
                "full_name": arguments.get("full_name"),
                "is_anonymous": arguments.get("is_anonymous", False)
            })
            response.raise_for_status()
            return [TextContent(type="text", text=json.dumps(response.json()))]

        elif name == "update_user":
            data = {k: v for k, v in arguments.items() if k != "user_id" and v is not None}
            response = await client.put(f"{API_BASE_URL}/{arguments['user_id']}", json=data)
            response.raise_for_status()
            return [TextContent(type="text", text=json.dumps(response.json()))]

        elif name == "delete_user":
            response = await client.delete(f"{API_BASE_URL}/{arguments['user_id']}")
            response.raise_for_status()
            return [TextContent(type="text", text="User deleted successfully")]

        elif name == "health_check":
            response = await client.get(f"{API_BASE_URL}/health")
            response.raise_for_status()
            return [TextContent(type="text", text=json.dumps(response.json()))]

        elif name == "search_users":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 10)
            response = await client.get(f"{API_BASE_URL}/search", params={"query": query, "limit": limit})
            response.raise_for_status()
            data = response.json()
            if not data:
                return [TextContent(type="text", text=f"Aucun utilisateur trouvé dans la base de données pour la recherche '{query}'.")]
            return [TextContent(type="text", text=json.dumps(data))]

        elif name == "toggle_user_status":
            user_id = arguments["user_id"]
            is_active = arguments["is_active"]
            response = await client.put(f"{API_BASE_URL}/{user_id}", json={"is_active": is_active})
            response.raise_for_status()
            return [TextContent(type="text", text=json.dumps(response.json()))]

        elif name == "get_user_stats":
            response = await client.get(f"{API_BASE_URL}/stats")
            response.raise_for_status()
            return [TextContent(type="text", text=json.dumps(response.json()))]

        elif name == "get_user_duplicates":
            response = await client.get(f"{API_BASE_URL}/duplicates")
            response.raise_for_status()
            return [TextContent(type="text", text=json.dumps(response.json()))]

        elif name == "merge_users":
            source_id = arguments["source_id"]
            target_id = arguments["target_id"]
            response = await client.post(f"{API_BASE_URL}/merge", json={"source_id": source_id, "target_id": target_id})
            response.raise_for_status()
            return [TextContent(type="text", text=json.dumps(response.json()))]

        elif name == "search_anonymous_users":
            limit = arguments.get("limit", 10)
            response = await client.get(f"{API_BASE_URL}/search", params={"is_anonymous": True, "limit": limit})
            response.raise_for_status()
            return [TextContent(type="text", text=json.dumps(response.json()))]

        elif name == "get_user_availability":
            user_id = arguments['user_id']
            response = await client.get(f"{API_BASE_URL}/{user_id}")
            response.raise_for_status()
            user_data = response.json()
            unavailability_periods = user_data.get("unavailability_periods", [])

            # STAFF-003 : Croiser avec les missions actives (proposed_team) pour détecter
            # les conflits de staffing. Un consultant déjà proposé sur une mission active
            # n'est PAS pleinement disponible même si ses unavailability_periods sont vides.
            active_missions = []
            missions_api_url = os.getenv("MISSIONS_API_URL", "http://missions_api:8009")
            try:
                missions_response = await client.get(
                    f"{missions_api_url}/missions/user/{user_id}/active",
                    timeout=5.0
                )
                if missions_response.status_code == 200:
                    missions_data = missions_response.json()
                    active_missions = missions_data.get("active_missions", [])
            except Exception as missions_err:
                logging.error(f"[get_user_availability] missions_api indisponible pour user {user_id}: {missions_err}")
                raise

            result = {
                "user_id": user_id,
                "unavailability_periods": unavailability_periods,
                "active_missions": active_missions,
                "is_available": len(active_missions) == 0 and len(unavailability_periods) == 0,
                "conflict_detected": len(active_missions) > 0,
                "summary": (
                    f"CONFLIT DÉTECTÉ : Le consultant est déjà staffé sur {len(active_missions)} mission(s) active(s). "
                    f"Missions : {', '.join(m['mission_title'] for m in active_missions)}"
                    if active_missions
                    else (
                        f"INDISPONIBILITÉS DÉCLARÉES : {len(unavailability_periods)} période(s) d'indisponibilité."
                        if unavailability_periods
                        else "DISPONIBLE : Aucun conflit de staffing ni indisponibilité déclarée."
                    )
                )
            }
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "get_users_availability_bulk":
            user_ids = arguments.get("user_ids", [])
            if not user_ids:
                return [TextContent(type="text", text="[]")]
            
            async def fetch_user_avail(uid):
                try:
                    res = await client.get(f"{API_BASE_URL}/{uid}", timeout=5.0)
                    if res.status_code != 200: return None
                    udata = res.json()
                    unavail = udata.get("unavailability_periods", [])
                    
                    active_m = []
                    missions_api_url = os.getenv("MISSIONS_API_URL", "http://missions_api:8009")
                    try:
                        m_res = await client.get(f"{missions_api_url}/missions/user/{uid}/active", timeout=5.0)
                        if m_res.status_code == 200:
                            active_m = m_res.json().get("active_missions", [])
                    except Exception as e:
                        logging.error(f"[get_users_availability_bulk] missions_api indisponible pour user {uid}: {e}")
                        raise
                    
                    return {
                        "user_id": uid,
                        "unavailability_periods": unavail,
                        "active_missions": active_m,
                        "is_available": len(active_m) == 0 and len(unavail) == 0,
                        "conflict_detected": len(active_m) > 0
                    }
                except Exception as err:
                    logging.error(f"[get_users_availability_bulk] Erreur sur user {uid}: {err}")
                    raise
                    
            results = await asyncio.gather(*(fetch_user_avail(uid) for uid in user_ids))
            results = [r for r in results if r is not None]
            return [TextContent(type="text", text=json.dumps(results))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return [TextContent(type="text", text=f"CONFLIT (409) : {e.response.text}. Ne PAS réessayer l'outil avec les mêmes paramètres.")]
        return [TextContent(type="text", text=f"HTTP Error: {e.response.status_code} - {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]
