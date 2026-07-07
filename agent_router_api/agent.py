"""
agent.py — Création de l'agent ADK + orchestration de la session Runner.

Ce module expose :
  - get_session_service() : singleton RedisSessionService
  - create_agent()        : construit l'Agent ADK avec système de prompts dynamique
  - run_agent_query()     : exécute une requête via le Runner et retourne un dict structuré

Les outils A2A (ask_hr_agent, ask_ops_agent, ask_missions_agent) et l'infrastructure
de transport HTTP (A2aRequestInterceptor, _call_sub_agent) sont dans ``a2a_tools.py``.
"""

import asyncio
import json
import logging
import os

import httpx  # noqa: F401,F811 — re-exported so tests can patch "agent.httpx.AsyncClient"
from a2a_tools import (  # noqa: F401 — backward-compat re-exports for test patching
    ROUTER_TOOLS, A2aRequestInterceptor, A2ASubAgentError, _call_sub_agent,
    ask_hr_agent, ask_missions_agent, ask_ops_agent, a2a_metadata_var)
from agent_commons.schemas import AgentQueryResponse, TokenUsage
from google.adk.agents import Agent
from google.genai import types
from mcp_client import auth_header_var, user_id_var
# Re-export des métriques pour compatibilité des patches de tests (mocker.patch("agent.A2A_CALL_*"))
from metrics import (A2A_CALL_DURATION, A2A_CALL_ERRORS_TOTAL,  # noqa: F401
                     A2A_CALL_RETRIES_TOTAL)
from opentelemetry.propagate import inject
from prompt_loader import _fetch_prompt_cached, build_instruction_text  # noqa: F401
# ADK v1.28+ WorkflowAgent — SequentialAgent + ParallelAgent (opt-in via ENABLE_WORKFLOW_AGENT)
from workflow_agent import build_workflow_agent
from agent_commons.session import RedisSessionService
from agent_commons.memory import RedisMemoryService
from shared.schemas.agents import AssistantResponse
from workflow_agent import ask_missions_agent_with_hr_alignment
import uuid
from google.adk.runners import Runner
from agent_commons.runner import build_runner_plugins

logger = logging.getLogger(__name__)


_session_service = None
_memory_service = None


def get_session_service():
    global _session_service
    if _session_service is None:
        _session_service = RedisSessionService(
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379/2"),
            redis_key_prefix="adk:sessions"
        )
    return _session_service


def get_memory_service():
    global _memory_service
    if _memory_service is None:
        _memory_service = RedisMemoryService(
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379/2")
        )
    return _memory_service


async def create_agent(session_id: str | None = None, preferred_language: str = "fr"):
    """Construit l'Agent ADK Router avec le prompt système récupéré depuis prompts_api.

    Délègue la construction du prompt à build_instruction_text() (prompt_loader.py)
    pour respecter la limite de 400 lignes (Golden Rule §14).
    """
    auth_header = auth_header_var.get(None)
    instruction_text = await build_instruction_text(
        session_id=session_id,
        auth_header=auth_header,
        preferred_language=preferred_language,
    )

    model = os.getenv("GEMINI_ROUTER_MODEL", os.getenv(
        "GEMINI_MODEL", "gemini-3.5-flash"))

    # ADK v1.28+ WorkflowAgent — Graphe d'États déterministe (opt-in via ENABLE_WORKFLOW_AGENT)
    if os.getenv("ENABLE_WORKFLOW_AGENT", "false").lower() == "true":
        logger.info(
            "[Router] Mode WorkflowAgent activé (StateGraphAgent classifier + router).")
        # Conserver le nom et la docstring d'origine pour que le LLM sache l'invoquer normalement
        ask_missions_agent_with_hr_alignment.__name__ = "ask_missions_agent"
        ask_missions_agent_with_hr_alignment.__doc__ = ask_missions_agent.__doc__

        # Charger dynamiquement le prompt du classificateur depuis Prompts API
        prompts_api_url = os.getenv(
            "PROMPTS_API_URL", "http://prompts_api:8000")
        classifier_prompt_url = f"{prompts_api_url.rstrip('/')}/agent_router_api.classifier/compiled"
        headers = {"Authorization": auth_header} if auth_header else {}
        classifier_instruction = await _fetch_prompt_cached("classifier", classifier_prompt_url, headers)

        return build_workflow_agent(
            hr_tool=ask_hr_agent,
            ops_tool=ask_ops_agent,
            missions_tool=ask_missions_agent_with_hr_alignment,
            classifier_instruction=classifier_instruction,
        )

    # P0 — Structured Output
    output_schema_kwargs = {}
    if os.getenv("ENABLE_OUTPUT_SCHEMA", "false").lower() == "true":
        output_schema_kwargs = {
            "output_schema": AssistantResponse,
            "output_key": "router_result"
        }

    return Agent(
        name="assistant_zenika_router",
        model=model,
        generate_content_config=types.GenerateContentConfig(
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="AUTO")
            ),
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    initial_delay=1, attempts=2),
            )
        ),
        instruction=instruction_text,
        description="Le point d'entrée Frontend de Zenika qui délègue le travail via le protocole A2A.",
        tools=ROUTER_TOOLS,
        **output_schema_kwargs,
    )


