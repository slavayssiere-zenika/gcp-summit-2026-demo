import os
import json
import logging
from typing import Optional
from google.genai import types
from google.adk.agents import Agent
from mcp_client import get_users_mcp, get_items_mcp, get_competencies_mcp, get_loki_mcp, get_cv_mcp, get_drive_mcp

logger = logging.getLogger(__name__)

_session_service = None

def get_session_service():
    global _session_service
    if _session_service is None:
        from session import RedisSessionService
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

async def analyze_cv(url: str, source_tag: Optional[str] = None) -> dict:
    """
    Télécharge, parse, extrait et convertit un CV (via un lien Google Docs) dans le système.
    Crée automatiquement le candidat, identifie ses compétences sémantiquement, et les rattache.
    Utiliser UNIQUEMENT si l'utilisateur demande d'analyser, d'importer ou de lire un CV depuis un lien.

    Args:
        url (str): L'URL publique du Google Doc contenant le CV.
        source_tag (str, optional): Tag thématique (ex: ville) associé à ce CV.
    """
    mcp = await get_cv_mcp()
    payload = {"url": url}
    if source_tag:
        payload["source_tag"] = source_tag
    result = await mcp.call_tool("analyze_cv", payload)
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

async def get_users_by_tag(tag: str) -> dict:
    """
    Récupère les identifiants et les liens des CV des utilisateurs associés à un tag spécifique (ex: localisation 'Niort').
    Utiliser cet outil UNIQUEMENT pour identifier des utilisateurs par localisation ou tag.
    
    Args:
        tag (str): La localisation ou le tag spécifique (ex: 'Niort').
    """
    mcp = await get_cv_mcp()
    result = await mcp.call_tool("get_users_by_tag", {"tag": tag})
    return format_mcp_result(result, "users_by_tag")

async def get_user_cv(user_id: int) -> dict:
    """
    Récupére le ou les liens source (Google Doc) originaux des CVs associés au collaborateur.
    Utilise cet outil UNIQUEMENT pour voir le profil CV exact ou les détails du CV importé pour un utilisateur.
    
    Args:
        user_id (int): L'identifiant interne de l'utilisateur cible.
    """
    mcp = await get_cv_mcp()
    result = await mcp.call_tool("get_user_cv", {"user_id": user_id})
    return format_mcp_result(result, "cv_profile")

async def get_user_missions(user_id: int) -> dict:
    """
    Récupère la liste des missions (projets, expériences) d'un consultant avec les compétences associées à chaque mission.
    Utiliser cet outil dès que l'utilisateur demande des détails sur l'expérience, les projets, ou un résumé basé sur les missions.
    
    Args:
        user_id (int): L'identifiant de l'utilisateur cible.
    """
    mcp = await get_cv_mcp()
    result = await mcp.call_tool("get_user_missions", {"user_id": user_id})
    return format_mcp_result(result, "missions")

async def get_candidate_rag_context(user_id: int) -> dict:
    """
    Récupère les informations vectorisées et distillées (résumé, missions, rôle) pour un candidat.
    Outil INDISPENSABLE pour générer une synthèse claire, justifier un profil ou comprendre le parcours d'un consultant de manière sémantique.
    
    Args:
        user_id (int): L'identifiant de l'utilisateur (candidat).
    """
    mcp = await get_cv_mcp()
    result = await mcp.call_tool("get_candidate_rag_context", {"user_id": user_id})
    return format_mcp_result(result, "rag_context")

async def global_reanalyze_cvs(tag: Optional[str] = None, user_id: Optional[int] = None) -> dict:
    """
    (Admin Only) Relance l'analyse complète des CVs pour extraire à nouveau les compétences et missions (utilise Gemini).
    Utile après une mise à jour de la taxonomie ou pour corriger un import.
    
    Args:
        tag (str, optional): Filtre par tag (ex: 'Niort').
        user_id (int, optional): Filtre par ID utilisateur spécifique.
    """
    mcp = await get_cv_mcp()
    payload = {}
    if tag: payload["tag"] = tag
    if user_id: payload["user_id"] = user_id
    result = await mcp.call_tool("global_reanalyze_cvs", payload)
    return format_mcp_result(result, "reanalyze")

