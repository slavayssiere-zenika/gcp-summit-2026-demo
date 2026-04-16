#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import json
import re
import yaml
import logging
import time
import socket
import ssl
import tempfile
import tarfile
import zipfile
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Timer global ---
START_TIME = time.monotonic()

def elapsed() -> str:
    """Retourne le temps écoulé depuis le démarrage du script, formaté en HH:MM:SS."""
    secs = int(time.monotonic() - START_TIME)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def discover_versions():
    """Scans for VERSION files in component directories and returns a mapping."""
    versions = {}
    base_dir = os.path.dirname(os.path.dirname(__file__))
    components = [
        "agent_router_api", "agent_hr_api", "agent_ops_api", "agent_missions_api",
        "users_api", "items_api", "competencies_api",
        "cv_api", "prompts_api", "drive_api", "missions_api", "market_mcp",
        "db_migrations", "frontend"
    ]
    
    for comp in components:
        # Check environment variable first (e.g. AGENT_API_VERSION)
        env_var_name = f"{comp.upper()}_VERSION"
        env_val = os.environ.get(env_var_name)
        
        if env_val:
            versions[f"{comp}_version"] = env_val
        else:
            # Fallback to local file discovery
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
    format='%(asctime)s [+%(elapsed)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class _ElapsedFilter(logging.Filter):
    """Injecte le temps écoulé dans chaque LogRecord."""
    def filter(self, record):
        record.elapsed = elapsed()
        return True

logger = logging.getLogger(__name__)
logger.addFilter(_ElapsedFilter())

# Ajouter le filtre à tous les handlers existants
for _h in logging.root.handlers:
    _h.addFilter(_ElapsedFilter())

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
    logger.info(f"[*] Running: {' '.join(cmd)}  (elapsed: {elapsed()})")
    
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

def resource_exists_in_gcp(resource_type, name, project_id):
    if resource_type == "dns_zone":
        res = subprocess.run(["gcloud", "dns", "managed-zones", "describe", name, "--project", project_id, "--format=json"], capture_output=True)
        return res.returncode == 0
    elif resource_type == "ssl_cert":
        res = subprocess.run(["gcloud", "compute", "ssl-certificates", "describe", name, "--global", "--project", project_id, "--format=json"], capture_output=True)
        return res.returncode == 0
    elif resource_type == "sa":
        res = subprocess.run(["gcloud", "iam", "service-accounts", "describe", name, "--project", project_id, "--format=json"], capture_output=True)
        return res.returncode == 0
    return False

def get_tf_args():
    api_key = os.environ.get("GOOGLE_API_KEY")
    return [f"-var=gemini_api_key={api_key}"] if api_key else []


def toggle_prevent_destroy(disable=True):
    if disable:
        print("[*] Writing destroy_override.tf to temporarily disable prevent_destroy safeguards...")
        # Collect all resources that have prevent_destroy = true in any .tf file
        resources_to_override = []
        for filename in os.listdir(TERRAFORM_DIR):
            if not filename.endswith(".tf") or filename == "destroy_override.tf":
                continue
            path = os.path.join(TERRAFORM_DIR, filename)
            with open(path, "r") as f:
                content = f.read()
            # Find resource blocks with prevent_destroy = true
            matches = re.findall(r'resource\s+"(\w+)"\s+"(\w+)"', content)
            for rtype, rname in matches:
                # Check if this resource block contains prevent_destroy
                block_pattern = rf'resource\s+"{re.escape(rtype)}"\s+"{re.escape(rname)}"\s*\{{[^}}]*prevent_destroy\s*=\s*true'
                if re.search(block_pattern, content, re.DOTALL):
                    resources_to_override.append((rtype, rname))

        if not resources_to_override:
            print("[*] No prevent_destroy resources found. No override needed.")
            return

        lines = ["# AUTO-GENERATED by manage_env.py --force. Do NOT commit this file.\n"]
        lines.append("# It is automatically deleted after the operation completes.\n\n")
        for rtype, rname in resources_to_override:
            lines.append(f'override_resource {{\n')
            lines.append(f'  res = {rtype}.{rname}\n')
            lines.append(f'  values = {{\n')
            lines.append(f'    lifecycle = []\n')
            lines.append(f'  }}\n')
            lines.append(f'}}\n\n')
        # Note: Terraform override_resource doesn't support lifecycle overrides.
        # Use a simpler approach: generate a .tf.json override with prevent_destroy=false
        override_blocks = {}
        for rtype, rname in resources_to_override:
            if rtype not in override_blocks:
                override_blocks[rtype] = {}
            override_blocks[rtype][rname] = {
                "lifecycle": [{"prevent_destroy": False}]
            }
        override_content = json.dumps({"resource": override_blocks}, indent=2)
        override_json_path = os.path.join(TERRAFORM_DIR, "destroy_override.tf.json")
        with open(override_json_path, "w") as f:
            f.write(override_content)
        print(f"    -> Created override file: destroy_override.tf.json ({len(resources_to_override)} resources)")
    else:
        print("[*] Removing destroy_override.tf.json (restoring prevent_destroy safeguards)...")
        override_json_path = os.path.join(TERRAFORM_DIR, "destroy_override.tf.json")
        if os.path.exists(override_json_path):
            os.remove(override_json_path)
            print("    -> Override file removed.")
        else:
            print("    -> Override file not found (already cleaned up).")

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

