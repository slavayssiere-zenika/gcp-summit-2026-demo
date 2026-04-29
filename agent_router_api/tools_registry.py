import asyncio
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from opentelemetry.propagate import inject
from agent_commons.schemas import get_tool_metadata
from agent_commons.jwt_middleware import verify_jwt_bearer as verify_jwt

router = APIRouter(dependencies=[Depends(verify_jwt)])
security = HTTPBearer()

MCP_SERVICES_CONFIG = [
    {"id": "users",        "name": "Users API",           "env": "USERS_API_URL"},
    {"id": "items",        "name": "Items API",           "env": "ITEMS_API_URL"},
    {"id": "drive",        "name": "Drive API",           "env": "DRIVE_API_URL"},
    {"id": "competencies", "name": "Competencies API",    "env": "COMPETENCIES_API_URL"},
    {"id": "cv",           "name": "CV API",              "env": "CV_API_URL"},
    {"id": "missions",     "name": "Missions API",        "env": "MISSIONS_API_URL"},
    {"id": "prompts",      "name": "Prompts API",         "env": "PROMPTS_API_URL"},
    {"id": "analytics",       "name": "Analytics & FinOps MCP", "env": "ANALYTICS_MCP_URL"},
    {"id": "monitoring",   "name": "Monitoring MCP",      "env": "MONITORING_MCP_URL"},
]

@router.get("/mcp/registry")
async def mcp_registry(auth: HTTPAuthorizationCredentials = Depends(security)):
    from agent import ROUTER_TOOLS

    auth_header = f"{auth.scheme} {auth.credentials}"

    async def fetch_tools(svc_config: dict) -> dict:
        base_url = os.getenv(svc_config["env"], "")
        if not base_url:
            return {"id": svc_config["id"], "name": svc_config["name"], "tools": [], "error": "URL non configurée"}

        headers = {"Authorization": auth_header}
        inject(headers)
        url = f"{base_url.rstrip('/')}/mcp/tools"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    raw_tools = res.json()
                    tools = []
                    for t in raw_tools:
                        params = []
                        schema = t.get("inputSchema", {})
                        properties = schema.get("properties", {})
                        required_fields = schema.get("required", [])
                        for pname, pdef in properties.items():
                            params.append({
                                "name": pname,
                                "type": pdef.get("type", "any"),
                                "default": pdef.get("default", None),
                                "required": pname in required_fields,
                            })
                        tools.append({
                            "name": t.get("name", ""),
                            "description": t.get("description", ""),
                            "parameters": params,
                        })
                    return {"id": svc_config["id"], "name": svc_config["name"], "tools": tools}
                else:
                    return {"id": svc_config["id"], "name": svc_config["name"], "tools": [], "error": f"HTTP {res.status_code}"}
        except Exception as e:
            return {"id": svc_config["id"], "name": svc_config["name"], "tools": [], "error": str(e)}

    results = await asyncio.gather(*[fetch_tools(s) for s in MCP_SERVICES_CONFIG])

    router_service = {
        "id": "router",
        "name": "Router Agent (Orchestrator)",
        "tools": get_tool_metadata(ROUTER_TOOLS)
    }

    all_services = [router_service] + list(results)
    return {"services": all_services}

@router.api_route("/mcp/proxy/{server_name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_mcp(server_name: str, path: str, request: Request, auth: HTTPAuthorizationCredentials = Depends(security)):
    normalized_name = server_name.lower().replace("-", "_").replace("_api", "").replace("_mcp", "")
    
    svc = next((s for s in MCP_SERVICES_CONFIG if s["id"] == normalized_name or s["id"] == server_name), None)
    
    base_url = None
    if svc:
        base_url = os.getenv(svc["env"])
    
    if not base_url:
        env_var_name = f"{normalized_name.upper()}_API_URL"
        base_url = os.getenv(env_var_name)
    
    if not base_url:
        raise HTTPException(status_code=404, detail=f"MCP Server {server_name} (ID: {normalized_name}) introuvable ou variable d'env manquante")
        
    auth_header = f"{auth.scheme} {auth.credentials}"
    headers = {"Authorization": auth_header}
    inject(headers)
    
    body = await request.body()
    target_path = f"{base_url.rstrip('/')}/{path}"
    query_params = request.url.query
    if query_params:
        target_path += "?" + query_params
        
    async with httpx.AsyncClient() as client:
        try:
            res = await client.request(
                method=request.method,
                url=target_path,
                headers=headers,
                content=body,
                timeout=300.0
            )
            resp_headers = {k: v for k, v in res.headers.items() if k.lower() not in ["content-length", "content-encoding", "transfer-encoding"]}
            return Response(content=res.content, status_code=res.status_code, headers=resp_headers)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Erreur de communication avec {server_name}: {str(exc)}")
