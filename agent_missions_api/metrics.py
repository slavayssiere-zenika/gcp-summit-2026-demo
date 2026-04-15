from prometheus_client import Counter, Histogram

QUERY_COUNT = Counter(
    "missions_agent_queries_total",
    "Total number of queries processed by agent_missions_api",
    ["agent", "status"]
)

QUERY_LATENCY = Histogram(
    "missions_agent_query_duration_seconds",
    "Latency of queries processed by agent_missions_api",
    ["agent"],
    buckets=[1, 5, 10, 20, 30, 45, 60, 90, 120]
)

AGENT_TOOL_CALLS_TOTAL = Counter(
    "missions_agent_tool_calls_total",
    "Total number of MCP tool calls made by agent_missions_api",
    ["tool_name"]
)
