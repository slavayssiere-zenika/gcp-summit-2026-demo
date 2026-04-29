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
CURRENT_PROJECT_ID = "slavayssiere-sandbox-462015"
SANITY_ERROR_COUNT = 0

def elapsed() -> str:
    """Retourne le temps écoulé depuis le démarrage du script, formaté en HH:MM:SS."""
    secs = int(time.monotonic() - START_TIME)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def generate_antigravity_error_report(task_context: str, error_message: str, tags: list = None):
    """Génère ou met à jour un rapport d'erreur Markdown pour l'Agent Antigravity."""
    global CURRENT_PROJECT_ID, SANITY_ERROR_COUNT
    SANITY_ERROR_COUNT += 1
    project_id = CURRENT_PROJECT_ID
    report_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "antigravity_sanity_error.md")
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tags_str = ", ".join(tags) if tags else "sanity-check"
    
    is_new = not os.path.exists(report_file)
    with open(report_file, "a", encoding="utf-8") as f:
        if is_new:
            f.write("# 🚨 Rapport d'Erreur Sanity Check (pour Antigravity)\n\n")
            f.write("> **Directives pour l'Agent Antigravity :**\n")
            f.write("> Analyse ces erreurs, cherche les causes probables et propose une réparation.\n")
            f.write(f"> 🔎 **IMPORTANT** : Pense à rechercher les logs pertinents directement dans GCP pour le projet `{project_id}` via les outils MCP.\n")
            f.write("> Une fois résolues, utilise la CLI Antigravity Memory pour logguer la solution.\n\n")
        
        f.write(f"## Erreur interceptée à {timestamp}\n\n")
        f.write(f"- **Contexte** : {task_context}\n")
        f.write(f"- **Projet GCP** : `{project_id}`\n")
        f.write(f"- **Tags** : `{tags_str}`\n")
        f.write(f"- **Détails de l'erreur** :\n\n")
        f.write("```text\n")
        f.write(f"{error_message}\n")
        f.write("```\n\n")
        f.write("---\n\n")
        
    # On utilise print car logger n'est défini que plus bas
    print(f"  [!] Rapport d'erreur Antigravity généré/mis à jour : {report_file}")


def discover_versions():
    """Scans for VERSION files in component directories and returns a mapping."""
    versions = {}
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    components = [
        "agent_router_api", "agent_hr_api", "agent_ops_api", "agent_missions_api",
        "users_api", "items_api", "competencies_api",
        "cv_api", "prompts_api", "drive_api", "missions_api", "analytics_mcp", "monitoring_mcp",
        "db_migrations", "db_init", "frontend"
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


# Mapping clé Terraform → nom du dossier/image Docker.
# Utilisé par build_image_urls() pour construire les URLs d'images.
# Doit rester synchronisé avec deploy.sh (DOCKER_REPO + service name).
SERVICE_IMAGE_MAP = {
    "users":          "users_api",
    "items":          "items_api",
    "competencies":   "competencies_api",
    "cv":             "cv_api",
    "missions":       "missions_api",
    "prompts":        "prompts_api",
    "db_migrations":  "db_migrations",
    "db_init":        "db_init",        # Image dédiée au Cloud Run Job d'initialisation AlloyDB
    "analytics":         "analytics_mcp",
    "monitoring":     "monitoring_mcp",
    "agent_router":   "agent_router_api",
    "agent_hr":       "agent_hr_api",
    "agent_ops":      "agent_ops_api",
    "agent_missions": "agent_missions_api",
    "drive":          "drive_api",
}


def build_image_urls(registry: str, versions: dict) -> dict:
    """
    Construit les URLs d'images Docker pour Terraform depuis le registre et les versions.

    Format de sortie : image_{tf_name} = {registry}/{docker_name}:{version}

    La version est lue depuis 'versions' (priorité YAML > fichier VERSION local),
    ce qui permet d'utiliser ':latest' en dev et ':v0.1.0' en uat/prd.
    Les mêmes tags sont produits par deploy.sh (build_and_push_standard/agent).
    """
    images = {}
    for tf_name, docker_name in SERVICE_IMAGE_MAP.items():
        version = versions.get(f"{docker_name}_version", "latest")
        images[f"image_{tf_name}"] = f"{registry}/{docker_name}:{version}"
    return images

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
    dependencies = ["terraform", "gcloud"]
    missing = []
    for dep in dependencies:
        if subprocess.run(["which", dep], capture_output=True).returncode != 0:
            missing.append(dep)
    
    if missing:
        raise DeploymentError(f"Dépendances manquantes : {', '.join(missing)}")
    logger.info("[+] Toutes les dépendances binaires sont satisfaites.")

TERRAFORM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "terraform")

