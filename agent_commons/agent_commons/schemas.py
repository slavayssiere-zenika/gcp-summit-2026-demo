"""
ADR12-4 — Contrat Pydantic A2A formalisé.

Modèles Pydantic partagés entre le Router (consumer) et les sous-agents (providers)
pour le protocole A2A (Agent-to-Agent HTTP).

Avantages :
- Validation automatique des payloads à l'entrée et à la sortie de chaque /a2a/query
- Documentation OpenAPI précise sur toutes les APIs
- Détection des régressions de protocole au runtime (FastAPI renvoie 422 explicite)
- Source de vérité unique dans agent_commons (DRY)

Usage (FastAPI sub-agent) :
    from agent_commons.schemas import A2ARequest, A2AResponse

    @router.post("/a2a/query", response_model=A2AResponse)
    async def a2a_query(request: A2ARequest, payload: dict = Depends(verify_jwt)):
        ...

Usage (Router — appel sortant) :
    from agent_commons.schemas import A2ARequest, A2AResponse
    body = A2ARequest(query=query, user_id=user_id)
    res = await client.post(url, json=body.model_dump(exclude_none=True))
    data = A2AResponse.model_validate(res.json())
"""

from __future__ import annotations

import inspect
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# QueryRequest — Entrée du endpoint /query (utilisateur → agent)
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    """Payload envoyé par le frontend ou le Router au endpoint POST /query d'un agent.

    Différent de A2ARequest (communication inter-agents) : QueryRequest est destiné
    aux appels initiés par un utilisateur humain via le frontend.
    """

    query: str = Field(..., description="La requête en langage naturel.", min_length=1)
    session_id: Optional[str] = Field(
        None,
        description=(
            "Identifiant de session ADK. Si absent, le sub JWT est utilisé comme "
            "session_id (comportement par défaut)."
        ),
    )
    user_id: Optional[str] = Field(
        None,
        description=(
            "Identifiant utilisateur propagé depuis le JWT sub. "
            "Utilisé pour l'isolation des sessions et le tracking FinOps."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "example": {"query": "Quels consultants sont disponibles ?"}
        }
    }


# ---------------------------------------------------------------------------
# A2ARequest — Communication inter-agents (Router → sous-agent)
# ---------------------------------------------------------------------------


class A2ARequest(BaseModel):
    """Payload envoyé par le Router à un sous-agent sur POST /a2a/query."""

    query: str = Field(..., description="La requête en langage naturel à traiter.", min_length=1)
    session_id: Optional[str] = Field(
        None,
        description=(
            "Identifiant de session ADK. Si absent, le sous-agent utilise le sub JWT "
            "comme session_id (comportement par défaut)."
        ),
    )
    user_id: Optional[str] = Field(
        None,
        description=(
            "Identifiant utilisateur propagé par le Router depuis le JWT sub. "
            "Utilisé pour l'isolation des sessions et le tracking FinOps."
        ),
    )

    model_config = {"json_schema_extra": {"example": {"query": "Quels consultants sont disponibles ?", "user_id": "alice@zenika.com"}}}


# ---------------------------------------------------------------------------
# Step (élément de la trace d'exécution — Expert Mode)
# ---------------------------------------------------------------------------


class AgentStep(BaseModel):
    """Un step de la trace d'exécution visible dans le mode Expert du frontend."""

    type: Literal["call", "result", "warning", "cache"] = Field(
        ...,
        description="Type de step : appel outil (call), résultat (result), avertissement guardrail (warning), hit cache (cache).",
    )
    tool: Optional[str] = Field(None, description="Nom du tool appelé (pour type=call/warning/cache).")
    args: Optional[dict[str, Any]] = Field(None, description="Arguments passés au tool ou métadonnées du step.")
    data: Optional[Any] = Field(None, description="Données retournées par le tool (pour type=result).")
    source: Optional[str] = Field(None, description="Nom du sous-agent source si délégation A2A (ex: 'hr_agent').")


# ---------------------------------------------------------------------------
# Usage (FinOps tokens)
# ---------------------------------------------------------------------------


class TokenUsage(BaseModel):
    """Consommation de tokens Gemini pour ce tour de conversation (FinOps)."""

    total_input_tokens: int = Field(0, ge=0, description="Tokens d'entrée consommés (prompt).")
    total_output_tokens: int = Field(0, ge=0, description="Tokens de sortie générés (completion).")
    estimated_cost_usd: float = Field(0.0, ge=0.0, description="Coût estimé en USD pour ce tour.")


# ---------------------------------------------------------------------------
# A2AResponse — Réponse d'un sous-agent
# ---------------------------------------------------------------------------


class A2AResponse(BaseModel):
    """Réponse retournée par un sous-agent sur POST /a2a/query."""

    response: str = Field(..., description="Réponse textuelle de l'agent en langage naturel.")
    data: Optional[Any] = Field(
        None,
        description=(
            "Données structurées optionnelles (liste d'utilisateurs, missions, compétences…) "
            "pour l'affichage frontend (displayType=cards/tree)."
        ),
    )
    steps: list[AgentStep] = Field(
        default_factory=list,
        description="Trace d'exécution des tools (mode Expert du frontend).",
    )
    thoughts: str = Field("", description="Chaîne de pensée Gemini (Thinking mode), concaténée.")
    usage: TokenUsage = Field(
        default_factory=TokenUsage,
        description="Consommation de tokens pour le tracking FinOps.",
    )
    source: Optional[str] = Field(None, description="Source de la réponse : 'adk_agent', 'semantic_cache', 'error'…")
    session_id: Optional[str] = Field(None, description="Session ADK utilisée pour cette requête.")
    semantic_cache_hit: Optional[bool] = Field(None, description="True si la réponse a été servie depuis le cache sémantique.")
    degraded: Optional[bool] = Field(None, description="True si le sous-agent a répondu en mode dégradé (erreur réseau).")

    model_config = {
        "json_schema_extra": {
            "example": {
                "response": "J'ai trouvé 3 consultants disponibles pour votre mission.",
                "data": {"items": [{"id": 1, "name": "Alice Martin"}]},
                "steps": [{"type": "call", "tool": "search_users", "args": {"skills": ["Python"]}}],
                "thoughts": "",
                "usage": {"total_input_tokens": 120, "total_output_tokens": 80, "estimated_cost_usd": 0.000033},
                "source": "adk_agent",
            }
        }
    }


# ---------------------------------------------------------------------------
# Tool metadata helper (introspection des tools ADK)
# ---------------------------------------------------------------------------


def get_tool_metadata(tools_list: list) -> list[dict]:
    """Retourne les métadonnées d'introspection d'une liste de tools ADK.

    Utilisé par le endpoint GET /mcp/registry pour exposer la liste des tools
    disponibles avec leurs signatures et docstrings.

    Args:
        tools_list: Liste de callables (fonctions ou instances ADK).

    Returns:
        Liste de dicts {name, description, parameters}.
    """
    metadata = []
    for tool in tools_list:
        doc = inspect.getdoc(tool) or "No description available"
        try:
            sig = inspect.signature(tool)
            params = [
                {
                    "name": name,
                    "type": str(param.annotation) if param.annotation != inspect.Parameter.empty else "any",
                    "default": str(param.default) if param.default != inspect.Parameter.empty else None,
                    "required": param.default == inspect.Parameter.empty,
                }
                for name, param in sig.parameters.items()
            ]
        except (ValueError, TypeError):
            params = []
        metadata.append({
            "name": getattr(tool, "__name__", str(tool)),
            "description": doc,
            "parameters": params,
        })
    return metadata
