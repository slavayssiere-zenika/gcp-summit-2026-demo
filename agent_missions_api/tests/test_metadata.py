"""
test_metadata.py — Couverture complète de metadata.py (0% → cible 100%).

Branches testées :
  - safe_get : obj=None, dict, objet avec attribut
  - extract_metadata_from_session :
    * Session vide / sans events
    * Thoughts (Gemini 2.0 : thought=True + texte, thought=str)
    * Tool calls (function_call, tool_call, call)
    * Déduplication des steps (sig identique ignoré)
    * Executable code
    * Actions alternatives (event.actions[].tool_call)
    * Tool results (function_response / result)
    * Unwrap MCP result JSON-string
    * model_dump / dict sur res_data
"""
import json

import pytest

from agent_commons.metadata import extract_metadata_from_session, safe_get


# ── safe_get ──────────────────────────────────────────────────────────────────

def test_safe_get_none_obj():
    assert safe_get(None, "key") is None
    assert safe_get(None, "key", "default") == "default"


def test_safe_get_dict():
    assert safe_get({"a": 1}, "a") == 1
    assert safe_get({"a": 1}, "missing", 99) == 99


def test_safe_get_object_attribute():
    class Obj:
        name = "zenika"

    assert safe_get(Obj(), "name") == "zenika"
    assert safe_get(Obj(), "absent", "fallback") == "fallback"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_event(parts=None, actions=None):
    """Construit un event dict minimaliste."""
    event = {}
    if parts is not None:
        event["content"] = {"parts": parts}
    if actions is not None:
        event["actions"] = actions
    return event


def _make_session(events):
    return {"events": events}


# ── Session vide ──────────────────────────────────────────────────────────────

def test_empty_session():
    result = extract_metadata_from_session(_make_session([]))
    assert result["steps"] == []
    assert result["thoughts"] == ""
    assert result["data"] is None


def test_session_none():
    result = extract_metadata_from_session(None)
    assert result["steps"] == []
    assert result["thoughts"] == ""
    assert result["data"] is None


def test_session_no_content():
    result = extract_metadata_from_session(_make_session([{}]))
    assert result["steps"] == []


# ── Thoughts ──────────────────────────────────────────────────────────────────

def test_thought_bool_true_extracts_text():
    """Gemini 2.0 Thinking : thought=True + text sur la même part."""
    event = _make_event(parts=[{"thought": True, "text": "Je réfléchis..."}])
    result = extract_metadata_from_session(_make_session([event]))
    assert "Je réfléchis..." in result["thoughts"]


def test_thought_string_value():
    """thought peut être une string directement."""
    event = _make_event(parts=[{"thought": "Analyse de la mission"}])
    result = extract_metadata_from_session(_make_session([event]))
    assert "Analyse de la mission" in result["thoughts"]


def test_thought_false_ignored():
    """thought=False ne doit rien ajouter."""
    event = _make_event(parts=[{"thought": False, "text": "Invisible"}])
    result = extract_metadata_from_session(_make_session([event]))
    assert result["thoughts"] == ""


def test_multiple_thoughts_joined():
    parts = [
        {"thought": True, "text": "Pensée 1"},
        {"thought": True, "text": "Pensée 2"},
    ]
    result = extract_metadata_from_session(_make_session([_make_event(parts=parts)]))
    assert "Pensée 1" in result["thoughts"]
    assert "Pensée 2" in result["thoughts"]


# ── Tool Calls ─────────────────────────────────────────────────────────────────

def test_function_call_captured():
    part = {"function_call": {"name": "list_missions", "args": {"skip": 0}}}
    result = extract_metadata_from_session(_make_session([_make_event(parts=[part])]))
    assert len(result["steps"]) == 1
    assert result["steps"][0]["type"] == "call"
    assert result["steps"][0]["tool"] == "list_missions"
    assert result["steps"][0]["args"] == {"skip": 0}


def test_tool_call_captured():
    part = {"tool_call": {"name": "get_mission", "args": {"mission_id": 42}}}
    result = extract_metadata_from_session(_make_session([_make_event(parts=[part])]))
    assert result["steps"][0]["tool"] == "get_mission"


def test_call_field_captured():
    part = {"call": {"name": "reanalyze_mission", "args": {}}}
    result = extract_metadata_from_session(_make_session([_make_event(parts=[part])]))
    assert result["steps"][0]["tool"] == "reanalyze_mission"


def test_args_as_json_string_is_parsed():
    """Si args est une string JSON, elle doit être parsée en dict."""
    args_str = json.dumps({"mission_id": 7})
    part = {"function_call": {"name": "get_mission", "args": args_str}}
    result = extract_metadata_from_session(_make_session([_make_event(parts=[part])]))
    assert result["steps"][0]["args"] == {"mission_id": 7}


def test_tool_call_list_multiple():
    """tcall peut être une liste de calls."""
    calls = [
        {"name": "list_missions", "args": {}},
        {"name": "get_mission", "args": {"mission_id": 1}},
    ]
    part = {"tool_call": calls}
    result = extract_metadata_from_session(_make_session([_make_event(parts=[part])]))
    tools = [s["tool"] for s in result["steps"]]
    assert "list_missions" in tools
    assert "get_mission" in tools


def test_deduplication_same_sig_ignored():
    """Deux events identiques → un seul step."""
    part = {"function_call": {"name": "list_missions", "args": {}}}
    events = [_make_event(parts=[part]), _make_event(parts=[part])]
    result = extract_metadata_from_session(_make_session(events))
    assert len(result["steps"]) == 1