PERSISTENT_RESOURCES = [
    # ── Zones DNS ───────────────────────────────────────────────────────────────
    "google_dns_managed_zone.env_zone",
    "google_dns_record_set.ns_delegation",   # délégation NS vers la zone parente
    # ── SSL & DNS records LB ─────────────────────────────────────────────────────
    "google_compute_managed_ssl_certificate.default",
    "google_dns_record_set.a",
    "google_dns_record_set.api_a",
    # Les zones extra (ex: zone-gen-skillz) et leurs ns_delegation sont éjectées
    # dynamiquement dans destroy() en fonction de extra_domains dans le YAML.
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

def get_tf_args(project_id: str = "slavayssiere-sandbox-462015") -> list:
    """Retourne les arguments -var supplémentaires pour terraform apply/plan/import."""
    return []



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
    run_cmd(["terraform", "init", "-reconfigure", "-upgrade"])

def set_workspace(env):
    # Try to select, if it fails, create it
    logger.info(f"[*] Selecting Terraform workspace: '{env}'...")
    res = run_cmd(["terraform", "workspace", "select", env], check=False)
    if res.returncode != 0:
        logger.info(f"[*] Workspace '{env}' not found. Creating it...")
        run_cmd(["terraform", "workspace", "new", env])
    else:
        logger.info(f"[*] Workspace '{env}' successfully selected.")

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

def build_importable_resources_map(env, project_id, region, extra_domains=None):
    """
    Retourne la table de correspondance exhaustive entre adresses Terraform et IDs
    GCP pour toutes les ressources susceptibles de générer une erreur 409 lors d'un
    apply sur un environnement dont les ressources existent déjà dans GCP mais pas
    dans le state Terraform (plateforme éphémère recréée).
    """
    cr_base  = f"projects/{project_id}/locations/{region}/services"
    mon_base = f"projects/{project_id}/services"
    dns_base = f"projects/{project_id}/managedZones"

    importable_map = {
        # ── Cloud Run Services ───────────────────────────────────────────────
        "google_cloud_run_v2_service.agent_hr_api":       f"{cr_base}/agent-hr-api-{env}",
        "google_cloud_run_v2_service.agent_ops_api":      f"{cr_base}/agent-ops-api-{env}",
        "google_cloud_run_v2_service.agent_router_api":   f"{cr_base}/agent-router-api-{env}",
        "google_cloud_run_v2_service.agent_missions_api": f"{cr_base}/agent-missions-api-{env}",
        "google_cloud_run_v2_service.analytics_mcp":         f"{cr_base}/analytics-mcp-{env}",
        "google_cloud_run_v2_service.monitoring_mcp":     f"{cr_base}/monitoring-mcp-{env}",
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
        "google_monitoring_custom_service.analytics_mcp_svc":       f"{mon_base}/analytics-mcp-service-{env}",
        "google_monitoring_custom_service.monitoring_mcp_svc":   f"{mon_base}/monitoring-mcp-service-{env}",
        "google_monitoring_custom_service.missions_api_svc":     f"{mon_base}/missions-api-service-{env}",
        "google_monitoring_custom_service.prompts_api_svc":      f"{mon_base}/prompts-api-service-{env}",
        "google_monitoring_custom_service.users_api_svc":        f"{mon_base}/users-api-service-{env}",
        # ── DNS Managed Zones ────────────────────────────────────────────────
        "google_dns_managed_zone.env_zone":      f"{dns_base}/zone-{env}",
        "google_dns_managed_zone.internal_zone": f"{dns_base}/internal-zone-{env}",
        # ── SSL Certificate ──────────────────────────────────────────────────
        "google_compute_managed_ssl_certificate.default": f"projects/{project_id}/global/sslCertificates/ssl-{env}",
    }

    # ── Zones DNS additionnelles (extra_domains) ──────────────────────
    # Ces ressources sont persistantes et doivent être importées si elles existent dans GCP.
    if extra_domains:
        for d in extra_domains:
            zone_name = d.get("zone_name", "")
            dns_name  = d.get("dns_name", "")  # ex: "gen-skillz.znk.io."
            if not zone_name:
                continue
            tf_zone_addr = f'google_dns_managed_zone.extra_zones["{zone_name}"]'
            tf_a_addr    = f'google_dns_record_set.extra_a["{zone_name}"]'
            gcp_zone_id  = f"{dns_base}/{zone_name}"
            importable_map[tf_zone_addr] = gcp_zone_id
            importable_map[tf_a_addr]    = f"{gcp_zone_id}/rrsets/{dns_name}/A"

    return importable_map
def import_resources_on_409(output, env, project_id, region, extra_domains=None):
    """
    Analyse la sortie d'un `terraform apply` pour détecter les erreurs 409
    (Conflict / Resource already exists) et importe automatiquement les
    ressources conflictuelles dans le state Terraform.
    """
    importable = build_importable_resources_map(env, project_id, region, extra_domains=extra_domains)

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
                ["terraform", "import"] + get_tf_args(project_id) + [addr, import_id],
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
    # Récupération des domaines additionnels depuis la config (ex: gen-skillz.znk.io en prd)
    extra_domains = config.get("extra_domains", [])

    zone_name = f"zone-{env}"
    if resource_exists_in_gcp("dns_zone", zone_name, project_id):
        import_persistent_resource(env, "google_dns_managed_zone.env_zone", f"projects/{project_id}/managedZones/{zone_name}")
        dns_name = f"{env}.{base_domain}."
        import_persistent_resource(env, "google_dns_record_set.a", f"projects/{project_id}/managedZones/{zone_name}/rrsets/{dns_name}/A")
        import_persistent_resource(env, "google_dns_record_set.api_a", f"projects/{project_id}/managedZones/{zone_name}/rrsets/api.{dns_name}/A")

    # Import des zones DNS additionnelles persistantes (ex: zone-gen-skillz pour gen-skillz.znk.io)
    for d in extra_domains:
        extra_zone_name = d.get("zone_name", "")
        extra_dns_name  = d.get("dns_name", "")
        if not extra_zone_name:
            continue
        if resource_exists_in_gcp("dns_zone", extra_zone_name, project_id):
            tf_addr = f'google_dns_managed_zone.extra_zones["{extra_zone_name}"]'
            import_persistent_resource(env, tf_addr, f"projects/{project_id}/managedZones/{extra_zone_name}")
            tf_a_addr = f'google_dns_record_set.extra_a["{extra_zone_name}"]'
            import_persistent_resource(env, tf_a_addr, f"projects/{project_id}/managedZones/{extra_zone_name}/rrsets/{extra_dns_name}/A")

    ssl_name = f"ssl-{env}"
    if resource_exists_in_gcp("ssl_cert", ssl_name, project_id):
        import_persistent_resource(env, "google_compute_managed_ssl_certificate.default", f"projects/{project_id}/global/sslCertificates/{ssl_name}")

    # NOTE: le SA sa-drive-{env}-v2 est déclaré comme data source (cr_drive.tf) — pas une resource Terraform.
    # Il est créé en dehors du cycle Terraform et est naturellement persistant (jamais détruit par apply/destroy).
    # Aucun import nécessaire.

    if force:
        print("[!] FORCE MODE: Bypassing prevent_destroy logic to allow replacements.")
        toggle_prevent_destroy(disable=True)

    try:
        # Extraction de la région depuis la config (fallback sur la valeur TF par défaut)
        region = config.get("region", "europe-west1")

        # Parallelisme adaptatif base sur les quotas GCP courants
        parallelism = get_gcp_quota_parallelism(project_id, region)
        apply_cmd = ["terraform", "apply", "-auto-approve",
                     f"-parallelism={parallelism}", "-lock-timeout=120s"] + get_tf_args(project_id)

        print(f"[*] Terraform Apply...")
        res = run_cmd(apply_cmd, check=False, live=True)

        if res.returncode != 0:
            # ── Passe 1 : import auto des ressources en conflit 409 ──────────
            print("[*] Apply échoué. Analyse des conflits 409 pour auto-import...")
            imported = import_resources_on_409(res.stdout, env, project_id, region, extra_domains=extra_domains)

            if imported > 0:
                print(f"[+] {imported} ressource(s) importée(s). Nouveau tentative d'apply...")
            else:
                print("[*] Aucun import 409 effectué. Pause 15s (consistance éventuelle GCP)...")
                time.sleep(15)

            res = run_cmd(apply_cmd, check=False, live=True)

        if res.returncode != 0:
            # ── Passe 2 : un 2e lot de 409 peut apparaître après le 1er import ──
            print("[*] 2ème apply échoué. Nouvelle analyse des conflits 409...")
            imported2 = import_resources_on_409(res.stdout, env, project_id, region, extra_domains=extra_domains)

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
        res = subprocess.run(["terraform", "output", "-json"], cwd=TERRAFORM_DIR, capture_output=True, text=True)
        try:
            import json
            outputs = json.loads(res.stdout)
            target_bucket = outputs.get("frontend_bucket_name", {}).get("value", "").strip()
        except Exception:
            target_bucket = ""
        if not target_bucket:
            err_msg = "Could not retrieve frontend_bucket_name from terraform outputs."
            print(f"[!] {err_msg}")
            generate_antigravity_error_report("Post-Deploy : Sync Frontend", err_msg, ["frontend", "sync", "terraform"])
            sys.exit(1)

        SOURCE_ARCHIVES_BUCKET = "z-gcp-summit-frontend"

        # 2. Identifier la dernière archive déposée (en utilisant gcloud storage ls)
        print(f"[*] Looking for the latest archive in gs://{SOURCE_ARCHIVES_BUCKET}/...")
        raw_ls = subprocess.run(["gcloud", "storage", "ls", f"gs://{SOURCE_ARCHIVES_BUCKET}/"], capture_output=True, text=True)
        if raw_ls.returncode != 0:
            err_msg = f"Failed to list gs://{SOURCE_ARCHIVES_BUCKET}/"
            print(f"[!] {err_msg}")
            generate_antigravity_error_report("Post-Deploy : Sync Frontend", err_msg, ["frontend", "sync", "gcloud"])
            sys.exit(1)
            
        lines = [l.strip() for l in raw_ls.stdout.split('\n') if l.strip()]
        urls = [line for line in lines if line.startswith("gs://")]
        if not urls:
            print(f"[*] No archives found in gs://{SOURCE_ARCHIVES_BUCKET}/. Skipping frontend sync.")
        else:
            # Sort by filename
            urls.sort()
            latest_archive_url = urls[-1]
            
            print(f"[*] Latest archive identified: {latest_archive_url}")
            
            # 3. Télécharger et extraire
            with tempfile.TemporaryDirectory() as tmpdir:
                archive_path = os.path.join(tmpdir, "archive")
                print(f"[*] Downloading {latest_archive_url}...")
                subprocess.run(["gcloud", "storage", "cp", latest_archive_url, archive_path], check=True)
                
                extract_dir = os.path.join(tmpdir, "extracted")
                os.makedirs(extract_dir, exist_ok=True)
                
                print("[*] Extracting archive...")
                try:
                    if latest_archive_url.endswith(".zip"):
                        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                            zip_ref.extractall(extract_dir)
                    else: # Fallback to tar
                        with tarfile.open(archive_path, 'r:*') as tar_ref:
                            tar_ref.extractall(extract_dir, filter='data')
                except Exception as e:
                    err_msg = f"Extraction failed: {e}. Is it a valid tar/zip archive?"
                    print(f"[!] {err_msg}")
                    generate_antigravity_error_report("Post-Deploy : Sync Frontend", err_msg, ["frontend", "sync", "extraction"])
                    sys.exit(1)
                    
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
                    ["gcloud", "storage", "rsync", sync_dir, f"gs://{target_bucket}/", "--recursive", "--delete-unmatched-destination-objects"],
                    capture_output=True, text=True
                )
                
                if rsync_res.returncode != 0:
                    err_msg = f"Frontend sync failed:\\n{rsync_res.stderr}"
                    print(f"[!] {err_msg}")
                    generate_antigravity_error_report("Post-Deploy : Sync Frontend", err_msg, ["frontend", "sync", "rsync"])
                    sys.exit(1)
                    
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
            all_domains = [front_dns_name, api_dns_name]
            if extra_domains:
                for d in extra_domains:
                    if d.get("dns_name"):
                        all_domains.append(d.get("dns_name").rstrip("."))
                        
            print(f"[*] Check 1/5: Waiting for DNS resolution to IP {lb_ip} for domains: {', '.join(all_domains)}...")
            
            all_resolved = True
            for domain in all_domains:
                resolved = False
                for _ in range(30):  # 30 * 10s = 5 mins max
                    try:
                        ip = socket.gethostbyname(domain)
                        if ip == lb_ip:
                            resolved = True
                            break
                    except Exception: pass
                    time.sleep(10)
                
                if resolved:
                    print(f"  [+] DNS {domain} resolves correctly to {lb_ip}")
                else:
                    err_msg = f"DNS resolution timeout (5 mins). {domain} does NOT point to {lb_ip}."
                    print(f"  [-] {err_msg}")
                    generate_antigravity_error_report("Sanity Check 1/3 : DNS Resolution", err_msg, ["dns", "sanity-check", "timeout"])
                    all_resolved = False
                    break
            
            if all_resolved:
                
                # --- CHECK 2: SSL PROVISIONING ---
                print(f"\n[*] Check 2/5: Waiting for GCP Managed SSL Certificate provisioning (Can take 15-30 mins)...")
                ssl_ready = False
                cert_creation_time = "Inconnue"
                cert_name = f"ssl-{env}"
                
                for attempt in range(60):
                    res = subprocess.run([
                        "gcloud", "compute", "ssl-certificates", "describe", cert_name,
                        "--global", "--project", project_id, "--format=json"
                    ], capture_output=True, text=True)
                    
                    if res.returncode == 0:
                        try:
                            cert_data = json.loads(res.stdout)
                            cert_creation_time = cert_data.get("creationTimestamp", "Inconnue")
                            managed = cert_data.get("managed", {})
                            status = managed.get("status", "")
                            domain_status = managed.get("domainStatus", {})
                            
                            if status == "ACTIVE":
                                print(f"  [+] SSL Certificate {cert_name} is fully ACTIVE!")
                                for d, st in sorted(domain_status.items()):
                                    print(f"      {d:<35} {st}")
                                ssl_ready = True
                                
                                # --- Fallback urllib verification for TLS handshake ---
                                try:
                                    import certifi
                                    ctx = ssl.create_default_context(cafile=certifi.where())
                                except ImportError:
                                    ctx = ssl.create_default_context()
                                ctx_to_use = ctx
                                break
                            else:
                                print(f"  [-] Certificate status: {status} (attempt {attempt+1}/60). Retrying in 20s...")
                                for d, st in sorted(domain_status.items()):
                                    # Print details of domains that are not yet active
                                    if st != "ACTIVE":
                                        print(f"      {d:<35} {st}")
                                time.sleep(20)
                        except Exception as e:
                            print(f"  [-] Error parsing gcloud output: {e}. Retrying in 20s...")
                            time.sleep(20)
                    else:
                        print(f"  [-] Failed to fetch certificate status. Retrying in 20s... (Error: {res.stderr.strip()[:100]})")
                        time.sleep(20)
                
                if ssl_ready:
                    age_str = ""
                    try:
                        if cert_creation_time != "Inconnue":
                            from datetime import datetime, timezone
                            dt = datetime.fromisoformat(cert_creation_time)
                            age = datetime.now(timezone.utc) - dt
                            mins = int(age.total_seconds() // 60)
                            age_str = f" [Il y a {mins} minutes]"
                    except Exception:
                        pass
                    print(f"  [+] Managed SSL Certificate is ACTIVE in GCP API. (Créé le: {cert_creation_time}){age_str}")
                    print(f"  [*] Waiting for the certificate to propagate to Google Edge nodes (TLS handshake)...")
                    tls_ready = False
                    
                    ctx_fallback = ssl.create_default_context()
                    ctx_fallback.check_hostname = False
                    ctx_fallback.verify_mode = ssl.CERT_NONE
                    
                    for attempt in range(90): # Wait up to 30 mins (90 * 20s) for Edge propagation
                        try:
                            req_test = urllib.request.Request(f"https://{front_dns_name}/", method="GET")
                            urllib.request.urlopen(req_test, timeout=10, context=ctx_to_use)
                            tls_ready = True
                            break
                        except urllib.error.HTTPError as e:
                            # 404/400/502 means TLS handshake succeeded!
                            tls_ready = True
                            break
                        except urllib.error.URLError as e:
                            err_msg = str(e.reason)
                            if "CERTIFICATE_VERIFY_FAILED" in err_msg:
                                if "unable to get local issuer certificate" in err_msg:
                                    print(f"  [!] macOS Python CA Bug detected. Bypassing strict verification...")
                                    ctx_to_use = ctx_fallback
                                    tls_ready = True
                                    break
                            print(f"  [-] TLS propagation not yet complete (attempt {attempt+1}/90). Retrying in 20s... (Error: {err_msg})")
                            time.sleep(20)
                        except Exception as e:
                            print(f"  [-] Unexpected error during TLS check (attempt {attempt+1}/90). Retrying in 20s... (Error: {e})")
                            time.sleep(20)
                            
                    if tls_ready:
                        print(f"  [+] TLS Handshake successful! The certificate is fully propagated.")
                    else:
                        err_msg = "SSL Edge propagation timeout (30 mins). TLS handshake failed. Sanity checks aborted."
                        print(f"  [!] {err_msg}")
                        generate_antigravity_error_report("Sanity Check 2/5 : TLS Handshake", err_msg, ["ssl", "tls", "sanity-check", "timeout"])
                        sys.exit(1)
                else:
                    err_msg = "SSL provisioning timeout (20 mins). Certificate is not ACTIVE in GCP API. Sanity checks aborted."
                    print(f"  [!] {err_msg}")
                    generate_antigravity_error_report("Sanity Check 2/5 : SSL Provisioning", err_msg, ["ssl", "sanity-check", "timeout"])
                    sys.exit(1)
                
                # --- CHECK 3: FRONTEND ---
                print(f"\n[*] Check 3/5: Testing Frontend website on https://{front_dns_name}/...")
                try:
                    front_url = f"https://{front_dns_name}/"
                    req_front = urllib.request.Request(front_url, method="GET")
                    resp_front = urllib.request.urlopen(req_front, timeout=15, context=ctx_to_use)
                    if resp_front.status == 200:
                        print(f"  [+] Frontend loaded OK (HTTP 200)")
                    else:
                        err_msg = f"Frontend FAIL (HTTP {resp_front.status})"
                        print(f"  [-] {err_msg}")
                        generate_antigravity_error_report("Sanity Check 3/5 : Frontend", err_msg, ["frontend", "sanity-check", f"HTTP_{resp_front.status}"])
                except urllib.error.HTTPError as e:
                    err_msg = f"Frontend FAIL (HTTP {e.code})"
                    print(f"  [-] {err_msg}")
                    generate_antigravity_error_report("Sanity Check 3/5 : Frontend", err_msg, ["frontend", "sanity-check", f"HTTP_{e.code}"])
                except Exception as e:
                    err_msg = f"Frontend FAIL ({type(e).__name__}: {e})"
                    print(f"  [-] {err_msg}")
                    generate_antigravity_error_report("Sanity Check 3/5 : Frontend", err_msg, ["frontend", "sanity-check", "exception"])
                
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
                                    "cv_api.generate_taxonomy_tree_map": "cv_api/cv_api.generate_taxonomy_tree_map.txt",
                                    "cv_api.generate_taxonomy_tree_deduplicate": "cv_api/cv_api.generate_taxonomy_tree_deduplicate.txt",
                                    "cv_api.generate_taxonomy_tree_reduce": "cv_api/cv_api.generate_taxonomy_tree_reduce.txt",
                                    "cv_api.generate_taxonomy_tree_sweep": "cv_api/cv_api.generate_taxonomy_tree_sweep.txt",
                                    "missions_api.extract_mission_info": "missions_api/extract_mission_info.txt",
                                    "missions_api.staffing_heuristics": "missions_api/staffing_heuristics.txt",
                                    "prompts_api.error_correction": "prompts_api/prompts_api.error_correction.txt"
                                }
                                
                                packaged_dir = os.path.join(os.path.dirname(__file__), "bundled_prompts")
                                is_container = os.path.exists("/.dockerenv") or "K_SERVICE" in os.environ
                                base_dir = packaged_dir if (is_container and os.path.exists(packaged_dir)) else os.path.dirname(os.path.dirname(__file__))
                                
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
                                    last_error_msg = ""
                                    for attempt in range(8):
                                        try:
                                            p_resp = urllib.request.urlopen(p_req, timeout=15, context=ctx_to_use)
                                            if p_resp.status in [200, 201]:
                                                print(f"  [+] Successfully {'updated' if http_method == 'PUT' else 'created'} prompt: {p_key}")
                                                seeded = True
                                                break
                                            else:
                                                last_error_msg = f"HTTP {p_resp.status}"
                                                print(f"  [-] Failed to seed {p_key} ({last_error_msg}). Retrying... (Attempt {attempt+1}/8)")
                                        except urllib.error.HTTPError as e:
                                            if e.code >= 500:
                                                print(f"  [-] API Server Error {e.code} for {p_key} (Possible IAM propagation delay). Retrying in 15s... (Attempt {attempt+1}/8)")
                                            else:
                                                last_error_msg = f"HTTP {e.code}"
                                                print(f"  [-] Error seeding {p_key}: {last_error_msg}. Retrying... (Attempt {attempt+1}/8)")
                                        except Exception as e:
                                            last_error_msg = f"{type(e).__name__}: {e}"
                                            print(f"  [-] Error seeding {p_key} ({last_error_msg}). Retrying... (Attempt {attempt+1}/8)")
                                        
                                        time.sleep(15)

                                    if not seeded:
                                        err_msg = f"Failed to seed {p_key} after all attempts. Last error: {last_error_msg}"
                                        print(f"  [!] {err_msg}")
                                        generate_antigravity_error_report(f"Sanity Check 4.5 : Seeding Prompts ({p_key})", err_msg, ["prompts_api", "sanity-check"])
                            break
                        else:
                            print(f"[-] Sanity Test FAIL: Login returned {response.status}")
                            break
                    except urllib.error.HTTPError as e:
                        if e.code >= 500:
                            print(f"  [-] API Server Error {e.code} (Possible Database IAM propagation delay). Retrying in 30s... (Attempt {attempt+1}/16)")
                            time.sleep(30)
                        elif e.code == 403:
                            # 403 peut être transitoire lors d'un 1er déploiement :
                            # la propagation IAM du rôle allUsers Cloud Run invoker
                            # peut prendre plusieurs minutes.
                            # On distingue le 403 infra GCP (HTML) du 403 applicatif (JSON).
                            raw = e.read()
                            msg = raw.decode('utf-8', errors='replace') if raw else 'N/A'
                            is_gcp_infra = '<html' in msg.lower() or '<!doctype' in msg.lower()
                            if is_gcp_infra:
                                print(f"  [-] 403 GCP Infrastructure (IAM not yet propagated). Retrying in 30s... (Attempt {attempt+1}/16)")
                                time.sleep(30)
                            else:
                                err_msg = f"HTTP 403 (App-level) during login. (Msg: {msg})"
                                print(f"[-] Sanity Test FAIL: {err_msg}")
                                generate_antigravity_error_report("Sanity Check 4/5 : API Login", err_msg, ["users_api", "auth", "sanity-check", "HTTP_403"])
                                break
                        else:
                            # Erreur applicative définitive (400, 401, 422...)
                            msg = e.read().decode('utf-8', errors='replace') if hasattr(e, 'read') else 'N/A'
                            err_msg = f"HTTP {e.code} during login via POST /auth/login. (Msg: {msg})"
                            print(f"[-] Sanity Test FAIL: {err_msg}")
                            generate_antigravity_error_report("Sanity Check 4/5 : API Login", err_msg, ["users_api", "auth", "sanity-check", f"HTTP_{e.code}"])
                            break
                    except Exception as e:
                        print(f"  [-] Unexpected error Exception request: {e}. Retrying in 30s... (Attempt {attempt+1}/16)")
                        time.sleep(30)
                
                if not login_success:
                    print("[-] Authentication flow totally failed after all attempts.")
                    
                # --- CHECK 5/5: API MICROSERVICES ---
                logger.info(f"\n[*] Check 5/5: Validating all API microservices routing (GET requests)...")
                # On teste toutes les routes déclarées dans le Load Balancer (lb.tf)
                health_ready_routes = [
                    "/api/health",                 # agent_router_api
                    "/api/agent-hr/health",        # agent_hr_api
                    "/api/agent-ops/health",       # agent_ops_api
                    "/api/agent-missions/health",  # agent_missions_api ← NEW
                    "/api/users/ready",            # users_api
                    "/api/items/ready",            # items_api
                    "/api/prompts/ready",          # prompts_api
                    "/api/competencies/ready",     # competencies_api
                    "/api/cv/ready",               # cv_api
                    "/api/drive/ready",            # drive_api
                    "/api/missions/ready",         # missions_api
                    "/api/analytics/ready",           # analytics_mcp (Deep readiness check)
                    "/monitoring-mcp/health"       # monitoring_mcp
                ]
                
                api_routes = []
                for hr_route in health_ready_routes:
                    api_routes.append(hr_route)
                    prefix = hr_route.rsplit("/", 1)[0]
                    # Also check /spec and /docs for each prefix
                    api_routes.append(f"{prefix}/spec")
                    api_routes.append(f"{prefix}/docs")
                
                def check_route(route):
                    api_url = f"https://{api_dns_name}{route}"
                    req_get = urllib.request.Request(api_url, method="GET")
                    try:
                        resp = urllib.request.urlopen(req_get, timeout=90, context=ctx_to_use)
                        return f"  [+] {route:<15} -> OK (HTTP {resp.status})"
                    except urllib.error.HTTPError as e:
                        err_msg = f"FAIL (HTTP {e.code} Error) sur {route}"
                        generate_antigravity_error_report("Sanity Check 5/5 : API Microservices", err_msg, ["routing", "sanity-check", f"HTTP_{e.code}"])
                        return f"  [-] {route:<15} -> {err_msg}"
                    except Exception as e:
                        err_msg = f"FAIL ({type(e).__name__}: {e}) sur {route}"
                        generate_antigravity_error_report("Sanity Check 5/5 : API Microservices", err_msg, ["routing", "sanity-check", "exception"])
                        return f"  [-] {route:<15} -> {err_msg}"

                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(check_route, route): route for route in api_routes}
                    for future in as_completed(futures):
                        logger.info(future.result())

                # --- CHECK 6/8: ZERO-TRUST VALIDATION (HTTP 401 WITHOUT TOKEN) ---
                logger.info(f"\n[*] Check 6/8: Validating Zero-Trust security (expecting 401 without token)...")
                protected_url = f"https://{api_dns_name}/api/users/me"
                req_zt = urllib.request.Request(protected_url, method="GET")
                try:
                    urllib.request.urlopen(req_zt, timeout=10, context=ctx_to_use)
                    err_msg = "Security Breach! Protected endpoint returned 200 OK without a JWT token."
                    logger.error(f"  [-] {err_msg}")
                    generate_antigravity_error_report("Sanity Check 6/8 : Zero-Trust", err_msg, ["security", "sanity-check", "zero-trust"])
                except urllib.error.HTTPError as e:
                    if e.code == 401:
                        logger.info("  [+] Zero-Trust OK: Access denied (HTTP 401) without token.")
                    else:
                        err_msg = f"Unexpected HTTP status {e.code} during Zero-Trust check."
                        logger.warning(f"  [-] {err_msg}")
                        generate_antigravity_error_report("Sanity Check 6/8 : Zero-Trust", err_msg, ["security", "sanity-check", f"HTTP_{e.code}"])
                except Exception as e:
                    err_msg = f"Unexpected error during Zero-Trust check: {e}"
                    logger.warning(f"  [-] {err_msg}")
                    generate_antigravity_error_report("Sanity Check 6/8 : Zero-Trust", err_msg, ["security", "sanity-check", "exception"])

                # --- CHECK 7/8: DATABASE READ-ONLY CONNECTIVITY WITH TOKEN ---
                logger.info(f"\n[*] Check 7/8: Validating DB read-only connectivity with JWT token...")
                if access_token:
                    req_db = urllib.request.Request(protected_url, method="GET")
                    req_db.add_header("Authorization", f"Bearer {access_token}")
                    try:
                        resp_db = urllib.request.urlopen(req_db, timeout=15, context=ctx_to_use)
                        if resp_db.status == 200:
                            logger.info("  [+] Read-Only DB Check OK: Successfully fetched user profile.")
                        else:
                            logger.error(f"  [-] Read-Only DB Check FAIL: HTTP {resp_db.status}")
                    except urllib.error.HTTPError as e:
                        err_msg = f"FAIL (HTTP {e.code}) when fetching user profile with valid token."
                        logger.error(f"  [-] {err_msg}")
                        generate_antigravity_error_report("Sanity Check 7/8 : DB Read-Only", err_msg, ["db", "sanity-check", f"HTTP_{e.code}"])
                    except Exception as e:
                        err_msg = f"Read-Only DB Check FAIL: {e}"
                        logger.error(f"  [-] {err_msg}")
                        generate_antigravity_error_report("Sanity Check 7/8 : DB Read-Only", err_msg, ["db", "sanity-check", "exception"])
                else:
                    logger.warning("  [!] Skipping Check 7: No access_token available (Check 4 failed).")

                # --- CHECK 8/8: MCP SIDECAR AVAILABILITY ---
                logger.info(f"\n[*] Check 8/8: Validating MCP Sidecar tools exposure...")
                # All data APIs and MCP natif expose tools
                mcp_routes = [
                    "/api/users/mcp/tools",
                    "/api/items/mcp/tools",
                    "/api/prompts/mcp/tools",
                    "/api/competencies/mcp/tools",
                    "/api/cv/mcp/tools",
                    "/api/drive/mcp/tools",
                    "/api/missions/mcp/tools",
                    "/api/analytics/mcp/tools",
                    "/monitoring-mcp/mcp/tools"
                ]
                for mcp_route in mcp_routes:
                    mcp_url = f"https://{api_dns_name}{mcp_route}"
                    req_mcp = urllib.request.Request(mcp_url, method="GET")
                    if access_token:
                        req_mcp.add_header("Authorization", f"Bearer {access_token}")
                    try:
                        resp_mcp = urllib.request.urlopen(req_mcp, timeout=15, context=ctx_to_use)
                        if resp_mcp.status == 200:
                            mcp_data = json.loads(resp_mcp.read().decode('utf-8'))
                            if isinstance(mcp_data, list):
                                tools_count = len(mcp_data)
                            else:
                                tools_count = len(mcp_data.get("tools", []))
                            logger.info(f"  [+] MCP {mcp_route} OK: Found {tools_count} tools.")
                        else:
                            err_msg = f"HTTP {resp_mcp.status}"
                            logger.error(f"  [-] MCP {mcp_route} FAIL: {err_msg}")
                            generate_antigravity_error_report("Sanity Check 8/8 : MCP Availability", err_msg, ["mcp", "sanity-check", f"HTTP_{resp_mcp.status}"])
                    except urllib.error.HTTPError as e:
                        err_msg = f"FAIL (HTTP {e.code}) on {mcp_route}"
                        logger.error(f"  [-] {err_msg}")
                        generate_antigravity_error_report("Sanity Check 8/8 : MCP Availability", err_msg, ["mcp", "sanity-check", f"HTTP_{e.code}"])
                    except Exception as e:
                        err_msg = f"MCP {mcp_route} FAIL: {e}"
                        logger.error(f"  [-] {err_msg}")
                        generate_antigravity_error_report("Sanity Check 8/8 : MCP Availability", err_msg, ["mcp", "sanity-check", "exception"])

                # --- CHECK 9/9: AIOPS METRICS ---
                logger.info(f"\n[*] Check 9/9: Validating AIOps metrics endpoint...")
                if access_token:
                    aiops_url = f"https://{api_dns_name}/api/analytics/metrics/aiops?force=true"
                    req_aiops = urllib.request.Request(aiops_url, method="GET")
                    req_aiops.add_header("Authorization", f"Bearer {access_token}")
                    try:
                        resp_aiops = urllib.request.urlopen(req_aiops, timeout=30, context=ctx_to_use)
                        if resp_aiops.status == 200:
                            logger.info(f"  [+] AIOps Metrics OK: {aiops_url}")
                        else:
                            err_msg = f"HTTP {resp_aiops.status}"
                            logger.error(f"  [-] AIOps Metrics FAIL: {err_msg}")
                            generate_antigravity_error_report("Sanity Check 9/9 : AIOps Metrics", err_msg, ["analytics_mcp", "sanity-check", f"HTTP_{resp_aiops.status}"])
                    except urllib.error.HTTPError as e:
                        err_msg = f"FAIL (HTTP {e.code}) on /api/analytics/metrics/aiops"
                        logger.error(f"  [-] {err_msg}")
                        generate_antigravity_error_report("Sanity Check 9/9 : AIOps Metrics", err_msg, ["analytics_mcp", "sanity-check", f"HTTP_{e.code}"])
                    except Exception as e:
                        err_msg = f"AIOps Metrics FAIL: {e}"
                        logger.error(f"  [-] {err_msg}")
                        generate_antigravity_error_report("Sanity Check 9/9 : AIOps Metrics", err_msg, ["analytics_mcp", "sanity-check", "exception"])
                else:
                    logger.warning("  [!] Skipping Check 9: No access_token available (Check 4 failed).")

                # --- CHECK EXTRA DOMAINS: DNS + SSL pour chaque domaine additionnel ---
                if extra_domains:
                    print(f"\n[*] Check Extra Domains: Validating additional domains DNS + SSL...")
                    for _d in extra_domains:
                        _host = _d.get("dns_name", "").rstrip(".")  # ex: "gen-skillz.znk.io"
                        if not _host:
                            continue
                        # SSL check
                        _ssl_ok = False
                        for _attempt in range(6):  # 6 * 20s = 2 mins max
                            try:
                                _req = urllib.request.Request(f"https://{_host}/", method="GET")
                                urllib.request.urlopen(_req, timeout=10, context=ctx_to_use)
                                _ssl_ok = True
                                break
                            except urllib.error.HTTPError:
                                _ssl_ok = True  # TLS handshake réussi même si HTTP error
                                break
                            except urllib.error.URLError as _e:
                                if "CERTIFICATE_VERIFY_FAILED" in str(_e.reason) and "unable to get local issuer" in str(_e.reason):
                                    _ssl_ok = True  # Bug macOS CA, on considère OK
                                    break
                                print(f"  [-] SSL {_host} not yet active (attempt {_attempt+1}/6). Retrying in 20s...")
                                time.sleep(20)
                            except Exception as _e:
                                print(f"  [-] SSL {_host} unexpected error ({_e}). Retrying in 20s...")
                                time.sleep(20)
                        if _ssl_ok:
                            print(f"  [+] SSL {_host} -> ACTIVE")
                        else:
                            print(f"  [!] SSL {_host} -> not provisioned yet (certificate may take 15-30 mins)")

                # --- INIT: FINOPS PRICING SEEDING ---
                print(f"\n[*] Post-Deploy: Seeding FinOps Pricing Data (BigQuery)...")
                try:
                    init_pricing_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analytics_mcp", "init_pricing.py")
                    if os.path.exists(init_pricing_path):
                        env_copy = os.environ.copy()
                        env_copy["GCP_PROJECT_ID"] = project_id
                        env_copy["BQ_LOCATION"] = config.get("bq_location", "europe-west1")
                        env_copy["FINOPS_DATASET_ID"] = f"finops_{env}"
                        res = subprocess.run([sys.executable, init_pricing_path], env=env_copy, capture_output=True, text=True)
                        if res.returncode == 0:
                            print("  [+] FinOps Pricing seeded successfully.")
                        else:
                            print(f"  [-] Failed to seed FinOps Pricing: {res.stderr.strip()[:200]}")
                    else:
                        print(f"  [-] init_pricing.py not found at {init_pricing_path}")
                except Exception as e:
                    print(f"  [-] Error running init_pricing.py: {e}")

            else:
                logger.error(f"[-] Sanity Test FAIL: DNS resolution timeout.")
                sys.exit(1)
        else:
            logger.warning("[!] Skipping Sanity check. Missing terraform outputs (lb_ip or admin_password).")

        if SANITY_ERROR_COUNT > 0:
            raise DeploymentError(f"{SANITY_ERROR_COUNT} Sanity Checks failed. Consultez le rapport antigravity_sanity_error.md")

    finally:
        if force:
            toggle_prevent_destroy(disable=False)

