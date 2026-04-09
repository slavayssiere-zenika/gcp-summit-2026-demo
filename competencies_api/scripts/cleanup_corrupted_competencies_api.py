import asyncio
import httpx
import json
import getpass
import sys
import os
import ast
import argparse
from typing import Dict, Any, List

def parse_args():
    parser = argparse.ArgumentParser(description="Zenika Competency Cleanup Tool")
    parser.add_argument("--domain", "-d", help="Base domain (e.g. dev.zenika.slavayssiere.fr)")
    parser.add_argument("--local", action="store_true", help="Use localhost with default ports (default if no domain)")
    parser.add_argument("--email", default="admin@zenika.com", help="Admin email to use for login")
    parser.add_argument("--insecure", "-k", action="store_true", help="Disable SSL verification")
    return parser.parse_args()

args = parse_args()

# Configuration Logic
if args.domain:
    print(f"Using environment domain: {args.domain}")
    USERS_API_URL = f"https://{args.domain}/auth"
    COMPETENCIES_API_URL = f"https://{args.domain}/comp-api"
else:
    print("Using local environment (localhost)")
    USERS_API_URL = os.getenv("USERS_API_URL", "http://localhost:8000")
    COMPETENCIES_API_URL = os.getenv("COMPETENCIES_API_URL", "http://localhost:8003")

ADMIN_EMAIL = args.email
VERIFY_SSL = not args.insecure

async def login(email: str, password: str) -> str:
    """Authenticates and returns the JWT token."""
    url = f"{USERS_API_URL.rstrip('/')}/login"
    async with httpx.AsyncClient(verify=VERIFY_SSL) as client:
        try:
            resp = await client.post(url, json={"email": email, "password": password})
            if resp.status_code == 401:
                print(f"Error: Invalid credentials for {email}")
                sys.exit(1)
            resp.raise_for_status()
            return resp.json()["access_token"]
        except Exception as e:
            print(f"Failed to connect to Users API at {url}: {e}")
            sys.exit(1)

