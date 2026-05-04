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

  - check_id_invention_guardrail(steps)
      Guardrail 3: detects tool calls with suspicious invented IDs (0, -1, null…).

  - check_name_grounding_guardrail(response_text, steps)
      Guardrail 4: warns when proper names in the response are absent from tool results.
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


MIN_SIMILARITY_SCORE = 0.55
"""Seuil de score de similarité RAG minimum pour considérer un profil comme pertinent.
Les profils avec un score inférieur à ce seuil sont exclus des résultats de recherche."""


def all_scores_below_threshold(result_data: Any, threshold: float = MIN_SIMILARITY_SCORE) -> bool:
    """Return True if ALL candidates in a search result have a similarity score below threshold.

    Handles the nested list format returned by search_best_candidates:
      - result_data is a list of dicts with a 'score' or 'similarity' key.
      - result_data is a dict with a 'result' key containing a JSON list.

    Returns False (not below threshold) if no scores are found — err on the side of showing results.
    """
    scores = []
    items = []

    if isinstance(result_data, list):
        items = result_data
    elif isinstance(result_data, dict):
        for key in ("results", "candidates", "users", "items", "data"):
            if key in result_data and isinstance(result_data[key], list):
                items = result_data[key]
                break

    for item in items:
        if isinstance(item, dict):
            score = item.get("score") or item.get("similarity") or item.get("relevance_score")
            if score is not None:
                try:
                    scores.append(float(score))
                except (ValueError, TypeError):
                    pass

    if not scores:
        return False  # No scores found — cannot determine, assume OK

    return all(s < threshold for s in scores)


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
    # Guardrail 2b — COM-006 : tous les scores < MIN_SIMILARITY_SCORE
    # Si search_best_candidates retourne des profils mais tous avec des scores < 0.55,
    # l'agent ne doit PAS confirmer des profils non-pertinents comme des "experts".
    all_low_scores = (
        not all_empty
        and candidate_search_results
        and all(
            r["tool"] == "search_best_candidates" and all_scores_below_threshold(r["result"])
            for r in candidate_search_results
            if r["tool"] == "search_best_candidates"
        )
        and any(r["tool"] == "search_best_candidates" for r in candidate_search_results)
    )
    searched_tools = list({r["tool"] for r in candidate_search_results})

    if (all_empty or all_low_scores) and response_text:
        trigger_reason = "résultats vides" if all_empty else "scores de similarité trop bas (< 0.55)"
        logger.warning(
            "%s 🚨 COM-006 GUARDRAIL TRIGGERED: %d candidate search tool(s) (%s) returned "
            "empty or low-score results (%s), but agent confirmed a candidate list. Overriding response.",
            agent_prefix,
            len(candidate_search_results),
            ", ".join(searched_tools),
            trigger_reason,
        )
        steps = list(steps)
        steps.insert(0, {
            "type": "warning",
            "tool": "GUARDRAIL_COM006",
            "args": {
                "message": (
                    f"COM-006 DÉCLENCHÉ : Les outils {searched_tools} ont retourné des résultats "
                    f"non pertinents ({trigger_reason}). "
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


# ---------------------------------------------------------------------------
# Guardrail 3 & 4 — re-exported from guardrails_grounding for backward compat
# ---------------------------------------------------------------------------
# These guardrails have been extracted to guardrails_grounding.py to keep this
# file under the 400-line modularity threshold (Golden Rule §14).
from agent_commons.guardrails_grounding import (  # noqa: F401, E402
    SUSPICIOUS_IDS,
    ID_ARG_KEYS,
    check_id_invention_guardrail,
    check_name_grounding_guardrail,
)
