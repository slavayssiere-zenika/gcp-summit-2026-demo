"""
runner.py — Generic ADK agent execution loop shared across all agents.

Extracted from the ``run_agent_query`` functions in agent_hr_api, agent_ops_api,
and agent_missions_api (the stream-processing loop was strictly identical across
all three files).

Key export:
  - run_agent_and_collect(runner, user_id, session_id, query, agent_name, agent_prefix)
      Execute the ADK runner and collect response text, steps, thoughts, and
      token usage from the event stream.

Constants:
  - MAX_TOOL_CALLS_WARNING  (int, env: A2A_MAX_TOOL_CALLS, default 12)
      When the number of distinct tool calls in a single run reaches this
      threshold, a ``TOOL_BUDGET`` warning step is appended.  This does NOT
      stop execution — it acts as an early-warning signal visible in Expert
      Mode and FinOps dashboards.

OTel Tracing (ADK Reasoning Observability):
  Each call to ``run_agent_and_collect`` produces an ``agent.<name>.run`` span.
  Within it:
    - LLM thoughts  → events  ``agent.thought``     on the parent span
    - Tool calls    → child spans ``agent.tool_call:<tool_name>``  (opened on call)
    - Tool results  → close the matching child span (or a fallback after the loop)

  When no exporter is configured (``OTEL_TRACES_EXPORTER=none`` in local/mock
  environments), OpenTelemetry produces no-op spans with zero overhead and zero
  network calls.  The instrumentation is therefore unconditional and safe everywhere.

AutoTracingPlugin (ADK 2.2+):
  ``build_runner_plugins()`` retourne une liste de plugins ADK à injecter dans
  ``Runner(plugins=...)``.  Elle active le ``AutoTracingPlugin`` natif ADK qui
  instrumente automatiquement par monkey-patching toutes les fonctions Python
  accessibles depuis l'InvocationContext (agent, tools, MCP clients…).

  Le plugin est no-op automatique quand le tracer OTel est un ``NoOpTracer``
  (ex: ``OTEL_TRACES_EXPORTER=none`` en local) — aucun overhead, aucun effet
  de bord.  Il coexiste avec le traçage custom de ``run_agent_and_collect``
  (spans ``agent.<name>.run`` + child spans ``agent.tool_call:*``) en
  produisant en complément des spans au niveau fonction pour le debugging fin.

  Activation contrôlée par la variable d'environnement :
    ADK_AUTO_TRACING=true  (défaut : false — opt-in explicite)
  Cette variable protège contre tout overhead inattendu en pré-prod.
"""

import json
import logging
import os
from typing import Any, List

try:
    from google.adk.plugins.auto_tracing_plugin import AutoTracingPlugin
    HAS_AUTO_TRACING = True
except ImportError:
    HAS_AUTO_TRACING = False

from google.adk.plugins.base_plugin import BasePlugin
from google.adk.events import Event
from google.genai import types
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)

# Tracer partagé pour toutes les exécutions ADK.
# En local (OTEL_TRACES_EXPORTER=none), ce tracer produit des no-op spans :
# aucun overhead, aucun effet de bord, aucun appel réseau.
_tracer = trace.get_tracer("agent_commons.runner")

# Longueur maximale des attributs de spans pour éviter les rejets des exportateurs OTel.
# Cloud Trace impose une limite de 256 caractères sur les attributs de type string.
_SPAN_ATTR_MAX_LEN: int = int(os.getenv("AGENT_OTEL_ATTR_MAX_LEN", "512"))

#: Maximum number of tool calls before a TOOL_BUDGET warning step is injected.
#: Configurable at deploy time via the A2A_MAX_TOOL_CALLS environment variable.
MAX_TOOL_CALLS_WARNING: int = int(os.getenv("A2A_MAX_TOOL_CALLS", "12"))