def flatten_competencies(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Recursively flattens a tree of competencies."""
    flat_list = []
    for item in items:
        # Create a copy without the children list to avoid confusion in the flat list
        node = item.copy()
        children = node.pop("sub_competencies", [])
        flat_list.append(node)
        if children:
            flat_list.extend(flatten_competencies(children))
    return flat_list

async def list_competencies(token: str) -> List[Dict[str, Any]]:
    """Retrieves all competencies using pagination with retry logic for 429s."""
    all_items = []
    skip = 0
    limit = 100 # Standard API limit
    headers = {"Authorization": f"Bearer {token}"}
    
    max_retries = 5
    
    async with httpx.AsyncClient(verify=VERIFY_SSL) as client:
        while True:
            url = f"{COMPETENCIES_API_URL.rstrip('/')}/?skip={skip}&limit={limit}"
            items = None
            
            backoff = 1
            for attempt in range(max_retries):
                try:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 429:
                        print(f"  Rate limited (429) during fetch. Retrying in {backoff}s... (Attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    
                    resp.raise_for_status()
                    data = resp.json()
                    items = data["items"] if isinstance(data, dict) and "items" in data else data
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        print(f"Failed to fetch competencies from {url} after {max_retries} attempts: {e}")
                        sys.exit(1)
                    await asyncio.sleep(0.5)

            if not items:
                break
                
            all_items.extend(items)
            
            # If we got fewer items than requested, we reached the end
            if len(items) < limit:
                break
                
            skip += limit
            # Small delay between pages to be gentle
            await asyncio.sleep(0.2)
    
    # Flatten the results since the API returns a tree
    return flatten_competencies(all_items)

async def update_competency(token: str, competency_id: int, update_data: Dict[str, Any]):
    """Updates a single competency via API with retry logic for 429s."""
    url = f"{COMPETENCIES_API_URL.rstrip('/')}/{competency_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    max_retries = 5
    backoff = 1 # Dynamic sleep time
    
    async with httpx.AsyncClient(verify=VERIFY_SSL) as client:
        for attempt in range(max_retries):
            try:
                resp = await client.put(url, headers=headers, json=update_data)
                
                if resp.status_code == 429:
                    print(f"  Rate limited (429). Retrying in {backoff}s... (Attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                
                if resp.status_code == 409:
                    print(f"  Conflict (409): A competency with name '{update_data['name']}' already exists.")
                    return "CONFLICT"
                    
                resp.raise_for_status()
                return True
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Failed to update competency {competency_id} after {max_retries} attempts: {e}")
                else:
                    await asyncio.sleep(0.5) # Short sleep before retrying other errors
        return False

async def get_competency_users(token: str, competency_id: int) -> List[int]:
    """Fetches user IDs associated with a competency."""
    url = f"{COMPETENCIES_API_URL.rstrip('/')}/{competency_id}/users"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(verify=VERIFY_SSL) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"  Warning: Could not fetch users for competency {competency_id}: {e}")
            return []

async def assign_competency_to_user(token: str, competency_id: int, user_id: int):
    """Assigns a competency to a user."""
    url = f"{COMPETENCIES_API_URL.rstrip('/')}/user/{user_id}/competency/{competency_id}"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(verify=VERIFY_SSL) as client:
        try:
            resp = await client.post(url, headers=headers)
            if resp.status_code != 201 and resp.status_code != 200:
                # If already assigned, usually returns 409 or similar, which is fine
                pass
            return True
        except Exception:
            return False

async def delete_competency(token: str, competency_id: int):
    """Deletes a competency."""
    url = f"{COMPETENCIES_API_URL.rstrip('/')}/{competency_id}"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(verify=VERIFY_SSL) as client:
        try:
            resp = await client.delete(url, headers=headers)
            resp.raise_for_status()
            return True
        except Exception as e:
            print(f"  Error deleting competency {competency_id}: {e}")
            return False

def parse_corrupted_name(name_str: str) -> Dict[str, str]:
    """Tries to parse a potentially stringified dictionary."""
    if not name_str.startswith('{'):
        return None
    
    try:
        # Try ast.literal_eval first (handles single quotes common in Python str(dict))
        data = ast.literal_eval(name_str)
        if isinstance(data, dict) and 'name' in data:
            return data
    except:
        pass
        
    try:
        # Try standard JSON
        data = json.loads(name_str.replace("'", "\""))
        if isinstance(data, dict) and 'name' in data:
            return data
    except:
        pass
        
    return None

async def main():
    print("=== Zenika Competency Cleanup Tool (API Mode) ===")
    print(f"Targeting: {ADMIN_EMAIL}")
    
    password = getpass.getpass(f"Enter password for {ADMIN_EMAIL}: ")
    if not password:
        print("Password cannot be empty.")
        return

    print("Authenticating...")
    token = await login(ADMIN_EMAIL, password)
    print("Login successful.")

    print("Fetching competencies list...")
    competencies = await list_competencies(token)
    print(f"Retrieved {len(competencies)} competencies.")

    corrupted_found = []
    for comp in competencies:
        parsed = parse_corrupted_name(comp["name"])
        if parsed:
            corrupted_found.append((comp, parsed))

    if not corrupted_found:
        print("No corrupted competencies found. Everything looks good!")
        return

    print(f"Found {len(corrupted_found)} corrupted competencies.")
    
    confirm = input("Do you want to proceed with the repair? (y/N): ")
    if confirm.lower() != 'y':
        print("Cleanup cancelled.")
        return

    success_count = 0
    for comp, fixed_data in corrupted_found:
        print(f"Fixing ID {comp['id']}: {comp['name'][:50]}... -> {fixed_data['name']}")
        
        update_payload = {
            "name": fixed_data["name"],
            "description": fixed_data.get("description") or comp.get("description")
        }
        
        result = await update_competency(token, comp["id"], update_payload)
        if result == True:
            success_count += 1
        elif result == "CONFLICT":
            print(f"  Resolving conflict by merging ID {comp['id']} into existing clean entry...")
            # 1. Find existing sibling by name in the list we fetched earlier
            existing_id = None
            target_name_lower = update_payload["name"].lower()
            for other_comp in competencies:
                if other_comp["name"].lower() == target_name_lower and not parse_corrupted_name(other_comp["name"]):
                    existing_id = other_comp["id"]
                    break
            
            if existing_id:
                print(f"  Found sibling ID {existing_id}. Transferring users...")
                user_ids = await get_competency_users(token, comp["id"])
                if user_ids:
                    print(f"    Transferring {len(user_ids)} user associations to ID {existing_id}...")
                    for uid in user_ids:
                        await assign_competency_to_user(token, existing_id, uid)
                
                print(f"    Deleting corrupted entry {comp['id']}...")
                if await delete_competency(token, comp["id"]):
                    print(f"    Successfully merged and deleted ID {comp['id']}.")
                    success_count += 1
            else:
                print(f"  Warning: Could not find a clean existing competency with name '{update_payload['name']}' to merge into.")

    print(f"Cleanup finished. Successfully repaired {success_count} entries.")

if __name__ == "__main__":
    asyncio.run(main())
