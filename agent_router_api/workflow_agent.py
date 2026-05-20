"""
workflow_agent.py — Graphe d'États StateGraphAgent (ADK v2) pour le router Zenika.

Implémente :
  - StateGraphAgent : agent de graphe d'états personnalisé tolérant aux pannes
  - ask_missions_agent_with_hr_alignment : alignement autonome en boucle fermée
  - build_workflow_agent : configure le graphe avec classifier et router
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import AsyncGenerator, ClassVar, Type
from typing_extensions import override

from google.adk.agents import LlmAgent, ParallelAgent
from google.adk.agents.base_agent import BaseAgent, BaseAgentState
from google.adk.agents.base_agent_config import BaseAgentConfig
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.features import experimental, FeatureName
from google.adk.utils.context_utils import Aclosing
from google.genai import types
from a2a_tools import ask_hr_agent, ask_missions_agent
from a2a_tools import ask_mixed_agents

logger = logging.getLogger(__name__)

# ── Modèle économique pour le Classifier ─────────────────────────────────────
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


@experimental(FeatureName.AGENT_STATE)
class StateGraphAgentState(BaseAgentState):
    """État persistant pour StateGraphAgent stocké dans session.state."""

    current_node: str = "classifier"
    history: list[str] = []


class StateGraphAgent(BaseAgent):
    """Graphe d'États personnalisé pour l'orchestration multi-agents Zenika."""

    config_type: ClassVar[Type[BaseAgentConfig]] = BaseAgentConfig

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        if not self.sub_agents or len(self.sub_agents) < 2:
            logger.warning("[StateGraphAgent] Pas assez de sous-agents configurés.")
            return

        classifier = self.sub_agents[0]
        router_agent = self.sub_agents[1]

        # Charger l'état persistant
        agent_state = self._load_agent_state(ctx, StateGraphAgentState)
        if agent_state is None:
            agent_state = StateGraphAgentState(current_node="classifier", history=[])

        pause_invocation = False

        # --- Étape 1 : Classification ---
        if agent_state.current_node == "classifier":
            logger.info("[StateGraphAgent] Exécution du nœud 'classifier'")
            agent_state.history.append("classifier")

            if ctx.is_resumable:
                ctx.set_agent_state(self.name, agent_state=agent_state)
                yield self._create_agent_state_event(ctx)

            async with Aclosing(classifier.run_async(ctx)) as agen:
                async for event in agen:
                    yield event
                    if ctx.should_pause_invocation(event):
                        pause_invocation = True

            if pause_invocation:
                return

            # Extraire le domaine classifié et transiter
            domain = extract_domain(ctx.session.state)
            logger.info("[StateGraphAgent] Domaine classifié : %s", domain)

            agent_state.current_node = f"router_{domain}"
            if ctx.is_resumable:
                ctx.set_agent_state(self.name, agent_state=agent_state)
                yield self._create_agent_state_event(ctx)

        # --- Étape 2 : Routage et exécution spécialisée ---
        if agent_state.current_node.startswith("router_"):
            node_name = agent_state.current_node
            logger.info("[StateGraphAgent] Exécution du nœud de routage : %s", node_name)
            agent_state.history.append(node_name)

            async with Aclosing(router_agent.run_async(ctx)) as agen:
                async for event in agen:
                    yield event
                    if ctx.should_pause_invocation(event):
                        pause_invocation = True

            if pause_invocation:
                return

            # Transition finale
            agent_state.current_node = "end"
            if ctx.is_resumable:
                ctx.set_agent_state(self.name, end_of_agent=True, agent_state=agent_state)
                yield self._create_agent_state_event(ctx)

        logger.info("[StateGraphAgent] Terminé. Historique: %s", agent_state.history)

    @override
    async def _run_live_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """Fall-back live non utilisé pour ce workflow."""
        if not self.sub_agents:
            return
        async with Aclosing(self.sub_agents[0].run_live(ctx)) as agen:
            async for event in agen:
                yield event


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
    """Extrait et normalise le domaine classifié depuis session.state."""
    raw = session_state.get("query_domain", "hr")
    if isinstance(raw, str):
        clean = re.sub(r"[^a-z]", "", raw.lower().strip())
        if clean in ("hr", "ops", "missions", "mixed"):
            return clean
    logger.warning("[Workflow] Domaine non reconnu '%s' — fallback 'hr'", raw)
    return "hr"


async def ask_missions_agent_with_hr_alignment(query: str, user_id: str = "") -> dict:
    """Wrapper intelligent pour ask_missions_agent avec alignement en boucle fermée via ask_hr_agent."""

    # 1. Appel initial
    res = await ask_missions_agent(query, user_id)
    if res.get("degraded") or "result" not in res:
        return res

    try:
        parsed = json.loads(res["result"])
        response_text = parsed.get("response", "")
    except Exception as e:
        logger.warning("[Alignment] Impossible de parser le JSON de ask_missions_agent: %s", e)
        return res

    # 2. Chercher si la réponse indique un identifiant de consultant manquant
    match = re.search(
        r"(?:identifiant|id|ID) manquant pour le consultant\s+([A-Za-zÀ-ÿ-]+(?:\s+[A-Za-zÀ-ÿ-]+)*)",
        response_text,
        re.IGNORECASE
    )

    if not match:
        return res

    consultant_name = match.group(1).strip()
    logger.info("[Alignment] 🔍 Consultant manquant détecté : '%s'. Déclenchement de l'alignement...", consultant_name)

    # 3. Interroger ask_hr_agent pour trouver l'ID
    hr_query = f"Donne-moi l'identifiant (UUID ou email) du consultant {consultant_name}"
    hr_res = await ask_hr_agent(hr_query, user_id)

    resolved_id = None
    if not hr_res.get("degraded") and "result" in hr_res:
        try:
            hr_parsed = json.loads(hr_res["result"])
            hr_response = hr_parsed.get("response", "")

            # Chercher un UUID ou un email dans la réponse
            uuid_match = re.search(
                r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                hr_response
            )
            email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", hr_response)

            if uuid_match:
                resolved_id = uuid_match.group(0)
            elif email_match:
                resolved_id = email_match.group(0)

        except Exception as e:
            logger.warning("[Alignment] Impossible de parser la réponse de ask_hr_agent: %s", e)

    if not resolved_id:
        logger.warning("[Alignment] ❌ Échec de la résolution de l'identifiant pour '%s'", consultant_name)
        return res

    logger.info("[Alignment] ✅ Résolution réussie pour '%s' : ID='%s'. Ré-exécution...", consultant_name, resolved_id)

    # 4. Ré-exécuter ask_missions_agent avec la requête enrichie
    enriched_query = f"{query} (avec l'identifiant du consultant {consultant_name} = {resolved_id})"
    final_res = await ask_missions_agent(enriched_query, user_id)
    return final_res


def build_workflow_agent(hr_tool, ops_tool, missions_tool) -> StateGraphAgent:
    """Construit le WorkflowAgent DAG Zenika (StateGraphAgent ADK v2).

    Args:
        hr_tool       : outil A2A ask_hr_agent (Python callable ADK tool)
        ops_tool      : outil A2A ask_ops_agent
        missions_tool : outil A2A ask_missions_agent (ou wrapper d'alignement)
    """

    classifier = _build_classifier_agent()

    router_model = os.getenv("GEMINI_ROUTER_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview"))

    router_agent = LlmAgent(
        name="zenika_workflow_router",
        model=router_model,
        instruction=(
            "Le domaine de la requête a déjà été classifié dans ta session sous la clé "
            "'query_domain'. Utilise cette information pour appeler directement le bon outil :\n"
            "- query_domain='hr'       → appelle ask_hr_agent\n"
            "- query_domain='ops'      → appelle ask_ops_agent\n"
            "- query_domain='missions' → appelle ask_missions_agent\n"
            "- query_domain='mixed'    → appelle ask_mixed_agents (interroge HR et Ops en parallèle)\n\n"
            "Réponds en français. Synthétise les résultats des outils de manière claire et concise."
        ),
        tools=[hr_tool, ops_tool, missions_tool, ask_mixed_agents],
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

    return StateGraphAgent(
        name="zenika_staffing_workflow",
        description=(
            "Workflow de staffing Zenika — pipeline de graphe d'états : "
            "classification du domaine puis délégation au spécialiste approprié."
        ),
        sub_agents=[classifier, router_agent],
    )


def build_parallel_staffing_agent(hr_tool, ops_tool) -> ParallelAgent:
    """Construit un ParallelAgent pour les requêtes mixtes HR+Ops simultanées."""
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
