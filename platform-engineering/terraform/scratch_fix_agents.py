import os

base_dir = "/Users/sebastien.lavayssiere/Code/test-open-code/platform-engineering/terraform"

def replace_in_file(filename, old, new):
    path = os.path.join(base_dir, filename)
    if os.path.exists(path):
        with open(path, 'r') as f:
            content = f.read()
        content = content.replace(old, new)
        with open(path, 'w') as f:
            f.write(content)

# Fix agent_sa in router
replace_in_file("cr_agent_router.tf", "google_service_account.agent_sa.email", "google_service_account.agent_router_sa.email")

# Fix agent_sa in hr
replace_in_file("cr_agent_hr.tf", "google_service_account.agent_sa.email", "google_service_account.agent_hr_sa.email")

# Fix agent_sa in ops
replace_in_file("cr_agent_ops.tf", "google_service_account.agent_sa.email", "google_service_account.agent_ops_sa.email")

# Fix Loki VM reference
old_loki = 'value = "http://${google_compute_instance.loki_vm[0].network_interface[0].network_ip}:8080/sse"'
new_loki = 'value = "http://api.internal.zenika/loki-mcp/"'
replace_in_file("cr_agent_ops.tf", old_loki, new_loki)

print("Agent SA & Loki fixes applied!")
