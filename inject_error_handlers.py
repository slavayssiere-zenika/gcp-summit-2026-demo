import os
import re

TARGET_FILES = [
    "cv_api/main.py",
    "users_api/main.py",
    "drive_api/main.py",
    "agent_hr_api/main.py",
    "agent_router_api/main.py",
    "agent_missions_api/main.py",
    "agent_ops_api/main.py",
    "items_api/main.py",
    "competencies_api/main.py",
    "missions_api/main.py",
    "prompts_api/main.py",
    "monitoring_mcp/mcp_app.py",
    "market_mcp/mcp_app.py",
    "users_api/mcp_app.py",
    "cv_api/mcp_app.py",
    "drive_api/mcp_app.py",
    "items_api/mcp_app.py",
    "competencies_api/mcp_app.py",
    "missions_api/mcp_app.py"
]

NEW_REPORT_FUNC = """import traceback
from fastapi.responses import JSONResponse
import httpx
import logging
import asyncio

async def report_exception_to_prompts_api(service_name: str, error_msg: str, trace_context: str, token: str):
    prompts_api_url = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        from opentelemetry.propagate import inject
        inject(headers)
    except Exception: raise

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{prompts_api_url}/errors/report",
                json={
                    "service_name": service_name,
                    "error_message": error_msg,
                    "context": trace_context[:2000]
                },
                headers=headers
            )
        except Exception as e:
            logging.error(f"Failed to report error to prompts_api: {e}")
            raise e

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = str(exc)
    trace_context = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    
    if token:
        asyncio.create_task(report_exception_to_prompts_api("[[SERVICE_NAME]]", error_msg, trace_context, token))
    
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
"""

for partial_path in TARGET_FILES:
    path = os.path.join(os.getcwd(), partial_path)
    if not os.path.exists(path):
        print(f"Skipping {path}, does not exist.")
        continue

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Determine service name based on filename
    service_name = partial_path.split("/")[0]

    # If it already has the old report_exception_to_prompts_api
    if "async def report_exception_to_prompts_api" in content:
        print(f"Found existing handler in {path}, replacing...")
        # Replace the entire block
        # Find where it starts
        start_idx = content.find("async def report_exception_to_prompts_api")
        # And let's find the end of global_exception_handler
        end_idx = content.find("return JSONResponse", start_idx)
        if end_idx != -1:
            # wait, it goes until the end of the line
            end_line_idx = content.find("\n", end_idx)
            block_to_remove = content[start_idx:end_line_idx]
            
            # Since imports might be before, we'll just inject right where report_exception_to_prompts_api was
            
            # Create customized replacement
            replacement = NEW_REPORT_FUNC.replace("[[SERVICE_NAME]]", service_name)
            # Remove `import traceback` etc if they conflict but python handles duplicate imports safely.
            
            new_content = content[:start_idx] + replacement + content[end_line_idx:]
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"-> Updated {path}")
            continue

    # If it DOES NOT have it, we append it right before the last main block
    print(f"No existing handler in {path}. Injecting...")
    replacement = NEW_REPORT_FUNC.replace("[[SERVICE_NAME]]", service_name)
    
    # We should inject it before the typical if __name__ == "__main__":
    if "if __name__ ==" in content:
        idx = content.find("if __name__ ==")
        new_content = content[:idx] + "\n" + replacement + "\n" + content[idx:]
    else:
        new_content = content + "\n" + replacement + "\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"-> Injected into {path}")
