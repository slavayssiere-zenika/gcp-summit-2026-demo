import glob
import re

for d in ["agent_router_api", "agent_hr_api", "agent_ops_api", "agent_missions_api"]:
    fpath = f"{d}/agent.py"
    try:
        with open(fpath, "r") as f:
            content = f.read()
        # Find exactly f"{prompts_api_url}/prompts/agent_{aname}.system_instruction"
        # Since it could be "agent_router_api.system_instruction" etc
        new_content = re.sub(r'(\.system_instruction)"', r'\1/compiled"', content)
        with open(fpath, "w") as f:
            f.write(new_content)
        print(f"Patched {fpath}")
    except Exception as e:
        print(e)
