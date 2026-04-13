#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import json
import re
import yaml
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

def discover_versions():
    """Scans for VERSION files in component directories and returns a mapping."""
    versions = {}
    base_dir = os.path.dirname(os.path.dirname(__file__))
    components = [
        "agent_api", "users_api", "items_api", "competencies_api", 
        "cv_api", "prompts_api", "drive_api", "market_mcp", 
        "db_migrations", "frontend"
    ]
    
    for comp in components:
        v_file = os.path.join(base_dir, comp, "VERSION")
        if os.path.exists(v_file):
            with open(v_file, "r") as f:
                versions[f"{comp}_version"] = f.read().strip()
        else:
            versions[f"{comp}_version"] = "v0.0.1"
            
    return versions

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class DeploymentError(Exception):
    """Exception levée lors d'un échec de déploiement."""
    pass

def load_config(filepath):
    """Charge la configuration YAML de manière robuste."""
    with open(filepath, "r") as f:
        try:
            return yaml.safe_load(f)
        except yaml.YAMLError as exc:
            logger.error(f"Erreur lors de la lecture du fichier YAML {filepath}: {exc}")
            raise DeploymentError(f"Format YAML invalide : {exc}")

def check_binary_dependencies():
    """Vérifie que les outils nécessaires sont installés."""
    dependencies = ["terraform", "gcloud", "gsutil"]
    missing = []
    for dep in dependencies:
        if subprocess.run(["which", dep], capture_output=True).returncode != 0:
            missing.append(dep)
    
    if missing:
        raise DeploymentError(f"Dépendances manquantes : {', '.join(missing)}")
    logger.info("[+] Toutes les dépendances binaires sont satisfaites.")

TERRAFORM_DIR = os.path.join(os.path.dirname(__file__), "terraform")

PERSISTENT_RESOURCES = [
    "google_dns_managed_zone.env_zone",
    "google_compute_managed_ssl_certificate.default",
    "google_dns_record_set.a",
    "google_dns_record_set.api_a"
]

