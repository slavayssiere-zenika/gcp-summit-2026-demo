import os
import re

base_dir = "/Users/sebastien.lavayssiere/Code/test-open-code/platform-engineering/terraform"

services = ["users", "items", "competencies", "cv", "missions", "prompts", "drive", "market", "agent_router", "agent_hr", "agent_ops"]
# analytics_mcp will be "market"
# agent_api will be replaced by agent_router, agent_hr, agent_ops

def read_tf(filename):
    with open(os.path.join(base_dir, filename), 'r') as f:
        return f.read()

def write_tf(filename, content):
    with open(os.path.join(base_dir, filename), 'w') as f:
        f.write(content.strip() + "\n")

# -- 1. Distribute Service Accounts and their bindings into their respective files --
# We will create a string builder for each service
unrolled_blocks = {s: [] for s in services}

for svc in services:
    sa_id = f"sa-{svc}-${{terraform.workspace}}-${{random_id.sa_suffix.hex}}"
    if svc == "drive":
        sa_id = f"sa-drive-${{terraform.workspace}}-v2"
        
    sa_block = f"""
# ==========================================
# Identité et Permissions
# ==========================================
resource "google_service_account" "{svc}_sa" {{
  account_id = "{sa_id}"
  create_ignore_already_exists = true
}}

resource "google_secret_manager_secret_iam_member" "{svc}_jwt_access" {{
  project   = data.google_secret_manager_secret.jwt_secret.project
  secret_id = data.google_secret_manager_secret.jwt_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${{google_service_account.{svc}_sa.email}}"
}}

resource "google_project_iam_member" "{svc}_otel_trace" {{
  project  = var.project_id
  role     = "roles/cloudtrace.agent"
  member   = "serviceAccount:${{google_service_account.{svc}_sa.email}}"
}}

resource "google_project_iam_member" "{svc}_otel_metric" {{
  project  = var.project_id
  role     = "roles/monitoring.metricWriter"
  member   = "serviceAccount:${{google_service_account.{svc}_sa.email}}"
}}

resource "google_project_iam_member" "{svc}_alloydb_client" {{
  project  = var.project_id
  role     = "roles/alloydb.client"
  member   = "serviceAccount:${{google_service_account.{svc}_sa.email}}"
}}

resource "google_project_iam_member" "{svc}_alloydb_databaseUser" {{
  project  = var.project_id
  role     = "roles/alloydb.databaseUser"
  member   = "serviceAccount:${{google_service_account.{svc}_sa.email}}"
}}

resource "google_alloydb_user" "{svc}_db_user" {{
  cluster    = google_alloydb_cluster.main.name
  user_id    = replace(google_service_account.{svc}_sa.email, ".gserviceaccount.com", "")
  user_type  = "ALLOYDB_IAM_USER"
  depends_on = [google_alloydb_instance.primary]
  lifecycle {{
    ignore_changes = [database_roles]
  }}
}}

# Autorisation invocation interne LB
resource "google_cloud_run_v2_service_iam_member" "{svc}_invoker" {{
  project  = google_cloud_run_v2_service.{svc}_api.project
  location = google_cloud_run_v2_service.{svc}_api.location
  name     = google_cloud_run_v2_service.{svc}_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}}

# ==========================================
# Routage et Load Balancing
# ==========================================
resource "google_compute_region_network_endpoint_group" "{svc}_neg" {{
  name                  = "neg-{svc}-${{terraform.workspace}}"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {{
    service = google_cloud_run_v2_service.{svc}_api.name
  }}
}}

resource "google_compute_backend_service" "{svc}_backend" {{
  name                  = "backend-{svc}-${{terraform.workspace}}"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.waf.id
  backend {{
    group = google_compute_region_network_endpoint_group.{svc}_neg.id
  }}
}}

resource "google_compute_region_backend_service" "{svc}_internal_backend" {{
  name                  = "backend-internal-{svc}-${{terraform.workspace}}"
  region                = var.region
  protocol              = "HTTP"
  load_balancing_scheme = "INTERNAL_MANAGED"
  backend {{
    group           = google_compute_region_network_endpoint_group.{svc}_neg.id
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
  }}
}}
"""
    
    # Custom extras
    if svc in ["cv", "missions", "agent_router", "agent_hr", "agent_ops"]:
        sa_block += f"""
resource "google_secret_manager_secret_iam_member" "{svc}_gemini_access" {{
  project   = data.google_secret_manager_secret.gemini_api_key.project
  secret_id = data.google_secret_manager_secret.gemini_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${{google_service_account.{svc}_sa.email}}"
}}
"""
    if svc == "users":
        sa_block += f"""
resource "google_secret_manager_secret_iam_member" "users_admin_pwd_access" {{
  project   = google_secret_manager_secret.admin_password.project
  secret_id = google_secret_manager_secret.admin_password.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${{google_service_account.users_sa.email}}"
}}
resource "google_secret_manager_secret_iam_member" "users_google_secret_id_access" {{
  project   = data.google_secret_manager_secret.google_secret_id.project
  secret_id = data.google_secret_manager_secret.google_secret_id.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${{google_service_account.users_sa.email}}"
}}
resource "google_secret_manager_secret_iam_member" "users_google_secret_key_access" {{
  project   = data.google_secret_manager_secret.google_secret_key.project
  secret_id = data.google_secret_manager_secret.google_secret_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${{google_service_account.users_sa.email}}"
}}
"""
    if svc == "missions":
        sa_block += f"""
resource "google_project_iam_member" "missions_documentai_user" {{
  project = var.project_id
  role    = "roles/documentai.apiUser"
  member  = "serviceAccount:${{google_service_account.missions_sa.email}}"
}}
"""
    if svc in ["agent_router", "agent_hr", "agent_ops"]:
        sa_block += f"""
resource "google_project_iam_member" "{svc}_logging_viewer" {{
  project = var.project_id
  role    = "roles/logging.viewer"
  member  = "serviceAccount:${{google_service_account.{svc}_sa.email}}"
}}
"""

    if svc == "market":
        sa_block += f"""
resource "google_project_iam_member" "market_bq_admin" {{
  project = var.project_id
  role    = "roles/bigquery.admin"
  member  = "serviceAccount:${{google_service_account.analytics_sa.email}}"
}}
resource "google_project_iam_member" "market_bq_job_user" {{
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${{google_service_account.analytics_sa.email}}"
}}
resource "google_project_iam_member" "market_trace_user" {{
  project = var.project_id
  role    = "roles/cloudtrace.user"
  member  = "serviceAccount:${{google_service_account.analytics_sa.email}}"
}}
"""

    if "market" in svc:
        sa_block = sa_block.replace(f"google_cloud_run_v2_service.{svc}_api", f"google_cloud_run_v2_service.analytics_mcp")
        
    unrolled_blocks[svc].append(sa_block)

