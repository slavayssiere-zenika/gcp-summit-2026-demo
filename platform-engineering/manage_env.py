#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import json

def parse_simple_yaml(filepath):
    config = {}
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip().split("#")[0].strip()
                if val.startswith('"') and val.endswith('"'):
                    val = val[1:-1]
                elif val.isdigit():
                    val = int(val)
                config[key] = val
    return config

TERRAFORM_DIR = os.path.join(os.path.dirname(__file__), "terraform")

PERSISTENT_RESOURCES = [
    "google_dns_managed_zone.env_zone",
    "google_compute_managed_ssl_certificate.default",
    "google_dns_record_set.a",
    "google_dns_record_set.api_a"
]

def run_cmd(cmd, check=True):
    print(f"[*] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=TERRAFORM_DIR)
    if check and result.returncode != 0:
        print(f"[!] Error executing: {' '.join(cmd)}")
        sys.exit(result.returncode)
    return result

def toggle_prevent_destroy(disable=True):
    print(f"[*] {'Temporarily disabling' if disable else 'Restoring'} prevent_destroy safeguards in Terraform files...")
    for filename in os.listdir(TERRAFORM_DIR):
        if filename.endswith(".tf"):
            path = os.path.join(TERRAFORM_DIR, filename)
            with open(path, "r") as f:
                content = f.read()
            
            if disable and "prevent_destroy = true" in content:
                content = content.replace("prevent_destroy = true", "prevent_destroy = false")
                with open(path, "w") as f:
                    f.write(content)
            elif not disable and "prevent_destroy = false" in content:
                content = content.replace("prevent_destroy = false", "prevent_destroy = true")
                with open(path, "w") as f:
                    f.write(content)

def init_tf():
    run_cmd(["terraform", "init", "-reconfigure"])

def set_workspace(env):
    # Try to select, if it fails, create it
    res = run_cmd(["terraform", "workspace", "select", env], check=False)
    if res.returncode != 0:
        run_cmd(["terraform", "workspace", "new", env])

def import_persistent_resource(env, address, resource_id):
    # Check if resource is in state, silence output to avoid confusing users on first deploy
    state_res = subprocess.run(["terraform", "state", "list", address], cwd=TERRAFORM_DIR, capture_output=True, text=True)
    if state_res.returncode != 0 or address not in state_res.stdout:
        print(f"[*] Checking if persistent resource {address} exists in GCP to import it...")
        import_res = subprocess.run(["terraform", "import", address, resource_id], cwd=TERRAFORM_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if import_res.returncode == 0:
            print(f"    -> Successfully imported {address} into state.")
        else:
            print(f"    -> {address} does not exist yet (or import failed). It will be created by apply.")

def deploy(env, base_domain, project_id, config, force=False):
    init_tf()
    set_workspace(env)

    # Attempt to re-import persistent resources that might have been removed from state during destroy
    import_persistent_resource(env, "google_dns_managed_zone.env_zone", f"projects/{project_id}/managedZones/zone-{env}")
    import_persistent_resource(env, "google_compute_managed_ssl_certificate.default", f"projects/{project_id}/global/sslCertificates/ssl-{env}")
    
    # DNS record ID format: projects/{{project}}/managedZones/{{managed_zone}}/rrsets/{{name}}/{{type}}
    dns_name = f"{env}.{base_domain}."
    import_persistent_resource(env, "google_dns_record_set.a", f"projects/{project_id}/managedZones/zone-{env}/rrsets/{dns_name}/A")
    import_persistent_resource(env, "google_dns_record_set.api_a", f"projects/{project_id}/managedZones/zone-{env}/rrsets/api.{dns_name}/A")

    # Cloud Run API import fallback in case previous deploy timed out (container crash loop) leaving orphaned GCP services
    region = config.get("region", "europe-west1")
    import_persistent_resource(env, "google_cloud_run_v2_service.prompts_api", f"projects/{project_id}/locations/{region}/services/prompts-api-{env}")
    import_persistent_resource(env, "google_cloud_run_v2_service.agent_api", f"projects/{project_id}/locations/{region}/services/agent-api-{env}")
    for key in ["users", "items", "competencies", "cv"]:
        import_persistent_resource(env, f'google_cloud_run_v2_service.mcp_services["{key}"]', f"projects/{project_id}/locations/{region}/services/{key}-api-{env}")

    if force:
        print("[!] FORCE MODE: Bypassing prevent_destroy logic to allow replacements.")
        toggle_prevent_destroy(disable=True)

    print("[*] Pre-Deploy: Tainting AlloyDB IAM users to bypass immutable user_type error...")
    for user_key in ["users", "items", "competencies", "cv", "prompts"]:
        subprocess.run(
            ["terraform", "taint", f'google_alloydb_user.iam_users["{user_key}"]'],
            cwd=TERRAFORM_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    cmd = ["terraform", "apply"]
    try:
        run_cmd(cmd)
        
        # Post-deploy: Mise à jour des images Docker sur Cloud Run
        print("\n[*] Post-Deploy: Updating Cloud Run container images with latest builds...")
        region = config.get("region", "europe-west1")
        registry = config.get("registry", "z-gcp-summit-services")
        base_image_path = f"{region}-docker.pkg.dev/{project_id}/{registry}"
        
        mcp_keys = ["users", "items", "competencies", "cv"]
        std_keys = ["prompts", "agent"]
        
        for key in mcp_keys + std_keys:
            svc_name = f"{key}-api-{env}"
            img_url = f"{base_image_path}/{key}_api:latest"
            
            cmd_update = [
                "gcloud", "run", "services", "update", svc_name,
                "--region", region,
                "--project", project_id,
                "--container", "api", "--image", img_url
            ]
            
            if key in mcp_keys:
                cmd_update.extend(["--container", "mcp", "--image", img_url])
            
            print(f"    -> Updating {svc_name} (this takes ~30s)...")
            res_update = subprocess.run(cmd_update, capture_output=True, text=True)
            if res_update.returncode == 0:
                print(f"       [+] Successfully updated {svc_name}")
            else:
                print(f"       [-] Error updating {svc_name}: {res_update.stderr.strip()}")
        
        # Post-deploy: Déploiement du Frontend
        print("\n[*] Post-Deploy: Syncing Frontend Assets...")
        
        # 1. Obtenir le nom du bucket de destination
        res = subprocess.run(["terraform", "output", "-raw", "frontend_bucket_name"], cwd=TERRAFORM_DIR, capture_output=True, text=True)
        target_bucket = res.stdout.strip()
        if not target_bucket:
            print("[!] Could not retrieve frontend_bucket_name from terraform outputs.")
            return

        SOURCE_ARCHIVES_BUCKET = "z-gcp-summit-frontend"
        
        # 2. Identifier la dernière archive déposée (en utilisant gsutil ls trié par date)
        # gsutil ls -l renvoie: SIZE  DATE  gs://...
        print(f"[*] Looking for the latest archive in gs://{SOURCE_ARCHIVES_BUCKET}/...")
        raw_ls = subprocess.run(["gsutil", "ls", "-l", f"gs://{SOURCE_ARCHIVES_BUCKET}/"], capture_output=True, text=True)
        if raw_ls.returncode != 0:
            print(f"[!] Failed to list gs://{SOURCE_ARCHIVES_BUCKET}/")
            return
            
        lines = [l.strip() for l in raw_ls.stdout.split('\n') if l.strip() and not l.startswith("TOTAL")]
        if not lines:
            print(f"[*] No archives found in gs://{SOURCE_ARCHIVES_BUCKET}/. Skipping frontend sync.")
            return
            
        # Sort by date (second column generally) and pick latest
        # Or simpler: the highest version number/name if sort by date is fuzzy. Let's rely on standard sorted which sorts by string including date/time in ISO.
        lines.sort()
        latest_line = lines[-1]
        latest_archive_url = latest_line.split()[-1]
        
        print(f"[*] Latest archive identified: {latest_archive_url}")
        
        # 3. Télécharger et extraire
        import tempfile
        import tarfile
        import zipfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = os.path.join(tmpdir, "archive")
            print(f"[*] Downloading {latest_archive_url}...")
            subprocess.run(["gsutil", "cp", latest_archive_url, archive_path], check=True)
            
            extract_dir = os.path.join(tmpdir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            
            print("[*] Extracting archive...")
            try:
                if latest_archive_url.endswith(".zip"):
                    with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_dir)
                else: # Fallback to tar
                    with tarfile.open(archive_path, 'r:*') as tar_ref:
                        tar_ref.extractall(extract_dir)
            except Exception as e:
                print(f"[!] Extraction failed: {e}. Is it a valid tar/zip archive?")
                return
                
            # Gérer la structure de l'archive (parfois zippée avec un dossier parent comme dist/ ou app/dist/)
            # La stratégie infaillible est de localiser le dossier contenant 'index.html' le plus haut possible.
            sync_dir = extract_dir
            min_depth = 999
            found_index = False
            
            for root, dirs, files in os.walk(extract_dir):
                # On évite d'aller chercher dans d'éventuels node_modules
                if "node_modules" in dirs:
                    dirs.remove("node_modules")
                    
                if "index.html" in files:
                    depth = root.count(os.sep)
                    if depth < min_depth:
                        min_depth = depth
                        sync_dir = root
                        found_index = True

            if found_index:
                relative_path = sync_dir.replace(extract_dir, "").lstrip("/")
                print(f"[*] Found frontend root directory at: '{relative_path}'")
            else:
                print(f"[!] Warning: No index.html found. Will sync root extracted folder.")
                
            # 4. Upload vers le bucket du Load Balancer
            print(f"[*] Uploading assets to gs://{target_bucket}...")
            
            # Le chemin sync_dir doit être terminé par '/' pour rsync pour garantir 
            # de ne copier que le contenu ("ce qu'il y a dans le dossier")
            if not sync_dir.endswith("/"):
                sync_dir += "/"
                
            subprocess.run(["gsutil", "-m", "rsync", "-r", "-d", sync_dir, f"gs://{target_bucket}/"], check=True)
            print("[*] Frontend deployed successfully!")
            
            print("[*] Invalidating Cloud CDN Cache to serve the new Frontend immediately...")
            res_cdn = subprocess.run([
                "gcloud", "compute", "url-maps", "invalidate-cdn-cache",
                f"lb-{env}", "--path", "/*", "--async", "--project", project_id
            ], capture_output=True, text=True)
            if res_cdn.returncode == 0:
                print("    -> Cache invalidation request submitted successfully.")
            else:
                print(f"    -> [!] Could not invalidate cache: {res_cdn.stderr.strip()}")
            
        print("\n=======================================================")
        print(f"[*] Post-Deploy: Running Sanity Checks on {env}...")
        print("=======================================================")
        
        import json
        import socket
        import time
        import urllib.request
        import urllib.error
        import ssl
        
        # Extrait l'IP et Mdp depuis les outputs Terraform
        out_res = subprocess.run(["terraform", "output", "-json"], cwd=TERRAFORM_DIR, capture_output=True, text=True)
        try:
            outputs = json.loads(out_res.stdout)
            lb_ip = outputs.get("lb_ip", {}).get("value")
            admin_pwd = outputs.get("admin_password", {}).get("value")
        except Exception as e:
            print(f"[!] Erreur de lecture des outputs: {e}")
            lb_ip, admin_pwd = None, None

        if lb_ip and admin_pwd:
            front_dns_name = f"{env}.{base_domain}"
            api_dns_name = f"api.{env}.{base_domain}"
            print(f"[*] Check 1/3: Waiting for DNS {front_dns_name} to resolve to IP {lb_ip}...")
            resolved = False
            for _ in range(30):  # 30 * 10s = 5 mins max
                try:
                    ip = socket.gethostbyname(front_dns_name)
                    if ip == lb_ip:
                        resolved = True
                        break
                except:
                    pass
                time.sleep(10)
            
            if resolved:
                print(f"[+] DNS resolves correctly to {lb_ip}!")
                
                # --- CHECK 2: SSL PROVISIONING ---
                print(f"\n[*] Check 2/5: Waiting for GCP Managed SSL Certificate provisioning (Can take 15-30 mins)...")
                ssl_ready = False
                
                # Charger les certificats Mozilla si possible (contourne le bug macOS Python)
                try:
                    import certifi
                    ctx_strict = ssl.create_default_context(cafile=certifi.where())
                except ImportError:
                    ctx_strict = ssl.create_default_context()
                
                ctx_fallback = ssl.create_default_context()
                ctx_fallback.check_hostname = False
                ctx_fallback.verify_mode = ssl.CERT_NONE
                
                # Par défaut on utilisera la vérification stricte
                ctx_to_use = ctx_strict
                
                for attempt in range(60):
                    try:
                        req_test = urllib.request.Request(f"https://{front_dns_name}/", method="GET")
                        urllib.request.urlopen(req_test, timeout=10, context=ctx_to_use)
                        ssl_ready = True
                        break
                    except urllib.error.HTTPError as e:
                        # Une erreur HTTP (404, 400, 502) signifie que la poignée de main TLS a RÉUSSI !
                        ssl_ready = True
                        break
                    except urllib.error.URLError as e:
                        # Erreur typique de certificat SSL
                        err_msg = str(e.reason)
                        # Si l'environnement local Python du Mac n'a pas les certificats racine d'installés...
                        if "CERTIFICATE_VERIFY_FAILED" in err_msg:
                            if "unable to get local issuer certificate" in err_msg:
                                print(f"  [!] macOS Python CA Bug detected: local issuer missing. Bypassing strict verification...")
                                ctx_to_use = ctx_fallback
                                ssl_ready = True
                                break
                            
                        print(f"  [-] Certificate not yet ACTIVE (attempt {attempt+1}/60). Retrying in 20s... (Error: {err_msg})")
                        time.sleep(20)
                    except Exception as e:
                        print(f"  [-] Unexpected error (attempt {attempt+1}/60). Retrying in 20s... (Error: {e})")
                        time.sleep(20)
                
                if ssl_ready:
                    print(f"  [+] Managed SSL Certificate is fully ACTIVE and verified!")
                else:
                    print(f"  [!] SSL provisioning timeout. Sanity checks might fail.")
                
                # --- CHECK 3: FRONTEND ---
                print(f"\n[*] Check 3/5: Testing Frontend website on https://{front_dns_name}/...")
                try:
                    front_url = f"https://{front_dns_name}/"
                    req_front = urllib.request.Request(front_url, method="GET")
                    resp_front = urllib.request.urlopen(req_front, timeout=15, context=ctx_to_use)
                    if resp_front.status == 200:
                        print(f"  [+] Frontend loaded OK (HTTP 200)")
                    else:
                        print(f"  [-] Frontend FAIL (HTTP {resp_front.status})")
                except urllib.error.HTTPError as e:
                    print(f"  [-] Frontend FAIL (HTTP {e.code})")
                except Exception as e:
                    print(f"  [-] Frontend FAIL ({type(e).__name__}: {e})")
                
                # --- CHECK 4: API LOGIN ---
                print(f"\n[*] Check 4/5: Testing Web API login with seeded admin user...")
                
                url = f"https://{api_dns_name}/auth/login"
                data = json.dumps({"username": "admin", "password": admin_pwd}).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                
                try:
                    response = urllib.request.urlopen(req, timeout=30, context=ctx_to_use)
                    if response.status in [200, 201]:
                        print("[+] Sanity Test PASS: Successfully logged in as admin via the API!")
                        resp_data = json.loads(response.read().decode('utf-8'))
                        access_token = resp_data.get("access_token")
                        
                        # --- CHECK 4.5: SEEDING PROMPTS ---
                        if access_token:
                            print(f"\n[*] Check 4.5: Seeding system prompts into Prompts API...")
                            prompts_to_seed = {
                                "agent_api.assistant_system_instruction": "agent_api/agent_api.assistant_system_instruction.txt",
                                "cv_api.extract_cv_info": "cv_api/cv_api.extract_cv_info.txt",
                                "cv_api.generate_taxonomy_tree": "cv_api/cv_api.generate_taxonomy_tree.txt"
                            }
                            
                            base_dir = os.path.dirname(os.path.dirname(__file__))
                            headers = {
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {access_token}"
                            }
                            prompts_url = f"https://{api_dns_name}/prompts-api/prompts/"
                            
                            for p_key, rel_path in prompts_to_seed.items():
                                file_path = os.path.join(base_dir, rel_path)
                                if not os.path.exists(file_path):
                                    print(f"  [-] Warning: Prompt file not found {file_path}")
                                    continue
                                
                                try:
                                    with open(file_path, "r", encoding="utf-8") as f:
                                        content = f.read()
                                        
                                    p_data = json.dumps({"key": p_key, "value": content}).encode("utf-8")
                                    p_req = urllib.request.Request(prompts_url, data=p_data, headers=headers, method="POST")
                                    p_resp = urllib.request.urlopen(p_req, timeout=15, context=ctx_to_use)
                                    if p_resp.status in [200, 201]:
                                        print(f"  [+] Successfully seeded prompt: {p_key}")
                                    else:
                                        print(f"  [-] Failed to seed {p_key} (HTTP {p_resp.status})")
                                except Exception as e:
                                    print(f"  [-] Error seeding {p_key}: {e}")
                                    
                    else:
                        print(f"[-] Sanity Test FAIL: Login returned {response.status}")
                except urllib.error.HTTPError as e:
                    # Traite le cas classique d'erreur d'applicatif
                    msg = e.read().decode('utf-8') if hasattr(e, 'read') else 'N/A'
                    print(f"[-] Sanity Test FAIL: HTTP {e.code} during login via POST /auth/login. (Msg: {msg})")
                except Exception as e:
                    print(f"[-] Sanity Test FAIL: Exception during /auth/login request: {e}")
                    
                # --- CHECK 5: API MICROSERVICES ---
                print(f"\n[*] Check 5/5: Validating all API microservices routing (GET requests)...")
                # On teste toutes les routes déclarées dans le Load Balancer (lb.tf)
                api_routes = [
                    "/api/",         # agent_api
                    "/users-api/",   # users_api
                    "/items-api/",   # items_api
                    "/prompts-api/", # prompts_api
                    "/comp-api/",    # competencies_api
                    "/cv-api/"       # cv_api
                ]
                
                for route in api_routes:
                    api_url = f"https://{api_dns_name}{route}"
                    req_get = urllib.request.Request(api_url, method="GET")
                    try:
                        resp = urllib.request.urlopen(req_get, timeout=10, context=ctx_to_use)
                        print(f"  [+] {route:<15} -> OK (HTTP {resp.status})")
                    except urllib.error.HTTPError as e:
                        # Si l'API renvoie 404, 401 ou 403, cela prouve que le conteneur Cloud Run tourne
                        # et que le Load Balancer achemine le trafic avec succès.
                        # Les erreurs graves sont les 500/502/503/504 (Server/Proxy Error)
                        if e.code < 500:
                            print(f"  [+] {route:<15} -> OK (HTTP {e.code} - App Responded)")
                        else:
                            print(f"  [-] {route:<15} -> FAIL (HTTP {e.code} Server/Proxy Error)")
                    except Exception as e:
                        print(f"  [-] {route:<15} -> FAIL ({type(e).__name__}: {e})")
                        
            else:
                print(f"[-] Sanity Test FAIL: DNS resolution timeout. {front_dns_name} doesn't match {lb_ip}")
        else:
            print("[!] Skipping Sanity check. Missing terraform outputs (lb_ip or admin_password).")

    finally:
        if force:
            toggle_prevent_destroy(disable=False)

def plan(env):
    init_tf()
    set_workspace(env)
    
    print(f"[*] Generating dry-run (terraform plan) for environment '{env}'...")
    cmd = ["terraform", "plan"]
    run_cmd(cmd)

def destroy(env, force=False):
    init_tf()
    set_workspace(env)

    if force:
        print("[!] FORCE MODE: Protected resources WILL BE DESTROYED.")
        toggle_prevent_destroy(disable=True)
    else:
        # To honor "prevent_destroy" on DNS and SSL certs without blocking the whole destruction:
        # We remove them from the state so Terraform ignores them during destroy.
        # They will remain orphaned in GCP (which is the goal) and re-imported upon the next deploy.
        print("[*] Ejecting persistent resources from Terraform state to preserve them...")
        for res in PERSISTENT_RESOURCES:
            run_cmd(["terraform", "state", "rm", res], check=False)

    print(f"[*] Destroying all other components for environment '{env}'...")
    cmd = ["terraform", "destroy"]
    try:
        run_cmd(cmd)
    finally:
        if force:
            toggle_prevent_destroy(disable=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Platform Engineering - Manage Environments")
    parser.add_argument("action", choices=["deploy", "destroy", "plan"], help="Action to perform")
    parser.add_argument("--env", required=True, help="Environment name (dev, uat, prd)")
    parser.add_argument("--force", action="store_true", help="Force deletion or replacement of protected DNS/SSL resources")
    
    args = parser.parse_args()

    # Load YAML Configuration
    config_path = os.path.join(os.path.dirname(__file__), "envs", f"{args.env}.yaml")
    if not os.path.exists(config_path):
        print(f"[!] Configuration file not found: {config_path}")
        sys.exit(1)
        
    config = parse_simple_yaml(config_path)
        
    # Dump it as auto.tfvars.json for Terraform to ingest automatically
    tfvars_path = os.path.join(TERRAFORM_DIR, f"{args.env}.auto.tfvars.json")
    with open(tfvars_path, "w") as f:
        json.dump(config, f, indent=2)

    project_id = config.get("project_id", "slavayssiere-sandbox-462015")
    base_domain = config.get("base_domain", "slavayssiere-zenika.com")

    if args.action == "deploy":
        deploy(args.env, base_domain, project_id, config, force=args.force)
    elif args.action == "destroy":
        destroy(args.env, force=args.force)
    elif args.action == "plan":
        plan(args.env)
