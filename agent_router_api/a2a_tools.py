"""
a2a_tools.py — Wrappers A2A + intercepteur JWT pour agent_router_api.

Ce module expose :
  - A2ASubAgentError      : exception typée pour les erreurs 4xx non-retryables
  - A2aRequestInterceptor : httpx.Auth qui injecte le JWT depuis auth_header_var
  - _is_circuit_open()    : circuit-breaker — retourne True si le sous-agent est en erreur récente
  - _record_failure()     : enregistre un échec (incrémente le compteur Redis/mémoire)
  - _record_success()     : réinitialise le circuit-breaker après un succès
  - _call_sub_agent()     : appel HTTP A2A résilient avec retry + circuit-breaker + mode dégradé
  - discover_sub_agents() : A2A v2 — récupère les AgentCards via /.well-known/agent.json (cache TTL)
  - _SUB_AGENT_REGISTRY   : registre statique des sous-agents (URL de base)
  - ask_hr_agent()        : outil LLM → délègue à l'Agent RH
  - ask_ops_agent()       : outil LLM → délègue à l'Agent Ops
  - ask_missions_agent()  : outil LLM → délègue à l'Agent Missions
  - ROUTER_TOOLS          : liste des outils à passer à Agent(tools=...)
"""

import asyncio
import json
import logging
import os
import time
import contextvars

import httpx
from mcp_client import auth_header_var, user_id_var
from metrics import (A2A_CALL_DURATION, A2A_CALL_ERRORS_TOTAL,
                     A2A_CALL_RETRIES_TOTAL)
from opentelemetry.propagate import inject
from agent_commons.ui_tools import render_ui_widgets

logger = logging.getLogger(__name__)

# Side-channel to pass massive data (UI elements, traces, sub-steps) to the router
# without injecting it into the LLM's context window (prevents 400 Context Overflow).
a2a_metadata_var = contextvars.ContextVar("a2a_metadata", default=None)

# ── Circuit-Breaker configuration ────────────────────────────────────────────
# After CB_FAILURE_THRESHOLD consecutive failures on a given agent, the circuit
# opens for CB_OPEN_DURATION_S seconds to avoid cascading timeout storms.
# Uses Redis via shared.cache for cross-process consistency.

CB_FAILURE_THRESHOLD: int = int(os.getenv("A2A_CB_FAILURE_THRESHOLD", "2"))
CB_OPEN_DURATION_S: float = float(os.getenv("A2A_CB_OPEN_DURATION_S", "30"))

from shared.cache import get_cache, set_cache  # noqa: E402


async def _is_circuit_open(agent_name: str) -> bool:
    """Return True if the circuit-breaker for *agent_name* is currently open.

    A circuit is open when the agent has failed at least CB_FAILURE_THRESHOLD
    times in a row AND the cooldown period has not yet elapsed.
    Fail-open policy: if state is missing, the circuit is considered closed.
    """
    state = await get_cache(f"cb:{agent_name}")
    if state is None:
        return False
    open_until = state.get("open_until", 0.0)
    if open_until and time.time() < open_until:
        return True
    # Cooldown elapsed — auto-reset to half-open
    if open_until and time.time() >= open_until:
        state["failures"] = 0
        state["open_until"] = 0.0
        await set_cache(f"cb:{agent_name}", state, 3600)
    return False


async def _record_failure(agent_name: str) -> None:
    """Record a failure for *agent_name* and open the circuit if threshold is reached."""
    state = await get_cache(f"cb:{agent_name}") or {"failures": 0, "open_until": 0.0}
    state["failures"] = state.get("failures", 0) + 1
    if state["failures"] >= CB_FAILURE_THRESHOLD:
        state["open_until"] = time.time() + CB_OPEN_DURATION_S
        logger.warning(
            "[A2A:%s] 🔴 Circuit-breaker OPEN for %.0fs after %d failures.",
            agent_name, CB_OPEN_DURATION_S, state["failures"],
        )
    await set_cache(f"cb:{agent_name}", state, 3600)


