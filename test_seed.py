import urllib.request, json, os, ssl

# Get admin password
ADMIN_PWD = os.popen("cd platform-engineering/terraform && terraform output -raw admin_password 2>/dev/null").read().strip()
if not ADMIN_PWD:
    print("Could not get admin pwd")
    exit(1)

# Get dns name
api_dns_name = os.popen("cd platform-engineering/terraform && terraform output -raw api_dns_name 2>/dev/null").read().strip()
if not api_dns_name:
    api_dns_name = "api.prd.znk.io"

ctx_to_use = ssl._create_unverified_context()

# Login
url = f"https://{api_dns_name}/auth/login"
data = json.dumps({"email": "admin@zenika.com", "password": ADMIN_PWD}).encode("utf-8")
req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

try:
    response = urllib.request.urlopen(req, timeout=10, context=ctx_to_use)
    access_token = json.loads(response.read().decode('utf-8')).get("access_token")
    print("Login successful")
except Exception as e:
    print("Login failed:", e)
    exit(1)

# Seeding
prompts_url = f"https://{api_dns_name}/api/prompts/"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {access_token}"
}
p_key = "cv_api.generate_taxonomy_tree_deduplicate"
content = "test content"

check_req = urllib.request.Request(f"{prompts_url}{p_key}", headers=headers, method="GET")
try:
    urllib.request.urlopen(check_req, timeout=10, context=ctx_to_use)
    http_method = "PUT"
    upsert_url = f"{prompts_url}{p_key}"
except urllib.error.HTTPError as e:
    if e.code == 404:
        http_method = "POST"
        upsert_url = prompts_url
    else:
        http_method = "POST"
        upsert_url = prompts_url
except Exception as e:
    print("GET error:", e)
    http_method = "POST"
    upsert_url = prompts_url

print(f"Will send {http_method} to {upsert_url}")
p_data = json.dumps({"key": p_key, "value": content}).encode("utf-8")
p_req = urllib.request.Request(upsert_url, data=p_data, headers=headers, method=http_method)
try:
    p_resp = urllib.request.urlopen(p_req, timeout=15, context=ctx_to_use)
    print("Seed success:", p_resp.status)
except Exception as e:
    print("Seed failed:", e)

