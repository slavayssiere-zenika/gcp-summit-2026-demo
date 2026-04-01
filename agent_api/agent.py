import os
import json
import logging
from typing import Optional
from google.genai import types
from google.adk.agents import Agent

from agent_api.mcp_client import get_users_mcp, get_items_mcp, get_competencies_mcp, get_loki_mcp, get_cv_mcp

logger = logging.getLogger(__name__)

_session_service = None

def get_session_service():
    global _session_service
    if _session_service is None:
        from agent_api.session import RedisSessionService
        _session_service = RedisSessionService()
    return _session_service


def format_mcp_result(result: list, data_type: str) -> dict:
    if not result:
        return {"result": "No result"}
    
    raw_text = result[0].get("text", "No result")
    if raw_text == "No result":
        return {"result": raw_text}
        
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict):
            if "items" not in data:
                data = {"items": [data]}
            data["dataType"] = data_type
        elif isinstance(data, list):
            data = {"dataType": data_type, "items": data}
            
        return {"result": json.dumps(data)}
    except Exception:
        return {"result": raw_text}


# --- CV Tools ---

async def analyze_cv(url: str) -> dict:
    """
    Télécharge, parse, extrait et convertit un CV (via un lien Google Docs) dans le système.
    Crée automatiquement le candidat, identifie ses compétences sémantiquement, et les rattache.
    Utiliser UNIQUEMENT si l'utilisateur demande d'analyser, d'importer ou de lire un CV depuis un lien.

    Args:
        url (str): L'URL publique du Google Doc contenant le CV.
    """
    mcp = await get_cv_mcp()
    result = await mcp.call_tool("analyze_cv", {"url": url})
    return format_mcp_result(result, "cv")

async def search_best_candidates(query: str, limit: int = 5) -> dict:
    """
    Recherche sémantiquement les meilleurs candidats pour un projet ou un besoin technique (RAG vectoriel).
    Exemple de query : 'un expert Kubernetes (GKE) qui gère du DevOps'.
    Utiliser cet outil UNIQUEMENT pour chercher, identifier, ou lister le(s) meilleur(s) profil(s) selon un besoin technique.
    
    Args:
        query (str): La phrase décrivant le besoin ou le rôle (technologies souhaitées, niveau...).
        limit (int): Le nombre maximum de profils à retenir (défaut 5).
    """
    mcp = await get_cv_mcp()
    result = await mcp.call_tool("search_best_candidates", {"query": query, "limit": limit})
    return format_mcp_result(result, "search_results")

async def recalculate_competencies_tree() -> dict:
    """
    Recalcule totalement l'arbre d'organisation des compétences RH (Taxonomie globale) en lisant la base de données entière des CVs avec Gemini. 
    L'arbre généré est renvoyé. Si l'arbre t'est retourné avec succès, affiche-le obligatoirement dans ta réponse JSON avec le format `"display_type": "tree"` ET assigne l'arbre à l'attribut `"data": [...]` pour que l'interface graphique de Vue.js le rende magiquement.
    (L'opération est sécurisée, elle donne un aperçu JSON structurel massif).
    """
    mcp = await get_cv_mcp()
    result = await mcp.call_tool("recalculate_competencies_tree", {})
    return format_mcp_result(result, "tree")

CV_TOOLS = [
    analyze_cv,
    search_best_candidates,
    recalculate_competencies_tree
]

# --- Users Tools ---

async def list_users(skip: int = 0, limit: int = 10) -> dict:
    """
    Liste les utilisateurs du système avec pagination.

    Args:
        skip (int): Nombre d'utilisateurs à ignorer (pagination). Par défaut 0.
        limit (int): Nombre maximum d'utilisateurs à retourner. Par défaut 10.
    """
    mcp = await get_users_mcp()
    result = await mcp.call_tool("list_users", {"skip": skip, "limit": limit})
    return format_mcp_result(result, "user")

async def get_user(user_id: int) -> dict:
    """
    Récupère les informations détaillées d'un utilisateur spécifique par son ID.

    Args:
        user_id (int): L'identifiant unique de l'utilisateur.
    """
    mcp = await get_users_mcp()
    result = await mcp.call_tool("get_user", {"user_id": user_id})
    return format_mcp_result(result, "user")