async def _record_success(agent_name: str) -> None:
    """Reset the circuit-breaker for *agent_name* after a successful call."""
    await set_cache(f"cb:{agent_name}", {"failures": 0, "open_until": 0.0}, 3600)


# ── Confidence scorer ─────────────────────────────────────────────────────────────

# Guardrail tool names that reduce confidence (set for O(1) lookup)
_GUARDRAIL_TOOLS: frozenset[str] = frozenset({
    "GUARDRAIL_HALLUCINATION",
    "GUARDRAIL_OPS_METRICS",
    "GUARDRAIL_ID_INVENTION",
    "GUARDRAIL_GROUNDING",
    "GUARDRAIL_COM006",
    "GUARDRAIL_GROUNDING_HR",
})


def _compute_confidence(steps: list[dict]) -> float:
    """Compute a confidence score (0.0 – 1.0) from a sub-agent's execution steps.

    Scoring rules (cumulative, floored at 0.0):
      - Base score: 1.0
      - No tool calls detected : -0.3 (risk of hallucination — no grounding)
      - Per guardrail warning step: -0.2 (a guardrail fired, trust is reduced)
      - TOOL_BUDGET warning present: -0.1 (context overflow risk)

    Args:
        steps: The ``steps`` list from the A2A response payload.

    Returns:
        Confidence score in [0.0, 1.0] (rounded to 2 decimal places).
    """
    if not steps:
        return 0.5  # Unknown — no execution trace

    call_count = sum(1 for s in steps if s.get("type") == "call")
    warning_steps = [s for s in steps if s.get("type") == "warning"]

    score = 1.0

    if call_count == 0:
        score -= 0.3  # No tool called — high hallucination risk

    for step in warning_steps:
        tool = step.get("tool", "")
        if tool in _GUARDRAIL_TOOLS:
            score -= 0.2  # A guardrail fired
        elif tool == "TOOL_BUDGET":
            score -= 0.1  # Context overflow risk

    return round(max(0.0, min(1.0, score)), 2)


# ── Exception typée ──────────────────────────────────────────────────────────

class A2ASubAgentError(Exception):
    """Raised when an A2A call fails with a 4xx client error (never retried)."""

    def __init__(self, agent_name: str, status_code: int, detail: str) -> None:
        self.agent_name = agent_name
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[A2A:{agent_name}] HTTP {status_code} — {detail}")


# ── Intercepteur Zero-Trust ───────────────────────────────────────────────────

class A2aRequestInterceptor(httpx.Auth):
    """Injecte le JWT Bearer courant dans chaque requête A2A sortante.

    Implémente le pattern ``httpx.Auth`` afin que la propagation Zero-Trust
    soit centralisée et testable indépendamment de la logique métier.
    Le token est lu depuis ``auth_header_var`` (contextvars) qui est alimenté
    par le handler ``/query`` ou ``/a2a/query`` de chaque agent.
    """

    def auth_flow(self, request: httpx.Request):
        auth = auth_header_var.get(None)
        if auth:
            request.headers["Authorization"] = auth
        yield request


# ── Appel HTTP A2A résilient ─────────────────────────────────────────────────

