#!/usr/bin/env python3
import os
import sys
import json
import logging
import argparse
import httpx
from pathlib import Path

# Zenika Colors (for logs)
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
RESET = "\033[0m"

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

PROMPTS_MAP = {
    "agent_router_api.system_instruction": "agent_router_api/agent_router_api.system_instruction.txt",
    "agent_hr_api.system_instruction": "agent_hr_api/agent_hr_api.system_instruction.txt",
    "agent_ops_api.system_instruction": "agent_ops_api/agent_ops_api.system_instruction.txt",
    "agent_missions_api.system_instruction": "agent_missions_api/agent_missions_api.system_instruction.txt",
    "cv_api.extract_cv_info": "cv_api/cv_api.extract_cv_info.txt",
    "cv_api.generate_taxonomy_tree": "cv_api/cv_api.generate_taxonomy_tree.txt",
    "missions_api.extract_mission_info": "missions_api/extract_mission_info.txt",
    "missions_api.staffing_heuristics": "missions_api/staffing_heuristics.txt"
}

# Services qui exposent un endpoint /cache/invalidate pour purge après sync
CACHE_INVALIDATION_MAP = {
    "missions_api.": "/api/missions",
}

async def sync_prompts(api_url: str, admin_email: str, admin_password: str):
    base_url = api_url.rstrip("/")
    # Auth is handled at the API gateway level — route is /api/login (not /auth/login directly)
    base_domain = base_url.replace('/api/prompts', '')
    auth_url = f"{base_domain}/api/login"
    
    logger.info(f"{YELLOW}[*] Authenticating as {admin_email}...{RESET}")
    
    async with httpx.AsyncClient(verify=False) as client:
        # 1. Login
        try:
            res = await client.post(auth_url, json={"email": admin_email, "password": admin_password})
            res.raise_for_status()
            token = res.json().get("access_token")
            logger.info(f"{GREEN}[+] Authentication successful.{RESET}")
        except Exception as e:
            logger.error(f"{RED}[!] Authentication failed: {e}{RESET}")
            sys.exit(1)
            
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Sync each prompt
        for key, rel_path in PROMPTS_MAP.items():
            file_path = Path(rel_path)
            if not file_path.exists():
                logger.warning(f"{YELLOW}[!] File not found, skipping: {rel_path}{RESET}")
                continue
                
            content = file_path.read_text(encoding="utf-8")
            logger.info(f"[*] Syncing {key}...")
            
            # Upsert logic
            try:
                # Check if exists
                check_res = await client.get(f"{base_url}/{key}", headers=headers)
                method = "PUT" if check_res.status_code == 200 else "POST"
                target_url = f"{base_url}/{key}" if method == "PUT" else f"{base_url}/"
                
                payload = {"key": key, "value": content}
                res = await client.request(method, target_url, json=payload, headers=headers)
                res.raise_for_status()
                logger.info(f"{GREEN}    -> Successfully {'updated' if method == 'PUT' else 'created'} {key}.{RESET}")

                # Invalidation du cache Redis pour les services qui en ont besoin
                for prefix, service_path in CACHE_INVALIDATION_MAP.items():
                    if key.startswith(prefix):
                        service_base = base_url.replace("/api/prompts", service_path).replace("/prompts", service_path)
                        try:
                            inv_res = await client.post(
                                f"{service_base}/cache/invalidate",
                                params={"prompt_key": key},
                                headers=headers,
                                timeout=5.0
                            )
                            if inv_res.status_code < 400:
                                logger.info(f"{GREEN}    -> Cache Redis invalidé pour '{key}' sur {service_path}.{RESET}")
                            else:
                                logger.warning(f"{YELLOW}    [!] Cache invalidation returned HTTP {inv_res.status_code} for '{key}'.{RESET}")
                        except Exception as cache_err:
                            logger.warning(f"{YELLOW}    [!] Cache invalidation failed for '{key}': {cache_err}{RESET}")

            except Exception as e:
                logger.error(f"{RED}    [!] Error syncing {key}: {e}{RESET}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync project prompts with Prompts API")
    parser.add_argument("--url", required=True, help="Base URL of the Prompts API (e.g., https://api.dev.example.com/api/prompts)")
    parser.add_argument("--email", default="admin@zenika.com", help="Admin email for auth")
    parser.add_argument("--password", required=True, help="Admin password for auth")
    
    args = parser.parse_args()
    
    import asyncio
    asyncio.run(sync_prompts(args.url, args.email, args.password))
