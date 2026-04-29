import os
import json
import logging
import time
from typing import Optional
from google.genai import types
from google.adk.agents import Agent
import httpx
from opentelemetry.propagate import inject
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from metrics import A2A_CALL_DURATION, A2A_CALL_ERRORS_TOTAL, A2A_CALL_RETRIES_TOTAL

logger = logging.getLogger(__name__)

_session_service = None

def get_session_service():
    global _session_service
    if _session_service is None:
        from session import RedisSessionService
        _session_service = RedisSessionService()
    return _session_service


# --- A2A Resilient HTTP Call ---

class A2ASubAgentError(Exception):
    """Raised when an A2A call fails and should not be retried (4xx client errors)."""
    def __init__(self, agent_name: str, status_code: int, detail: str):
        self.agent_name = agent_name
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[A2A:{agent_name}] HTTP {status_code} — {detail}")


async def _call_sub_agent(
    agent_name: str,
    url: str,
    query: str,
    user_id: str,
    timeout: float,
    auth_header: Optional[str],
) -> dict:
    """
    Appel HTTP A2A vers un sous-agent avec retry automatique sur les erreurs réseau
    et les erreurs serveur 5xx. Les erreurs 4xx (client) ne sont pas retentées.
    Retourne un dict structuré avec 'degraded: True' si toutes les tentatives échouent.
    """
    headers = {}
    inject(headers)  # Propagate OTel trace context
    if auth_header:
        headers["Authorization"] = auth_header

    attempt = 0

    async def _do_request() -> dict:
        nonlocal attempt
        if attempt > 0:
            A2A_CALL_RETRIES_TOTAL.labels(agent=agent_name).inc()
            logger.warning(f"[A2A:{agent_name}] Retry attempt #{attempt}")
        attempt += 1

        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            res = await client.post(f"{url.rstrip('/')}/a2a/query", json={"query": query, "user_id": user_id})

            # 4xx = client error, ne pas retenter
            if 400 <= res.status_code < 500:
                raise A2ASubAgentError(agent_name, res.status_code, res.text[:200])

            res.raise_for_status()  # 5xx → httpx.HTTPStatusError → retriable
            return res.json()

    start = time.monotonic()
    last_error: Exception = Exception("Agent call never attempted")

    for i in range(2):  # 1 tentative initiale + 1 retry
        try:
            data = await _do_request()
            duration = time.monotonic() - start
            A2A_CALL_DURATION.labels(agent=agent_name).observe(duration)
            logger.info(f"[A2A:{agent_name}] Success in {duration:.2f}s (attempt #{attempt})")
            return data
        except A2ASubAgentError as e:
            # Erreur client — pas de retry
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
            if i < 1:  # Attendre avant le retry réseau
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
            break  # Erreur inconnue → pas de retry

    # Toutes les tentatives ont échoué → réponse dégradée structurée
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


# --- A2A Protocol Tools ---

async def ask_hr_agent(query: str, user_id: str = "user_1") -> dict:
    """
    Délègue une requête à l'Agent RH (Talent Acquisition & Staffing).
    Utiliser cet outil si l'utilisateur pose une question concernant:
    - La recherche de candidats ou profils.
    - L'analyse ou la lecture de CVs (notamment via un lien Google Drive).
    - La création ou la gestion de missions (staffing, sélection d'équipe).
    - Les utilisateurs internes ou les compétences (Tree).
    
    Args:
        query (str): La requête détaillée, claire et complète à transmettre à l'Agent RH. Reformule bien pour qu'il ait tout le contexte sans ambiguïté.
        user_id (str): L'identifiant de l'utilisateur (email ou sub JWT) pour l'isolation des sessions.
    """
    from mcp_client import auth_header_var
    hr_url = os.getenv("AGENT_HR_API_URL", "http://agent_hr_api:8080")
    auth = auth_header_var.get(None)

    logger.info(f"[A2A] Dispatching query to HR Agent: {query[:50]}...")
    data = await _call_sub_agent("hr_agent", hr_url, query, user_id, timeout=60.0, auth_header=auth)

    if data.get("degraded"):
        return {"result": json.dumps(data)}

    return {"result": json.dumps({
        "agent": "hr_agent",
        "response": data.get("response"),
        "data": data.get("data"),
        "steps": data.get("steps", []),
        "thoughts": data.get("thoughts", ""),
        "usage": data.get("usage", {})
    })}