def plan(env):
    init_tf()
    set_workspace(env)
    
    logger.info(f"[*] Generating dry-run (terraform plan) for environment '{env}'...")
    project_id = os.environ.get("TF_VAR_project_id", "slavayssiere-sandbox-462015")
    cmd = ["terraform", "plan"] + get_tf_args(project_id)
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

        # Éjecter aussi les zones DNS additionnelles (extra_domains) pour les préserver
        _extra = config.get("extra_domains", [])
        for _d in _extra:
            _zone = _d.get("zone_name", "")
            if not _zone:
                continue
            _tf_zone = f'google_dns_managed_zone.extra_zones["{_zone}"]'
            _tf_ns   = f'google_dns_record_set.extra_ns_delegation["{_zone}"]'
            _tf_a    = f'google_dns_record_set.extra_a["{_zone}"]'
            run_cmd(["terraform", "state", "rm", _tf_zone], check=False)
            run_cmd(["terraform", "state", "rm", _tf_ns], check=False)
            run_cmd(["terraform", "state", "rm", _tf_a], check=False)

    print("[*] Ejecting AlloyDB users and Drive Service Account from Terraform state to preserve them...")
    state_list_res = subprocess.run(["terraform", "state", "list"], cwd=TERRAFORM_DIR, capture_output=True, text=True)
    if state_list_res.returncode == 0:
        for line in state_list_res.stdout.splitlines():
            line = line.strip()
            if line.startswith("google_alloydb_user."):
                # NOTE: google_service_account.cr_sa["drive"] n'existe pas (data source) — pas à éjecter
                run_cmd(["terraform", "state", "rm", line], check=False)

    print(f"[*] Destroying all other components for environment '{env}'...")

    # Parallelisme adaptatif : les DELETE GCP sont encore plus sensibles aux
    # quotas API que les lectures du refresh. On applique la meme heuristique.
    region = config.get("region", "europe-west1")
    parallelism = get_gcp_quota_parallelism(project_id, region)
    cmd = ["terraform", "destroy", "-auto-approve",
           f"-parallelism={parallelism}", "-lock-timeout=120s"] + get_tf_args(project_id)

    try:
        res = run_cmd(cmd, check=False, live=True)
        if res.returncode != 0:
            print("[*] Destroy echoue. Pause 15s et nouvelle tentative...")
            time.sleep(15)
            res = run_cmd(cmd, check=False, live=True)
            if res.returncode != 0:
                print(f"[!] Echec definitif du destroy.")
                sys.exit(res.returncode)
        if SANITY_ERROR_COUNT > 0:
            raise DeploymentError(f"{SANITY_ERROR_COUNT} Sanity Checks failed. Consultez le rapport antigravity_sanity_error.md")

    finally:
        if force:
            toggle_prevent_destroy(disable=False)

