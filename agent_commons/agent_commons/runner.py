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
"""

import json
import logging
import os
from typing import Any

from google.genai import types

logger = logging.getLogger(__name__)

#: Maximum number of tool calls before a TOOL_BUDGET warning step is injected.
#: Configurable at deploy time via the A2A_MAX_TOOL_CALLS environment variable.
MAX_TOOL_CALLS_WARNING: int = int(os.getenv("A2A_MAX_TOOL_CALLS", "12"))


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
    display_type: str | None = None  # Capturé depuis render_ui_widgets ADK

    # P2-2 — Tool budget tracking
    tool_call_count: int = 0
    budget_warning_injected: bool = False

    new_message = types.Content(role="user", parts=[types.Part(text=query)])

    logger.info("%s Starting runner.run_async...", agent_prefix)
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
    ):
        has_content = hasattr(event, "content") and event.content is not None

        if has_content:
            # ----------------------------------------------------------------
            # 1. Exhaustive metadata extraction from parts
            # ----------------------------------------------------------------
            for part in (list(event.content.parts) if hasattr(event.content, "parts") else []):
                # a) Thoughts (Gemini 2.0 Thinking support)
                thought_val = getattr(part, "thought", None)
                if thought_val:
                    thoughts.append(str(thought_val))

                # b) Tool Calls
                tcall = getattr(part, "tool_call", None) or getattr(part, "function_call", None)
                if tcall:
                    calls = tcall if isinstance(tcall, list) else [tcall]
                    for call in calls:
                        name = getattr(call, "name", "unknown")
                        args = getattr(call, "args", {})
                        sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                        if sig not in seen_steps:
                            logger.info("%s Captured Tool Call: %s", agent_prefix, name)
                            steps.append({"type": "call", "tool": name, "args": args})
                            seen_steps.add(sig)
                            # P2-2: increment budget counter per unique tool call
                            tool_call_count += 1
                            if tool_call_count == MAX_TOOL_CALLS_WARNING and not budget_warning_injected:
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
                                            "Risque de context overflow ou de timeout sur la prochaine requête. "
                                            "Synthétisez les résultats actuels plutôt que d'effectuer de nouveaux appels."
                                        ),
                                        "tool_call_count": tool_call_count,
                                        "threshold": MAX_TOOL_CALLS_WARNING,
                                    },
                                })
                                budget_warning_injected = True

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
                        except Exception: raise
                    sig = f"result:{json.dumps(res_data, sort_keys=True)}"
                    if sig not in seen_steps:
                        last_tool_data = res_data
                        steps.append({"type": "result", "data": res_data})
                        seen_steps.add(sig)

        # --------------------------------------------------------------------
        # 1.1 Alternative extraction for some ADK event structures (actions)
        # --------------------------------------------------------------------
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
                    display_type = res_uri[5:]  # ex: "consultants", "profile", "evaluations"
                    logger.info("%s Captured render_ui_widgets: %s", agent_prefix, display_type)

            for action in event.actions:
                tc = getattr(action, "tool_call", None)
                if tc:
                    name = getattr(tc, "name", "unknown")
                    args = getattr(tc, "args", {})
                    sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                    if sig not in seen_steps:
                        logger.info("%s Captured Tool Call (actions): %s", agent_prefix, name)
                        steps.append({"type": "call", "tool": name, "args": args})
                        seen_steps.add(sig)

        if hasattr(event, "get_function_calls"):
            for fc in (event.get_function_calls() or []):
                name = getattr(fc, "name", "unknown")
                args = getattr(fc, "args", {})
                sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                if sig not in seen_steps:
                    steps.append({"type": "call", "tool": name, "args": args})
                    seen_steps.add(sig)

        # --------------------------------------------------------------------
        # 2. Text response aggregation (model role only, no thoughts/tool calls)
        # --------------------------------------------------------------------
        role_val = getattr(event.content, "role", "").lower() if has_content else ""
        is_assistant = role_val in ["assistant", "model", f"assistant_zenika_{agent_name}"]

        if has_content and is_assistant:
            if isinstance(event.content, str):
                response_parts.append(event.content)
            elif hasattr(event.content, "parts"):
                for part in event.content.parts:
                    if (
                        getattr(part, "text", None)
                        and not getattr(part, "tool_call", None)
                        and not getattr(part, "thought", None)
                    ):
                        response_parts.append(part.text)

        # --------------------------------------------------------------------
        # 3. Usage tracking (FinOps)
        # --------------------------------------------------------------------
        u = (
            getattr(event.response, "usage_metadata", None)
            if hasattr(event, "response")
            else getattr(event, "usage_metadata", None)
        )
        if u:
            it = getattr(u, "prompt_token_count", 0) or (u.get("prompt_token_count", 0) if isinstance(u, dict) else 0)
            ot = getattr(u, "candidates_token_count", 0) or (u.get("candidates_token_count", 0) if isinstance(u, dict) else 0)
            total_input_tokens = max(total_input_tokens, it)
            total_output_tokens = max(total_output_tokens, ot)

    if tool_call_count > 0:
        logger.info(
            "%s run_agent_and_collect completed: %d tool calls, budget_warning=%s",
            agent_prefix, tool_call_count, budget_warning_injected,
        )

    response_text = "".join(response_parts)
    return response_text, steps, thoughts, total_input_tokens, total_output_tokens, last_tool_data, display_type

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
    display_type: str | None = None  # Capturé depuis render_ui_widgets ADK

    new_message = types.Content(role="user", parts=[types.Part(text=query)])

    logger.info("%s Starting runner.run_async...", agent_prefix)
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
    ):
        has_content = hasattr(event, "content") and event.content is not None

        if has_content:
            # ----------------------------------------------------------------
            # 1. Exhaustive metadata extraction from parts
            # ----------------------------------------------------------------
            for part in (list(event.content.parts) if hasattr(event.content, "parts") else []):
                # a) Thoughts (Gemini 2.0 Thinking support)
                thought_val = getattr(part, "thought", None)
                if thought_val:
                    thoughts.append(str(thought_val))

                # b) Tool Calls
                tcall = getattr(part, "tool_call", None) or getattr(part, "function_call", None)
                if tcall:
                    calls = tcall if isinstance(tcall, list) else [tcall]
                    for call in calls:
                        name = getattr(call, "name", "unknown")
                        args = getattr(call, "args", {})
                        sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                        if sig not in seen_steps:
                            logger.info("%s Captured Tool Call: %s", agent_prefix, name)
                            steps.append({"type": "call", "tool": name, "args": args})
                            seen_steps.add(sig)

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
                        except Exception: raise
                    sig = f"result:{json.dumps(res_data, sort_keys=True)}"
                    if sig not in seen_steps:
                        last_tool_data = res_data
                        steps.append({"type": "result", "data": res_data})
                        seen_steps.add(sig)

        # --------------------------------------------------------------------
        # 1.1 Alternative extraction for some ADK event structures (actions)
        # --------------------------------------------------------------------
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
                    display_type = res_uri[5:]  # ex: "consultants", "profile", "evaluations"
                    logger.info("%s Captured render_ui_widgets: %s", agent_prefix, display_type)

            for action in event.actions:
                tc = getattr(action, "tool_call", None)
                if tc:
                    name = getattr(tc, "name", "unknown")
                    args = getattr(tc, "args", {})
                    sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                    if sig not in seen_steps:
                        logger.info("%s Captured Tool Call (actions): %s", agent_prefix, name)
                        steps.append({"type": "call", "tool": name, "args": args})
                        seen_steps.add(sig)

        if hasattr(event, "get_function_calls"):
            for fc in (event.get_function_calls() or []):
                name = getattr(fc, "name", "unknown")
                args = getattr(fc, "args", {})
                sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                if sig not in seen_steps:
                    steps.append({"type": "call", "tool": name, "args": args})
                    seen_steps.add(sig)

        # --------------------------------------------------------------------
        # 2. Text response aggregation (model role only, no thoughts/tool calls)
        # --------------------------------------------------------------------
        role_val = getattr(event.content, "role", "").lower() if has_content else ""
        is_assistant = role_val in ["assistant", "model", f"assistant_zenika_{agent_name}"]

        if has_content and is_assistant:
            if isinstance(event.content, str):
                response_parts.append(event.content)
            elif hasattr(event.content, "parts"):
                for part in event.content.parts:
                    if (
                        getattr(part, "text", None)
                        and not getattr(part, "tool_call", None)
                        and not getattr(part, "thought", None)
                    ):
                        response_parts.append(part.text)

        # --------------------------------------------------------------------
        # 3. Usage tracking (FinOps)
        # --------------------------------------------------------------------
        u = (
            getattr(event.response, "usage_metadata", None)
            if hasattr(event, "response")
            else getattr(event, "usage_metadata", None)
        )
        if u:
            it = getattr(u, "prompt_token_count", 0) or (u.get("prompt_token_count", 0) if isinstance(u, dict) else 0)
            ot = getattr(u, "candidates_token_count", 0) or (u.get("candidates_token_count", 0) if isinstance(u, dict) else 0)
            total_input_tokens = max(total_input_tokens, it)
            total_output_tokens = max(total_output_tokens, ot)

    response_text = "".join(response_parts)
    return response_text, steps, thoughts, total_input_tokens, total_output_tokens, last_tool_data, display_type