async def create_user(username: str, email: str, full_name: Optional[str] = None) -> dict:
    """
    Crée un nouvel utilisateur dans le système.

    Args:
        username (str): Le nom d'utilisateur unique.
        email (str): L'adresse email de l'utilisateur.
        full_name (str, optional): Le nom complet de l'utilisateur.
    """
    mcp = await get_users_mcp()
    result = await mcp.call_tool("create_user", {"username": username, "email": email, "full_name": full_name})
    return format_mcp_result(result, "user")

async def update_user(user_id: int, username: Optional[str] = None, email: Optional[str] = None, 
                full_name: Optional[str] = None, is_active: Optional[bool] = None) -> dict:
    """
    Met à jour les informations d'un utilisateur existant.

    Args:
        user_id (int): L'identifiant de l'utilisateur à modifier.
        username (str, optional): Nouveau nom d'utilisateur.
        email (str, optional): Nouvelle adresse email.
        full_name (str, optional): Nouveau nom complet.
        is_active (bool, optional): État d'activation du compte.
    """
    params = {"user_id": user_id}
    if username is not None: params["username"] = username
    if email is not None: params["email"] = email
    if full_name is not None: params["full_name"] = full_name
    if is_active is not None: params["is_active"] = is_active
    mcp = await get_users_mcp()
    result = await mcp.call_tool("update_user", params)
    return format_mcp_result(result, "user")

async def delete_user(user_id: int) -> dict:
    """
    Supprime un utilisateur du système. Attention, cette action est irréversible.

    Args:
        user_id (int): L'identifiant de l'utilisateur à supprimer.
    """
    mcp = await get_users_mcp()
    result = await mcp.call_tool("delete_user", {"user_id": user_id})
    return format_mcp_result(result, "user")

async def search_users(query: str, limit: int = 10) -> dict:
    """
    Recherche des utilisateurs par prénom, nom, email ou nom d'utilisateur.

    Args:
        query (str): Le terme de recherche (ex: un nom, un prénom ou un email).
        limit (int): Nombre maximum de résultats. Par défaut 10.
    """
    mcp = await get_users_mcp()
    result = await mcp.call_tool("search_users", {"query": query, "limit": limit})
    return format_mcp_result(result, "user")

async def toggle_user_status(user_id: int, is_active: bool) -> dict:
    """
    Active ou désactive un utilisateur.

    Args:
        user_id (int): L'identifiant de l'utilisateur.
        is_active (bool): True pour activer, False pour désactiver.
    """
    mcp = await get_users_mcp()
    result = await mcp.call_tool("toggle_user_status", {"user_id": user_id, "is_active": is_active})
    return format_mcp_result(result, "user")

async def get_user_stats() -> dict:
    """
    Obtient des statistiques globales sur les utilisateurs (total, actifs, inactifs).
    """
    mcp = await get_users_mcp()
    result = await mcp.call_tool("get_user_stats", {})
    return format_mcp_result(result, "user_stats")

async def health_check_users() -> dict:
    """
    Vérifie si l'API des utilisateurs est opérationnelle.
    """
    mcp = await get_users_mcp()
    result = await mcp.call_tool("health_check_users", {})
    return format_mcp_result(result, "health")

USERS_TOOLS = [
    list_users, get_user, create_user, update_user, delete_user, 
    search_users, toggle_user_status, get_user_stats, health_check_users
]

# --- Items Tools ---

async def list_items(skip: int = 0, limit: int = 10) -> dict:
    """
    Liste les items présents dans le système avec pagination.

    Args:
        skip (int): Nombre d'items à ignorer. Par défaut 0.
        limit (int): Nombre maximum d'items à retourner. Par défaut 10.
    """
    mcp = await get_items_mcp()
    result = await mcp.call_tool("list_items", {"skip": skip, "limit": limit})
    return format_mcp_result(result, "item")

async def get_item(item_id: int) -> dict:
    """
    Récupère les informations d'un item spécifique par son ID.

    Args:
        item_id (int): L'identifiant unique de l'item.
    """
    mcp = await get_items_mcp()
    result = await mcp.call_tool("get_item", {"item_id": item_id})
    return format_mcp_result(result, "item")

async def create_item(name: str, user_id: int, description: Optional[str] = None) -> dict:
    """
    Crée un nouvel item associé à un utilisateur.

    Args:
        name (str): Le nom de l'item.
        user_id (int): L'ID de l'utilisateur propriétaire de l'item.
        description (str, optional): Une description de l'item.
    """
    mcp = await get_items_mcp()
    result = await mcp.call_tool("create_item", {"name": name, "user_id": user_id, "description": description})
    return format_mcp_result(result, "item")

