import os
import re

base_dir = "/Users/sebastien.lavayssiere/Code/test-open-code"
env_pattern = re.compile(r'os\.(?:getenv|environ\.get|environ\[)\s*[\'"]([A-Z0-9_]+)[\'"]')

def extract_env_vars_for_dir(directory):
    env_vars = set()
    for root, dirs, files in os.walk(directory):
        if '.tmp' in root or '.venv' in root or 'venv' in root or '.pytest_cache' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    matches = env_pattern.findall(content)
                    env_vars.update(matches)
    return sorted(list(env_vars))

dirs_to_check = [
    "users_api", "items_api", "competencies_api", "cv_api", "missions_api", 
    "prompts_api", "drive_api", "analytics_mcp", 
    "agent_router_api", "agent_hr_api", "agent_ops_api"
]

results = {}
for d in dirs_to_check:
    full_path = os.path.join(base_dir, d)
    if os.path.exists(full_path):
        results[d] = extract_env_vars_for_dir(full_path)

for d, vars in results.items():
    print(f"[{d}]")
    for v in vars:
        print(f"  - {v}")
    print()