async def _call_sub_agent(
    agent_name: str,
    url: str,
    query: str,
    user_id: str,
    timeout: float = 30.0,
) -> dict:
    """Appel HTTP A2A vers un sous-agent avec retry automatique et circuit-breaker.

    - Circuit-breaker : si le sous-agent a échoué CB_FAILURE_THRESHOLD fois de suite,
      retour immédiat en mode dégradé sans attente (CB_OPEN_DURATION_S secondes).
    - Retry sur erreurs réseau, 5xx ET 429 (max 3 tentatives, backoff exponentiel + jitter).
    - 429 : header Retry-After respecté en priorité (sinon backoff exponentiel).
    - Fail-fast sur les erreurs 4xx non-retryables (401, 403, 404, 422).
    - Retourne un dict avec ``degraded: True`` si toutes les tentatives échouent.
    """
    # Circuit-breaker check — fail fast if the agent is already in error state
    if await _is_circuit_open(agent_name):
        logger.warning(
            "[A2A:%s] 🔴 Circuit-breaker OPEN — returning immediate degraded response.",
            agent_name,
        )
        return {
            "response": (
                f"❌ Le sous-agent {agent_name} est temporairement indisponible "
                "(circuit-breaker actif). Veuillez réessayer dans quelques instants."
            ),
            "degraded": True,
            "reason": "circuit_breaker_open",
            "data": None,
            "steps": [{
                "type": "warning",
                "tool": f"{agent_name}:CB_OPEN",
                "args": {"message": f"Circuit-breaker ouvert pour {agent_name}."},
            }],
            "thoughts": "",
            "usage": {"total_input_tokens": 0, "total_output_tokens": 0, "estimated_cost_usd": 0},
        }

    headers: dict = {}
    inject(headers)  # Propagate OTel trace context

    # 4xx codes that are NEVER retried (client error — no point retrying)
    _NON_RETRYABLE_4XX = frozenset({401, 403, 404, 422})
    # 429 is retryable — it signals transient server saturation, not a client bug
    _RETRYABLE_CODES = frozenset({429, 500, 502, 503, 504})

    attempt = 0
    start = time.monotonic()
    last_error: Exception = Exception("Agent call never attempted")

    for i in range(3):
        attempt += 1
        if i > 0:
            A2A_CALL_RETRIES_TOTAL.labels(agent=agent_name).inc()
            logger.warning(f"[A2A:{agent_name}] Retry attempt #{attempt}")

        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers, auth=A2aRequestInterceptor()) as client:
                res = await client.post(f"{url.rstrip('/')}/a2a/query", json={"query": query, "user_id": user_id})

            if res.status_code in _NON_RETRYABLE_4XX:
                # Fail-fast : erreur client, inutile de retenter
                raise A2ASubAgentError(agent_name, res.status_code, res.text[:200])

            if res.status_code == 429:
                # 429 retryable : respecter Retry-After ou backoff exponentiel
                retry_after_header = res.headers.get("Retry-After", "").strip()
                if retry_after_header:
                    try:
                        wait = min(float(retry_after_header), 60.0)
                    except ValueError:
                        wait = min(2.0 * (2 ** i) + __import__("random").uniform(0, 1), 60.0)
                else:
                    wait = min(2.0 * (2 ** i) + __import__("random").uniform(0, 1), 60.0)
                A2A_CALL_ERRORS_TOTAL.labels(agent=agent_name, reason="rate_limited").inc()
                logger.warning(
                    "[A2A:%s] 429 Rate-Limited (attempt #%d) — retry dans %.1fs.",
                    agent_name, attempt, wait,
                )
                last_error = A2ASubAgentError(agent_name, 429, "Rate limited")
                await asyncio.sleep(wait)
                continue

            if res.status_code in _RETRYABLE_CODES:
                wait = min(2.0 * (2 ** i) + __import__("random").uniform(0, 1), 30.0)
                A2A_CALL_ERRORS_TOTAL.labels(agent=agent_name, reason="server_error").inc()
                logger.warning(
                    "[A2A:%s] Server error %d (attempt #%d) — retry dans %.1fs.",
                    agent_name, res.status_code, attempt, wait,
                )
                last_error = Exception(f"HTTP {res.status_code}")
                await asyncio.sleep(wait)
                continue

            res.raise_for_status()
            data = res.json()
            duration = time.monotonic() - start
            A2A_CALL_DURATION.labels(agent=agent_name).observe(duration)
            logger.info(f"[A2A:{agent_name}] Success in {duration:.2f}s (attempt #{attempt})")
            await _record_success(agent_name)
            return data

        except A2ASubAgentError as e:
            duration = time.monotonic() - start
            A2A_CALL_DURATION.labels(agent=agent_name).observe(duration)
            A2A_CALL_ERRORS_TOTAL.labels(agent=agent_name, reason="client_error").inc()
            logger.error(f"[A2A:{agent_name}] Non-retriable error {e.status_code}: {e.detail}")
            last_error = e
            break  # Pas de retry sur les erreurs client non-retryables

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            A2A_CALL_ERRORS_TOTAL.labels(agent=agent_name, reason="network").inc()
            logger.warning(f"[A2A:{agent_name}] Network error (attempt #{attempt}): {e}")
            last_error = e
            if i < 2:
                await asyncio.sleep(min(2.0 * (2 ** i), 10.0))

        except Exception as e:
            A2A_CALL_ERRORS_TOTAL.labels(agent=agent_name, reason="unknown").inc()
            logger.error(f"[A2A:{agent_name}] Unexpected error: {e}")
            last_error = e
            break

    A2A_CALL_DURATION.labels(agent=agent_name).observe(time.monotonic() - start)
    reason = str(last_error)[:300]
    logger.error(f"[A2A:{agent_name}] All attempts failed. Returning degraded response. Reason: {reason}")
    await _record_failure(agent_name)
    return {
        "response": (
            f"❌ Le sous-agent {agent_name} est temporairement indisponible. "
            "Veuillez réessayer dans quelques instants."
        ),
        "degraded": True,
        "reason": reason,
        "data": None,
        "steps": [{
            "type": "warning",
            "tool": f"{agent_name}:UNAVAILABLE",
            "args": {"message": f"Sous-agent injoignable : {reason}"},
        }],
        "thoughts": "",
        "usage": {"total_input_tokens": 0, "total_output_tokens": 0, "estimated_cost_usd": 0},
    }