async def ask_ops_agent(query: str, user_id: str = "user_1") -> dict:
    """
    Délègue une requête à l'Agent Ops (FinOps, Système & Drive Integration).
    Utiliser cet outil UNIQUEMENT si l'utilisateur pose une question concernant:
    - La santé du système, la topologie ou l'architecture technique GCP.
    - Le FinOps, la facture IA, l'estimation des coûts, le marché.
    - La modification de la configuration système de parsing Google Drive (dossiers synchronisés).
    - L'exploration technique de logs bruts Applicatifs avec Grafana/Loki.
    - La gestion des System Prompts (création, modification) et la remontée d'erreurs pour générer des directives de prompt.
    
    Args:
        query (str): La requête ou la commande technique à envoyer à l'Agent Ops.
        user_id (str): L'identifiant de l'utilisateur (email ou sub JWT) pour l'isolation des sessions.
    """
    from mcp_client import auth_header_var
    ops_url = os.getenv("AGENT_OPS_API_URL", "http://agent_ops_api:8080")
    auth = auth_header_var.get(None)

    logger.info(f"[A2A] Dispatching query to Ops Agent: {query[:50]}...")
    data = await _call_sub_agent("ops_agent", ops_url, query, user_id, timeout=60.0, auth_header=auth)

    if data.get("degraded"):
        return {"result": json.dumps(data)}

    return {"result": json.dumps({
        "agent": "ops_agent",
        "response": data.get("response"),
        "data": data.get("data"),
        "steps": data.get("steps", []),
        "thoughts": data.get("thoughts", ""),
        "usage": data.get("usage", {})
    })}