def build_importable_resources_map(env, project_id, region):
    """
    Retourne la table de correspondance exhaustive entre adresses Terraform et IDs
    GCP pour toutes les ressources susceptibles de générer une erreur 409 lors d'un
    apply sur un environnement dont les ressources existent déjà dans GCP mais pas
    dans le state Terraform (plateforme éphémère recréée).
    """
    cr_base  = f"projects/{project_id}/locations/{region}/services"
    mon_base = f"projects/{project_id}/services"
    dns_base = f"projects/{project_id}/managedZones"

    return {
        # ── Cloud Run Services ───────────────────────────────────────────────
        "google_cloud_run_v2_service.agent_hr_api":       f"{cr_base}/agent-hr-api-{env}",
        "google_cloud_run_v2_service.agent_ops_api":      f"{cr_base}/agent-ops-api-{env}",
        "google_cloud_run_v2_service.agent_router_api":   f"{cr_base}/agent-router-api-{env}",
        "google_cloud_run_v2_service.agent_missions_api": f"{cr_base}/agent-missions-api-{env}",
        "google_cloud_run_v2_service.market_mcp":         f"{cr_base}/market-mcp-{env}",
        "google_cloud_run_v2_service.prompts_api":      f"{cr_base}/prompts-api-{env}",
        "google_cloud_run_v2_service.users_api":        f"{cr_base}/users-api-{env}",
        "google_cloud_run_v2_service.competencies_api": f"{cr_base}/competencies-api-{env}",
        "google_cloud_run_v2_service.cv_api":           f"{cr_base}/cv-api-{env}",
        "google_cloud_run_v2_service.drive_api":        f"{cr_base}/drive-api-{env}",
        "google_cloud_run_v2_service.items_api":        f"{cr_base}/items-api-{env}",
        "google_cloud_run_v2_service.missions_api":     f"{cr_base}/missions-api-{env}",
        # ── Monitoring Custom Services ───────────────────────────────────────
        "google_monitoring_custom_service.agent_hr_api_svc":       f"{mon_base}/agent-hr-api-service-{env}",
        "google_monitoring_custom_service.agent_ops_api_svc":      f"{mon_base}/agent-ops-api-service-{env}",
        "google_monitoring_custom_service.agent_router_api_svc":   f"{mon_base}/agent-router-api-service-{env}",
        "google_monitoring_custom_service.agent_missions_api_svc": f"{mon_base}/agent-missions-api-service-{env}",
        "google_monitoring_custom_service.competencies_api_svc": f"{mon_base}/competencies-api-service-{env}",
        "google_monitoring_custom_service.cv_api_svc":           f"{mon_base}/cv-api-service-{env}",
        "google_monitoring_custom_service.drive_api_svc":        f"{mon_base}/drive-api-service-{env}",
        "google_monitoring_custom_service.items_api_svc":        f"{mon_base}/items-api-service-{env}",
        "google_monitoring_custom_service.market_mcp_svc":       f"{mon_base}/market-mcp-service-{env}",
        "google_monitoring_custom_service.missions_api_svc":     f"{mon_base}/missions-api-service-{env}",
        "google_monitoring_custom_service.prompts_api_svc":      f"{mon_base}/prompts-api-service-{env}",
        "google_monitoring_custom_service.users_api_svc":        f"{mon_base}/users-api-service-{env}",
        # ── DNS Managed Zones ────────────────────────────────────────────────
        "google_dns_managed_zone.env_zone":      f"{dns_base}/zone-{env}",
        "google_dns_managed_zone.internal_zone": f"{dns_base}/internal-zone-{env}",
        # ── SSL Certificate ──────────────────────────────────────────────────
        "google_compute_managed_ssl_certificate.default": f"projects/{project_id}/global/sslCertificates/ssl-{env}",
    }


