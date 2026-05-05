import os
import subprocess
import json

services = [
    "users_api",
    "items_api",
    "competencies_api",
    "missions_api",
    "cv_api",
    "prompts_api",
    "drive_api",
    "agent_commons"
]

results = {}

for service in services:
    print(f"Analyzing {service}...")
    if not os.path.exists(service):
        continue
    
    # Check if there is a schemas.py file
    schemas_path = None
    for root, _, files in os.walk(service):
        if "venv" in root or ".venv" in root:
            continue
        if "schemas.py" in files:
            schemas_path = os.path.join(root, "schemas.py")
            break
            
    if not schemas_path:
        print(f"No schemas.py found in {service}")
        continue
        
    cmd = f"cd {service} && python3 -m pytest --cov=src --cov-report=json tests/ > /dev/null 2>&1"
    subprocess.run(cmd, shell=True)
    
    cov_file = os.path.join(service, "coverage.json")
    if os.path.exists(cov_file):
        with open(cov_file, "r") as f:
            cov_data = json.load(f)
            # Find schemas.py in the report
            schema_key = next((k for k in cov_data.get("files", {}).keys() if "schemas.py" in k), None)
            if schema_key:
                file_cov = cov_data["files"][schema_key]
                percent = file_cov["summary"]["percent_covered_display"]
                missing_lines = file_cov.get("missing_lines", [])
                results[service] = {"percent": percent, "missing_lines": missing_lines, "file": schema_key}
                print(f"  -> {percent}% coverage (Missing lines: {missing_lines})")
            else:
                print(f"  -> schemas.py not in coverage report")
    else:
        print(f"  -> Failed to generate coverage report")

print("\n--- Summary ---")
for s, data in results.items():
    print(f"{s}: {data['percent']}% (Missing: {data['missing_lines']})")

