"""
guardrails_grounding.py — Guardrails 3 & 4 (ID invention + Name grounding).

Extracted from guardrails.py to respect the 400-line modularity constraint.

Key exports:
  - SUSPICIOUS_IDS, ID_ARG_KEYS
  - check_id_invention_guardrail(steps) → Guardrail 3
  - check_name_grounding_guardrail(response_text, steps) → Guardrail 4
"""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Guardrail 3 — ID Invention detection
# ---------------------------------------------------------------------------

#: IDs that strongly indicate the model invented / guessed a value rather than
#: resolving it from a prior tool result.
SUSPICIOUS_IDS: frozenset = frozenset({
    "0", "-1", "null", "none", "unknown", "user_1", "user1",
    "id", "<id>", "<user_id>", "123", "999", "9999",
})

#: Tool argument keys that carry entity identifiers subject to this check.
ID_ARG_KEYS: frozenset = frozenset({
    "user_id", "id", "mission_id", "candidate_id", "competency_id",
    "item_id", "folder_id", "agent_id",
})


def check_id_invention_guardrail(
    steps: list[dict],
    agent_prefix: str = "",
) -> list[dict]:
    """Guardrail 3: Detect tool calls with suspicious / invented entity IDs.

    An ID value of 0, -1, null, 'user_1', or other sentinel strings in an
    argument that carries an entity identifier (user_id, mission_id …) is a
    strong signal that the model guessed the ID rather than resolving it via a
    prior search tool call.

    This guardrail appends a ``GUARDRAIL_ID_INVENTION`` warning step for each
    suspicious call found.  It does **not** modify the response text — the
    warning is visible in Expert Mode.

    Args:
        steps:        List of step dicts already collected.
        agent_prefix: Log prefix string (e.g. ``"[HR]"``).

    Returns:
        Possibly extended steps list (original list is not mutated).
    """
    steps = list(steps)  # avoid mutating caller's list
    extra: list[dict] = []

    for step in steps:
        if step.get("type") != "call":
            continue
        tool_name = step.get("tool", "")
        args = step.get("args") or {}
        for key, value in args.items():
            if key.lower() not in ID_ARG_KEYS:
                continue
            str_val = str(value).strip().lower()
            if str_val in SUSPICIOUS_IDS or (str_val.lstrip("-").isdigit() and int(str_val) <= 0):
                logger.warning(
                    "%s ⚠️ GUARDRAIL_ID: Tool '%s' called with suspicious ID '%s=%s'.",
                    agent_prefix, tool_name, key, value,
                )
                extra.append({
                    "type": "warning",
                    "tool": "GUARDRAIL_ID_INVENTION",
                    "args": {
                        "message": (
                            f"L'outil '{tool_name}' a été appelé avec un ID suspect "
                            f"('{key}={value}'). L'agent a probablement inventé cet identifiant "
                            f"plutôt que de le résoudre via search_users / list_missions. "
                            f"Résultat potentiellement halluciné."
                        )
                    },
                })

    steps.extend(extra)
    return steps


# ---------------------------------------------------------------------------
# Guardrail 4 — Name grounding (warning only)
# ---------------------------------------------------------------------------

#: Known entity names / tech terms that are NOT consultant names — prevents
#: false positives on brand / technology names.
_KNOWN_ENTITIES: frozenset = frozenset({
    "Zenika", "Google", "GCP", "AWS", "Azure", "Azure DevOps",
    "Google Cloud", "Google Drive", "Google BigQuery",
    "React", "Python", "Java", "Kubernetes", "Docker", "Terraform",
    "Spring", "Spring Boot", "Spring Framework",
    "Angular", "TypeScript", "JavaScript",
    "FastAPI", "Redis", "PostgreSQL", "BigQuery", "Gemini",
    "Cloud Run", "GitHub", "GitLab", "Jenkins", "Ansible",
    "No-Go", "Aucun", "Agent", "Orchestrateur", "Missions",
    "Niort", "Paris", "Lyon", "Bordeaux", "Sèvres", "Bizanos", "Saumur",
})

#: Regex matching sequences of 2+ capitalised words (likely proper names).
_NAME_PATTERN = re.compile(
    r'\b([A-ZÀÂÉÈÊËÎÏÔÙÛÜ][a-zàâéèêëîïôùûü]+'
    r'(?:[\s-][A-ZÀÂÉÈÊËÎÏÔÙÛÜ][a-zàâéèêëîïôùûü]+)+)\b'
)


def _extract_names_from_data(data: Any, target: set[str]) -> None:
    """Recursively extract string values of 'name'-like keys from a data structure."""
    if isinstance(data, dict):
        for key, val in data.items():
            if key.lower() in (
                "username", "full_name", "name", "email",
                "first_name", "last_name", "display_name",
            ):
                if isinstance(val, str) and val.strip():
                    target.add(val.strip().lower())
            else:
                _extract_names_from_data(val, target)
    elif isinstance(data, list):
        for item in data:
            _extract_names_from_data(item, target)


def check_name_grounding_guardrail(
    response_text: str,
    steps: list[dict],
    agent_prefix: str = "",
) -> tuple[str, list[dict]]:
    """Guardrail 4: Warn when proper names in the response are absent from tool results.

    After the agent has produced a response, this guardrail:
    1. Extracts all named entities returned by MCP tools (username, full_name…).
    2. Scans the response text for sequences of 2+ capitalised words (candidate names).
    3. Flags any candidate name not found in the tool results as potentially hallucinated.

    This guardrail is **warning-only** — it never suppresses or modifies the response
    text.  The ``GUARDRAIL_NAME_GROUNDING`` step is visible in Expert Mode and a badge
    is shown next to the FinOps cost indicator in the UI.

    Args:
        response_text: Raw response text collected from the event stream.
        steps:         List of step dicts already collected.
        agent_prefix:  Log prefix string (e.g. ``"[HR]"``).

    Returns:
        Tuple ``(response_text, steps)`` — response_text is never modified.
    """
    # Collect names anchored in tool results
    tool_names: set[str] = set()
    for step in steps:
        if step.get("type") == "result":
            _extract_names_from_data(step.get("data"), tool_names)

    if not tool_names:
        # No data from tools — Guardrail 1 already handles the zero-tool case
        return response_text, steps

    # Find candidate proper names in the response text
    candidate_names = _NAME_PATTERN.findall(response_text)

    unanchored = [
        name for name in candidate_names
        if name not in _KNOWN_ENTITIES
        and not any(
            name.lower() in tn or tn in name.lower()
            for tn in tool_names
        )
    ]

    # De-duplicate preserving order
    seen: set[str] = set()
    unique_unanchored = []
    for n in unanchored:
        if n not in seen:
            seen.add(n)
            unique_unanchored.append(n)

    if unique_unanchored:
        logger.warning(
            "%s ⚠️ GUARDRAIL_NAME: %d name(s) cited in response but absent from tool results: %s",
            agent_prefix, len(unique_unanchored), unique_unanchored,
        )
        steps = list(steps)  # avoid mutating caller's list
        steps.append({
            "type": "warning",
            "tool": "GUARDRAIL_NAME_GROUNDING",
            "args": {
                "message": (
                    f"Noms cités dans la réponse mais absents des résultats MCP : "
                    f"{unique_unanchored}. "
                    f"Ces profils n'ont pas été retournés par les outils — "
                    f"ils peuvent être hallucinés. Vérifiez les données sources."
                ),
                "unanchored_names": unique_unanchored,
            },
        })

    return response_text, steps