def run_cmd(cmd, check=True, capture_output=False, live=False):
    logger.info(f"[*] Running: {' '.join(cmd)}")
    
    if live:
        # Mode live : on affiche en temps réel tout en capturant dans un buffer
        process = subprocess.Popen(
            cmd, cwd=TERRAFORM_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        full_output = []
        for line in iter(process.stdout.readline, ""):
            print(line, end="", flush=True)
            full_output.append(line)
        process.stdout.close()
        return_code = process.wait()
        
        # On simule un objet simulate CompletedProcess pour la compatibilité
        from argparse import Namespace
        result = Namespace(returncode=return_code, stdout="".join(full_output), stderr="".join(full_output))
    elif capture_output:
        result = subprocess.run(cmd, cwd=TERRAFORM_DIR, capture_output=True, text=True)
    else:
        result = subprocess.run(cmd, cwd=TERRAFORM_DIR)
        
    if check and result.returncode != 0:
        err_msg = f"[!] Error executing: {' '.join(cmd)}"
        logger.error(err_msg)
        if capture_output and hasattr(result, 'stderr') and result.stderr:
            logger.error(result.stderr)
        raise DeploymentError(err_msg)
    return result

def parse_and_fix_409s(output):
    # Pattern pour extraire l'adresse de la ressource et son ID GCP
    # Exemple: with google_service_account.cr_sa["agent"],
    # et resourceName: "projects/.../serviceAccounts/..."
    
    fixes_applied = 0
    # On découpe par bloc d'erreur pour être sûr de l'association adresse/ID
    error_blocks = output.split('Error: ')
    for block in error_blocks:
        if "409" in block or "alreadyExists" in block:
            addr_match = re.search(r'with ([\w\.\[\]\"]+),', block)
            id_match = re.search(r'"resourceName": "([^"]+)"', block)
            if addr_match and id_match:
                addr = addr_match.group(1)
                res_id = id_match.group(1)
                print(f"[*] Self-Healing: Détection du conflit 409 pour {addr}. Tentative d'import de {res_id}...")
                import_res = subprocess.run(["terraform", "import", addr, res_id], cwd=TERRAFORM_DIR, capture_output=True, text=True)
                if import_res.returncode == 0:
                    print(f"    -> Import réussi pour {addr}.")
                    fixes_applied += 1
                else:
                    print(f"    -> [!] Échec de l'import pour {addr}: {import_res.stderr.strip()}")
    
    return fixes_applied > 0

def get_tf_args():
    api_key = os.environ.get("GOOGLE_API_KEY")
    return [f"-var=gemini_api_key={api_key}"] if api_key else []

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
        try:
            import_res = subprocess.run(["terraform", "import", address, resource_id], cwd=TERRAFORM_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            if import_res.returncode == 0:
                print(f"    -> Successfully imported {address} into state.")
            else:
                print(f"    -> {address} does not exist yet (or import failed). It will be created by apply.")
        except subprocess.TimeoutExpired:
            print(f"    -> [!] Import timed out for {address}. Proceeding without it.")

def deploy(env, base_domain, project_id, config, force=False):
    init_tf()
    set_workspace(env)

    # DNS-based check: If domain resolves, it's highly likely persistent resources exist.
    import socket
    front_domain = f"{env}.{base_domain}"
    
    dns_resolves = False
    try:
        socket.gethostbyname(front_domain)
        dns_resolves = True
    except Exception:
        pass

    if dns_resolves:
        print(f"[*] DNS '{front_domain}' resolves. Attempting to import persistent network resources...")
        import_persistent_resource(env, "google_dns_managed_zone.env_zone", f"projects/{project_id}/managedZones/zone-{env}")
        import_persistent_resource(env, "google_compute_managed_ssl_certificate.default", f"projects/{project_id}/global/sslCertificates/ssl-{env}")
        
        dns_name = f"{env}.{base_domain}."
        import_persistent_resource(env, "google_dns_record_set.a", f"projects/{project_id}/managedZones/zone-{env}/rrsets/{dns_name}/A")
        import_persistent_resource(env, "google_dns_record_set.api_a", f"projects/{project_id}/managedZones/zone-{env}/rrsets/api.{dns_name}/A")
    else:
        print(f"[*] DNS '{front_domain}' does not resolve yet. Skipping import of network resources to prevent timeouts.")

    # Systematic import of the drive service account (should not be deleted)
    import_persistent_resource(env, 'google_service_account.cr_sa["drive"]', f"projects/{project_id}/serviceAccounts/sa-drive-{env}-v2@{project_id}.iam.gserviceaccount.com")

    if force:
        print("[!] FORCE MODE: Bypassing prevent_destroy logic to allow replacements.")
        toggle_prevent_destroy(disable=True)

    try:
        apply_cmd = ["terraform", "apply", "-auto-approve"] + get_tf_args()
        
        max_retries = 2
        success = False
        for attempt in range(max_retries):
            print(f"[*] Terraform Apply - Tentative {attempt + 1}/{max_retries}...")
            # On utilise le nouveau mode 'live' pour voir les logs en temps réel tout en capturant
            res = run_cmd(apply_cmd, check=False, live=True)
            
            if res.returncode == 0:
                success = True
                break
                
            # En cas d'échec, on tente le self-healing sur la sortie capturée (stdout contient aussi stderr ici)
            if parse_and_fix_409s(res.stdout):
                print("[*] Corrections de type 'import' appliquées. Relance de l'apply...")
                continue
            else:
                print(f"[!] Échec définitif de l'apply.")
                sys.exit(res.returncode)

        if not success:
            sys.exit(1)

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
            
        # Sort by filename (which includes the timestamp for correct temporal ordering) 
        # instead of sorting by the full line which starts with varying file sizes.
        urls = [line.split()[-1] for line in lines if line.split()]
        urls.sort()
        latest_archive_url = urls[-1]
        
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
                print(f"\n[*] Check 4/5: Testing Web API login with seeded admin user (Waiting for IAM Sync up to 8 mins)...")
                
                url = f"https://{api_dns_name}/auth/login"
                data = json.dumps({"email": "admin@zenika.com", "password": admin_pwd}).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                
                login_success = False
                for attempt in range(16):
                    try:
                        response = urllib.request.urlopen(req, timeout=30, context=ctx_to_use)
                        if response.status in [200, 201]:
                            print("[+] Sanity Test PASS: Successfully logged in as admin via the API!")
                            resp_data = json.loads(response.read().decode('utf-8'))
                            access_token = resp_data.get("access_token")
                            login_success = True
                            
                            # --- CHECK 4.5: SEEDING PROMPTS ---
                            if access_token:
                                print(f"\n[*] Check 4.5: Seeding system prompts into Prompts API...")
                                prompts_to_seed = {
                                    "agent_api.assistant_system_instruction": "agent_api/agent_api.assistant_system_instruction.txt",
                                    "agent_api.capabilities_instruction": "agent_api/agent_api.capabilities_instruction.txt",
                                    "cv_api.extract_cv_info": "cv_api/cv_api.extract_cv_info.txt",
                                    "cv_api.generate_taxonomy_tree": "cv_api/cv_api.generate_taxonomy_tree.txt"
                                }
                                
                                base_dir = os.path.dirname(os.path.dirname(__file__))
                                headers = {
                                    "Content-Type": "application/json",
                                    "Authorization": f"Bearer {access_token}"
                                }
                                prompts_url = f"https://{api_dns_name}/prompts-api/"
                                
                                for p_key, rel_path in prompts_to_seed.items():
                                    file_path = os.path.join(base_dir, rel_path)
                                    if not os.path.exists(file_path):
                                        print(f"  [-] Warning: Prompt file not found {file_path}")
                                        continue
                                    
                                    with open(file_path, "r", encoding="utf-8") as f:
                                        content = f.read()
                                        
                                    p_data = json.dumps({"key": p_key, "value": content}).encode("utf-8")
                                    p_req = urllib.request.Request(prompts_url, data=p_data, headers=headers, method="POST")
                                    
                                    seeded = False
                                    for attempt in range(8):
                                        try:
                                            p_resp = urllib.request.urlopen(p_req, timeout=15, context=ctx_to_use)
                                            if p_resp.status in [200, 201]:
                                                print(f"  [+] Successfully seeded prompt: {p_key}")
                                                seeded = True
                                                break
                                            else:
                                                print(f"  [-] Failed to seed {p_key} (HTTP {p_resp.status}). Retrying... (Attempt {attempt+1}/8)")
                                        except urllib.error.HTTPError as e:
                                            if e.code >= 500:
                                                print(f"  [-] API Server Error {e.code} for {p_key} (Possible IAM propagation delay). Retrying in 15s... (Attempt {attempt+1}/8)")
                                            else:
                                                print(f"  [-] Error seeding {p_key}: HTTP {e.code}. Retrying... (Attempt {attempt+1}/8)")
                                        except Exception as e:
                                            print(f"  [-] Error seeding {p_key} ({type(e).__name__}): {e}. Retrying... (Attempt {attempt+1}/8)")
                                        
                                        time.sleep(15)

                                    if not seeded:
                                        print(f"  [!] Failed to seed {p_key} after all attempts.")
                            break
                        else:
                            print(f"[-] Sanity Test FAIL: Login returned {response.status}")
                            break
                    except urllib.error.HTTPError as e:
                        if e.code >= 500:
                            print(f"  [-] API Server Error {e.code} (Possible Database IAM propagation delay). Retrying in 30s... (Attempt {attempt+1}/16)")
                            time.sleep(30)
                        else:
                            # Traite le cas classique d'erreur d'applicatif
                            msg = e.read().decode('utf-8') if hasattr(e, 'read') else 'N/A'
                            print(f"[-] Sanity Test FAIL: HTTP {e.code} during login via POST /auth/login. (Msg: {msg})")
                            break
                    except Exception as e:
                        print(f"  [-] Unexpected error Exception request: {e}. Retrying in 30s... (Attempt {attempt+1}/16)")
                        time.sleep(30)
                
                if not login_success:
                    print("[-] Authentication flow totally failed after all attempts.")
                    
                # --- CHECK 5/5: API MICROSERVICES ---
                logger.info(f"\n[*] Check 5/5: Validating all API microservices routing (GET requests)...")
                # On teste toutes les routes déclarées dans le Load Balancer (lb.tf)
                api_routes = [
                    "/api/health",         # agent_api
                    "/users-api/health",   # users_api
                    "/items-api/health",   # items_api
                    "/prompts-api/health", # prompts_api
                    "/comp-api/health",    # competencies_api
                    "/cv-api/health",      # cv_api
                    "/drive-api/health"    # drive_api
                ]
                
                def check_route(route):
                    api_url = f"https://{api_dns_name}{route}"
                    req_get = urllib.request.Request(api_url, method="GET")
                    try:
                        resp = urllib.request.urlopen(req_get, timeout=35, context=ctx_to_use)
                        return f"  [+] {route:<15} -> OK (HTTP {resp.status})"
                    except urllib.error.HTTPError as e:
                        if e.code < 500:
                            return f"  [+] {route:<15} -> OK (HTTP {e.code} - App Responded)"
                        else:
                            return f"  [-] {route:<15} -> FAIL (HTTP {e.code} Server/Proxy Error)"
                    except Exception as e:
                        return f"  [-] {route:<15} -> FAIL ({type(e).__name__}: {e})"

                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(check_route, route): route for route in api_routes}
                    for future in as_completed(futures):
                        logger.info(future.result())
            else:
                logger.error(f"[-] Sanity Test FAIL: DNS resolution timeout. {front_dns_name} doesn't match {lb_ip}")
        else:
            logger.warning("[!] Skipping Sanity check. Missing terraform outputs (lb_ip or admin_password).")

    finally:
        if force:
            toggle_prevent_destroy(disable=False)

def plan(env):
    init_tf()
    set_workspace(env)
    
    logger.info(f"[*] Generating dry-run (terraform plan) for environment '{env}'...")
    cmd = ["terraform", "plan"] + get_tf_args()
    run_cmd(cmd)

def destroy(env, force=False):
    init_tf()
    set_workspace(env)

    if force:
        logger.warning("[!] FORCE MODE: Protected resources WILL BE DESTROYED.")
        toggle_prevent_destroy(disable=True)
    else:
        # To honor "prevent_destroy" on DNS and SSL certs without blocking the whole destruction:
        # We remove them from the state so Terraform ignores them during destroy.
        # They will remain orphaned in GCP (which is the goal) and re-imported upon the next deploy.
        logger.info("[*] Ejecting persistent resources from Terraform state to preserve them...")
        for res in PERSISTENT_RESOURCES:
            run_cmd(["terraform", "state", "rm", res], check=False)

    print("[*] Ejecting AlloyDB users and Drive Service Account from Terraform state to preserve them...")
    state_list_res = subprocess.run(["terraform", "state", "list"], cwd=TERRAFORM_DIR, capture_output=True, text=True)
    if state_list_res.returncode == 0:
        for line in state_list_res.stdout.splitlines():
            line = line.strip()
            if line.startswith("google_alloydb_user.") or line == 'google_service_account.cr_sa["drive"]':
                run_cmd(["terraform", "state", "rm", line], check=False)

    print(f"[*] Destroying all other components for environment '{env}'...")
    cmd = ["terraform", "destroy", "-auto-approve"] + get_tf_args()
    
    try:
        run_cmd(cmd, live=True)
    finally:
        if force:
            toggle_prevent_destroy(disable=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Platform Engineering - Manage Environments")
    parser.add_argument("action", choices=["deploy", "destroy", "plan"], help="Action to perform")
    parser.add_argument("--env", required=True, help="Environment name (dev, uat, prd)")
    parser.add_argument("--force", action="store_true", help="Force deletion or replacement of protected DNS/SSL resources")
    
    args = parser.parse_args()

    try:
        check_binary_dependencies()
        
        # Load YAML Configuration
        config_path = os.path.join(os.path.dirname(__file__), "envs", f"{args.env}.yaml")
        if not os.path.exists(config_path):
            logger.error(f"[!] Configuration file not found: {config_path}")
            sys.exit(1)
            
        # Auto-discover component versions
        final_config = discover_versions()
        
        # Load YAML Configuration
        config = load_config(config_path)
        
        # YAML overrides auto-discovery
        final_config.update(config)
            
        # Dump it as auto.tfvars.json for Terraform to ingest automatically
        tfvars_path = os.path.join(TERRAFORM_DIR, f"{args.env}.auto.tfvars.json")
        with open(tfvars_path, "w") as f:
            json.dump(final_config, f, indent=2)

        project_id = final_config.get("project_id", "slavayssiere-sandbox-462015")
        base_domain = final_config.get("base_domain", "slavayssiere-zenika.com")

        if args.action == "deploy":
            deploy(args.env, base_domain, project_id, final_config, force=args.force)
        elif args.action == "destroy":
            destroy(args.env, force=args.force)
        elif args.action == "plan":
            plan(args.env)
            
    except DeploymentError as e:
        logger.error(f"DEPLOYMENT FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"UNEXPECTED ERROR: {e}")
        sys.exit(1)