async def update_item(item_id: int, name: Optional[str] = None, description: Optional[str] = None) -> dict:
    """
    Met à jour les informations d'un item existant.

    Args:
        item_id (int): L'identifiant de l'item à modifier.
        name (str, optional): Nouveau nom de l'item.
        description (str, optional): Nouvelle description.
    """
    params = {"item_id": item_id}
    if name is not None: params["name"] = name
    if description is not None: params["description"] = description
    mcp = await get_items_mcp()
    result = await mcp.call_tool("update_item", params)
    return format_mcp_result(result, "item")

async def delete_item(item_id: int) -> dict:
    """
    Supprime un item du système.

    Args:
        item_id (int): L'identifiant de l'item à supprimer.
    """
    mcp = await get_items_mcp()
    result = await mcp.call_tool("delete_item", {"item_id": item_id})
    return format_mcp_result(result, "item")

async def get_item_with_user(item_id: int) -> dict:
    """
    Récupère un item enrichi avec les informations de son propriétaire.

    Args:
        item_id (int): L'identifiant de l'item.
    """
    mcp = await get_items_mcp()
    result = await mcp.call_tool("get_item_with_user", {"item_id": item_id})
    return format_mcp_result(result, "item")

async def search_items(query: str, limit: int = 10) -> dict:
    """
    Recherche des items par nom ou description.

    Args:
        query (str): Le terme de recherche.
        limit (int): Nombre maximum de résultats. Par défaut 10.
    """
    mcp = await get_items_mcp()
    result = await mcp.call_tool("search_items", {"query": query, "limit": limit})
    return format_mcp_result(result, "item")

async def get_items_by_user(user_id: int) -> dict:
    """
    Récupère TOUS les items appartenant à un utilisateur spécifique.

    Args:
        user_id (int): L'identifiant de l'utilisateur dont on veut lister les items.
    """
    mcp = await get_items_mcp()
    result = await mcp.call_tool("get_items_by_user", {"user_id": user_id})
    return format_mcp_result(result, "item")

async def get_item_stats() -> dict:
    """
    Obtient des statistiques sur les items (total, répartition par utilisateur).
    """
    mcp = await get_items_mcp()
    result = await mcp.call_tool("get_item_stats", {})
    return format_mcp_result(result, "item_stats")

async def health_check_items() -> dict:
    """
    Vérifie si l'API des items est opérationnelle.
    """
    mcp = await get_items_mcp()
    result = await mcp.call_tool("health_check_items", {})
    return format_mcp_result(result, "health")

ITEMS_TOOLS = [
    list_items, get_item, create_item, update_item, delete_item, 
    get_item_with_user, search_items, get_items_by_user, get_item_stats, health_check_items
]

# --- Competencies Tools ---

async def list_competencies(skip: int = 0, limit: int = 10) -> dict:
    """
    Liste toutes les compétences (skills) disponibles dans le catalogue.
    """
    mcp = await get_competencies_mcp()
    result = await mcp.call_tool("list_competencies", {"skip": skip, "limit": limit})
    return format_mcp_result(result, "competency")

async def get_competency(competency_id: int) -> dict:
    """
    Récupère les détails d'une compétence spécifique.
    """
    mcp = await get_competencies_mcp()
    result = await mcp.call_tool("get_competency", {"competency_id": competency_id})
    return format_mcp_result(result, "competency")

async def create_competency(name: str, description: Optional[str] = None, parent_id: Optional[int] = None) -> dict:
    """
    Crée une nouvelle compétence dans le catalogue. Peut être rattachée à une compétence parente si parent_id est précisé.
    """
    mcp = await get_competencies_mcp()
    payload = {"name": name, "description": description}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    result = await mcp.call_tool("create_competency", payload)
    return format_mcp_result(result, "competency")


async def delete_competency(competency_id: int) -> dict:
    """
    Supprime définitivement une compétence du catalogue.
    """
    mcp = await get_competencies_mcp()
    result = await mcp.call_tool("delete_competency", {"competency_id": competency_id})
    return format_mcp_result(result, "competency")