# ── Outils LLM A2A ───────────────────────────────────────────────────────────

async def ask_hr_agent(query: str, user_id: str = "") -> dict:
    """
    Délègue une requête à l'Agent RH (Talent & Compétences).
    Utiliser cet outil si l'utilisateur pose une question concernant :
    - La recherche ou la consultation de profils consultants.
    - L'analyse ou la lecture de CVs (notamment via un lien Google Drive).
    - Les compétences des consultants (arbre taxonomique, évaluation, coaching CV, scoring Gemini).
    - L'historique des missions **d'un consultant nommé** (ex: "quelles missions a faites Jean ?").
    - La disponibilité d'un consultant spécifique.
    NE PAS utiliser pour lister les missions client ou proposer une équipe → utiliser `ask_missions_agent`.

    Args:
        query (str): La requête détaillée à transmettre à l'Agent RH. Inclure tout le contexte pertinent.
        user_id (str): L'identifiant de l'utilisateur (email JWT). Laissé vide — automatiquement résolu depuis le token.
    """
    effective_user_id = user_id or user_id_var.get("anonymous")
    hr_url = os.getenv("AGENT_HR_API_URL", "http://agent_hr_api:8080")

    logger.info(f"[A2A] Dispatching query to HR Agent (user={effective_user_id[:20]}): {query[:50]}...")
    data = await _call_sub_agent("hr_agent", hr_url, query, effective_user_id, timeout=60.0)

    if data.get("degraded"):
        return {"result": json.dumps(data)}

    metadata_list = a2a_metadata_var.get()
    if metadata_list is not None:
        metadata_list.append({
            "agent": "hr_agent",
            "data": data.get("data"),
            "display_type": data.get("display_type"),
            "steps": data.get("steps", []),
            "usage": data.get("usage", {}),
        })

    return {"result": json.dumps({
        "agent": "hr_agent",
        "response": data.get("response"),
        "thoughts": data.get("thoughts", ""),
        "confidence": _compute_confidence(data.get("steps", [])),
    })}