async def get_most_experienced_consultants(limit: int = 5) -> dict:
    """
    Récupère le classement des consultants les plus expérimentés basés sur les années d'expérience extraites de leurs CVs.
    Utiliser cet outil UNIQUEMENT pour répondre à des questions sur l'expérience globale, l'expertise ou qui est le 'plus expérimenté'.
    
    Args:
        limit (int): Le nombre maximum de profils à retenir (défaut 5).
    """
    mcp = await get_cv_mcp()
    result = await mcp.call_tool("get_most_experienced_consultants", {"limit": limit})
    return format_mcp_result(result, "experience_ranking")

CV_TOOLS = [
    analyze_cv,
    search_best_candidates,
    recalculate_competencies_tree,
    get_users_by_tag,
    get_user_cv,
    get_user_missions,
    get_candidate_rag_context,
    global_reanalyze_cvs,
    get_most_experienced_consultants
]

# --- Drive Tools ---

async def add_drive_folder(google_folder_id: str, tag: str) -> dict:
    """
    Ajoute un nouveau répertoire Google Drive à la liste des dossiers scruptés pour extraire automatiquement les CVs.
    
    Args:
        google_folder_id (str): L'ID Google Drive du répertoire cible.
        tag (str): Tag business associé (ex: 'Paris', 'Data').
    """
    mcp = await get_drive_mcp()
    result = await mcp.call_tool("add_drive_folder", {"google_folder_id": google_folder_id, "tag": tag})
    return format_mcp_result(result, "drive")

async def list_drive_folders() -> dict:
    """
    Liste les dossiers Google Drive actuellement suivis par la plateforme Zenika.
    """
    mcp = await get_drive_mcp()
    result = await mcp.call_tool("list_drive_folders", {})
    return format_mcp_result(result, "drive_folders")

async def delete_drive_folder(folder_id: int) -> dict:
    """
    Supprime un dossier du suivi (arrêt de scanner les CVs dans ce répertoire).
    
    Args:
        folder_id (int): L'identifiant interne en base de données du dossier à supprimer.
    """
    mcp = await get_drive_mcp()
    result = await mcp.call_tool("delete_drive_folder", {"folder_id": folder_id})
    return format_mcp_result(result, "drive")

async def get_drive_status() -> dict:
    """
    Consulte le statut de synchronisation Drive (statistiques de documents parsés, en erreur, etc).
    """
    mcp = await get_drive_mcp()
    result = await mcp.call_tool("get_drive_status", {})
    return format_mcp_result(result, "drive_status")

async def trigger_drive_sync() -> dict:
    """
    Déclenche manuellement une synchronisation planifiée pour scruter les changements (delta) sur tous les dossiers configurés.
    """
    mcp = await get_drive_mcp()
    result = await mcp.call_tool("trigger_drive_sync", {})
    return format_mcp_result(result, "drive_sync")