# Let's fix the files by appending these blocks and replacing internal google_service_account references
for svc in services:
    if svc == "market":
        fname = "cr_market.tf" # wait, earlier we viewed cloudrun.tf and it had resource "google_cloud_run_v2_service" "analytics_mcp"
        fname = "cr_agent.tf" # let's just make sure cr_market.tf is where analytics_mcp lives
        pass
    
    # We will just append them to the existing cr_*.tf
    # But FIRST we must substitute 'google_service_account.cr_sa["cv"].email' -> 'google_service_account.cv_sa.email'
    pass

for svc in services:
    fname = f"cr_{svc}.tf"
    if svc == "market":
        # Check if cr_market.tf exists
        if not os.path.exists(os.path.join(base_dir, "cr_market.tf")):
            with open(os.path.join(base_dir, "cr_market.tf"), "w") as f:
                # Need to move analytics_mcp here if not done
                pass
                
    if os.path.exists(os.path.join(base_dir, fname)):
        with open(os.path.join(base_dir, fname), "a") as f:
            f.write("\n" + "\n".join(unrolled_blocks[svc]))
            
        # Replace occurrences in the file
        content = read_tf(fname)
        content = re.sub(r'google_service_account\.cr_sa\["([^"]+)"\]', f'google_service_account.\g<1>_sa', content)
        # Handle time_sleep replacement
        content = re.sub(r'depends_on\s*=\s*\[\s*time_sleep\.wait_for_iam_propagation\s*,', 'depends_on = [', content)
        content = re.sub(r'time_sleep\.wait_for_iam_propagation\s*,?', '', content)
        write_tf(fname, content)