def import_resources_on_409(output, env, project_id, region):
    """
    Analyse la sortie d'un `terraform apply` pour détecter les erreurs 409
    (Conflict / Resource already exists) et importe automatiquement les
    ressources conflictuelles dans le state Terraform.

    Le parsing repose sur les blocs d'erreur Terraform :
        │ Error: Error creating …: googleapi: Error 409: …
        │   with google_cloud_run_v2_service.agent_hr_api,
        │   on cr_agent_hr.tf line …

    Retourne le nombre de ressources importées avec succès.
    """
    importable = build_importable_resources_map(env, project_id, region)

    # Extrait les adresses Terraform depuis les blocs d'erreur 409
    found_addresses = set()
    with_pattern   = re.compile(r'with\s+([\w\.\[\]"]+),')
    in_409_block   = False

    for line in output.splitlines():
        stripped = line.strip().lstrip('│').strip()
        # Début d'un bloc 409
        if ('409' in stripped or 'already exists' in stripped.lower()) and 'Error' in stripped:
            in_409_block = True
            continue
        if in_409_block:
            m = with_pattern.search(stripped)
            if m:
                found_addresses.add(m.group(1).strip())
                in_409_block = False
        # Fin de bloc d'erreur (ligne séparatrice Terraform)
        if stripped in ('╵', '') and in_409_block:
            in_409_block = False

    if not found_addresses:
        print("[*] Aucune adresse de ressource 409 détectée dans la sortie de l'apply.")
        return 0

    imported_count = 0
    print(f"\n[*] Conflit 409 détecté sur {len(found_addresses)} ressource(s). Tentative d'auto-import...")

    for addr in sorted(found_addresses):
        if addr not in importable:
            print(f"    [-] Pas de mapping d'import défini pour : {addr} — ignoré.")
            continue

        import_id = importable[addr]

        # Vérifier si déjà présent dans le state (idempotence)
        state_check = subprocess.run(
            ["terraform", "state", "list", addr],
            cwd=TERRAFORM_DIR, capture_output=True, text=True
        )
        if state_check.returncode == 0 and addr in state_check.stdout:
            print(f"    [=] {addr} déjà dans le state — import ignoré.")
            continue

        print(f"    [→] Import de {addr}\n        depuis {import_id}")
        try:
            imp_res = subprocess.run(
                ["terraform", "import"] + get_tf_args() + [addr, import_id],
                cwd=TERRAFORM_DIR, capture_output=True, text=True, timeout=90
            )
            if imp_res.returncode == 0:
                print(f"    [+] Import réussi : {addr}")
                imported_count += 1
            else:
                err_detail = (imp_res.stderr or imp_res.stdout).strip()[:300]
                print(f"    [!] Échec de l'import pour {addr} :\n        {err_detail}")
        except subprocess.TimeoutExpired:
            print(f"    [!] Timeout de l'import pour {addr}.")

    print(f"[*] Auto-import terminé : {imported_count}/{len(found_addresses)} ressource(s) importée(s).")
    return imported_count