def build_runner_plugins() -> List[BasePlugin]:
    """Construit la liste de plugins ADK à injecter dans Runner(plugins=...).

    Active ``AutoTracingPlugin`` (ADK 2.2+) si la variable d'environnement
    ``ADK_AUTO_TRACING=true`` est définie.  Le plugin instrumente par
    monkey-patching toutes les fonctions Python accessibles depuis l'agent
    (tools, MCP clients, guardrails…) avec des spans OTel.

    Comportement en environnement sans exporteur OTel
    (``OTEL_TRACES_EXPORTER=none``) : le plugin détecte un ``NoOpTracer``
    et ne modifie aucune fonction — zéro overhead, zéro effet de bord.

    Returns:
        Liste (possiblement vide) de ``BasePlugin`` à passer au ``Runner``.
    """
    plugins: List[BasePlugin] = []
    if os.getenv("ADK_AUTO_TRACING", "false").lower() == "true":
        if HAS_AUTO_TRACING:
            logger.info(
                "[runner] AutoTracingPlugin activé (ADK_AUTO_TRACING=true) — "
                "instrumentation OTel auto des fonctions agent en scope."
            )
            plugins.append(AutoTracingPlugin())
        else:
            logger.warning(
                "[runner] ADK_AUTO_TRACING=true demandé mais AutoTracingPlugin est "
                "introuvable dans cette version de google-adk. Instrumentation auto ignorée."
            )
    return plugins


