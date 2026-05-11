import json
import os
import httpx
import urllib.parse

def main():
    token_path = os.path.expanduser("~/.cache/zenika_mcp_cli_token.json")
    with open(token_path, "r") as f:
        data = json.load(f)
        token = data["token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    base_url = "https://prd.zenika.slavayssiere.fr/api/prompts"
    
    prompts = []
    skip = 0
    limit = 500
    while True:
        response = httpx.get(f"{base_url}/?skip={skip}&limit={limit}", headers=headers)
        response.raise_for_status()
        batch = response.json().get("prompts", [])
        prompts.extend(batch)
        if len(batch) < limit:
            break
        skip += limit
    
    error_prompts = [p for p in prompts if p["key"].startswith("error_correction:")]
    print(f"Found {len(error_prompts)} error prompts to delete.")
    
    for p in error_prompts:
        key = urllib.parse.quote(p["key"], safe='')
        delete_resp = httpx.delete(f"{base_url}/{key}", headers=headers)
        if delete_resp.status_code == 200:
            print(f"Deleted {p['key']}")
        else:
            print(f"Failed to delete {p['key']}: {delete_resp.status_code} - {delete_resp.text}")

if __name__ == "__main__":
    main()