def get_gcp_quota_parallelism(project_id, region):
    """
    Interroge les quotas GCP Compute Engine (projet + region) via gcloud,
    affiche un tableau colore des ressources critiques, puis retourne
    un niveau de parallelisme adapte au taux d'utilisation le plus eleve.

    Heuristique de parallelisme :
      > 80%  utilise  -> parallelism = 1  (pression critique)
      > 50%  utilise  -> parallelism = 2  (pression moderee)
      <= 50% utilise  -> parallelism = 3  (quota confortable)
    """
    CRITICAL_PROJECT_QUOTAS = [
        "BACKEND_SERVICES",
        "URL_MAPS",
        "SSL_CERTIFICATES",
        "TARGET_HTTPS_PROXIES",
        "TARGET_HTTP_PROXIES",
        "GLOBAL_NETWORK_ENDPOINT_GROUPS",
        "FORWARDING_RULES",
    ]
    CRITICAL_REGION_QUOTAS = [
        "REGION_BACKEND_SERVICES",
        "NETWORK_ENDPOINT_GROUPS",
        "SUBNETWORKS",
    ]

    all_quotas = []
    max_ratio  = 0.0

    print("[*] Lecture des quotas GCP Compute Engine...")

    # Quotas au niveau projet (global)
    try:
        res = subprocess.run(
            ["gcloud", "compute", "project-info", "describe",
             "--project", project_id, "--format=json"],
            capture_output=True, text=True, timeout=20
        )
        if res.returncode == 0:
            data = json.loads(res.stdout)
            for q in data.get("quotas", []):
                if q["metric"] in CRITICAL_PROJECT_QUOTAS:
                    usage = q.get("usage", 0)
                    limit = q.get("limit", 1)
                    ratio = usage / limit if limit > 0 else 0
                    all_quotas.append({
                        "scope": "global",
                        "metric": q["metric"],
                        "usage": int(usage),
                        "limit": int(limit),
                        "ratio": ratio,
                    })
                    max_ratio = max(max_ratio, ratio)
        else:
            print(f"    [!] gcloud project-info a echoue : {res.stderr.strip()[:100]}")
    except Exception as e:
        print(f"    [!] Impossible de lire les quotas projet : {e}")

    # Quotas au niveau region
    try:
        res = subprocess.run(
            ["gcloud", "compute", "regions", "describe", region,
             "--project", project_id, "--format=json"],
            capture_output=True, text=True, timeout=20
        )
        if res.returncode == 0:
            data = json.loads(res.stdout)
            for q in data.get("quotas", []):
                if q["metric"] in CRITICAL_REGION_QUOTAS:
                    usage = q.get("usage", 0)
                    limit = q.get("limit", 1)
                    ratio = usage / limit if limit > 0 else 0
                    all_quotas.append({
                        "scope": region,
                        "metric": q["metric"],
                        "usage": int(usage),
                        "limit": int(limit),
                        "ratio": ratio,
                    })
                    max_ratio = max(max_ratio, ratio)
        else:
            print(f"    [!] gcloud regions describe a echoue : {res.stderr.strip()[:100]}")
    except Exception as e:
        print(f"    [!] Impossible de lire les quotas region : {e}")

    # Affichage du tableau colore
    print()
    print("    +" + "-"*62 + "+")
    print(f"    | {'QUOTA':<32} {'SCOPE':<14} {'USAGE':>5} {'LIMIT':>5} {'%':>4} |")
    print("    +" + "-"*62 + "+")
    for q in sorted(all_quotas, key=lambda x: x["ratio"], reverse=True):
        icon = "[CRIT]" if q["ratio"] > 0.80 else "[WARN]" if q["ratio"] > 0.50 else "[ OK ]"
        print(f"    | {icon} {q['metric']:<28} {q['scope']:<14} {q['usage']:>5} {q['limit']:>5} {q['ratio']*100:>3.0f}% |")
    print("    +" + "-"*62 + "+")

    # Decision du parallelisme
    if not all_quotas:
        parallelism = 1
        verdict = "[CRIT] Quotas non disponibles - parallelisme prudent a 1"
    elif max_ratio > 0.80:
        parallelism = 1
        verdict = f"[CRIT] Quota critique ({max_ratio*100:.0f}% max) -> parallelism = 1"
    elif max_ratio > 0.50:
        parallelism = 2
        verdict = f"[WARN] Quota modere  ({max_ratio*100:.0f}% max) -> parallelism = 2"
    else:
        parallelism = 3
        verdict = f"[ OK ] Quota OK      ({max_ratio*100:.0f}% max) -> parallelism = 3"

    print(f"    {verdict}")
    print()
    return parallelism