async def ask_missions_agent(query: str, user_id: str = "user_1") -> dict:
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
        user_id (str): L'identifiant de l'utilisateur (email ou sub JWT) pour l'isolation des sessions.
    """
    from mcp_client import auth_header_var
    missions_url = os.getenv("AGENT_MISSIONS_API_URL", "http://agent_missions_api:8080")
    auth = auth_header_var.get(None)

    logger.info(f"[A2A] Dispatching query to Missions Agent: {query[:50]}...")
    # Timeout 90s : pipeline staffing (get_mission + search_best_candidates + RAG x3 + LLM)
    data = await _call_sub_agent("missions_agent", missions_url, query, user_id, timeout=90.0, auth_header=auth)

    if data.get("degraded"):
        return {"result": json.dumps(data)}

    return {"result": json.dumps({
        "agent": "missions_agent",
        "response": data.get("response"),
        "data": data.get("data"),
        "steps": data.get("steps", []),
        "thoughts": data.get("thoughts", ""),
        "usage": data.get("usage", {})
    })}


ROUTER_TOOLS = [ask_hr_agent, ask_ops_agent, ask_missions_agent]


async def create_agent(session_id: str | None = None):
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    instruction_text = "Tu es l'Orchestrateur Principal de la plateforme Zenika, le 'Front-Desk'. Ton rôle est de diriger la demande vers le hub approprié en utilisant tes outils de délégation (A2A). Ne dis pas 'je vais interroger mon collègue', sois direct."
    try:
        from mcp_client import auth_header_var
        auth_header = auth_header_var.get(None)
        headers = {"Authorization": auth_header} if auth_header else {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(
                f"{prompts_api_url.rstrip('/')}/agent_router_api.system_instruction/compiled",
                headers=headers,
            )
            if res.status_code == 200:
                instruction_text = res.json()["value"]
            else:
                logger.warning(f"Failed to fetch system prompt from prompts_api: {res.status_code} (using built-in default)")
    except Exception as e:
        logger.warning(f"Error fetching system prompt: {e}")
        
    if session_id and session_id != "anon":
        try:
            from mcp_client import auth_header_var
            auth_header = auth_header_var.get()
            headers = {"Authorization": auth_header} if auth_header else {}
            async with httpx.AsyncClient() as client:
                res = await client.get(f"{prompts_api_url.rstrip('/')}/user_{session_id}", headers=headers, timeout=5.0)
                if res.status_code == 200:
                    user_prompt = res.json().get("value", "")
                    if user_prompt:
                        instruction_text += f"\n\n--- INSTRUCTIONS UTILISATEUR ({session_id}) ---\n{user_prompt}\n------------------------------------------------------------"
        except Exception as e:
            logger.warning(f"Error fetching user system prompt for session {session_id}: {e}")
            
    # AGENTS.md §1.4 : variable dédiée per-agent. GEMINI_MODEL est le fallback legacy.
    model = os.getenv("GEMINI_ROUTER_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview"))

    agent = Agent(
        name="assistant_zenika_router",
        model=model,
        generate_content_config=types.GenerateContentConfig(
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            ),
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(initial_delay=1, attempts=2),
            )
        ),
        instruction=instruction_text,
        description="Le point d'entrée Frontend de Zenika qui délègue le travail via le protocole A2A.",
        tools=ROUTER_TOOLS
    )
    
    return agent


async def run_agent_query(query: str, session_id: str | None = None, auth_token: str | None = None, user_id: str = "unknown@zenika.com") -> dict:
    """
    Exécute une requête via le Runner ADK.

    auth_token : Bearer token complet ("Bearer eyJ..."). Passé explicitement depuis le
    handler HTTP pour garantir la propagation JWT même quand les coroutines ADK
    s'exécutent dans un contexte asyncio distinct (Runner à événements multiples).
    Sans ce paramètre, auth_header_var peut être None dans ask_missions_agent,
    provocant un 401 lors de l'appel A2A interne.
    """
    from google.adk.runners import Runner
    from mcp_client import auth_header_var
    import uuid

    # --- Fix JWT propagation [STAFF-007] ---
    # Re-setter auth_header_var dans CE contexte asyncio (coroutine du runner)
    # garantit que les tools ADK (ask_*_agent) lisent le bon token.
    if auth_token:
        auth_header_var.set(auth_token)

    session_id = session_id or str(uuid.uuid4())
    session_service = get_session_service()

    agent = await create_agent(session_id)
    runner = Runner(app_name="zenika_assistant", agent=agent, session_service=session_service)

    try:
        session = await session_service.get_session(app_name="zenika_assistant", user_id=user_id, session_id=session_id)
        if session is None:
            raise KeyError("Session not found")
    except Exception:
        await session_service.create_session(app_name="zenika_assistant", user_id=user_id, session_id=session_id)

    response_parts = []
    last_tool_data = None
    steps = []
    seen_steps = set()
    thoughts = []
    # Vul 4 (Option A): Separate router-own tokens (logged to BQ) from cumulative total (returned in response)
    router_input_tokens = 0   # Router's own Gemini tokens only — used for BQ logging
    router_output_tokens = 0
    total_input_tokens = 0    # Cumulative (router + sub-agents) — used in the response usage field
    total_output_tokens = 0
    
    new_message = types.Content(role="user", parts=[types.Part(text=query)])

    try:
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=new_message):
            has_content = hasattr(event, 'content') and event.content is not None
            
            if has_content:
                # 1. Metadata extraction from parts
                for part in (list(event.content.parts) if hasattr(event.content, 'parts') else []):
                    # a) Thoughts (Gemini 2.0 Thinking support)
                    thought_val = getattr(part, 'thought', None)
                    if thought_val:
                        if isinstance(thought_val, bool) and thought_val:
                            thoughts.append(getattr(part, 'text', ""))
                        else:
                            thoughts.append(str(thought_val))
                    
                    # b) Tool Calls (Observe orchestration)
                    tcall = getattr(part, 'tool_call', None) or getattr(part, 'function_call', None)
                    if tcall:
                        calls = tcall if isinstance(tcall, list) else [tcall]
                        for call in calls:
                            name = getattr(call, 'name', 'unknown')
                            args = getattr(call, 'args', {})
                            sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                            if sig not in seen_steps:
                                steps.append({"type": "call", "tool": name, "args": args})
                                seen_steps.add(sig)
                    
                    # c) Tool Results (Aggregate Sub-Agent data)
                    fres = getattr(part, 'function_response', None)
                    if fres:
                        res_data = getattr(fres, 'response', fres)
                        if hasattr(res_data, 'model_dump'): res_data = res_data.model_dump()
                        elif hasattr(res_data, 'dict'): res_data = res_data.dict()
                        
                        # Unwrap MCP 'result' JSON string (Crucial for sub-agent data access)
                        if isinstance(res_data, dict) and "result" in res_data and isinstance(res_data["result"], str) and res_data["result"].startswith("{"):
                            try: res_data = json.loads(res_data["result"])
                            except Exception as e: logger.warning(f"Erreur ignorée lors du parsing JSON: {e}")

                        # Aggregate sub-agent metadata if this is an A2A delegation
                        if isinstance(res_data, dict) and "response" in res_data:
                            sub_agent_name = res_data.get("agent", "sub_agent")
                            
                            # Extract sub-agent thoughts
                            sub_thoughts = res_data.get("thoughts", "")
                            if sub_thoughts: thoughts.append(f"[{sub_agent_name}] {sub_thoughts}")
                            
                            # Prefix sub-agent steps with their source for Expert Mode clarity
                            sub_steps = res_data.get("steps", [])
                            sub_tool_calls = [s for s in sub_steps if s.get("type") == "call"]
                            
                            if not sub_tool_calls and res_data.get("response"):
                                # Sub-agent produced a response without calling ANY tool — hallucination signal
                                logger.warning(f"[Router] ⚠️ Sub-agent '{sub_agent_name}' responded with ZERO tool calls.")
                                steps.append({
                                    "type": "warning",
                                    "tool": f"{sub_agent_name}:GUARDRAIL",
                                    "args": {"message": f"[{sub_agent_name}] Aucun outil appelé par le sous-agent. Réponse potentiellement hallucinée."}
                                })
                            
                            for s in sub_steps:
                                prefixed = dict(s)
                                if "tool" in prefixed:
                                    prefixed["tool"] = f"{sub_agent_name}:{prefixed['tool']}"
                                prefixed["source"] = sub_agent_name
                                sig_key = f"sub:{json.dumps(prefixed, sort_keys=True)}"
                                if sig_key not in seen_steps:
                                    steps.append(prefixed)
                                    seen_steps.add(sig_key)
                            
                            sub_use = res_data.get("usage", {})
                            sub_in = sub_use.get("total_input_tokens", 0)
                            sub_out = sub_use.get("total_output_tokens", 0)
                            total_input_tokens += sub_in
                            total_output_tokens += sub_out
                            
                            # Propagate ONLY business data from sub-agent if it exists
                            last_tool_data = res_data.get("data")
                        else:
                            # Normal tool results are business data by definition
                            last_tool_data = res_data
                        
                        sig = f"result:{json.dumps(res_data, sort_keys=True)}"
                        if sig not in seen_steps:
                            steps.append({"type": "result", "data": res_data})
                            seen_steps.add(sig)

            # 2. Text response aggregation
            # We only aggregate text from model role, excluding tool calls and thoughts
            role_val = getattr(event.content, 'role', "").lower() if has_content else ""
            is_assistant = role_val in ["assistant", "model", "assistant_zenika"]
            
            if has_content and is_assistant:
                if isinstance(event.content, str):
                    response_parts.append(event.content)
                elif hasattr(event.content, 'parts'):
                    for part in event.content.parts:
                        if getattr(part, 'text', None) and not getattr(part, 'tool_call', None) and not getattr(part, 'thought', None):
                            response_parts.append(part.text)
            
            # 3. Router Usage tracking (FinOps)
            u = getattr(event.response, 'usage_metadata', None) if hasattr(event, 'response') else getattr(event, 'usage_metadata', None)
            if u:
                it = getattr(u, 'prompt_token_count', 0) or (u.get('prompt_token_count', 0) if isinstance(u, dict) else 0)
                ot = getattr(u, 'candidates_token_count', 0) or (u.get('candidates_token_count', 0) if isinstance(u, dict) else 0)
                # Vul 4: Router tracks its OWN tokens separately for BQ logging
                router_input_tokens = max(router_input_tokens, it)
                router_output_tokens = max(router_output_tokens, ot)
                # Add to cumulative total for the response usage field
                total_input_tokens = max(total_input_tokens, it)

    except ValueError as adk_err:
        # OPS-002 — Interception des erreurs internes ADK liées à l'historique de session.
        # L'erreur "No function call event found for function responses ids: {...}" survient
        # quand la session Redis contient un function_response orphelin (sans function_call
        # correspondant), typiquement après une interruption en mi-stream ou un timeout.
        # Stratégie : logger l'erreur, retourner une réponse dégradée STRUCTURÉE (schema-complète)
        # plutôt que de laisser l'exception remonter et retourner {"response": "Erreur: ...", "source": "error"}
        # qui casse le schema validator des tests et l'UI FinOps.
        error_msg = str(adk_err)
        if "No function call event found" in error_msg:
            logger.warning(
                f"[OPS-002] ADK session history corruption detected for session '{session_id}'. "
                f"Orphaned function_response in Redis history. Error: {error_msg}. "
                "Returning structured degraded response."
            )
            steps.append({
                "type": "warning",
                "tool": "adk_runner:SESSION_CORRUPTION",
                "args": {
                    "message": (
                        "La session contient un historique corrompu (réponse d'outil sans appel correspondant). "
                        "L'historique de session a été préservé mais cette requête n'a pu être traitée. "
                        "Conseil : démarrer une nouvelle session ou effacer l'historique via /history DELETE."
                    ),
                    "technical_detail": error_msg
                }
            })
            response_parts.append(
                "⚠️ Une erreur technique de session s'est produite lors du traitement de votre requête. "
                "L'historique de la session peut être corrompu. "
                "Je vous recommande de rafraîchir la page ou d'effacer l'historique de conversation pour continuer."
            )
        else:
            # Autre ValueError ADK — re-logger et continuer avec ce qu'on a collecté
            logger.error(f"[run_agent_query] Unexpected ADK ValueError for session '{session_id}': {adk_err}")
            response_parts.append(f"⚠️ Erreur inattendue lors du traitement: {error_msg}")

    except Exception as gemini_err:
        # OPS-003 — Interception du dépassement de context window Gemini (400 INVALID_ARGUMENT)
        # Survient quand l'historique de session accumulé dépasse 1M tokens (gemini-3.1-pro-preview).
        # Stratégie : réinitialiser la session Redis pour libérer le contexte, retourner une réponse
        # guidée invitant l'utilisateur à relancer sa question.
        err_str = str(gemini_err)
        if "input token count exceeds" in err_str or "INVALID_ARGUMENT" in err_str:
            logger.warning(
                f"[OPS-003] Gemini context window overflow for session '{session_id}'. "
                f"Session history too long (>1M tokens). Auto-resetting session. Error: {err_str[:200]}"
            )
            # Reset automatique de la session Redis pour éviter que chaque requête suivante échoue
            try:
                session_service_local = get_session_service()
                session_to_delete = await session_service_local.get_session(
                    app_name="zenika_assistant", user_id=user_id, session_id=session_id
                )
                if session_to_delete:
                    session_service_local._delete_session_impl(
                        app_name="zenika_assistant", user_id=user_id, session_id=session_id
                    )
                    logger.info(f"[OPS-003] Session '{session_id}' supprimée après context overflow.")
            except Exception as reset_err:
                logger.warning(f"[OPS-003] Session reset failed (non-critical): {reset_err}")
            steps.append({
                "type": "warning",
                "tool": "adk_runner:CONTEXT_OVERFLOW",
                "args": {
                    "message": "La fenêtre de contexte Gemini a été dépassée. L'historique de conversation a été réinitialisé automatiquement.",
                    "technical_detail": err_str[:300]
                }
            })
            response_parts.append(
                "⚠️ La conversation a atteint la limite de mémoire du modèle IA. "
                "Votre historique de session a été réinitialisé automatiquement. "
                "Vous pouvez relancer votre question — la prochaine requête sera traitée normalement."
            )
        else:
            # Autre exception non interceptée — la remonter pour le global_exception_handler
            raise



    response_text = "".join(response_parts)
    
    # Vul 4: Log ONLY router's own tokens to BigQuery (sub-agents log their own separately)
    if router_input_tokens > 0 or router_output_tokens > 0:
        try:
            # Utiliser le vrai user_id (sub JWT) plutôt que la session_id pour le tracking FinOps
            user_email = user_id if "@" in str(user_id) else f"{user_id}@zenika.com"
            from mcp_client import auth_header_var
            auth_header = auth_header_var.get()
            analytics_url = os.getenv("ANALYTICS_MCP_URL", "http://api.internal.zenika/analytics-mcp/")
            headers = {"Authorization": auth_header} if auth_header else {}
            inject(headers)
            import asyncio
            async def log_bq():
                try:
                    async with httpx.AsyncClient(timeout=10.0, headers=headers) as c:
                        await c.post(f"{analytics_url.rstrip('/')}/mcp/call", json={
                            "name": "log_ai_consumption",
                            "arguments": {
                                "user_email": user_email,
                                "action": "orchestrator_routing",
                                "model": agent.model,
                                "input_tokens": router_input_tokens,
                                "output_tokens": router_output_tokens,
                                "metadata": {"query": query[:100]}
                            }
                        })
                except Exception as e:
                    logger.warning(f"[FinOps] BQ token logging failed (non-critical): {e}")
            asyncio.create_task(log_bq())
        except Exception as e:
            logger.warning(f"[FinOps] Failed to schedule BQ logging task (non-critical): {e}")

    final_result = {
        "response": response_text,
        "thoughts": "\n".join(thoughts),
        "data": last_tool_data,
        "steps": steps,
        "source": "adk_agent",
        "session_id": session_id,
        "usage": {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "estimated_cost_usd": round(total_input_tokens * 0.000000075 + total_output_tokens * 0.0000003, 6)
        }
    }

    return final_result
