import asyncio
import httpx
import json
import os
import time

async def test():
    users_url = "https://gen-skillz.znk.io/api/users"
    
    cache_file = os.path.expanduser("~/.cache/zenika_mcp_cli_token.json")
    try:
        with open(cache_file, "r") as f:
            data = json.load(f)
            token = data.get("token")
    except Exception as e:
        print("Failed to get MCP CLI token:", e)
        return

    async with httpx.AsyncClient() as client:
        # Generate Service Token
        res2 = await client.post(f"{users_url}/internal/service-token", headers={"Authorization": f"Bearer {token}"}, timeout=10.0)
        svc_token = res2.json().get("access_token")
        
        # We cannot hit api.internal.zenika from outside GCP, so we must use the MCP tool 'run_gcloud_command' 
        # or just test it inside GCP. 
        # Wait, I CANNOT test it inside GCP using python script unless I deploy it or use `run_command` in a Cloud Run instance.
        
asyncio.run(test())