if __name__ == "__main__":
    # Nettoyage de l'ancien rapport d'erreurs
    report_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "antigravity_sanity_error.md")
    if os.path.exists(report_file):
        os.remove(report_file)

    parser = argparse.ArgumentParser(description="Platform Engineering - Manage Environments")
    parser.add_argument("action", choices=["deploy", "destroy", "plan"], help="Action to perform")
    parser.add_argument("--env", required=True, help="Environment name (dev, uat, prd)")
    parser.add_argument("--force", action="store_true", help="Force deletion or replacement of protected DNS/SSL resources")
    
    args = parser.parse_args()

    try:
        check_binary_dependencies()
        
        # Load YAML Configuration
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "envs", f"{args.env}.yaml")
        if not os.path.exists(config_path):
            logger.error(f"[!] Configuration file not found: {config_path}")
            sys.exit(1)
            
        # Auto-discover component versions from local VERSION files
        local_versions = discover_versions()

        # Load YAML Configuration
        config = load_config(config_path)

        # Versions declared in the YAML take priority over local VERSION files.
        # This allows pinning a specific version in UAT/PRD without a local rebuild.
        # Priority chain: env var > YAML _version > local VERSION file
        yaml_versions = {k: v for k, v in config.items() if k.endswith("_version") and v}
        merged_versions = {**local_versions, **yaml_versions}

        # If the YAML declares image_registry, build all image URLs from it.
        # Otherwise fall back to legacy behaviour (image_* keys declared directly in YAML).
        registry = config.get("image_registry")
        if registry:
            images = build_image_urls(registry, merged_versions)
        else:
            # Legacy: image_* keys come directly from YAML (rétrocompatibilité)
            images = {k: v for k, v in config.items() if k.startswith("image_")}
            logger.warning(
                "[!] 'image_registry' absent du YAML — utilisation des clés image_* directes. "
                "Migrez vers 'image_registry' pour simplifier la configuration."
            )

        # Base config = everything except image_* and *_version keys (handled above)
        base_config = {
            k: v for k, v in config.items()
            if not k.startswith("image_") and not k.endswith("_version")
        }

        # Final flat config for Terraform
        final_config = {**base_config, **merged_versions, **images}

        # Clean up any existing auto.tfvars.json files to prevent variable bleeding
        for fname in os.listdir(TERRAFORM_DIR):
            if fname.endswith(".auto.tfvars.json"):
                try:
                    os.remove(os.path.join(TERRAFORM_DIR, fname))
                except OSError:
                    pass

        # Dump it as auto.tfvars.json for Terraform to ingest automatically
        tfvars_path = os.path.join(TERRAFORM_DIR, f"{args.env}.auto.tfvars.json")
        with open(tfvars_path, "w") as f:
            json.dump(final_config, f, indent=2)
        logger.info(f"[+] {args.env}.auto.tfvars.json généré ({len(final_config)} variables).")

        project_id = final_config.get("project_id", "slavayssiere-sandbox-462015")
        CURRENT_PROJECT_ID = project_id
        base_domain = final_config.get("base_domain", "slavayssiere-zenika.com")

        if args.action == "deploy":
            deploy(args.env, base_domain, project_id, final_config, force=args.force)
        elif args.action == "destroy":
            destroy(args.env, project_id, final_config, force=args.force)
        elif args.action == "plan":
            plan(args.env)
            
    except DeploymentError as e:
        logger.error(f"DEPLOYMENT FAILED: {e}")
        generate_antigravity_error_report("Exécution Terraform / Déploiement infra", str(e), ["terraform", "deployment", "infrastructure"])
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
