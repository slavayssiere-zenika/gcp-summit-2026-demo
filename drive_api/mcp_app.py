from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import os
import uvicorn
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from mcp_server import list_tools, call_tool

app = FastAPI(title="CV Analysis MCP Sidecar")
FastAPIInstrumentor.instrument_app(app, excluded_urls="health")

class ToolCallRequest(BaseModel):
    name: str
    arguments: dict = {}

@app.get("/mcp/tools")
async def get_tools():
    tools = await list_tools()
    return [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in tools]

@app.post("/mcp/call")
async def execute_tool(request: ToolCallRequest, http_request: Request):
    auth_header = http_request.headers.get("Authorization")
    if auth_header:
        from mcp_server import mcp_auth_header_var
        mcp_auth_header_var.set(auth_header)
    
    try:
        result = await call_tool(request.name, request.arguments)
        return {"result": [r.model_dump() for r in result]}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "cv-mcp"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
