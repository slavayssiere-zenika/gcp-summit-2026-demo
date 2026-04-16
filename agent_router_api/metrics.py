from prometheus_client import Counter, Histogram

AGENT_QUERIES_TOTAL = Counter("agent_queries_total", "Total number of queries processed by the agent")
AGENT_TOOL_CALLS_TOTAL = Counter("agent_tool_calls_total", "Total number of tool calls made by the agent", ["tool_name"])

# A2A Circuit-Breaker metrics
A2A_CALL_DURATION = Histogram(
    "a2a_call_duration_seconds",
    "Duration of A2A calls to sub-agents",
    ["agent"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 90.0]
)
A2A_CALL_ERRORS_TOTAL = Counter(
    "a2a_call_errors_total",
    "Total number of A2A call errors per sub-agent",
    ["agent", "reason"]
)
A2A_CALL_RETRIES_TOTAL = Counter(
    "a2a_call_retries_total",
    "Total number of A2A call retries per sub-agent",
    ["agent"]
)
