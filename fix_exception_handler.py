import os
import glob
import re
import sys

directories = ["users_api", "items_api", "competencies_api", "missions_api", "cv_api", "drive_api", "prompts_api"]

fallback_code = """

async def get_service_token_fallback() -> str:
    import httpx, os, logging
    logger = logging.getLogger(__name__)
    dev_token = os.getenv("DEV_SERVICE_TOKEN")
    if dev_token:
        return dev_token
        
    try:
        users_api_url = os.getenv("USERS_API_URL", "http://users_api:8000")
        async with httpx.AsyncClient() as client:
            res_meta = await client.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=users_api",
                headers={"Metadata-Flavor": "Google"},
                timeout=2.0
            )
            if res_meta.status_code == 200:
                id_token = res_meta.text
                res = await client.post(f"{users_api_url}/auth/service-account/login", json={"id_token": id_token})
                if res.status_code == 200:
                    return res.json().get("access_token", "")
    except Exception: raise
    return ""
"""

for d in directories:
    main_file = f"{d}/main.py"
    if not os.path.exists(main_file):
        continue
    with open(main_file, "r") as f:
        content = f.read()

    # Apply fix 1: truncation
    content = content.replace('trace_context[:2000]', 'trace_context[-2000:] if len(trace_context) > 2000 else trace_context')

    # Apply fix 2: token fallback
    if 'get_service_token_fallback' not in content:
        idx = content.find("async def report_exception_to_prompts_api")
        if idx != -1:
            content = content[:idx] + fallback_code + "\n" + content[idx:]

        handler_re = re.search(r'(@app\.exception_handler\(Exception\).*?def global_exception_handler.*?)(if token:)(.*?return JSONResponse)', content, flags=re.DOTALL)
        if handler_re:
            new_handler = handler_re.group(1) + "if not token:\n        token = await get_service_token_fallback()\n    \n    if token:" + handler_re.group(3)
            content = content[:handler_re.start()] + new_handler + content[handler_re.end():]
        else:
            print(f"Could not find matching handler in {d}")

    with open(main_file, "w") as f:
        f.write(content)
    print(f"Patched {main_file}")
