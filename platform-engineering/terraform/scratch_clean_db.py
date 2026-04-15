import os
import re

base_dir = "/Users/sebastien.lavayssiere/Code/test-open-code/platform-engineering/terraform"

def remove_alloydb_blocks(filename):
    path = os.path.join(base_dir, filename)
    if not os.path.exists(path):
        return

    with open(path, 'r') as f:
        content = f.read()

    # Match block for google_project_iam_member alloydb_client
    content = re.sub(r'resource "google_project_iam_member" "[^"]+_alloydb_client" \{.*?\}\n+', '', content, flags=re.DOTALL)
    
    # Match block for google_project_iam_member alloydb_databaseUser
    content = re.sub(r'resource "google_project_iam_member" "[^"]+_alloydb_databaseUser" \{.*?\}\n+', '', content, flags=re.DOTALL)
    
    # Match block for google_alloydb_user
    content = re.sub(r'resource "google_alloydb_user" "[^"]+" \{.*?\}\n+', '', content, flags=re.DOTALL)

    with open(path, 'w') as f:
        f.write(content)

remove_alloydb_blocks("cr_agent_ops.tf")
remove_alloydb_blocks("cr_agent_hr.tf")
remove_alloydb_blocks("cr_agent_router.tf")
remove_alloydb_blocks("cr_market.tf")

print("Removed AlloyDB configurations from non-database agents")