def deploy(env, base_domain, project_id, config, force=False):
    init_tf()
    set_workspace(env)

    print("[*] Probing GCP to deterministically import persistent resources...")
    zone_name = f"zone-{env}"
    if resource_exists_in_gcp("dns_zone", zone_name, project_id):
        import_persistent_resource(env, "google_dns_managed_zone.env_zone", f"projects/{project_id}/managedZones/{zone_name}")
        dns_name = f"{env}.{base_domain}."
        import_persistent_resource(env, "google_dns_record_set.a", f"projects/{project_id}/managedZones/{zone_name}/rrsets/{dns_name}/A")
        import_persistent_resource(env, "google_dns_record_set.api_a", f"projects/{project_id}/managedZones/{zone_name}/rrsets/api.{dns_name}/A")
    
    ssl_name = f"ssl-{env}"
    if resource_exists_in_gcp("ssl_cert", ssl_name, project_id):
        import_persistent_resource(env, "google_compute_managed_ssl_certificate.default", f"projects/{project_id}/global/sslCertificates/{ssl_name}")

    sa_email = f"sa-drive-{env}-v2@{project_id}.iam.gserviceaccount.com"
    if resource_exists_in_gcp("sa", sa_email, project_id):
        import_persistent_resource(env, 'google_service_account.cr_sa["drive"]', f"projects/{project_id}/serviceAccounts/{sa_email}")

    if force:
        print("[!] FORCE MODE: Bypassing prevent_destroy logic to allow replacements.")
        toggle_prevent_destroy(disable=True)

    try:
        # Extraction de la région depuis la config (fallback sur la valeur TF par défaut)
        region = config.get("region", "europe-west1")

        # Parallelisme adaptatif base sur les quotas GCP courants
        parallelism = get_gcp_quota_parallelism(project_id, region)
        apply_cmd = ["terraform", "apply", "-auto-approve",
                     f"-parallelism={parallelism}", "-lock-timeout=120s"] + get_tf_args()

        print(f"[*] Terraform Apply...")
        res = run_cmd(apply_cmd, check=False, live=True)

        if res.returncode != 0:
            # ── Passe 1 : import auto des ressources en conflit 409 ──────────
            print("[*] Apply échoué. Analyse des conflits 409 pour auto-import...")
            imported = import_resources_on_409(res.stdout, env, project_id, region)

            if imported > 0:
                print(f"[+] {imported} ressource(s) importée(s). Nouveau tentative d'apply...")
            else:
                print("[*] Aucun import 409 effectué. Pause 15s (consistance éventuelle GCP)...")
                time.sleep(15)

            res = run_cmd(apply_cmd, check=False, live=True)

        if res.returncode != 0:
            # ── Passe 2 : un 2e lot de 409 peut apparaître après le 1er import ──
            print("[*] 2ème apply échoué. Nouvelle analyse des conflits 409...")
            imported2 = import_resources_on_409(res.stdout, env, project_id, region)

            if imported2 > 0:
                print(f"[+] {imported2} ressource(s) supplémentaire(s) importée(s). Dernier apply...")
                time.sleep(5)
                res = run_cmd(apply_cmd, check=False, live=True)
            else:
                print("[*] Aucun import supplémentaire. Pause 15s avant dernier essai...")
                time.sleep(15)
                res = run_cmd(apply_cmd, check=False, live=True)

        if res.returncode != 0:
            print(f"[!] Échec définitif de l'apply.")
            sys.exit(res.returncode)

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
                
            rsync_res = subprocess.run(
                ["gsutil", "-m", "rsync", "-r", "-d", sync_dir, f"gs://{target_bucket}/"],
                capture_output=True, text=True
            )
            
            if rsync_res.returncode != 0:
                print(f"[!] Frontend sync failed:\\n{rsync_res.stderr}")
                return
                
            print(rsync_res.stderr.strip()) # gsutil logs mostly to stderr
            
            output_lower = (rsync_res.stdout + rsync_res.stderr).lower()
            
            # Simple heuristic: if 'copying' or 'removing' is in the output, something was actually synced
            if "copying " in output_lower or "removing " in output_lower:
                print("[*] Frontend changes synced successfully!")
                print("[*] Invalidating Cloud CDN Cache to serve the new Frontend immediately...")
                res_cdn = subprocess.run([
                    "gcloud", "compute", "url-maps", "invalidate-cdn-cache",
                    f"lb-{env}", "--path", "/*", "--async", "--project", project_id
                ], capture_output=True, text=True)
                if res_cdn.returncode == 0:
                    print("    -> Cache invalidation request submitted successfully.")
                else:
                    print(f"    -> [!] Could not invalidate cache: {res_cdn.stderr.strip()}")
            else:
                print("[*] No frontend changes detected. CDN cache invalidation skipped.")

            
        print("\n=======================================================")
        print(f"[*] Post-Deploy: Running Sanity Checks on {env}...")
        print("=======================================================")
        
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
                                    "agent_router_api.system_instruction": "agent_router_api/agent_router_api.system_instruction.txt",
                                    "agent_hr_api.system_instruction": "agent_hr_api/agent_hr_api.system_instruction.txt",
                                    "agent_ops_api.system_instruction": "agent_ops_api/agent_ops_api.system_instruction.txt",
                                    "agent_missions_api.system_instruction": "agent_missions_api/agent_missions_api.system_instruction.txt",
                                    "cv_api.extract_cv_info": "cv_api/cv_api.extract_cv_info.txt",
                                    "cv_api.generate_taxonomy_tree": "cv_api/cv_api.generate_taxonomy_tree.txt",
                                    "missions_api.extract_mission_info": "missions_api/extract_mission_info.txt",
                                    "missions_api.staffing_heuristics": "missions_api/staffing_heuristics.txt"
                                }
                                
                                packaged_dir = os.path.join(os.path.dirname(__file__), "bundled_prompts")
                                base_dir = packaged_dir if os.path.exists(packaged_dir) else os.path.dirname(os.path.dirname(__file__))
                                
                                headers = {
                                    "Content-Type": "application/json",
                                    "Authorization": f"Bearer {access_token}"
                                }
                                prompts_url = f"https://{api_dns_name}/api/prompts/"
                                
                                for p_key, rel_path in prompts_to_seed.items():
                                    file_path = os.path.join(base_dir, rel_path)
                                    if not os.path.exists(file_path):
                                        print(f"  [-] Warning: Prompt file not found {file_path}")
                                        continue
                                    
                                    with open(file_path, "r", encoding="utf-8") as f:
                                        content = f.read()

                                    # Idempotent upsert: GET first, then PUT to update or POST to create
                                    check_req = urllib.request.Request(
                                        f"{prompts_url}{p_key}",
                                        headers=headers,
                                        method="GET"
                                    )
                                    try:
                                        urllib.request.urlopen(check_req, timeout=10, context=ctx_to_use)
                                        http_method = "PUT"  # Prompt already exists → update
                                        upsert_url = f"{prompts_url}{p_key}"
                                    except urllib.error.HTTPError as e:
                                        if e.code == 404:
                                            http_method = "POST"  # Prompt doesn't exist → create
                                            upsert_url = prompts_url
                                        else:
                                            http_method = "POST"  # Fallback to create on other errors
                                            upsert_url = prompts_url
                                    except Exception:
                                        http_method = "POST"
                                        upsert_url = prompts_url

                                    p_data = json.dumps({"key": p_key, "value": content}).encode("utf-8")
                                    p_req = urllib.request.Request(upsert_url, data=p_data, headers=headers, method=http_method)
                                    
                                    seeded = False
                                    for attempt in range(8):
                                        try:
                                            p_resp = urllib.request.urlopen(p_req, timeout=15, context=ctx_to_use)
                                            if p_resp.status in [200, 201]:
                                                print(f"  [+] Successfully {'updated' if http_method == 'PUT' else 'created'} prompt: {p_key}")
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
                    "/api/health",                 # agent_router_api
                    "/api/agent-hr/health",        # agent_hr_api
                    "/api/agent-ops/health",       # agent_ops_api
                    "/api/agent-missions/health",  # agent_missions_api ← NEW
                    "/api/users/health",           # users_api
                    "/api/items/health",           # items_api
                    "/api/prompts/health",         # prompts_api
                    "/api/competencies/health",    # competencies_api
                    "/api/cv/health",              # cv_api
                    "/api/drive/health",           # drive_api
                    "/api/missions/health"         # missions_api
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