DRIVE_TOOLS = [
    add_drive_folder,
    list_drive_folders,
    delete_drive_folder,
    get_drive_status,
    trigger_drive_sync
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

async def create_user(username: str, email: str, full_name: Optional[str] = None, is_anonymous: bool = False) -> dict:
    """
    Crée un nouvel utilisateur dans le système.
    
    Args:
        username (str): Le nom d'utilisateur unique.
        email (str): L'adresse email de l'utilisateur.
        full_name (str, optional): Le nom complet de l'utilisateur.
        is_anonymous (bool, optional): Marquer le profil comme anonyme/provisoire.
    """
    mcp = await get_users_mcp()
    result = await mcp.call_tool("create_user", {
        "username": username, 
        "email": email, 
        "full_name": full_name,
        "is_anonymous": is_anonymous
    })
    return format_mcp_result(result, "user")

async def update_user(user_id: int, username: Optional[str] = None, email: Optional[str] = None, 
                full_name: Optional[str] = None, is_active: Optional[bool] = None, is_anonymous: Optional[bool] = None) -> dict:
    """
    Met à jour les informations d'un utilisateur existant.

    Args:
        user_id (int): L'identifiant de l'utilisateur à modifier.
        username (str, optional): Nouveau nom d'utilisateur.
        email (str, optional): Nouvelle adresse email.
        full_name (str, optional): Nouveau nom complet.
        is_active (bool, optional): État d'activation du compte.
        is_anonymous (bool, optional): Changer le statut d'anonymisation.
    """
    params = {"user_id": user_id}
    if username is not None: params["username"] = username
    if email is not None: params["email"] = email
    if full_name is not None: params["full_name"] = full_name
    if is_active is not None: params["is_active"] = is_active
    if is_anonymous is not None: params["is_anonymous"] = is_anonymous
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

async def get_users_bulk(user_ids: list[int]) -> dict:
    """
    Récupère les informations détaillées de plusieurs utilisateurs en une seule fois, à partir de leurs identifiants.
    Utilisez cet outil après avoir récupéré une liste d'IDs (par exemple depuis list_competency_users).
    
    Args:
        user_ids (list[int]): La liste des identifiants des utilisateurs à récupérer.
    """
    mcp = await get_users_mcp()
    result = await mcp.call_tool("get_users_bulk", {"user_ids": user_ids})
    return format_mcp_result(result, "users_bulk")

async def merge_users(source_id: int, target_id: int) -> dict:
    """
    Fusionne un utilisateur (source) dans un autre (cible). 
    Le profil source est désactivé et toutes ses données (CV, items, compétences) sont transférées vers le profil cible.
    Utiliser cet outil UNIQUEMENT pour corriger des doublons ou rattacher un profil anonyme à un collaborateur réel.
    
    Args:
        source_id (int): L'ID de l'utilisateur à fusionner (et supprimer/désactiver).
        target_id (int): L'ID de l'utilisateur maître à conserver.
    """
    mcp = await get_users_mcp()
    result = await mcp.call_tool("merge_users", {"source_id": source_id, "target_id": target_id})
    return format_mcp_result(result, "merge")

async def search_anonymous_users(limit: int = 10) -> dict:
    """
    Recherche les profils marqués comme anonymes ou provisoires dans le système.
    Utile pour identifier les CVs importés qui n'ont pas encore été rattachés à un collaborateur réel.
    """
    mcp = await get_users_mcp()
    result = await mcp.call_tool("search_anonymous_users", {"limit": limit})
    return format_mcp_result(result, "anonymous_users")

USERS_TOOLS = [
    list_users, get_user, create_user, update_user, delete_user, 
    search_users, toggle_user_status, get_user_stats, health_check_users, get_users_bulk,
    merge_users, search_anonymous_users
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

async def apply_competency_tree(tree: dict) -> dict:
    """
    Applique et persiste un arbre de compétences complet dans la base de données (Admin uniquement).
    Cet outil est utilisé pour valider et enregistrer une taxonomie après un recalcul.
    
    Args:
        tree (dict): L'objet JSON représentant l'arbre hiérarchique des compétences.
    """
    mcp = await get_competencies_mcp()
    result = await mcp.call_tool("bulk_import_tree", {"tree": tree})
    return format_mcp_result(result, "bulk_import")


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

async def search_competencies(query: str, limit: int = 10) -> dict:
    """
    Recherche une ou plusieurs compétences par leur nom. Outil indispensable pour trouver l'ID d'une compétence (ex: "AWS").
    """
    mcp = await get_competencies_mcp()
    result = await mcp.call_tool("search_competencies", {"query": query, "limit": limit})
    return format_mcp_result(result, "competency_search")

async def list_competency_users(competency_id: int) -> dict:
    """
    Récupère la liste des identifiants des utilisateurs (user_ids) qui possèdent une compétence spécifique.
    Pour obtenir les noms et détails de ces utilisateurs, utilisez ensuite get_users_bulk avec les identifiants retournés.
    """
    mcp = await get_competencies_mcp()
    result = await mcp.call_tool("list_competency_users", {"competency_id": competency_id})
    return format_mcp_result(result, "competency_users")


COMPETENCIES_TOOLS = [
    list_competencies, get_competency, create_competency, apply_competency_tree,
    delete_competency, assign_competency_to_user, remove_competency_from_user,
    list_user_competencies, search_competencies, list_competency_users
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
    from opentelemetry.propagate import inject
    try:
        loki_url = os.getenv("LOKI_URL", "http://loki:3100")
        headers = {}
        inject(headers)
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(f"{loki_url}/loki/api/v1/query", params={"query": query}, headers=headers)
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

# --- GCP Logging Tools ---

async def gcp_query_logs(filter_str: str, limit: int = 100) -> dict:
    """
    Exécute une requête native sur Google Cloud Logging (Stackdriver) pour analyser les logs des applications sur GCP.
    
    Args:
        filter_str (str): Filtre stackdriver (ex: 'resource.type="cloud_run_revision" AND severity>="ERROR"').
        limit (int): Nombre max de lignes retournées. Par défaut 100.
    """
    try:
        from google.cloud import logging as cloud_logging
        client = cloud_logging.Client()
        entries = client.list_entries(filter_=filter_str, page_size=limit)
        
        logs = []
        for entry in entries:
            logs.append({
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "severity": entry.severity,
                "payload": entry.payload,
                "resource": entry.resource.labels if entry.resource else {}
            })
            if len(logs) >= limit:
                break
                
        # Mock du format cible habituel du MCP
        return format_mcp_result([{"text": json.dumps(logs)}], "gcp_logs")
    except Exception as e:
        logger.error(f"Error in gcp_query_logs: {e}")
        return {"result": f"Erreur Google Cloud Logging: {e}"}

GCP_LOGGING_TOOLS = [
    gcp_query_logs
]


async def create_agent(session_id: str | None = None):
    import httpx
    try:
        prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{prompts_api_url}/prompts/agent_api.assistant_system_instruction", timeout=5.0)
            res.raise_for_status()
            instruction_text = res.json()["value"]
            
            # Fetch capabilities
            res_cap = await client.get(f"{prompts_api_url}/prompts/agent_api.capabilities_instruction", timeout=5.0)
            if res_cap.status_code == 200:
                capabilities_text = res_cap.json().get("value", "")
                if capabilities_text:
                    instruction_text += f"\n\n--- CAPACITÉS DE L'AGENT ---\n{capabilities_text}\n------------------------------------------------------------"
    except Exception as e:
        print(f"Error fetching system prompt from prompts_api: {e}")
        instruction_text = "Tu es un assistant IA. Réponds brièvement."
        
    if session_id and session_id != "anon":
        try:
            from mcp_client import auth_header_var
            auth_header = auth_header_var.get()
            headers = {"Authorization": auth_header} if auth_header else {}
            
            async with httpx.AsyncClient() as client:
                res = await client.get(f"{prompts_api_url}/prompts/user_{session_id}", headers=headers, timeout=5.0)
                if res.status_code == 200:
                    user_prompt = res.json().get("value", "")
                    if user_prompt:
                        instruction_text += f"\n\n--- INSTRUCTIONS SPÉCIFIQUES DE L'UTILISATEUR ({session_id}) ---\n{user_prompt}\n------------------------------------------------------------"
        except Exception as e:
            print(f"Error fetching personal prompt for {session_id}: {e}")
            
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    # Choix dynamique des outils de log
    use_gcp_logging = os.getenv("USE_GCP_LOGGING", "false").lower() == "true"
    log_tools = GCP_LOGGING_TOOLS if use_gcp_logging else LOKI_TOOLS
    
    agent = Agent(
        name="assistant_zenika",
        model=model,
        generate_content_config=types.GenerateContentConfig(
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(initial_delay=1, attempts=2),
            )
        ),
        instruction=instruction_text,
        description="Assistant IA pour la gestion des utilisateurs, items et compétences. Et analyse des logs via Loki ou GCP.",
        tools=[*USERS_TOOLS, *ITEMS_TOOLS, *COMPETENCIES_TOOLS, *CV_TOOLS, *DRIVE_TOOLS, *log_tools]
    )
    
    return agent


async def run_agent_query(query: str, session_id: str | None = None) -> dict:
    from google.adk.runners import Runner
    import uuid
    
    session_id = session_id or str(uuid.uuid4())
    
    session_service = get_session_service()
    agent = await create_agent(session_id)
    runner = Runner(app_name="zenika_assistant", agent=agent, session_service=session_service)
    
    # Explicitly create the session if it doesn't exist
    # This is required by the google-adk Runner to avoid "Session not found" errors
    try:
        session = await session_service.get_session(
            app_name="zenika_assistant", 
            user_id="user_1", 
            session_id=session_id
        )
        if session is None:
            raise KeyError("Session not found")
    except Exception:
        await session_service.create_session(
            app_name="zenika_assistant",
            user_id="user_1",
            session_id=session_id
        )
    
    response_parts = []
    last_tool_data = None
    steps = []  # Liste pour capturer l'historique des outils (mode expert)
    
    # The new_message must be a structured Content object, not a plain string
    new_message = types.Content(
        role="user",
        parts=[types.Part(text=query)]
    )
    
    steps = []
    seen_steps = set()
    thoughts = []
    
    async for event in runner.run_async(
        user_id="user_1",
        session_id=session_id,
        new_message=new_message
    ):
        # 1. Detect roles
        author = getattr(event, 'author', None)
        has_content = hasattr(event, 'content') and event.content is not None
        role = getattr(event.content, 'role', None) if has_content else None
        
        author_val = str(author or "").lower()
        role_val = str(role or "").lower()
        is_assistant = any(x in ["assistant", "model", "assistant_zenika"] for x in [author_val, role_val])
        is_tool = any(x in ["tool", "function"] for x in [author_val, role_val])
        
        logger.info(f"--- EVENT: author={author_val} role={role_val} ---")

        # 2. Process EVERYTHING in EVERY event (Exhaustive Scan)
        if has_content:
            parts = list(event.content.parts) if hasattr(event.content, 'parts') else []
            for i, part in enumerate(parts):
                # a) Capture Thoughts
                thought_val = getattr(part, 'thought', None)
                if thought_val:
                    logger.info(f"Captured thought: {str(thought_val)[:50]}...")
                    thoughts.append(str(thought_val))
                
                # b) Capture Tool Calls (Assistant requesting tool)
                tcall = getattr(part, 'tool_call', None) or getattr(part, 'function_call', None)
                if tcall:
                    calls = tcall if isinstance(tcall, list) else [tcall]
                    for call in calls:
                        name = getattr(call, 'name', 'unknown')
                        args = getattr(call, 'args', {})
                        sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                        if sig not in seen_steps:
                            logger.info(f"Captured tool call (part): {name}")
                            steps.append({"type": "call", "tool": name, "args": args})
                            seen_steps.add(sig)
                
                # c) Capture Tool Results (Tool providing data)
                fres = getattr(part, 'function_response', None)
                raw_text = getattr(part, 'text', None)
                
                if fres:
                    res_data = getattr(fres, 'response', fres)
                    if hasattr(res_data, 'model_dump'): res_data = res_data.model_dump()
                    elif hasattr(res_data, 'dict'): res_data = res_data.dict()
                    
                    # Unwrap MCP 'result' JSON string
                    if isinstance(res_data, dict) and "result" in res_data and isinstance(res_data["result"], str) and res_data["result"].startswith("{"):
                        try: res_data = json.loads(res_data["result"])
                        except: pass
                    
                    sig = f"result:{json.dumps(res_data, sort_keys=True)}"
                    if sig not in seen_steps:
                        last_tool_data = res_data
                        steps.append({"type": "result", "data": res_data})
                        seen_steps.add(sig)
                        logger.info(f"Captured tool data (fres)")
                elif raw_text and role_val in ["tool", "user"]:
                    # Try to parse JSON from tool results embedded in text
                    try:
                        data_obj = json.loads(raw_text)
                        if isinstance(data_obj, dict) and "result" in data_obj:
                            try: data_obj = json.loads(data_obj["result"])
                            except: data_obj = data_obj["result"]
                        
                        sig = f"result:{json.dumps(data_obj, sort_keys=True)}"
                        if sig not in seen_steps:
                            last_tool_data = data_obj
                            steps.append({"type": "result", "data": data_obj})
                            seen_steps.add(sig)
                            logger.info(f"Captured tool data (json_text)")
                    except: pass

        # 3. Capture alternative Event-level metadata
        if hasattr(event, 'actions') and event.actions:
            for action in event.actions:
                tc = getattr(action, 'tool_call', None)
                if tc:
                    name = getattr(tc, 'name', "unknown")
                    args = getattr(tc, 'args', {})
                    sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                    if sig not in seen_steps:
                        logger.info(f"Captured tool call (action): {name}")
                        steps.append({"type": "call", "tool": name, "args": args})
                        seen_steps.add(sig)
        
        if hasattr(event, 'get_function_calls'):
            for fc in (event.get_function_calls() or []):
                name = getattr(fc, 'name', "unknown")
                args = getattr(fc, 'args', {})
                sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                if sig not in seen_steps:
                    logger.info(f"Captured tool call (event_method): {name}")
                    steps.append({"type": "call", "tool": name, "args": args})
                    seen_steps.add(sig)

        if hasattr(event, 'get_function_responses'):
            for fr in (event.get_function_responses() or []):
                res_data = getattr(fr, 'response', fr)
                if hasattr(res_data, 'model_dump'): res_data = res_data.model_dump()
                elif hasattr(res_data, 'dict'): res_data = res_data.dict()
                
                # Unwrap MCP 'result' JSON string
                if isinstance(res_data, dict) and "result" in res_data and isinstance(res_data["result"], str) and res_data["result"].startswith("{"):
                    try: res_data = json.loads(res_data["result"])
                    except: pass
                
                sig = f"result:{json.dumps(res_data, sort_keys=True)}"
                if sig not in seen_steps:
                    last_tool_data = res_data
                    steps.append({"type": "result", "data": res_data})
                    seen_steps.add(sig)
                    logger.info(f"Captured tool data (event_method)")

        # 4. Aggregate final response text (only if it's the model speaking to user)
        if has_content and is_assistant:
            if isinstance(event.content, str):
                response_parts.append(event.content)
            elif hasattr(event.content, 'parts'):
                for part in event.content.parts:
                    itcall = getattr(part, 'tool_call', None) or getattr(part, 'function_call', None)
                    ithought = getattr(part, 'thought', None)
                    itext = getattr(part, 'text', None)
                    if itext and not itcall and not ithought:
                        response_parts.append(itext)
    
    response_text = "".join(response_parts)
    thought_text = "\n".join(thoughts)
    
    return {
        "response": response_text,
        "thoughts": thought_text,
        "data": last_tool_data,
        "steps": steps, # Nouveau champ pour le mode expert
        "source": "adk_agent",
        "session_id": session_id
    }