async def run_agent_and_collect(
    runner,
    user_id: str,
    session_id: str,
    query: str,
    agent_name: str,
    agent_prefix: str,
) -> tuple[str, list, list, int, int, Any, str | None]:
    """Execute the ADK runner and collect structured output from the event stream.

    This is the core event-processing loop that was duplicated verbatim in all
    three agent.py files.  It processes ``runner.run_async()`` events and:

      1. Extracts thoughts (Gemini 2.0 Thinking mode).
      2. Captures tool calls and their results (steps).
      3. Aggregates final response text from the model role.
      4. Tracks input / output token counts for FinOps.
      5. Injects a TOOL_BUDGET warning step when MAX_TOOL_CALLS_WARNING is reached.

    OTel tracing: each call produces an ``agent.<name>.run`` span.
      - LLM thoughts      → ``agent.thought`` events on the run span
      - tool_calls        → child spans ``agent.tool_call:<name>`` (opened on call)
      - function_response → closes the matching child span

    Args:
        runner:       Google ADK ``Runner`` instance (already initialised).
        user_id:      User identifier propagated from the JWT sub.
        session_id:   Ephemeral session UUID (generated per-request).
        query:        Raw user query string.
        agent_name:   ADK app_name (e.g. ``"zenika_hr_assistant"``).
        agent_prefix: Log prefix (e.g. ``"[HR]"``).

    Returns:
        Tuple of:
          - response_text      (str)        — aggregated model response
          - steps              (list)       — tool calls + results
          - thoughts           (list)       — raw thought strings
          - total_input_tokens (int)
          - total_output_tokens(int)
          - last_tool_data     (Any)        — last tool result payload
          - display_type       (str | None) — ui:// widget slug emitted via render_ui_widgets
    """
    response_parts: list[str] = []
    last_tool_data: Any = None
    steps: list[dict] = []
    seen_steps: set[str] = set()
    thoughts: list[str] = []
    total_input_tokens = 0
    total_output_tokens = 0
    display_type: str | None = None

    # P1 — Support de la mémoire Redis
    memory_service = getattr(runner, "memory", None)
    memory_context = ""
    if memory_service and hasattr(memory_service, "search_memory"):
        try:
            mem_res = await memory_service.search_memory(app_name=agent_name, user_id=user_id, query=query)
            if mem_res.memories:
                memory_context = "\n".join(
                    [m.content for m in mem_res.memories])
                logger.info("%s [Memory] Loaded %d past turns.",
                            agent_prefix, len(mem_res.memories))
        except Exception as e:
            logger.warning(
                "%s [Memory] Failed to load memory: %s", agent_prefix, e)

    # P2-2 — Tool budget tracking
    tool_call_count: int = 0
    budget_warning_injected: bool = False

    # OTel — child spans ouverts par tool_call, fermés à la function_response.
    _active_tool_spans: dict[str, Any] = {}

    # Événements capturés pour la mémoire en fin de run (P1)
    all_events: List[Event] = []

    # Construction du message (on injecte la mémoire dans le prompt si présente)
    full_query = query
    if memory_context:
        full_query = f"Context from past interactions:\n{memory_context}\n\nUser Query: {query}"

    new_message = types.Content(
        role="user", parts=[types.Part(text=full_query)])

    span_name = f"agent.{agent_name}.run"
    with _tracer.start_as_current_span(span_name) as run_span:
        run_span.set_attribute("agent.name", agent_name)
        run_span.set_attribute("agent.user_id", user_id)
        run_span.set_attribute("agent.session_id", session_id)
        run_span.set_attribute("agent.query", query[:_SPAN_ATTR_MAX_LEN])

        logger.info("%s Starting runner.run_async...", agent_prefix)
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
            ):
                all_events.append(event)
                # 1. Extraction de l'usage (UsageMetadata est sur chaque event ADK ou son .response)
                u = getattr(event, "usage_metadata", None)
                if u is None and hasattr(event, "response"):
                    u = getattr(event.response, "usage_metadata", None)

                if u:
                    it = getattr(u, "prompt_token_count", 0) or 0
                    ot = getattr(u, "candidates_token_count", 0) or 0
                    if isinstance(it, int):
                        total_input_tokens = max(total_input_tokens, it)
                    if isinstance(ot, int):
                        total_output_tokens = max(total_output_tokens, ot)

                has_content = hasattr(
                    event, "content") and event.content is not None

                # ----------------------------------------------------------------
                # 1. Exhaustive metadata extraction from parts
                # ----------------------------------------------------------------
                if has_content:
                    parts = getattr(event.content, "parts", None)
                    for part in (list(parts) if parts is not None else []):
                        # a) Thoughts (Gemini 2.0 Thinking support)
                        thought_val = getattr(part, "thought", None)
                        if thought_val:
                            thoughts.append(str(thought_val))
                            # OTel — pensée LLM enregistrée comme événement sur le span run
                            run_span.add_event(
                                "agent.thought",
                                {"thought": str(thought_val)[
                                    :_SPAN_ATTR_MAX_LEN]},
                            )

                        # b) Tool Calls
                        tcall = getattr(part, "tool_call", None) or getattr(
                            part, "function_call", None)
                        if tcall:
                            calls = tcall if isinstance(
                                tcall, list) else [tcall]
                            for call in calls:
                                name = getattr(call, "name", "unknown")
                                args = getattr(call, "args", {})
                                sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                                if sig not in seen_steps:
                                    logger.info(
                                        "%s Captured Tool Call: %s", agent_prefix, name)
                                    steps.append(
                                        {"type": "call", "tool": name, "args": args})
                                    seen_steps.add(sig)
                                    # P2-2: budget counter
                                    tool_call_count += 1
                                    if (
                                        tool_call_count == MAX_TOOL_CALLS_WARNING
                                        and not budget_warning_injected
                                    ):
                                        logger.warning(
                                            "%s ⚠️ TOOL_BUDGET: %d tool calls reached (threshold=%d). "
                                            "Risk of context overflow or timeout.",
                                            agent_prefix, tool_call_count, MAX_TOOL_CALLS_WARNING,
                                        )
                                        steps.append({
                                            "type": "warning",
                                            "tool": "TOOL_BUDGET",
                                            "args": {
                                                "message": (
                                                    f"Limite de {MAX_TOOL_CALLS_WARNING} appels d'outils atteinte. "
                                                    "Risque de context overflow ou de timeout. "
                                                    "Synthétisez les résultats actuels plutôt "
                                                    "que d'effectuer de nouveaux appels."
                                                ),
                                                "tool_call_count": tool_call_count,
                                                "threshold": MAX_TOOL_CALLS_WARNING,
                                            },
                                        })
                                        budget_warning_injected = True
                                    # OTel — ouvre un child span pour cet appel d'outil
                                    tool_span = _tracer.start_span(
                                        f"agent.tool_call:{name}")
                                    tool_span.set_attribute("tool.name", name)
                                    args_str = json.dumps(
                                        args, sort_keys=True, default=str)
                                    tool_span.set_attribute(
                                        "tool.args", args_str[:_SPAN_ATTR_MAX_LEN])
                                    _active_tool_spans[name] = tool_span

                        # c) Tool Results
                        fres = getattr(part, "function_response", None)
                        if fres:
                            res_data = getattr(fres, "response", fres)
                            if hasattr(res_data, "model_dump"):
                                res_data = res_data.model_dump()
                            elif hasattr(res_data, "dict"):
                                res_data = res_data.dict()
                            # Unwrap MCP 'result' JSON string
                            if (
                                isinstance(res_data, dict)
                                and "result" in res_data
                                and isinstance(res_data["result"], str)
                                and res_data["result"].startswith("{")
                            ):
                                try:
                                    res_data = json.loads(res_data["result"])
                                except Exception:
                                    raise
                            sig = f"result:{json.dumps(res_data, sort_keys=True)}"
                            if sig not in seen_steps:
                                last_tool_data = res_data
                                steps.append(
                                    {"type": "result", "data": res_data})
                                seen_steps.add(sig)
                                # OTel — ferme le child span de l'outil correspondant
                                res_tool_name = getattr(fres, "name", None)
                                if res_tool_name and res_tool_name in _active_tool_spans:
                                    ts = _active_tool_spans.pop(res_tool_name)
                                    res_str = json.dumps(res_data, default=str)[
                                        :_SPAN_ATTR_MAX_LEN]
                                    ts.set_attribute("tool.result", res_str)
                                    ts.set_status(Status(StatusCode.OK))
                                    ts.end()
                                elif not res_tool_name and _active_tool_spans:
                                    # Fermeture de tous les spans orphelins (fres sans nom)
                                    for ts in list(_active_tool_spans.values()):
                                        ts.set_status(Status(StatusCode.OK))
                                        ts.end()
                                    _active_tool_spans.clear()

                # ----------------------------------------------------------------
                # 1.1 Alternative extraction for some ADK event structures (actions)
                # ----------------------------------------------------------------
                if hasattr(event, "actions") and event.actions:
                    # Capture render_ui_widgets → display_type hint for A2A propagation
                    widgets = (
                        getattr(event.actions, "render_ui_widgets", None)
                        or getattr(event.actions, "renderUiWidgets", None)
                        or []
                    )
                    for widget in (widgets or []):
                        payload = getattr(widget, "payload", {}) or {}
                        res_uri = payload.get("resource_uri", "")
                        if res_uri.startswith("ui://"):
                            # ex: "consultants", "profile", "evaluations"
                            display_type = res_uri[5:]
                            logger.info(
                                "%s Captured render_ui_widgets: %s", agent_prefix, display_type)

                    for action in event.actions:
                        tc = getattr(action, "tool_call", None)
                        if tc:
                            name = getattr(tc, "name", "unknown")
                            args = getattr(tc, "args", {})
                            sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                            if sig not in seen_steps:
                                logger.info(
                                    "%s Captured Tool Call (actions): %s", agent_prefix, name)
                                steps.append(
                                    {"type": "call", "tool": name, "args": args})
                                seen_steps.add(sig)

                if hasattr(event, "get_function_calls"):
                    for fc in (event.get_function_calls() or []):
                        name = getattr(fc, "name", "unknown")
                        args = getattr(fc, "args", {})
                        sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                        if sig not in seen_steps:
                            steps.append(
                                {"type": "call", "tool": name, "args": args})
                            seen_steps.add(sig)

                # ----------------------------------------------------------------
                # 2. Text response aggregation (model role only, no thoughts/tool calls)
                # ----------------------------------------------------------------
                role_raw = getattr(event.content, "role",
                                   "") if has_content else ""
                role_val = role_raw.lower() if role_raw is not None else ""
                is_assistant = role_val in [
                    "assistant", "model", f"assistant_zenika_{agent_name}"]

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

        finally:
            # P1 — Sauvegarde en mémoire du tour de conversation
            if memory_service and hasattr(memory_service, "add_events_to_memory") and all_events:
                try:
                    await memory_service.add_events_to_memory(
                        app_name=agent_name,
                        user_id=user_id,
                        events=all_events,
                        session_id=session_id
                    )
                except Exception as e:
                    logger.warning(
                        "%s [Memory] Failed to save memory: %s", agent_prefix, e)

            # OTel — ferme tous les child spans d'outils encore ouverts (ex: timeout)
            for ts in list(_active_tool_spans.values()):
                ts.set_status(
                    Status(StatusCode.ERROR, "span closed without response"))
                ts.end()
            _active_tool_spans.clear()

        # OTel — attributs de synthèse sur le span run (exécutés seulement si pas d'exception)
        run_span.set_attribute("agent.tool_call_count", tool_call_count)
        run_span.set_attribute("agent.thought_count", len(thoughts))
        run_span.set_attribute("agent.total_input_tokens", total_input_tokens)
        run_span.set_attribute(
            "agent.total_output_tokens", total_output_tokens)
        run_span.set_attribute("agent.budget_warning", budget_warning_injected)
        run_span.set_status(Status(StatusCode.OK))

    if tool_call_count > 0:
        logger.info(
            "%s run_agent_and_collect completed: %d tool calls, budget_warning=%s",
            agent_prefix, tool_call_count, budget_warning_injected,
        )

    response_text = "".join(response_parts)
    return response_text, steps, thoughts, total_input_tokens, total_output_tokens, last_tool_data, display_type