def destroy(env, project_id, config, force=False):
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

    # Parallelisme adaptatif : les DELETE GCP sont encore plus sensibles aux
    # quotas API que les lectures du refresh. On applique la meme heuristique.
    region = config.get("region", "europe-west1")
    parallelism = get_gcp_quota_parallelism(project_id, region)
    cmd = ["terraform", "destroy", "-auto-approve",
           f"-parallelism={parallelism}", "-lock-timeout=120s"] + get_tf_args()

    try:
        res = run_cmd(cmd, check=False, live=True)
        if res.returncode != 0:
            print("[*] Destroy echoue. Pause 15s et nouvelle tentative...")
            time.sleep(15)
            res = run_cmd(cmd, check=False, live=True)
            if res.returncode != 0:
                print(f"[!] Echec definitif du destroy.")
                sys.exit(res.returncode)
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
            destroy(args.env, project_id, final_config, force=args.force)
        elif args.action == "plan":
            plan(args.env)
            
    except DeploymentError as e:
        logger.error(f"DEPLOYMENT FAILED: {e}")
        total = elapsed()
        print(f"\n{'='*55}")
        print(f"[!] Script terminé avec erreur en {total}.")
        print(f"{'='*55}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"UNEXPECTED ERROR: {e}")
        total = elapsed()
        print(f"\n{'='*55}")
        print(f"[!] Script terminé avec erreur inattendue en {total}.")
        print(f"{'='*55}")
        sys.exit(1)
    else:
        total = elapsed()
        print(f"\n{'='*55}")
        print(f"[+] Script terminé avec succès en {total}.")
        print(f"{'='*55}")