async def run_agent_query(
    query: str,
    session_id: str | None = None,
    auth_token: str | None = None,
    user_id: str = "unknown@zenika.com",
    preferred_language: str = "fr",
) -> dict:
    """Exécute une requête via le Runner ADK et retourne un dict structuré.

    auth_token : Bearer token complet ("Bearer eyJ..."). Passé explicitement depuis le
    handler HTTP pour garantir la propagation JWT même quand les coroutines ADK
    s'exécutent dans un contexte asyncio distinct (Runner à événements multiples).
    Sans ce paramètre, auth_header_var peut être None dans ask_missions_agent,
    provocant un 401 lors de l'appel A2A interne.
    """

    # Fix JWT propagation [STAFF-007] — re-setter auth_header_var dans CE contexte asyncio
    if auth_token:
        auth_header_var.set(auth_token)
    if user_id and user_id != "unknown@zenika.com":
        user_id_var.set(user_id)

    session_id = session_id or str(uuid.uuid4())
    session_service = get_session_service()
    memory_service = get_memory_service()

    agent = await create_agent(session_id, preferred_language=preferred_language)
    runner = Runner(
        app_name="zenika_assistant",
        agent=agent,
        session_service=session_service,
        memory_service=memory_service,
        plugins=build_runner_plugins(),
    )

    # P1 — Charger la mémoire
    memory_context = ""
    if memory_service:
        try:
            mem_res = await memory_service.search_memory(app_name="zenika_assistant", user_id=user_id, query=query)
            if mem_res.memories:
                memory_context = "\n".join(
                    [m.content for m in mem_res.memories])
                logger.info(
                    "[Router] [Memory] Loaded %d past turns.", len(mem_res.memories))
        except Exception as e:
            logger.warning("[Router] [Memory] Failed to load memory: %s", e)

    try:
        session = await session_service.get_session(
            app_name="zenika_assistant", user_id=user_id, session_id=session_id
        )
        if session is None:
            raise KeyError("Session not found")
    except Exception as e:
        logger.debug(
            "[agent] Session not found or error (creating new): %s", e)
        await session_service.create_session(
            app_name="zenika_assistant", user_id=user_id, session_id=session_id
        )

    a2a_metadata_var.set([])

    response_parts: list[str] = []
    last_tool_data = None
    steps: list[dict] = []
    seen_steps: set[str] = set()
    thoughts: list[str] = []
    # Hint UI propagé depuis render_ui_widgets des sous-agents
    sub_agent_display_type: str | None = None
    # Vul 4: Router's own Gemini tokens only (for BQ logging) vs cumulative total (for response)
    router_input_tokens = 0
    router_output_tokens = 0
    total_input_tokens = 0
    total_output_tokens = 0
    all_events: list = []
    response_text = ""

    # Construction du message (on injecte la mémoire dans le prompt si présente)
    full_query = query
    if memory_context:
        full_query = f"Context from past interactions:\n{memory_context}\n\nUser Query: {query}"

    new_message = types.Content(
        role="user", parts=[types.Part(text=full_query)])

    try:
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=new_message):
            all_events.append(event)
            # 1. Extraction de l'usage (UsageMetadata est sur chaque event ADK ou son .response)
            u = getattr(event, "usage_metadata", None)
            if u is None and hasattr(event, "response"):
                u = getattr(event.response, "usage_metadata", None)

            if u:
                it = getattr(u, "prompt_token_count", 0) or 0
                ot = getattr(u, "candidates_token_count", 0) or 0
                try:
                    router_input_tokens = max(router_input_tokens, it)
                except TypeError:
                    pass
                try:
                    total_input_tokens = max(total_input_tokens, it)
                except TypeError:
                    pass
                try:
                    router_output_tokens = max(router_output_tokens, ot)
                except TypeError:
                    pass
                try:
                    total_output_tokens = max(total_output_tokens, ot)
                except TypeError:
                    pass

            has_content = hasattr(
                event, "content") and event.content is not None
            if has_content:
                parts = getattr(event.content, "parts", None)
                for part in (list(parts) if parts is not None else []):
                    # a) Thoughts (Gemini 2.0 Thinking support)
                    thought_val = getattr(part, "thought", None)
                    if thought_val:
                        thoughts.append(
                            getattr(part, "text", "") if isinstance(
                                thought_val, bool) else str(thought_val)
                        )

                    # b) Tool Calls (Observe orchestration)
                    tcall = getattr(part, "tool_call", None) or getattr(
                        part, "function_call", None)
                    if tcall:
                        calls = tcall if isinstance(tcall, list) else [tcall]
                        for call in calls:
                            name = getattr(call, "name", "unknown")
                            args = getattr(call, "args", {})
                            sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                            if sig not in seen_steps:
                                steps.append(
                                    {"type": "call", "tool": name, "args": args})
                                seen_steps.add(sig)

                    # c) Tool Results (Aggregate Sub-Agent data)
                    fres = getattr(part, "function_response", None)
                    if fres:
                        res_data = getattr(fres, "response", fres)
                        if hasattr(res_data, "model_dump"):
                            res_data = res_data.model_dump()
                        elif hasattr(res_data, "dict"):
                            res_data = res_data.dict()

                        # Unwrap MCP 'result' JSON string (Crucial for sub-agent data access)
                        if (
                            isinstance(res_data, dict)
                            and "result" in res_data
                            and isinstance(res_data["result"], str)
                            and res_data["result"].startswith("{")
                        ):
                            try:
                                res_data = json.loads(res_data["result"])
                            except Exception as e:
                                logger.warning(
                                    f"Erreur ignorée lors du parsing JSON: {e}")

                        # Aggregate sub-agent metadata if this is an A2A delegation
                        is_a2a = isinstance(
                            res_data, dict) and "response" in res_data
                        if is_a2a:
                            sub_agent_name = res_data.get("agent", "sub_agent")

                            sub_thoughts = res_data.get("thoughts", "")
                            if sub_thoughts:
                                thoughts.append(
                                    f"[{sub_agent_name}] {sub_thoughts}")
                        else:
                            last_tool_data = res_data

                        # Process side-channeled metadata to avoid Context Window Overflow
                        metadata_list = a2a_metadata_var.get()
                        if metadata_list:
                            for meta in metadata_list:
                                meta_agent_name = meta.get(
                                    "agent", "sub_agent")
                                sub_steps = meta.get("steps", [])
                                sub_tool_calls = [
                                    s for s in sub_steps if s.get("type") == "call"]

                                if not sub_tool_calls and is_a2a and res_data.get("response"):
                                    logger.warning(
                                        f"[Router] ⚠️ Sub-agent '{meta_agent_name}' responded with ZERO tool calls."
                                    )
                                    steps.append({
                                        "type": "warning",
                                        "tool": f"{meta_agent_name}:GUARDRAIL",
                                        "args": {
                                            "message": f"[{meta_agent_name}] Aucun outil appelé. "
                                            "Réponse potentiellement hallucinée."
                                        },
                                    })

                                for s in sub_steps:
                                    prefixed = dict(s)
                                    if "tool" in prefixed:
                                        prefixed["tool"] = f"{meta_agent_name}:{prefixed['tool']}"
                                    prefixed["source"] = meta_agent_name
                                    sig_key = f"sub:{json.dumps(prefixed, sort_keys=True)}"
                                    if sig_key not in seen_steps:
                                        steps.append(prefixed)
                                        seen_steps.add(sig_key)

                                sub_use = meta.get("usage", {})
                                total_input_tokens += sub_use.get(
                                    "total_input_tokens", 0)
                                total_output_tokens += sub_use.get(
                                    "total_output_tokens", 0)

                                if meta.get("data") is not None:
                                    last_tool_data = meta.get("data")
                                if meta.get("display_type") and not sub_agent_display_type:
                                    sub_agent_display_type = meta.get(
                                        "display_type")

                            metadata_list.clear()

                        sig = f"result:{json.dumps(res_data, sort_keys=True)}"
                        if sig not in seen_steps:
                            steps.append({"type": "result", "data": res_data})
                            seen_steps.add(sig)

            # Text response aggregation (model role only)
            role_raw = getattr(event.content, "role", "")
            role_val = role_raw.lower() if role_raw is not None else ""
            is_assistant = role_val in [
                "assistant", "model", "assistant_zenika"]

            if has_content and is_assistant:
                if isinstance(event.content, str):
                    response_parts.append(event.content)
                elif getattr(event.content, "parts", None) is not None:
                    for part in event.content.parts:
                        if (
                            getattr(part, "text", None)
                            and not getattr(part, "tool_call", None)
                            and not getattr(part, "thought", None)
                        ):
                            response_parts.append(part.text)

    except ValueError as adk_err:
        # OPS-002 — Session history corruption (orphaned function_response in Redis)
        error_msg = str(adk_err)
        if "No function call event found" in error_msg:
            logger.warning(
                f"[OPS-002] ADK session history corruption for session '{session_id}': {error_msg}"
            )
            steps.append({
                "type": "warning",
                "tool": "adk_runner:SESSION_CORRUPTION",
                "args": {
                    "message": (
                        "La session contient un historique corrompu. "
                        "Conseil : démarrer une nouvelle session ou effacer l'historique."
                    ),
                    "technical_detail": error_msg,
                },
            })
            response_parts.append(
                "⚠️ Une erreur technique de session s'est produite. "
                "Je vous recommande de rafraîchir la page ou d'effacer l'historique."
            )
        else:
            logger.error(
                f"[run_agent_query] Unexpected ADK ValueError for session '{session_id}': {adk_err}")
            response_parts.append(
                f"⚠️ Erreur inattendue lors du traitement: {error_msg}")

    except Exception as gemini_err:
        # OPS-003 — Gemini context window overflow (400 INVALID_ARGUMENT)
        err_str = str(gemini_err)
        if "input token count exceeds" in err_str:
            logger.warning(
                f"[OPS-003] Gemini context window overflow for session '{session_id}'. "
                f"Auto-resetting session. Error: {err_str[:200]}"
            )
            try:
                ss = get_session_service()
                s = await ss.get_session(app_name="zenika_assistant", user_id=user_id, session_id=session_id)
                if s:
                    ss._delete_session_impl(
                        app_name="zenika_assistant", user_id=user_id, session_id=session_id)
                    logger.info(
                        f"[OPS-003] Session '{session_id}' supprimée après context overflow.")
            except Exception as reset_err:
                logger.warning(
                    f"[OPS-003] Session reset failed (non-critical): {reset_err}")
            steps.append({
                "type": "warning",
                "tool": "adk_runner:CONTEXT_OVERFLOW",
                "args": {
                    "message": "La fenêtre de contexte a été dépassée. L'historique a été réinitialisé.",
                    "technical_detail": err_str[:300],
                },
            })
            response_parts.append(
                "⚠️ La conversation a atteint la limite de mémoire du modèle IA. "
                "Votre historique a été réinitialisé. Vous pouvez relancer votre question."
            )
        else:
            raise
    finally:
        # P1 — Sauvegarde en mémoire du tour de conversation
        if memory_service and all_events:
            try:
                await memory_service.add_events_to_memory(
                    app_name="zenika_assistant",
                    user_id=user_id,
                    events=all_events,
                    session_id=session_id
                )
            except Exception as e:
                logger.warning(f"[Router] [Memory] Failed to save memory: {e}")

    # FinOps — log router's own tokens to BigQuery (sub-agents log their own separately)
    if router_input_tokens > 0 or router_output_tokens > 0:
        try:
            user_email = user_id if "@" in str(
                user_id) else f"{user_id}@zenika.com"
            analytics_url = os.getenv(
                "ANALYTICS_MCP_URL", "http://api.internal.zenika/analytics-mcp/")

            # On capture le token explicitement avant create_task pour éviter toute perte de contexte var
            current_token = auth_header_var.get(None) or auth_token

            async def _log_bq(token_to_use: str):
                try:
                    headers = {
                        "Authorization": token_to_use} if token_to_use else {}
                    inject(headers)
                    async with httpx.AsyncClient(timeout=10.0, headers=headers) as c:
                        await c.post(f"{analytics_url.rstrip('/')}/mcp/call", json={
                            "name": "log_ai_consumption",
                            "arguments": {
                                "user_email": user_email,
                                "action": "orchestrator_routing",
                                "model": agent.model,
                                "input_tokens": router_input_tokens,
                                "output_tokens": router_output_tokens,
                                "metadata": {"query": query[:100]},
                            },
                        })
                except Exception as e:
                    logger.warning(
                        f"[FinOps] BQ token logging failed (non-critical): {e}")

            asyncio.create_task(_log_bq(current_token))
        except Exception as e:
            logger.warning(
                f"[FinOps] Failed to schedule BQ logging task (non-critical): {e}")

    response_text = "".join(response_parts)

    # --- ENABLE_OUTPUT_SCHEMA : Extraction du résultat structuré pour le Frontend ---
    if os.getenv("ENABLE_OUTPUT_SCHEMA", "false").lower() == "true":
        try:
            updated_session = await session_service.get_session(
                app_name="zenika_assistant", user_id=user_id, session_id=session_id
            )
            if updated_session and hasattr(updated_session, "state"):
                res = updated_session.state.get("router_result")
                if res:
                    # Conversion AssistantResponse -> AgentQueryResponse
                    response_text = res.get("answer", response_text)
                    sub_agent_display_type = res.get(
                        "display_type", sub_agent_display_type)
                    last_tool_data = res.get("data", last_tool_data)
                    logger.info(
                        "[Router] ✅ Response mapped from AssistantResponse structure.")
        except Exception as e:
            logger.warning(
                f"[Router] Failed to extract AssistantResponse from state: {e}")

    return AgentQueryResponse(
        response=response_text,
        thoughts="\n".join(thoughts),
        data=last_tool_data,
        display_type=sub_agent_display_type,
        steps=steps,
        source="adk_agent",
        session_id=session_id,
        usage=TokenUsage(
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            estimated_cost_usd=round(
                total_input_tokens * 0.000000075 + total_output_tokens * 0.0000003, 6
            ),
        ),
    ).model_dump(exclude_none=False)
