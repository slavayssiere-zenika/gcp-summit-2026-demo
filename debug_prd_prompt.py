import urllib.request, json
import os, ssl

ctx = ssl._create_unverified_context()

ADMIN_PWD = os.popen("cd platform-engineering/terraform && terraform output -raw admin_password 2>/dev/null").read().strip()
if not ADMIN_PWD:
    print("Could not get admin pwd")
    exit(1)

# Login
login_req = urllib.request.Request(
    "https://api.prd.znk.io/auth/login",
    data=json.dumps({"email": "admin@zenika.com", "password": ADMIN_PWD}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
try:
    with urllib.request.urlopen(login_req, context=ctx) as resp:
        access_token = json.loads(resp.read())["access_token"]
        print("Logged in")
except Exception as e:
    print("Login failed:", e)
    exit(1)

# Fetch
req = urllib.request.Request(
    "https://api.prd.znk.io/api/prompts/cv_api.generate_taxonomy_tree_deduplicate",
    headers={"Authorization": f"Bearer {access_token}"}
)
try:
    with urllib.request.urlopen(req, context=ctx) as resp:
        print("PROMPT STATUS:", resp.status)
        print("PROMPT:", resp.read().decode("utf-8")[:100])
except urllib.error.HTTPError as e:
    print("Fetch failed HTTPError:", e.code, e.reason)
except Exception as e:
    print("Fetch failed:", type(e).__name__, e)