async def ask_ops_agent(query: str, user_id: str = "") -> dict:
    """
    Délègue une requête à l'Agent Ops (FinOps, Système & Drive Integration).
    Utiliser cet outil UNIQUEMENT si l'utilisateur pose une question concernant:
    - La santé du système, la topologie ou l'architecture technique GCP.
    - Le FinOps, la facture IA, l'estimation des coûts, le marché.
    - La modification de la configuration système de parsing Google Drive (dossiers synchronisés).
    - L'exploration technique de logs bruts Applicatifs avec Grafana/Loki.
    - La gestion des System Prompts (création, modification) et la remontée d'erreurs.

    Args:
        query (str): La requête ou la commande technique à envoyer à l'Agent Ops.
        user_id (str): L'identifiant de l'utilisateur (email JWT). Laissé vide — automatiquement résolu depuis le token.
    """
    effective_user_id = user_id or user_id_var.get("anonymous")
    ops_url = os.getenv("AGENT_OPS_API_URL", "http://agent_ops_api:8080")

    logger.info(f"[A2A] Dispatching query to Ops Agent (user={effective_user_id[:20]}): {query[:50]}...")
    data = await _call_sub_agent("ops_agent", ops_url, query, effective_user_id, timeout=60.0)

    if data.get("degraded"):
        return {"result": json.dumps(data)}

    metadata_list = a2a_metadata_var.get()
    if metadata_list is not None:
        metadata_list.append({
            "agent": "ops_agent",
            "data": data.get("data"),
            "display_type": data.get("display_type"),
            "steps": data.get("steps", []),
            "usage": data.get("usage", {}),
        })

    return {"result": json.dumps({
        "agent": "ops_agent",
        "response": data.get("response"),
        "thoughts": data.get("thoughts", ""),
        "confidence": _compute_confidence(data.get("steps", [])),
    })}


async def ask_missions_agent(query: str, user_id: str = "") -> dict:
    """
    Délègue une requête à l'Agent Missions (Staffing Director).
    Utiliser cet outil UNIQUEMENT si l'utilisateur pose une question concernant :
    - La liste, le détail ou la consultation d'une mission client.
    - Le staffing d'une mission : proposer une équipe de consultants qualifiés.
    - Le cycle de vie d'une mission (statut, re-analyse IA, clôture, scoring No-Go).
    - Le matching consultants/mission ou la recommandation d'équipe.

    NE PAS utiliser pour : la gestion des profils RH, l'import de CVs, les compétences → `ask_hr_agent`.
    NE PAS utiliser pour : la santé système, les coûts IA, les logs → `ask_ops_agent`.

    Args:
        query (str): La requête détaillée à transmettre à l'Agent Missions.
            Inclure l'ID de mission si connu, les compétences recherchées, tout le contexte pertinent.
        user_id (str): L'identifiant de l'utilisateur (email JWT). Laissé vide — automatiquement résolu depuis le token.
    """
    effective_user_id = user_id or user_id_var.get("anonymous")
    missions_url = os.getenv("AGENT_MISSIONS_API_URL", "http://agent_missions_api:8080")

    logger.info(f"[A2A] Dispatching query to Missions Agent (user={effective_user_id[:20]}): {query[:50]}...")
    # Timeout 90s : pipeline staffing (get_mission + search_best_candidates + RAG x3 + LLM)
    data = await _call_sub_agent("missions_agent", missions_url, query, effective_user_id, timeout=90.0)

    if data.get("degraded"):
        return {"result": json.dumps(data)}

    metadata_list = a2a_metadata_var.get()
    if metadata_list is not None:
        metadata_list.append({
            "agent": "missions_agent",
            "data": data.get("data"),
            "display_type": data.get("display_type"),
            "steps": data.get("steps", []),
            "usage": data.get("usage", {}),
        })

    return {"result": json.dumps({
        "agent": "missions_agent",
        "response": data.get("response"),
        "thoughts": data.get("thoughts", ""),
        "confidence": _compute_confidence(data.get("steps", [])),
    })}


