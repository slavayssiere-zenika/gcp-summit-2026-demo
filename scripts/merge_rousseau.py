import httpx
import json
import os
import sys
from pathlib import Path

# Imite la logique de mcp_cli.py
BASE_URL = "https://prd.zenika.slavayssiere.fr"
TOKEN_CACHE = Path.home() / ".cache" / "zenika_mcp_cli_token.json"

def get_token():
    if not TOKEN_CACHE.exists():
        print("❌ Token cache not found. Please run 'python3 scripts/mcp_cli.py health' first.")
        sys.exit(1)
    data = json.loads(TOKEN_CACHE.read_text())
    return data["token"]

def merge_rousseau():
    token = get_token()
    source_id = 160 # Anon CRO
    target_id = 277 # Christopher ROUSSEAU
    
    print(f"🚀 Merging user {source_id} into {target_id}...")
    
    url = f"{BASE_URL}/api/users/merge"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"source_id": source_id, "target_id": target_id}
    
    resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
    
    if resp.status_code == 200:
        print(f"✅ Success: {resp.json().get('message')}")
    else:
        print(f"❌ Error {resp.status_code}: {resp.text}")

if __name__ == "__main__":
    merge_rousseau()
