"""
a2a_tools.py — Wrappers A2A + intercepteur JWT pour agent_router_api.

Ce module expose :
  - A2ASubAgentError      : exception typée pour les erreurs 4xx non-retryables
  - A2aRequestInterceptor : httpx.Auth qui injecte le JWT depuis auth_header_var
  - _call_sub_agent()     : appel HTTP A2A résilient avec retry + mode dégradé
  - ask_hr_agent()        : outil LLM → délègue à l'Agent RH
  - ask_ops_agent()       : outil LLM → délègue à l'Agent Ops
  - ask_missions_agent()  : outil LLM → délègue à l'Agent Missions
  - ROUTER_TOOLS          : liste des outils à passer à Agent(tools=...)
"""

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
    """Appel HTTP A2A vers un sous-agent avec retry automatique.

    - Retry sur erreurs réseau et 5xx (max 2 tentatives, backoff 2s).
    - Pas de retry sur les erreurs 4xx (erreur client → immédiat).
    - Retourne un dict avec ``degraded: True`` si toutes les tentatives échouent.
    """
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
                import asyncio
                await asyncio.sleep(2.0)
        except httpx.HTTPStatusError as e:
            duration = time.monotonic() - start
            A2A_CALL_ERRORS_TOTAL.labels(agent=agent_name, reason="server_error").inc()
            logger.warning(f"[A2A:{agent_name}] Server error {e.response.status_code} (attempt #{attempt})")
            last_error = e
            if i < 1:
                import asyncio
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
    return {
        "response": f"❌ Le sous-agent {agent_name} est temporairement indisponible. Veuillez réessayer dans quelques instants.",
        "degraded": True,
        "reason": reason,
        "data": None,
        "steps": [{"type": "warning", "tool": f"{agent_name}:UNAVAILABLE", "args": {"message": f"Sous-agent injoignable : {reason}"}}],
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
        "display_type": data.get("display_type"),  # Propagé depuis render_ui_widgets ADK
        "steps": data.get("steps", []),
        "thoughts": data.get("thoughts", ""),
        "usage": data.get("usage", {})
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
        "usage": data.get("usage", {})
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
        "usage": data.get("usage", {})
    })}


# Liste des outils exposés au Router LLM
ROUTER_TOOLS = [ask_hr_agent, ask_ops_agent, ask_missions_agent]
