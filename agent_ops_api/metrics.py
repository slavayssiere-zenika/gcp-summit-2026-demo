from prometheus_client import Counter

AGENT_QUERIES_TOTAL = Counter("agent_queries_total", "Total number of queries processed by the agent")
AGENT_TOOL_CALLS_TOTAL = Counter("agent_tool_calls_total", "Total number of tool calls made by the agent", ["tool_name"])
