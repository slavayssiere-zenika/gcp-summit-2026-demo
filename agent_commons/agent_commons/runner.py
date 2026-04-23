"""
runner.py — Generic ADK agent execution loop shared across all agents.

Extracted from the ``run_agent_query`` functions in agent_hr_api, agent_ops_api,
and agent_missions_api (the stream-processing loop was strictly identical across
all three files).

Key export:
  - run_agent_and_collect(runner, user_id, session_id, query, agent_name, agent_prefix)
      Execute the ADK runner and collect response text, steps, thoughts, and
      token usage from the event stream.
"""

import json
import logging
from typing import Any

from google.genai import types

logger = logging.getLogger(__name__)


async def run_agent_and_collect(
    runner,
    user_id: str,
    session_id: str,
    query: str,
    agent_name: str,
    agent_prefix: str,
) -> tuple[str, list, list, int, int, Any]:
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
          - response_text      (str)   — aggregated model response
          - steps              (list)  — tool calls + results
          - thoughts           (list)  — raw thought strings
          - total_input_tokens (int)
          - total_output_tokens(int)
          - last_tool_data     (Any)   — last tool result payload
    """
    response_parts: list[str] = []
    last_tool_data: Any = None
    steps: list[dict] = []
    seen_steps: set[str] = set()
    thoughts: list[str] = []
    total_input_tokens = 0
    total_output_tokens = 0

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
    return response_text, steps, thoughts, total_input_tokens, total_output_tokens, last_tool_data