# ── A2A v2 — Service Discovery ────────────────────────────────────────────────
# Registre statique des sous-agents avec leur URL de base.
# Alimenté par les variables d'environnement (configurées dans docker-compose / Cloud Run).
_SUB_AGENT_REGISTRY: dict[str, str] = {
    "hr_agent": os.getenv("AGENT_HR_API_URL", "http://agent_hr_api:8080"),
    "ops_agent": os.getenv("AGENT_OPS_API_URL", "http://agent_ops_api:8080"),
    "missions_agent": os.getenv("AGENT_MISSIONS_API_URL", "http://agent_missions_api:8080"),
}

# Cache TTL pour les AgentCards (évite les appels réseau redondants — 5 min)
_AGENT_CARD_CACHE_TTL_S: int = int(os.getenv("AGENT_CARD_CACHE_TTL_S", "300"))


async def discover_sub_agents(force_refresh: bool = False) -> dict[str, dict]:
    """A2A v2 — Découverte dynamique des sous-agents via GET /.well-known/agent.json.

    Interroge chaque sous-agent enregistré dans _SUB_AGENT_REGISTRY pour récupérer
    son AgentCard (nom, description, compétences, endpoint). Les résultats sont mis en
    cache TTL (_AGENT_CARD_CACHE_TTL_S = 5 min par défaut) pour éviter les appels
    réseau redondants sur chaque requête.

    Usage typique : appelé au démarrage du Router pour construire le contexte système
    de l'agent LLM et enrichir les docstrings des outils avec les capacités réelles.

    Args:
        force_refresh: Si True, ignore le cache et interroge les agents directement.

    Returns:
        Dict ``{agent_name: agent_card_dict}`` pour chaque agent accessible.
        Les agents inaccessibles sont absents du dict (pas d'erreur levée — fail-soft).
    """
    result: dict[str, dict] = {}

    for agent_name, base_url in _SUB_AGENT_REGISTRY.items():
        if not force_refresh:
            cached = await get_cache(f"agent_card:{agent_name}")
            if cached is not None:
                result[agent_name] = cached
                logger.debug("[A2A:discovery] Cache HIT for %s", agent_name)
                continue

        discovery_url = f"{base_url.rstrip('/')}/.well-known/agent.json"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(discovery_url)
                res.raise_for_status()
                card = res.json()
                await set_cache(f"agent_card:{agent_name}", card, _AGENT_CARD_CACHE_TTL_S)
                result[agent_name] = card
                logger.info(
                    "[A2A:discovery] ✅ AgentCard fetched for %s — skills: %s",
                    agent_name,
                    [s.get("id") for s in card.get("skills", [])],
                )
        except Exception as e:
            logger.warning(
                "[A2A:discovery] ⚠️ Could not fetch AgentCard for %s at %s: %s",
                agent_name, discovery_url, e,
            )

    return result


