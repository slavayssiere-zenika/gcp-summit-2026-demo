import httpx
import os
import subprocess
import json
import time


def get_token():
    try:
        with open(os.path.expanduser("~/.cache/zenika_mcp_cli_token.json"), "r") as f:
            data = json.load(f)
            if data["expires_at"] > time.time() + 60:
                return data["token"]
    except Exception:
        pass

    # We don't have a valid token, let's just ask the admin script
    result = subprocess.run(["python3", "scripts/admin.py", "token"], capture_output=True, text=True)
    for line in result.stdout.split('\n'):
        if "Bearer " in line:
            return line.split("Bearer ")[1].strip()
    return None


def main():
    token = get_token()
    if not token:
        print("Failed to get token")
        return

    headers = {"Authorization": f"Bearer {token}"}

    # Get all prompts
    r = httpx.get("https://prd.zenika.slavayssiere.fr/api/prompts/", headers=headers)
    if r.status_code != 200:
        print(f"Failed to list prompts: {r.text}")
        return

    data = r.json()
    prompts = data.get("prompts", data.get("items", data)) if isinstance(data, dict) else data
    if not isinstance(prompts, list):
        print("Expected a list of prompts")
        return
    print(f"Total prompts found: {len(prompts)}")
    deleted = 0
    for p in prompts:
        key = p.get("key", "")
        if str(key).startswith("error_correction:"):
            res = httpx.delete(f"https://prd.zenika.slavayssiere.fr/api/prompts/{key}", headers=headers)
            if res.status_code in (200, 204):
                print(f"Deleted {key}")
                deleted += 1
            else:
                print(f"Failed to delete {key}: {res.status_code} {res.text}")

    print(f"Deleted {deleted} error corrections.")


if __name__ == "__main__":
    main()
