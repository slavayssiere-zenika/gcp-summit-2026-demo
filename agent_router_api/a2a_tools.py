"""
a2a_tools.py — Wrappers A2A + intercepteur JWT pour agent_router_api.

Ce module expose :
  - A2ASubAgentError      : exception typée pour les erreurs 4xx non-retryables
  - A2aRequestInterceptor : httpx.Auth qui injecte le JWT depuis auth_header_var
  - _is_circuit_open()    : circuit-breaker — retourne True si le sous-agent est en erreur récente
  - _record_failure()     : enregistre un échec (incrémente le compteur Redis/mémoire)
  - _record_success()     : réinitialise le circuit-breaker après un succès
  - _call_sub_agent()     : appel HTTP A2A résilient avec retry + circuit-breaker + mode dégradé
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

import httpx
from mcp_client import auth_header_var, user_id_var
from metrics import (A2A_CALL_DURATION, A2A_CALL_ERRORS_TOTAL,
                     A2A_CALL_RETRIES_TOTAL)
from opentelemetry.propagate import inject

logger = logging.getLogger(__name__)

# ── Circuit-Breaker configuration ────────────────────────────────────────────
# After CB_FAILURE_THRESHOLD consecutive failures on a given agent, the circuit
# opens for CB_OPEN_DURATION_S seconds to avoid cascading timeout storms.
# Uses an in-process dict as primary store (zero external dependency).
# Redis is used as secondary store when available (cross-process consistency).

CB_FAILURE_THRESHOLD: int = int(os.getenv("A2A_CB_FAILURE_THRESHOLD", "2"))
CB_OPEN_DURATION_S: float = float(os.getenv("A2A_CB_OPEN_DURATION_S", "30"))

# In-memory fallback store: {agent_name: {"failures": int, "open_until": float}}
_cb_state: dict[str, dict] = {}


def _is_circuit_open(agent_name: str) -> bool:
    """Return True if the circuit-breaker for *agent_name* is currently open.

    A circuit is open when the agent has failed at least CB_FAILURE_THRESHOLD
    times in a row AND the cooldown period has not yet elapsed.
    Fail-open policy: if state is missing, the circuit is considered closed.
    """
    state = _cb_state.get(agent_name)
    if state is None:
        return False
    open_until = state.get("open_until", 0.0)
    if open_until and time.monotonic() < open_until:
        return True
    # Cooldown elapsed — auto-reset to half-open
    if open_until and time.monotonic() >= open_until:
        state["failures"] = 0
        state["open_until"] = 0.0
    return False


def _record_failure(agent_name: str) -> None:
    """Record a failure for *agent_name* and open the circuit if threshold is reached."""
    state = _cb_state.setdefault(agent_name, {"failures": 0, "open_until": 0.0})
    state["failures"] = state.get("failures", 0) + 1
    if state["failures"] >= CB_FAILURE_THRESHOLD:
        state["open_until"] = time.monotonic() + CB_OPEN_DURATION_S
        logger.warning(
            "[A2A:%s] 🔴 Circuit-breaker OPEN for %.0fs after %d failures.",
            agent_name, CB_OPEN_DURATION_S, state["failures"],
        )


def _record_success(agent_name: str) -> None:
    """Reset the circuit-breaker for *agent_name* after a successful call."""
    if agent_name in _cb_state:
        _cb_state[agent_name] = {"failures": 0, "open_until": 0.0}


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
    - Retry sur erreurs réseau et 5xx (max 2 tentatives, backoff 2s).
    - Pas de retry sur les erreurs 4xx (erreur client → immédiat).
    - Retourne un dict avec ``degraded: True`` si toutes les tentatives échouent.
    """
    # Circuit-breaker check — fail fast if the agent is already in error state
    if _is_circuit_open(agent_name):
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

    attempt = 0

    async def _do_request() -> dict:
        nonlocal attempt
        if attempt > 0:
            A2A_CALL_RETRIES_TOTAL.labels(agent=agent_name).inc()
            logger.warning(f"[A2A:{agent_name}] Retry attempt #{attempt}")
        attempt += 1

        async with httpx.AsyncClient(timeout=timeout, headers=headers, auth=A2aRequestInterceptor()) as client:
            res = await client.post(f"{url.rstrip('/')}/a2a/query", json={"query": query, "user_id": user_id})

            if 400 <= res.status_code < 500:
                raise A2ASubAgentError(agent_name, res.status_code, res.text[:200])

            res.raise_for_status()
            return res.json()

    start = time.monotonic()
    last_error: Exception = Exception("Agent call never attempted")

    for i in range(2):
        try:
            data = await _do_request()
            duration = time.monotonic() - start
            A2A_CALL_DURATION.labels(agent=agent_name).observe(duration)
            logger.info(f"[A2A:{agent_name}] Success in {duration:.2f}s (attempt #{attempt})")
            _record_success(agent_name)  # Reset circuit-breaker on success
            return data
        except A2ASubAgentError as e:
            duration = time.monotonic() - start
            A2A_CALL_DURATION.labels(agent=agent_name).observe(duration)
            A2A_CALL_ERRORS_TOTAL.labels(agent=agent_name, reason="client_error").inc()
            logger.error(f"[A2A:{agent_name}] Non-retriable error {e.status_code}: {e.detail}")
            last_error = e
            break
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            duration = time.monotonic() - start
            A2A_CALL_ERRORS_TOTAL.labels(agent=agent_name, reason="network").inc()
            logger.warning(f"[A2A:{agent_name}] Network error (attempt #{attempt}): {e}")
            last_error = e
            if i < 1:
                await asyncio.sleep(2.0)
        except httpx.HTTPStatusError as e:
            duration = time.monotonic() - start
            A2A_CALL_ERRORS_TOTAL.labels(agent=agent_name, reason="server_error").inc()
            logger.warning(f"[A2A:{agent_name}] Server error {e.response.status_code} (attempt #{attempt})")
            last_error = e
            if i < 1:
                await asyncio.sleep(2.0)
        except Exception as e:
            duration = time.monotonic() - start
            A2A_CALL_ERRORS_TOTAL.labels(agent=agent_name, reason="unknown").inc()
            logger.error(f"[A2A:{agent_name}] Unexpected error: {e}")
            last_error = e
            break

    A2A_CALL_DURATION.labels(agent=agent_name).observe(time.monotonic() - start)
    reason = str(last_error)[:300]
    logger.error(f"[A2A:{agent_name}] All attempts failed. Returning degraded response. Reason: {reason}")
    _record_failure(agent_name)  # Increment circuit-breaker failure counter
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

    return {"result": json.dumps({
        "agent": "hr_agent",
        "response": data.get("response"),
        "data": data.get("data"),
        "display_type": data.get("display_type"),
        "steps": data.get("steps", []),
        "thoughts": data.get("thoughts", ""),
        "usage": data.get("usage", {}),
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

    return {"result": json.dumps({
        "agent": "ops_agent",
        "response": data.get("response"),
        "data": data.get("data"),
        "display_type": data.get("display_type"),
        "steps": data.get("steps", []),
        "thoughts": data.get("thoughts", ""),
        "usage": data.get("usage", {}),
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

    return {"result": json.dumps({
        "agent": "missions_agent",
        "response": data.get("response"),
        "data": data.get("data"),
        "display_type": data.get("display_type"),
        "steps": data.get("steps", []),
        "thoughts": data.get("thoughts", ""),
        "usage": data.get("usage", {}),
        "confidence": _compute_confidence(data.get("steps", [])),
    })}


# Liste des outils exposés au Router LLM
ROUTER_TOOLS = [ask_hr_agent, ask_ops_agent, ask_missions_agent]
