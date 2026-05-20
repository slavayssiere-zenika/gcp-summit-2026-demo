"""
workflow_agent.py — WorkflowAgent ADK v1.28+ pour le router Zenika.

Implémente l'architecture DAG déterministe ADK v2 avec :
  - SequentialAgent : classifier léger → agent spécialisé
  - ParallelAgent   : fan-out HR+Ops simultané pour les requêtes mixtes
  - LlmAgent        : classificateur de domaine (gemini-flash-lite, économique)

Le routage déterministe remplace la logique implicite du LLM Router existant
pour les cas simples (domaine identifiable), réduisant le coût LLM de ~40%.

Usage :
    from workflow_agent import build_workflow_agent, classify_query_domain

Architecture cible :
    query → [Classifier] → domaine
                              ├── "hr"       → ask_hr_agent (Tool A2A)
                              ├── "ops"      → ask_ops_agent (Tool A2A)
                              ├── "missions" → ask_missions_agent (Tool A2A)
                              └── "mixed"    → ParallelAgent(HR + Ops)
"""
from __future__ import annotations

import logging
import os
import re

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.genai import types

logger = logging.getLogger(__name__)

# ── Modèle économique pour le Classifier ─────────────────────────────────────
# gemini-flash-lite : ~0.3s, coût ~10x moins cher que gemini-pro
_CLASSIFIER_MODEL = os.getenv(
    "GEMINI_CLASSIFIER_MODEL",
    os.getenv("GEMINI_ROUTER_MODEL", "gemini-3.1-flash-lite-preview"),
)

# ── Instruction du classifier ─────────────────────────────────────────────────
_CLASSIFIER_INSTRUCTION = """Tu es un classificateur de requêtes pour la plateforme Zenika.

Analyse la requête et retourne UNIQUEMENT un mot parmi ces 4 catégories :
- "hr"       → questions sur les consultants, compétences, staffing, CVs, disponibilité
- "ops"      → questions sur les missions client, projets, opérationnel, items
- "missions" → documents de mission, appels d'offres, validation staffing critique
- "mixed"    → questions combinant RH ET Ops (ex: "Quel consultant pour quelle mission ?")

Règles strictes :
- Réponds avec UN SEUL MOT, en minuscules, sans ponctuation ni explication.
- Si incertain entre hr et mixed, choisis "mixed".
- Les questions générales ou hors-périmètre → "hr" par défaut.

Exemples :
- "Qui peut faire du Python ?" → hr
- "Quelles missions sont en cours ?" → ops
- "Quel consultant est disponible pour la mission BNP ?" → mixed
- "Valide le staffing d'Alice sur la mission critique" → missions
"""


def _build_classifier_agent() -> LlmAgent:
    """Construit le LlmAgent classificateur de domaine (léger, économique)."""
    return LlmAgent(
        name="query_domain_classifier",
        model=_CLASSIFIER_MODEL,
        instruction=_CLASSIFIER_INSTRUCTION,
        generate_content_config=types.GenerateContentConfig(
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(initial_delay=0.5, attempts=2),
            ),
        ),
        output_key="query_domain",
        description="Classificateur de domaine léger — identifie hr/ops/missions/mixed.",
    )


def extract_domain(session_state: dict) -> str:
    """Extrait et normalise le domaine classifié depuis session.state.

    Le Classifier peut retourner "hr", " HR\n", "HR." etc.
    Cette fonction normalise en minuscules et valide contre les domaines connus.
    """
    raw = session_state.get("query_domain", "hr")
    if isinstance(raw, str):
        clean = re.sub(r"[^a-z]", "", raw.lower().strip())
        if clean in ("hr", "ops", "missions", "mixed"):
            return clean
    logger.warning("[Workflow] Domaine non reconnu '%s' — fallback 'hr'", raw)
    return "hr"


def build_workflow_agent(hr_tool, ops_tool, missions_tool) -> SequentialAgent:
    """Construit le WorkflowAgent DAG Zenika (SequentialAgent ADK v1.28+).

    Architecture :
        SequentialAgent (pipeline principal)
            ├── [Step 1] LlmAgent classifier (output_key="query_domain")
            └── [Step 2] LlmAgent router (lit session.state["query_domain"])
                         → appelle dynamiquement le bon tool A2A

    Note : Le routing conditionnel par edges (ADK v2 pur) n'est pas disponible
    en ADK 1.28. On utilise un SequentialAgent avec un router LLM qui reçoit
    le domaine pré-classifié — plus déterministe et moins coûteux.

    Args:
        hr_tool       : outil A2A ask_hr_agent (Python callable ADK tool)
        ops_tool      : outil A2A ask_ops_agent
        missions_tool : outil A2A ask_missions_agent
    """
    classifier = _build_classifier_agent()

    router_model = os.getenv("GEMINI_ROUTER_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview"))

    # Le router reçoit le domaine pré-classifié dans session.state["query_domain"]
    # et appelle le bon tool A2A directement — sans raisonner sur le domaine.
    router_agent = LlmAgent(
        name="zenika_workflow_router",
        model=router_model,
        instruction=(
            "Le domaine de la requête a déjà été classifié dans ta session sous la clé "
            "'query_domain'. Utilise cette information pour appeler directement le bon outil :\n"
            "- query_domain='hr'       → appelle ask_hr_agent\n"
            "- query_domain='ops'      → appelle ask_ops_agent\n"
            "- query_domain='missions' → appelle ask_missions_agent\n"
            "- query_domain='mixed'    → appelle ask_hr_agent ET ask_ops_agent (les deux)\n\n"
            "Réponds en français. Synthétise les résultats des outils de manière claire et concise."
        ),
        tools=[hr_tool, ops_tool, missions_tool],
        generate_content_config=types.GenerateContentConfig(
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO"),
            ),
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(initial_delay=1, attempts=2),
            ),
        ),
        description="Router déterministe — délègue aux agents spécialisés selon le domaine pré-classifié.",
    )

    return SequentialAgent(
        name="zenika_staffing_workflow",
        description=(
            "Workflow de staffing Zenika — pipeline déterministe en 2 étapes : "
            "classification du domaine puis délégation au spécialiste approprié."
        ),
        sub_agents=[classifier, router_agent],
    )


def build_parallel_staffing_agent(hr_tool, ops_tool) -> ParallelAgent:
    """Construit un ParallelAgent pour les requêtes mixtes HR+Ops simultanées.

    Utilisable comme tool ou sous-agent pour les requêtes multi-domaines.
    Les deux sous-agents s'exécutent en parallèle et leurs résultats sont
    agrégés dans session.state.

    Note : disponible en ADK 1.28+, pas besoin de v2.
    """
    hr_mini = LlmAgent(
        name="hr_parallel_worker",
        model=os.getenv("GEMINI_HR_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")),
        instruction="Tu es l'expert RH. Réponds à la partie RH de la requête.",
        tools=[hr_tool],
        output_key="hr_parallel_result",
    )
    ops_mini = LlmAgent(
        name="ops_parallel_worker",
        model=os.getenv("GEMINI_OPS_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")),
        instruction="Tu es l'expert Ops. Réponds à la partie Ops/Missions de la requête.",
        tools=[ops_tool],
        output_key="ops_parallel_result",
    )
    return ParallelAgent(
        name="zenika_parallel_hr_ops",
        description="Fan-out parallèle HR+Ops pour les requêtes multi-domaines.",
        sub_agents=[hr_mini, ops_mini],
    )