def _build_docstring_from_card(card: dict, tool_fn_name: str) -> str:
    """Construit la docstring LLM d'un outil A2A à partir d'une AgentCard.

    La docstring produite suit le format que google-adk injecte dans le contexte
    du LLM comme description de l'outil. Elle doit être :
    - Claire sur CE QUE fait l'agent (skills avec descriptions)
    - Explicite sur QUAND utiliser cet outil (routing_hints.do_use_when)
    - Explicite sur QUAND NE PAS l'utiliser (routing_hints.do_not_use_when)
    - Illustrée par des exemples concrets (examples)

    Args:
        card:         L'AgentCard retournée par GET /.well-known/agent.json.
        tool_fn_name: Nom de la fonction Python (pour les logs).

    Returns:
        Docstring complète prête à être assignée à ``fn.__doc__``.
    """
    lines: list[str] = []

    name = card.get("name", tool_fn_name)
    description = card.get("description", "")
    lines.append(f"{description}")
    lines.append("")

    # ── Capacités (skills) ────────────────────────────────────────────────────
    skills = card.get("skills", [])
    if skills:
        lines.append("Capacités disponibles :")
        for skill in skills:
            skill_name = skill.get("name", skill.get("id", ""))
            skill_desc = skill.get("description", "")
            lines.append(f"  - {skill_name} : {skill_desc}")
        lines.append("")

    # ── Routing — quand utiliser ──────────────────────────────────────────────
    hints = card.get("routing_hints", {})
    do_use = hints.get("do_use_when", [])
    if do_use:
        lines.append("Utiliser cet outil quand :")
        for hint in do_use:
            lines.append(f"  ✓ {hint}")
        lines.append("")

    # ── Routing — quand NE PAS utiliser ──────────────────────────────────────
    do_not = hints.get("do_not_use_when", [])
    if do_not:
        lines.append("NE PAS utiliser cet outil quand :")
        for hint in do_not:
            lines.append(f"  ✗ {hint}")
        lines.append("")

    # ── Exemples d'invocation ─────────────────────────────────────────────────
    examples = card.get("examples", [])
    if examples:
        lines.append("Exemples de requêtes :")
        for ex in examples[:4]:
            lines.append(f'  - "{ex.get("query", "")}"')
        lines.append("")

    # ── Args (constant — tous les tools A2A ont la même signature) ────────────
    lines.append("Args:")
    lines.append("    query (str): La requête détaillée à transmettre à l'agent. Inclure tout le contexte pertinent.")
    lines.append("    user_id (str): L'identifiant utilisateur (email JWT). Laissé vide — résolu depuis le token.")

    logger.info("[A2A:enrich] Docstring built for '%s' from AgentCard '%s'", tool_fn_name, name)
    return "\n".join(lines)


# Mapping tool_function → agent_name dans le registre de discovery
_TOOL_AGENT_MAP: dict[str, str] = {
    "ask_hr_agent": "hr_agent",
    "ask_ops_agent": "ops_agent",
    "ask_missions_agent": "missions_agent",
}


def enrich_tool_docstrings(cards: dict[str, dict]) -> None:
    """Injecte les docstrings LLM dynamiques depuis les AgentCards dans les tool functions.

    Appelée au démarrage du Router (lifespan) après ``discover_sub_agents()``.
    Met à jour l'attribut ``__doc__`` de chaque fonction A2A tool afin que
    google-adk expose les bonnes descriptions au LLM lors de la création de l'Agent.

    Fail-soft : si une AgentCard est manquante pour un agent donné, la docstring
    statique hardcodée dans le code source est conservée.

    Args:
        cards: Dict ``{agent_name: agent_card_dict}`` retourné par discover_sub_agents().
    """
    import sys
    current_module = sys.modules[__name__]

    for fn_name, agent_name in _TOOL_AGENT_MAP.items():
        card = cards.get(agent_name)
        if card is None:
            logger.warning(
                "[A2A:enrich] No AgentCard for '%s' — keeping static docstring for '%s'.",
                agent_name, fn_name,
            )
            continue

        fn = getattr(current_module, fn_name, None)
        if fn is None:
            logger.warning("[A2A:enrich] Function '%s' not found in module — skipping.", fn_name)
            continue

        new_doc = _build_docstring_from_card(card, fn_name)
        fn.__doc__ = new_doc
        logger.info(
            "[A2A:enrich] ✅ Docstring updated for '%s' (%d chars from AgentCard '%s').",
            fn_name, len(new_doc), card.get("name", agent_name),
        )


# Liste des outils exposés au Router LLM
ROUTER_TOOLS = [ask_hr_agent, ask_ops_agent, ask_missions_agent, render_ui_widgets]
