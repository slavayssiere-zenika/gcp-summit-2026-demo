import os
import re

base_dir = "/Users/sebastien.lavayssiere/Code/test-open-code/platform-engineering/terraform"

def remove_external_backend(filename, backend_name):
    path = os.path.join(base_dir, filename)
    if not os.path.exists(path):
        return

    with open(path, 'r') as f:
        content = f.read()

    # Match block for google_compute_backend_service
    pattern = r'resource "google_compute_backend_service" "' + backend_name + r'" \{.*?\n\}\n*'
    content = re.sub(pattern, '', content, flags=re.DOTALL)

    with open(path, 'w') as f:
        f.write(content)

remove_external_backend("cr_agent_ops.tf", "agent_ops_backend")
remove_external_backend("cr_agent_hr.tf", "agent_hr_backend")
remove_external_backend("cr_market.tf", "market_backend")

print("Removed orphaned external backends for isolated services!")
