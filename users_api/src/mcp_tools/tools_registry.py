from mcp.types import Tool

def get_mcp_tools() -> list[Tool]:
    """Retourne la liste complète des outils MCP exposés par l'API Users."""
    return [
        Tool(
            name="list_users",
            description=(
                "Liste tous les utilisateurs avec pagination. "
                "Utiliser uniquement pour des listings génériques sans critère de recherche. "
                "Si un nom ou email est connu, préférer search_users qui est plus précis."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "skip": {"type": "integer", "description": "Number of users to skip", "default": 0},
                    "limit": {"type": "integer", "description": "Maximum number of users to return", "default": 10}
                }
            }
        ),
        Tool(
            name="get_user",
            description=(
                "Récupère un utilisateur par son ID (entier). "
                "ATTENTION : n'appeler qu'avec un ID réel issu d'un appel précédent à search_users. "
                "Ne JAMAIS inventer ou deviner un ID."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "The user ID"}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="get_users_bulk",
            description=(
                "Résout une liste d'IDs utilisateurs en profils complets (full_name, email, is_anonymous, agency). "
                "⚡ OUTIL RECOMMANDÉ pour convertir des IDs en noms après list_competency_users. "
                "TOUJOURS préférer cet outil à list_users quand tu disposes déjà d'une liste d'IDs. "
                "list_users est limité à 100 résultats et non filtrable par IDs — ne l'utiliser que pour des listings génériques. "
                "Passer les IDs par lots si > 100 éléments."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of user IDs to retrieve"
                    }
                },
                "required": ["user_ids"]
            }
        ),
        Tool(
            name="create_user",
            description=(
                "Crée un nouvel utilisateur. "
                "Si le mot de passe n'est pas fourni explicitement, générer un mot de passe aléatoire sécurisé (ex: UUID). "
                "Ne JAMAIS échouer avec une erreur 422 pour cause de mot de passe manquant."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Username"},
                    "email": {"type": "string", "description": "Email address"},
                    "password": {"type": "string", "description": "User password"},
                    "full_name": {"type": "string", "description": "Full name (optional)"},
                    "is_anonymous": {"type": "boolean", "description": "Is this an anonymous/provisional profile?", "default": False}
                },
                "required": ["username", "email", "password"]
            }
        ),
        Tool(
            name="update_user",
            description="Update a user",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "The user ID"},
                    "username": {"type": "string", "description": "New username (optional)"},
                    "email": {"type": "string", "description": "New email (optional)"},
                    "full_name": {"type": "string", "description": "New full name (optional)"},
                    "is_active": {"type": "boolean", "description": "Active status (optional)"},
                    "is_anonymous": {"type": "boolean", "description": "Anonymous status (optional)"}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="delete_user",
            description=(
                "ACTION DESTRUCTIVE ET IRRÉVERSIBLE. Supprime définitivement un utilisateur et toutes ses données associées. "
                "Ne PAS appeler sans confirmation explicite de l'utilisateur dans sa requête. "
                "Toujours proposer update_user (désactivation via is_active=false) comme alternative moins destructive."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "The user ID"}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="health_check",
            description="Check if the API is healthy",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="search_users",
            description=(
                "PREMIÈRE ÉTAPE OBLIGATOIRE pour tout flux impliquant un utilisateur identifié par son nom. "
                "Recherche par username, email ou nom complet. "
                "Retourne une liste d'utilisateurs avec leurs IDs réels. "
                "TOUJOURS appeler avant get_user, list_user_competencies, get_user_cv ou get_candidate_rag_context. "
                "Ne JAMAIS inventer un user_id sans passer par cet outil d'abord. "
                "Utiliser des mots-clés simples sans accents (ex: 'Lavayssiere' et non 'Lavayssière')."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Maximum number of results", "default": 10}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="toggle_user_status",
            description="Activate or deactivate a user",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "The user ID"},
                    "is_active": {"type": "boolean", "description": "Set user active status"}
                },
                "required": ["user_id", "is_active"]
            }
        ),
        Tool(
            name="get_user_stats",
            description="Get statistics about users",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="get_user_duplicates",
            description="Get a list of potential duplicate users based on name similarity",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="merge_users",
            description="Merge a source user into a target user",
            inputSchema={
                "type": "object",
                "required": ["source_id", "target_id"]
            }
        ),
        Tool(
            name="search_anonymous_users",
            description="Search for users marked as anonymous/provisional inside the platform.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Maximum results", "default": 10}
                }
            }
        ),
        Tool(
            name="get_user_availability",
            description=(
                "Retourne la disponibilité consolidée d'un consultant en deux dimensions :\n"
                "1. unavailability_periods : indisponibilités déclarées (congés, formation, inter-contrat).\n"
                "2. active_missions : missions sur lesquelles le consultant est actuellement STAFFÉ (proposed_team). "
                "Un consultant avec des active_missions est déjà engagé — il n'est PAS pleinement disponible. "
                "TOUJOURS vérifier active_missions avant d'affirmer qu'un consultant est disponible pour une nouvelle mission."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "The user ID"}
                },
                "required": ["user_id"]
            }
        ),
        Tool(
            name="get_users_availability_bulk",
            description=(
                "Retourne la disponibilité consolidée d'une liste de consultants (bulk). "
                "Très utile pour filtrer rapidement une liste de candidats sans faire 50 appels séparés."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Liste d'IDs utilisateurs"
                    }
                },
                "required": ["user_ids"]
            }
        )
    ]
