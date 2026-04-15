import re
import os

base_dir = "/Users/sebastien.lavayssiere/Code/test-open-code/platform-engineering/terraform"
cloudrun_tf_path = os.path.join(base_dir, "cloudrun.tf")

with open(cloudrun_tf_path, "r") as f:
    content = f.read()

# We need to extract the three resources explicitly
def extract_and_remove(content, resource_type, resource_name):
    # Regex to find the whole block: resource "type" "name" { ... }
    # This matches the block handling nested braces
    pattern = rf'resource\s+"{resource_type}"\s+"{resource_name}"\s+{{'
    match = re.search(pattern, content)
    if not match:
        return content, ""
    
    start = match.start()
    brace_count = 0
    end = -1
    
    for i in range(start, len(content)):
        if content[i] == '{':
            brace_count += 1
        elif content[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break
                
    if end != -1:
        block = content[start:end]
        # Remove from content
        content = content[:start] + content[end:]
        return content, block
    return content, ""

content, prompts_block = extract_and_remove(content, "google_cloud_run_v2_service", "prompts_api")
content, drive_block = extract_and_remove(content, "google_cloud_run_v2_service", "drive_api")
content, agent_block = extract_and_remove(content, "google_cloud_run_v2_service", "agent_api")
content, mcp_block = extract_and_remove(content, "google_cloud_run_v2_service", "mcp_services")

# Remove locals related to mcp
locals_pattern = r'locals\s+\{\s+mcp_services[\s\S]*?\}'
content = re.sub(locals_pattern, '', content)

# Remove the comments that say "Modèle pour les services", "Services standards"
content = re.sub(r'# ==============================================================\s+# Modèle pour les services avec Sidecar MCP\s+# ==============================================================', '', content)
content = re.sub(r'# ==============================================================\s+# Services standards\s+# ==============================================================', '', content)

with open(os.path.join(base_dir, "cr_prompts.tf"), "w") as f:
    f.write(prompts_block)
    
with open(os.path.join(base_dir, "cr_drive.tf"), "w") as f:
    f.write(drive_block)
    
with open(os.path.join(base_dir, "cr_agent.tf"), "w") as f:
    f.write(agent_block)

# Remove extra newlines in cloudrun.tf
content = re.sub(r'\n{3,}', '\n\n', content)

with open(cloudrun_tf_path, "w") as f:
    f.write(content.strip() + "\n")

print("Cleanup done.")
