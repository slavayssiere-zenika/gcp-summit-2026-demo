"""a2a_utils.py — Utilitaires A2A partagés entre sous-agents.

Fournit ``make_agent_card()`` pour construire la réponse
``/.well-known/agent.json`` (A2A v2 Service Discovery).

Conformité : https://google.github.io/A2A/specification/#agent-card
"""
import os
from typing import Any


def make_agent_card(
    name: str,
    description: str,
    url_env_var: str,
    default_url: str,
    skills: list[dict[str, Any]],
    routing_hints: dict[str, Any] | None = None,
    examples: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Construit un dict AgentCard conforme à la spec A2A v2.

    Args:
        name: Nom de l'agent (ex: "HR Agent (Talent & Compétences)").
        description: Description fonctionnelle de l'agent.
        url_env_var: Variable d'environnement contenant l'URL de base (ex: "AGENT_HR_API_URL").
        default_url: URL par défaut si la variable n'est pas définie (ex: "http://agent_hr_api:8080").
        skills: Liste des capacités de l'agent (dicts avec id, name, description, tags).
        routing_hints: Optionnel — dict ``do_use_when`` / ``do_not_use_when`` pour le router.
        examples: Optionnel — liste d'exemples de requêtes.

    Returns:
        dict conforme au schéma AgentCard A2A v2.
    """
    base_url = os.getenv(url_env_var, default_url)
    card: dict[str, Any] = {
        "name": name,
        "description": description,
        "version": os.getenv("APP_VERSION", "unknown"),
        "url": base_url,
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": skills,
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False,
        },
        "endpoints": {
            "query": f"{base_url}/a2a/query",
        },
    }
    if routing_hints:
        card["routing_hints"] = routing_hints
    if examples:
        card["examples"] = examples
    return card
