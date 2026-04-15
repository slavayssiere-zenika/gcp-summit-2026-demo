import os
import re

base_dir = "/Users/sebastien.lavayssiere/Code/test-open-code/platform-engineering/terraform"

def fix_resource_names(filename):
    path = os.path.join(base_dir, filename)
    if not os.path.exists(path):
        return

    with open(path, 'r') as f:
        content = f.read()

    # We want to replace `account_id = "sa-agent_ops...` with `sa-agent-ops`
    # We want to replace `name = "neg-agent_ops...` with `neg-agent-ops`
    # We want to replace `name = "backend-agent_ops...` with `backend-agent-ops`
    
    # Simple targeted replacements on strings:
    content = content.replace('"sa-agent_ops', '"sa-agent-ops')
    content = content.replace('"neg-agent_ops', '"neg-agent-ops')
    content = content.replace('"backend-agent_ops', '"backend-agent-ops')
    content = content.replace('"backend-internal-agent_ops', '"backend-internal-agent-ops')
    
    content = content.replace('"sa-agent_hr', '"sa-agent-hr')
    content = content.replace('"neg-agent_hr', '"neg-agent-hr')
    content = content.replace('"backend-agent_hr', '"backend-agent-hr')
    content = content.replace('"backend-internal-agent_hr', '"backend-internal-agent-hr')

    content = content.replace('"sa-agent_router', '"sa-agent-router')
    content = content.replace('"neg-agent_router', '"neg-agent-router')
    content = content.replace('"backend-agent_router', '"backend-agent-router')
    content = content.replace('"backend-internal-agent_router', '"backend-internal-agent-router')

    with open(path, 'w') as f:
        f.write(content)

fix_resource_names("cr_agent_ops.tf")
fix_resource_names("cr_agent_hr.tf")
fix_resource_names("cr_agent_router.tf")

print("Fixed resource names regex compliance!")