async def assign_competency_to_user(user_id: int, competency_id: int) -> dict:
    """
    Assigne une compétence à un utilisateur spécifique.
    """
    mcp = await get_competencies_mcp()
    result = await mcp.call_tool("assign_competency_to_user", {"user_id": user_id, "competency_id": competency_id})
    return format_mcp_result(result, "competency")

async def remove_competency_from_user(user_id: int, competency_id: int) -> dict:
    """
    Retire une compétence d'un utilisateur.
    """
    mcp = await get_competencies_mcp()
    result = await mcp.call_tool("remove_competency_from_user", {"user_id": user_id, "competency_id": competency_id})
    return format_mcp_result(result, "competency")

async def list_user_competencies(user_id: int) -> dict:
    """
    Liste toutes les compétences possédées par un utilisateur donné.
    """
    mcp = await get_competencies_mcp()
    result = await mcp.call_tool("list_user_competencies", {"user_id": user_id})
    return format_mcp_result(result, "competency")

COMPETENCIES_TOOLS = [
    list_competencies, get_competency, create_competency, delete_competency,
    assign_competency_to_user, remove_competency_from_user, list_user_competencies
]

# --- Loki Tools ---

async def loki_query(query: str, start: str = None, end: str = None, limit: int = 100) -> dict:
    """
    Exécute une requête LogQL sur Grafana Loki pour analyser les logs des conteneurs.

    Args:
        query (str): Requête LogQL (ex: '{container="items_api"} |= "error"').
        start (str): Timestamp de début (ex: '1h'). Optionnel.
        end (str): Timestamp de fin. Optionnel.
        limit (int): Nombre max de lignes retournées. Par défaut 100.
    """
    try:
        mcp = await get_loki_mcp()
        args = {"query": query, "limit": limit}
        if start: args["start"] = start
        if end: args["end"] = end
        result = await mcp.call_tool("loki_query", args)
        return format_mcp_result(result, "loki_logs")
    except Exception as e:
        logger.error(f"Error in loki_query: {e}")
        return {"result": f"Erreur lors de l'interrogation de Loki: {e}"}

async def loki_label_names() -> dict:
    """
    Liste les noms des labels Loki disponibles pour filtrer les logs.
    """
    try:
        mcp = await get_loki_mcp()
        result = await mcp.call_tool("loki_label_names", {})
        return format_mcp_result(result, "loki_labels")
    except Exception as e:
        logger.error(f"Error in loki_label_names: {e}")
        return {"result": f"Erreur Loki: {e}"}

async def loki_label_values(label: str) -> dict:
    """
    Liste les valeurs possibles pour un label Loki spécifique (ex: conteneur).
    """
    try:
        mcp = await get_loki_mcp()
        result = await mcp.call_tool("loki_label_values", {"label": label})
        return format_mcp_result(result, "loki_values")
    except Exception as e:
        logger.error(f"Error in loki_label_values: {e}")
        return {"result": f"Erreur Loki: {e}"}

async def loki_metric_aggregator(query: str) -> dict:
    """
    Exécute une requête LogQL d'agrégation (Matrix/Vector) sur Grafana Loki.
    Outil STRICTEMENT réservé aux statistiques, calculs, sum(), rate(), etc.
    Ne PAS utiliser pour récupérer des logs bruts.
    Exemple pour le service le plus utilisé: sum by (container) (count_over_time({container=~".+"}[1h]))
    
    Args:
        query (str): Requête LogQL d'agrégation mathématique (Matrix/Vector).
    """
    import httpx
    import os
    try:
        loki_url = os.getenv("LOKI_URL", "http://loki:3100")
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(f"{loki_url}/loki/api/v1/query", params={"query": query})
            if res.status_code == 200:
                data = res.json()
                return {"result": str(data)}
            return {"result": f"Erreur Loki HTTP {res.status_code}: {res.text}"}
    except Exception as e:
        return {"result": f"Exception Loki Metrics: {str(e)}"}

LOKI_TOOLS = [
    loki_query,
    loki_label_names,
    loki_label_values,
    loki_metric_aggregator
]