# ── Executable Code ───────────────────────────────────────────────────────────

def test_executable_code_captured():
    part = {"executable_code": {"code": "print('hello')"}}
    result = extract_metadata_from_session(_make_session([_make_event(parts=[part])]))
    assert result["steps"][0]["type"] == "code_execution"
    assert result["steps"][0]["code"] == "print('hello')"


def test_code_field_fallback():
    """code peut être dans part.code (pas executable_code)."""
    part = {"code": {"code": "1+1"}}
    result = extract_metadata_from_session(_make_session([_make_event(parts=[part])]))
    assert result["steps"][0]["type"] == "code_execution"


def test_executable_code_deduplication():
    part = {"executable_code": {"code": "x = 1"}}
    events = [_make_event(parts=[part]), _make_event(parts=[part])]
    result = extract_metadata_from_session(_make_session(events))
    code_steps = [s for s in result["steps"] if s["type"] == "code_execution"]
    assert len(code_steps) == 1


# ── Actions (structure alternative) ───────────────────────────────────────────

def test_actions_tool_call_captured():
    """event.actions[].tool_call → capturé comme step 'call'."""
    actions = [{"tool_call": {"name": "search_best_candidates", "args": {"query": "python"}}}]
    event = _make_event(actions=actions)
    result = extract_metadata_from_session(_make_session([event]))
    assert result["steps"][0]["type"] == "call"
    assert result["steps"][0]["tool"] == "search_best_candidates"


def test_actions_without_tool_call_ignored():
    actions = [{"other_field": "value"}]
    event = _make_event(actions=actions)
    result = extract_metadata_from_session(_make_session([event]))
    assert result["steps"] == []


# ── Tool Results ──────────────────────────────────────────────────────────────

def test_function_response_captured():
    part = {"function_response": {"response": {"missions": [{"id": 1}]}}}
    result = extract_metadata_from_session(_make_session([_make_event(parts=[part])]))
    assert result["steps"][0]["type"] == "result"
    assert result["data"] == {"missions": [{"id": 1}]}


def test_result_field_fallback():
    part = {"result": {"response": {"count": 5}}}
    result = extract_metadata_from_session(_make_session([_make_event(parts=[part])]))
    assert result["steps"][0]["type"] == "result"


def test_mcp_result_json_string_unwrapped():
    """Unwrap MCP 'result' JSON-string encapsulé."""
    inner = json.dumps({"missions": [{"id": 99}]})
    part = {"function_response": {"response": {"result": inner}}}
    result = extract_metadata_from_session(_make_session([_make_event(parts=[part])]))
    assert result["data"] == {"missions": [{"id": 99}]}


def test_result_non_json_string_not_unwrapped():
    """Si result est une string non-JSON, on ne tente pas de parser."""
    part = {"function_response": {"response": {"result": "not-json"}}}
    result = extract_metadata_from_session(_make_session([_make_event(parts=[part])]))
    # Reste tel quel — pas d'unwrap
    assert result["data"]["result"] == "not-json"


def test_result_model_dump():
    """res_data avec model_dump() doit être converti en dict."""

    class FakeModel:
        def model_dump(self):
            return {"converted": True}

    part = {"function_response": {"response": FakeModel()}}
    result = extract_metadata_from_session(_make_session([_make_event(parts=[part])]))
    assert result["data"] == {"converted": True}


def test_result_dict_method_fallback():
    """res_data avec .dict() (legacy Pydantic v1) doit être converti."""

    class LegacyModel:
        def dict(self):
            return {"legacy": True}

    part = {"function_response": {"response": LegacyModel()}}
    result = extract_metadata_from_session(_make_session([_make_event(parts=[part])]))
    assert result["data"] == {"legacy": True}


def test_last_tool_data_is_latest_result():
    """data contient le dernier résultat (last_tool_data)."""
    part1 = {"function_response": {"response": {"step": 1}}}
    part2 = {"function_response": {"response": {"step": 2}}}
    events = [_make_event(parts=[part1]), _make_event(parts=[part2])]
    result = extract_metadata_from_session(_make_session(events))
    assert result["data"] == {"step": 2}


def test_result_deduplication():
    part = {"function_response": {"response": {"x": 1}}}
    events = [_make_event(parts=[part]), _make_event(parts=[part])]
    result = extract_metadata_from_session(_make_session(events))
    result_steps = [s for s in result["steps"] if s["type"] == "result"]
    assert len(result_steps) == 1


# ── Mixed scenario ─────────────────────────────────────────────────────────────

def test_full_pipeline_scenario():
    """Scénario complet : thought → call → result."""
    events = [
        _make_event(parts=[{"thought": True, "text": "Je cherche les missions"}]),
        _make_event(parts=[{"function_call": {"name": "list_missions", "args": {}}}]),
        _make_event(parts=[{"function_response": {"response": {"missions": [{"id": 1}]}}}]),
    ]
    result = extract_metadata_from_session(_make_session(events))

    assert "Je cherche les missions" in result["thoughts"]
    call_steps = [s for s in result["steps"] if s["type"] == "call"]
    result_steps = [s for s in result["steps"] if s["type"] == "result"]
    assert len(call_steps) == 1
    assert len(result_steps) == 1
    assert result["data"] == {"missions": [{"id": 1}]}
