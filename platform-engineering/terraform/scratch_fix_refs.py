import os
import re
import glob

base_dir = "/Users/sebastien.lavayssiere/Code/test-open-code/platform-engineering/terraform"

for filepath in glob.glob(os.path.join(base_dir, "*.tf")):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # replace cr_sa["agent"] to agent_router_sa
    content = content.replace('google_service_account.cr_sa["agent"]', 'google_service_account.agent_router_sa')
    
    # replace the rest
    content = re.sub(r'google_service_account\.cr_sa\["([^"]+)"\]', r'google_service_account.\g<1>_sa', content)
    
    with open(filepath, 'w') as f:
        f.write(content)
        
print("References fixed!")