INSTRUCTION = """Tu es un assistant IA spécialisé dans la gestion des utilisateurs, des items et des compétences.

Tu as accès à trois APIs:
1. **Users API** - Pour gérer les utilisateurs (liste, création, modification, suppression, recherche)
2. **Items API** - Pour gérer les items (liste, création, modification, suppression, recherche)
3. **Competencies API** - Pour gérer les compétences et les assigner aux utilisateurs

**Instructions Cruciales pour l'Interface Graphique (Frontend):**
- **Tu DOIS IMPÉRATIVEMENT formater tes réponses finales sous forme de code JSON valide**. Ne réponds plus par du texte brut classique. Le frontend s'attend à parser ta réponse visuellement.
- La structure de ton JSON de réponse final DOIT être la suivante :
```json
{
  "reply": "Ton message textuel naturel en Français et concis (ex: J'ai trouvé 3 candidats parfaits).",
  "display_type": "table", // ou "cards", "profile", "text_only" selon ce qui est le plus adapté
  "data": [ {} ] // Injecte ici les données brutes issues des outils MCP (les items, les profils ou les IDs)
}
```
- Pour les listes ou résultats de recherche, privilégie `table` ou `cards` dans "display_type" et assure-toi que "data" contient le tableau complet des éléments trouvés.
- Si une erreur se produit, utilise le `display_type` "error" et explique l'erreur dans "reply".

Ne rajoute aucun texte avant ou après le bloc JSON. Réponds en Markdown JSON (ex: ```json ... ```) ou JSON pur."""


def create_agent():
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    agent = Agent(
        name="assistant_zenika",
        model=model,
        generate_content_config=types.GenerateContentConfig(
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(initial_delay=1, attempts=2),
            )
        ),
        instruction=INSTRUCTION,
        description="Assistant IA pour la gestion des utilisateurs, items et compétences. Et analyse des logs via Loki.",
        tools=[*USERS_TOOLS, *ITEMS_TOOLS, *COMPETENCIES_TOOLS, *CV_TOOLS, *LOKI_TOOLS]
    )
    
    return agent


async def run_agent_query(query: str, session_id: str | None = None) -> dict:
    from google.adk.runners import Runner
    import uuid
    
    session_id = session_id or str(uuid.uuid4())
    
    session_service = get_session_service()
    agent = create_agent()
    runner = Runner(app_name="zenika_assistant", agent=agent, session_service=session_service)
    
    # Explicitly create the session if it doesn't exist
    # This is required by the google-adk Runner to avoid "Session not found" errors
    try:
        await session_service.get_session(session_id)
    except Exception:
        await session_service.create_session(
            app_name="zenika_assistant",
            user_id="user_1",
            session_id=session_id
        )
    
    response_parts = []
    last_tool_data = None
    
    # The new_message must be a structured Content object, not a plain string
    new_message = types.Content(
        role="user",
        parts=[types.Part(text=query)]
    )
    
    async for event in runner.run_async(
        user_id="user_1",
        session_id=session_id,
        new_message=new_message
    ):
        # Log event for debugging
        author = getattr(event, 'author', 'unknown')
        logger.debug(f"ADK Event: {type(event)} author={author}")
        
        # Capture structured data from tool results
        if author == 'tool' and hasattr(event, 'content'):
            if hasattr(event.content, 'parts'):
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        try:
                            # Our tools return {"result": "JSON_STRING"}
                            raw_data = json.loads(part.text)
                            if isinstance(raw_data, dict) and "result" in raw_data:
                                try:
                                    last_tool_data = json.loads(raw_data["result"])
                                except:
                                    last_tool_data = raw_data["result"]
                            else:
                                last_tool_data = raw_data
                        except:
                            pass

        if hasattr(event, 'content') and event.content:
            # Only add non-tool responses to the text (to avoid JSON in chat bubbles)
            if author != 'tool':
                if isinstance(event.content, str):
                    response_parts.append(event.content)
                elif hasattr(event.content, 'parts'):
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            response_parts.append(part.text)
    
    response_text = "".join(response_parts)
    
    try:
        from google.adk.events.event import Event
        final_content = types.Content(role="assistant", parts=[types.Part(text=response_text)])
        final_event = Event(author="assistant", content=final_content, partial=False)
        session = await session_service.get_session(
            app_name="zenika_assistant", 
            user_id="user_1", 
            session_id=session_id
        )
        if session:
            await session_service.append_event(session, final_event)
    except Exception as e:
        logger.error(f"Failed to append final response to history: {e}")
    
    return {
        "response": response_text,
        "data": last_tool_data,
        "source": "adk_agent",
        "session_id": session_id
    }
