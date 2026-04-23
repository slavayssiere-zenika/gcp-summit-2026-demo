"""
metadata.py — ADK session metadata extractor shared across all agents.

Extracted from agent_missions_api/metadata.py (cleanest version).
Functionally identical to agent_hr_api and agent_ops_api variants (cosmetic
differences only).
"""

import json


def safe_get(obj, key, default=None):
    """Robustly fetch from both object attributes and dictionary keys."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def extract_metadata_from_session(session) -> dict:
    """Exhaustively parse history events to extract steps, thoughts, and data.

    Ensures consistency between live queries and history endpoints, even after
    Redis reload.

    Returns:
        dict with keys ``steps``, ``thoughts`` (str), and ``data``.
    """
    steps = []
    seen_steps: set = set()
    thoughts = []
    last_tool_data = None

    events = safe_get(session, "events", [])

    for event in events:
        content = safe_get(event, "content")
        parts = safe_get(content, "parts", [])
        if not isinstance(parts, list):
            parts = [parts]

        # 1. Capture Thoughts (Gemini 2.0 Thinking support)
        for part in parts:
            thought_val = safe_get(part, "thought")
            if thought_val:
                text = ""
                # Handle boolean flag vs text value
                if isinstance(thought_val, bool) and thought_val:
                    text = safe_get(part, "text", "")
                else:
                    text = str(thought_val)
                if text:
                    thoughts.append(text)

        # 2. Capture Tool Calls (Steps)
        for part in parts:
            tcall = (
                safe_get(part, "tool_call")
                or safe_get(part, "function_call")
                or safe_get(part, "call")
            )
            ecode = safe_get(part, "executable_code") or safe_get(part, "code")

            if tcall:
                calls = tcall if isinstance(tcall, list) else [tcall]
                for call in calls:
                    name = safe_get(call, "name", "unknown")
                    args = safe_get(call, "args", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception: raise
                    sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                    if sig not in seen_steps:
                        steps.append({"type": "call", "tool": name, "args": args})
                        seen_steps.add(sig)

            if ecode:
                code_text = safe_get(ecode, "code", str(ecode))
                sig = f"code:{code_text}"
                if sig not in seen_steps:
                    steps.append({"type": "code_execution", "code": code_text})
                    seen_steps.add(sig)

        # Structure alternative (actions)
        actions = safe_get(event, "actions", [])
        for action in actions:
            tc = safe_get(action, "tool_call")
            if tc:
                name = safe_get(tc, "name", "unknown")
                args = safe_get(tc, "args", {})
                sig = f"call:{name}:{json.dumps(args, sort_keys=True)}"
                if sig not in seen_steps:
                    steps.append({"type": "call", "tool": name, "args": args})
                    seen_steps.add(sig)

        # 3. Capture Tool Results
        for part in parts:
            fres = safe_get(part, "function_response") or safe_get(part, "result")
            if fres:
                res_data = safe_get(fres, "response", fres)
                if hasattr(res_data, "model_dump"):
                    res_data = res_data.model_dump()
                elif hasattr(res_data, "dict"):
                    res_data = res_data.dict()
                # Unwrap MCP 'result' string
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

    return {
        "steps": steps,
        "thoughts": "\n".join(thoughts),
        "data": last_tool_data,
    }
