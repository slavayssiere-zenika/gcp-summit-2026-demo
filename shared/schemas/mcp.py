"""Consumer DTO for MCP tool responses (agent_commons mcp_client)."""
from typing import Any, List, Optional

from pydantic import BaseModel


class McpContent(BaseModel):
    """Single content item in an MCP tool call result."""

    type: str
    text: Optional[str] = None


class McpToolResult(BaseModel):
    """Standard MCP tool call response envelope.

    The 'result' key is the standard field returned by the MCP sidecar.
    Using model_validate() will catch any protocol drift.
    """

    result: List[Any] = []
