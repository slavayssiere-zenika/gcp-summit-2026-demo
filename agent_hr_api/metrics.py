from prometheus_client import Counter, REGISTRY


def _get_or_create_counter(name, documentation, labelnames=()):
    """Retourne un Counter existant ou en crée un nouveau (safe pour les tests parallèles)."""
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    return Counter(name, documentation, list(labelnames))


AGENT_QUERIES_TOTAL = _get_or_create_counter(
    "agent_queries_total",
    "Total number of queries processed by the agent"
)
AGENT_TOOL_CALLS_TOTAL = _get_or_create_counter(
    "agent_tool_calls_total",
    "Total number of tool calls made by the agent",
    ["tool_name"]
)
