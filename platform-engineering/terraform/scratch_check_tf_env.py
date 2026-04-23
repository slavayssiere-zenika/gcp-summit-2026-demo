import os
import re

base_dir = "/Users/sebastien.lavayssiere/Code/test-open-code"
tf_dir = os.path.join(base_dir, "platform-engineering", "terraform")

env_pattern = re.compile(r'os\.(?:getenv|environ\.get|environ\[)\s*[\'"]([A-Z0-9_]+)[\'"]')

# 1. Parse PY files
dirs_to_check = [
    "users_api", "items_api", "competencies_api", "cv_api", "missions_api", 
    "prompts_api", "drive_api", "analytics_mcp", 
    "agent_router_api", "agent_hr_api", "agent_ops_api"
]

py_envs = {}
for d in dirs_to_check:
    full_path = os.path.join(base_dir, d)
    if os.path.exists(full_path):
        env_vars = set()
        for root, dirs, files in os.walk(full_path):
            if '.tmp' in root or '.venv' in root or 'venv' in root or '.pytest_cache' in root:
                continue
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        matches = env_pattern.findall(content)
                        env_vars.update(matches)
        
        py_envs[d] = sorted(list(env_vars))
        
# 2. Parse TF files
tf_envs = {}
tf_pattern = re.compile(r'name\s*=\s*[\'"]([A-Z0-9_]+)[\'"]')
for d in dirs_to_check:
    tf_file = f"cr_{d.replace('_api', '')}.tf"
    tf_path = os.path.join(tf_dir, tf_file)
    if not os.path.exists(tf_path):
        # drive is cr_drive.tf, analytics_mcp is cr_market.tf or analytics_mcp.tf?
        # let's try direct matches
        pass
    
    # Just fall back to scanning all TF files
    pass

for root, dirs, files in os.walk(tf_dir):
    for file in files:
        if file.endswith('.tf'):
            file_path = os.path.join(root, file)
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # we need to map TF to service
                # We can do this roughly by looking at resource name
                blocks = re.findall(r'resource "google_cloud_run_v2_service" "([^"]+)".*?\{(.*?^\})', content, re.M | re.S)
                for svc_name, svc_block in blocks:
                    matches = tf_pattern.findall(svc_block)
                    tf_envs[svc_name] = sorted(list(set(matches)))
                    
print("=== Missing Environment Variables Analysis ===")
print("Note: TF injection is checked per Cloud Run Service.\n")
for d, required in py_envs.items():
    svc_name = d
    # Match TF names (e.g. cv_api in py_envs maps to cv_api in tf_envs)
    provided = tf_envs.get(svc_name, [])
    
    missing = [req for req in required if req not in provided]
    
    # Filter out common python/system env vars that are not expected to be in TF
    ignore_list = [
        "APPENGINE_RUNTIME", "COMP_CWORD", "COMP_WORDS", "EDITOR", "PIP_EXISTS_ACTION", 
        "PIP_NO_INPUT", "USERPROFILE", "VISUAL", "WEB_CONCURRENCY", "_PIP_RUNNING_IN_SUBPROCESS", 
        "_PIP_USE_IMPORTLIB_METADATA", "_PYPROJECT_HOOKS_BUILD_BACKEND", "_PYTHON_HOST_PLATFORM", "__PYVENV_LAUNCHER__",
        "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_LOCATION", "GOOGLE_CLOUD_PROJECT", "GOOGLE_GENAI_REPLAYS_DIRECTORY",
        "PROMETHEUS_MULTIPROC_DIR", "SSL_CERT_DIR", "SSL_CERT_FILE"
    ]
    missing = [m for m in missing if m not in ignore_list]
    
    print(f"[{svc_name}]")
    print(f"  Required (Py) : {required}")
    print(f"  Provided (TF) : {provided}")
    if missing:
        print(f"  -> MISSING in TF: {missing}")
    else:
        print(f"  -> OK")
    print()