# -- 2. Cleanup cloudrun.tf --
cloudrun_tf = read_tf("cloudrun.tf")
# Delete everything related to cr_sa
cloudrun_tf = re.sub(r'resource "google_service_account" "cr_sa".*?create_ignore_already_exists = true\n\}', '', cloudrun_tf, flags=re.DOTALL)
# Delete all google_secret_manager_secret_iam_member
cloudrun_tf = re.sub(r'resource "google_secret_manager_secret_iam_member" [^}]+\}', '', cloudrun_tf, flags=re.DOTALL)
# Delete all google_project_iam_member
cloudrun_tf = re.sub(r'resource "google_project_iam_member" [^}]+\}', '', cloudrun_tf, flags=re.DOTALL)
# Delete time_sleep
cloudrun_tf = re.sub(r'resource "time_sleep" "wait_for_iam_propagation" [^}]+\}', '', cloudrun_tf, flags=re.DOTALL)
# Delete cloud_run_v2_service_iam_member
cloudrun_tf = re.sub(r'resource "google_cloud_run_v2_service_iam_member" [^}]+\}', '', cloudrun_tf, flags=re.DOTALL)
# Replace cloud_scheduler cr_sa reference
cloudrun_tf = cloudrun_tf.replace('google_service_account.cr_sa["drive"].email', 'google_service_account.drive_sa.email')

write_tf("cloudrun.tf", cloudrun_tf)

# -- 3. Cleanup database.tf --
database_tf = read_tf("database.tf")
database_tf = re.sub(r'resource "google_alloydb_user" "iam_users".*?ignore_changes = \[database_roles\]\n  \}\n\}', '', database_tf, flags=re.DOTALL)
write_tf("database.tf", database_tf)

# -- 4. Cleanup lb.tf --
lb_tf = read_tf("lb.tf")
# Delete all NEGs
lb_tf = re.sub(r'resource "google_compute_region_network_endpoint_group" [^}]+\}\n\}', '', lb_tf, flags=re.DOTALL)
# Also single nested cloud run ones
lb_tf = re.sub(r'resource "google_compute_region_network_endpoint_group" [^\{]+\{.*?cloud_run \{.*?\}\n\}', '', lb_tf, flags=re.DOTALL)

# Delete all Backend Services
lb_tf = re.sub(r'resource "google_compute_backend_service" "mcp_backend" [^\{]+\{.*?backend \{.*?\}\n\}', '', lb_tf, flags=re.DOTALL)
lb_tf = re.sub(r'resource "google_compute_backend_service" "[^"]+" [^\{]+\{.*?backend \{.*?\}\n\}', '', lb_tf, flags=re.DOTALL)

# In URL Map, replace references
# old: service = google_compute_backend_service.mcp_backend["users"].id -> new: service = google_compute_backend_service.users_backend.id
lb_tf = re.sub(r'service = google_compute_backend_service\.mcp_backend\["([^"]+)"\]\.id', r'service = google_compute_backend_service.\g<1>_backend.id', lb_tf)
# old: service = google_compute_backend_service.agent_backend.id -> new: service = google_compute_backend_service.agent_router_backend.id
lb_tf = lb_tf.replace("google_compute_backend_service.agent_backend.id", "google_compute_backend_service.agent_router_backend.id")
lb_tf = lb_tf.replace("google_compute_backend_service.prompts_backend.id", "google_compute_backend_service.prompts_backend.id")

write_tf("lb.tf", lb_tf)

# -- 5. Cleanup lb-internal.tf --
lbi_tf = read_tf("lb-internal.tf")
lbi_tf = re.sub(r'resource "google_compute_region_backend_service" [^\{]+\{.*?backend \{.*?\}\n\}', '', lbi_tf, flags=re.DOTALL)

lbi_tf = re.sub(r'default_service = google_compute_region_backend_service\.internal_mcp_backend\["([^"]+)"\]\.id', r'default_service = google_compute_region_backend_service.\g<1>_internal_backend.id', lbi_tf)
lbi_tf = re.sub(r'service\s*=\s*google_compute_region_backend_service\.internal_mcp_backend\["([^"]+)"\]\.id', r'service = google_compute_region_backend_service.\g<1>_internal_backend.id', lbi_tf)

lbi_tf = lbi_tf.replace("google_compute_region_backend_service.internal_prompts_backend.id", "google_compute_region_backend_service.prompts_internal_backend.id")
lbi_tf = lbi_tf.replace("google_compute_region_backend_service.internal_drive_backend.id", "google_compute_region_backend_service.drive_internal_backend.id")
lbi_tf = lbi_tf.replace("google_compute_region_backend_service.internal_market_backend.id", "google_compute_region_backend_service.market_internal_backend.id")
write_tf("lb-internal.tf", lbi_tf)

# -- 6. Cleanup pubsub.tf --
pub_tf = read_tf("pubsub.tf")
pub_tf = re.sub(r'google_cloud_run_v2_service\.mcp_services\["([^"]+)"\]', r'google_cloud_run_v2_service.\g<1>_api', pub_tf)
write_tf("pubsub.tf", pub_tf)

print("Unrolling applied!")
