"""
guardrails.py — Anti-hallucination guardrails shared across all agents.

Extracted from agent_hr_api/agent.py (Guardrail 1 is identical in all three
agents; COM-006 / Guardrail 2 is specific to HR but lives here so it can be
imported and unit-tested from a single location).

Key exports:
  - check_hallucination_guardrail(response_text, steps)
      Guardrail 1: detects responses produced with zero tool calls.

  - is_empty_candidate_result(result_data)
      Helper used by Guardrail 2 (COM-006) to detect empty search results.

  - check_empty_candidate_guardrail(candidate_search_results, response_text, steps)
      Guardrail 2 (COM-006): intercepts hallucinated candidate lists when all
      search tools returned empty results.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Guardrail 1 — Zero tool calls
# ---------------------------------------------------------------------------

def check_hallucination_guardrail(
    response_text: str,
    steps: list[dict],
    agent_prefix: str = "",
) -> tuple[str, list[dict]]:
    """Inject a warning when the agent responded without calling any tool.

    If the model produced a text answer without invoking *any* MCP tool, the
    response is very likely hallucinated (fabricated from model memory).  This
    guardrail prepends a visible warning to the response and inserts a
    ``GUARDRAIL`` step so Expert Mode can surface it.

    Args:
        response_text: Raw response text collected from the event stream.
        steps:         List of step dicts already collected.
        agent_prefix:  Log prefix string (e.g. ``"[HR]"``).

    Returns:
        Tuple ``(response_text, steps)`` — possibly modified.
    """
    tool_calls_made = [s for s in steps if s.get("type") == "call"]
    if response_text and not tool_calls_made:
        logger.warning(
            "%s ⚠️ HALLUCINATION RISK: Agent produced a response with ZERO tool calls.",
            agent_prefix,
        )
        steps = list(steps)  # avoid mutating caller's list
        steps.insert(0, {
            "type": "warning",
            "tool": "GUARDRAIL",
            "args": {
                "message": (
                    "AUCUN OUTIL N'A ÉTÉ APPELÉ. La réponse ci-dessus provient de la mémoire du modèle, "
                    "PAS de la base Zenika. Elle est potentiellement hallucinée."
                )
            },
        })
        response_text = (
            "⚠️ ATTENTION : Cette réponse n'est pas fondée sur des données réelles "
            "(aucun outil MCP consulté).\n"
            "Les informations ci-dessous peuvent être inventées. Veuillez relancer la recherche.\n\n"
            + response_text
        )
    return response_text, steps


# ---------------------------------------------------------------------------
# Guardrail 2 — COM-006 (empty candidate search results)
# ---------------------------------------------------------------------------

def is_empty_candidate_result(result_data: Any) -> bool:
    """Return True if a candidate search tool result is empty.

    Detects the common formats returned by MCP sidecars:
      - None
      - Empty list: []
      - Dict with empty collection under a known key: {\"results\": [], ...}
      - Dict with count/total == 0

    Used by COM-006 to prevent hallucination of fictional consultant profiles.
    """
    if result_data is None:
        return True
    if isinstance(result_data, list) and len(result_data) == 0:
        return True
    if isinstance(result_data, dict):
        for key in ("results", "candidates", "users", "items", "data"):
            if key in result_data:
                val = result_data[key]
                if isinstance(val, list) and len(val) == 0:
                    return True
        if result_data.get("total", -1) == 0 or result_data.get("count", -1) == 0:
            return True
    return False


def check_empty_candidate_guardrail(
    candidate_search_results: list[dict],
    response_text: str,
    steps: list[dict],
    agent_prefix: str = "",
) -> tuple[str, list[dict], Any]:
    """Override hallucinated candidate lists when all searches returned empty.

    COM-006: If every candidate-search tool invoked during the run returned an
    empty result set, the agent MUST NOT produce a list of consultants.  This
    guardrail replaces the fabricated response with a neutral \"no results\"
    message and injects a ``GUARDRAIL_COM006`` step.

    Args:
        candidate_search_results: List of ``{\"tool\": str, \"result\": Any}`` dicts
                                  accumulated during the run.
        response_text:            Raw model response text.
        steps:                    Current steps list.
        agent_prefix:             Log prefix string (e.g. ``"[HR]"``).

    Returns:
        Tuple ``(response_text, steps, last_tool_data)``  — possibly overridden.
    """
    last_tool_data: Any = None

    if not candidate_search_results:
        return response_text, steps, last_tool_data

    all_empty = all(is_empty_candidate_result(r["result"]) for r in candidate_search_results)
    searched_tools = list({r["tool"] for r in candidate_search_results})

    if all_empty and response_text:
        logger.warning(
            "%s 🚨 COM-006 GUARDRAIL TRIGGERED: %d candidate search tool(s) (%s) returned EMPTY "
            "results, but agent still produced a candidate list. Overriding response.",
            agent_prefix,
            len(candidate_search_results),
            ", ".join(searched_tools),
        )
        steps = list(steps)
        steps.insert(0, {
            "type": "warning",
            "tool": "GUARDRAIL_COM006",
            "args": {
                "message": (
                    f"COM-006 DÉCLENCHÉ : Les outils {searched_tools} ont retourné 0 résultat. "
                    "La réponse originale de l'agent a été remplacée pour éviter l'hallucination "
                    "de profils fictifs."
                )
            },
        })
        response_text = (
            "Aucun profil trouvé dans la base Zenika pour cette recherche.\n"
            "Les outils de recherche consultés n'ont retourné aucun consultant "
            "correspondant à vos critères.\n"
            "Souhaitez-vous élargir la recherche (modifier les critères, retirer un filtre géographique) ?"
        )

    return response_text, steps, last_tool_data
