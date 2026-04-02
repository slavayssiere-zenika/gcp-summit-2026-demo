from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import os
import uvicorn

# We import the list_tools and call_tool decorators directly from the Python file
# that registered them with the MCP Server object, but we invoke them dynamically via Python 
# instead of relying on the SDK's execution loop.
from mcp_server import list_tools, call_tool

app = FastAPI(title="Items MCP Sidecar (HTTP Standard)")

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app, excluded_urls="health")

class ToolCallRequest(BaseModel):
    name: str
    arguments: dict = {}

@app.get("/mcp/tools")
async def get_tools():
    # Invoke the mcp python function directly
    tools = await list_tools()
    return [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in tools]

@app.post("/mcp/call")
async def execute_tool(request: ToolCallRequest, http_request: Request):
    auth_header = http_request.headers.get("Authorization")
    if auth_header:
        from mcp_server import mcp_auth_header_var
        mcp_auth_header_var.set(auth_header)
    
    try:
        # Evaluate call_tool dynamically bypassing the mcp.Server event loop queue
        result = await call_tool(request.name, request.arguments)
        
        # Result is a list of TextContent objects. We serialize them to JSON format.
        return {"result": [r.model_dump() for r in result]}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "items-mcp", "transport": "http"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
