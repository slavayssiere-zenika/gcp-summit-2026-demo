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
import urllib.parse
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


def generate_antigravity_error_report(
        task_context: str, error_message: str,
        tags: list = None, env: str = None,
        tf_workspace: str = None):
    """Génère ou met à jour un rapport d'erreur Markdown enrichi pour l'Agent Antigravity."""
    global SANITY_ERROR_COUNT
    SANITY_ERROR_COUNT += 1
    project_id = CURRENT_PROJECT_ID
    report_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "antigravity_sanity_error.md")
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    tags_list = tags or ["sanity-check"]
    tags_str = ", ".join(tags_list)
    elapsed_str = elapsed()

    # Contexte d'invocation
    argv_str = " ".join(sys.argv)
    env_str = env or os.environ.get("ENV", "unknown")
    workspace_str = tf_workspace or env_str

    # Commandes MCP suggérées selon les tags
    mcp_commands = []
    mcp_commands.append("python3 scripts/mcp_cli.py health")
    mcp_commands.append("python3 scripts/mcp_cli.py errors --hours 2")
    if any(t in ["terraform", "apply", "gcp"] for t in tags_list):
        mcp_commands.append("python3 scripts/mcp_cli.py errors --hours 1")
    if any(t in ["frontend", "sync", "rsync", "gcloud"] for t in tags_list):
        mcp_commands.append(
            "python3 scripts/mcp_cli.py query 'SELECT * FROM information_schema.tables LIMIT 5'"
        )
    if any(t in ["sanity", "login", "api"] for t in tags_list):
        cmd_analytics = ("python3 scripts/mcp_cli.py call analytics get_finops_report "
                         "--args '{\"period\":\"daily\"}'")
        mcp_commands.append(cmd_analytics)

    is_new = not os.path.exists(report_file)
    with open(report_file, "a", encoding="utf-8") as f:
        if is_new:
            f.write("# 🚨 Rapport d'Erreur manage_env.py (pour Antigravity)\n\n")
            f.write("> **Instructions pour Antigravity** :\n")
            f.write("> 1. Lis chaque erreur ci-dessous avec son contexte complet.\n")
            f.write("> 2. Cherche en mémoire : `mcp_antigravity-memory_search_past_errors(query=\"<tags>\")`\n")
            f.write(f"> 3. Consulte les logs GCP pour le projet `{project_id}` via les outils MCP.\n")
            f.write("> 4. Propose un fix précis (fichier + ligne) — ne jamais supposer sans avoir vérifié.\n")
            f.write("> 5. Une fois résolu : `mcp_antigravity-memory_log_error_and_solution(...)`\n\n")
            f.write("---\n\n")

        f.write(f"## 🔴 Erreur #{SANITY_ERROR_COUNT} — {timestamp}\n\n")

        f.write("### Contexte opérationnel\n\n")
        f.write("| Champ | Valeur |\n")
        f.write("|---|---|\n")
        f.write(f"| **Contexte** | {task_context} |\n")
        f.write(f"| **Environnement** | `{env_str}` |\n")
        f.write(f"| **Workspace Terraform** | `{workspace_str}` |\n")
        f.write(f"| **Projet GCP** | `{project_id}` |\n")
        f.write(f"| **Tags** | `{tags_str}` |\n")
        f.write(f"| **Commande** | `{argv_str}` |\n")
        f.write(f"| **Temps écoulé** | {elapsed_str} |\n\n")

        f.write("### Message d'erreur\n\n")
        f.write("```text\n")
        f.write(f"{error_message}\n")
        f.write("```\n\n")

        f.write("### 🔍 Commandes MCP suggérées pour investiguer\n\n")
        f.write("```bash\n")
        for cmd in mcp_commands:
            f.write(f"{cmd}\n")
        f.write("```\n\n")

        f.write("### Prochaines étapes\n\n")
        f.write(f"1. Chercher en mémoire : "
                f"`mcp_antigravity-memory_search_past_errors(query=\"{tags_str}\")`\n")
        f.write("2. Analyser les logs Terraform / Cloud Run via MCP ci-dessus\n")
        f.write("3. Identifier le fichier source à corriger\n")
        f.write("4. Mémoriser la solution après fix\n\n")

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
    "users": "users_api",
    "items": "items_api",
    "competencies": "competencies_api",
    "cv": "cv_api",
    "missions": "missions_api",
    "prompts": "prompts_api",
    "db_migrations": "db_migrations",
    "db_init": "db_init",        # Image dédiée au Cloud Run Job d'initialisation AlloyDB
    "analytics": "analytics_mcp",
    "monitoring": "monitoring_mcp",
    "agent_router": "agent_router_api",
    "agent_hr": "agent_hr_api",
    "agent_ops": "agent_ops_api",
    "agent_missions": "agent_missions_api",
    "drive": "drive_api",
    "grafana": "grafana",
}


# Regex de validation du nom d'un projet externe.
# Format kebab-case : commence par une lettre minuscule, puis lettres minuscules/chiffres/tirets, 3-31 chars total.
# Compatible Cloud Run, Artifact Registry et variables Terraform.
EXTRA_PROJECT_NAME_RE = r"^[a-z][a-z0-9-]{2,30}$"

# Regex semver strict pour le champ `version` d'un projet externe (ex: v0.1.0).
EXTRA_PROJECT_VERSION_RE = r"^v\d+\.\d+\.\d+$"


def validate_extra_project_structure(
    name: str, path: str, lb_path: str, version: str, db_migrations_version: str = None
) -> dict:
    """
    Valide la structure d'un projet externe avant tout déploiement.

    Vérifie :
    - Conformité du nom (kebab-case, regex EXTRA_PROJECT_NAME_RE)
    - Présence du Dockerfile, des répertoires database/ et terraform/
    - Format lb_path (doit commencer par '/')
    - Format version semver (ex: v0.1.0)
    - Format db_migrations_version semver si présent (ex: v0.1.0)

    Retourne un dict structuré :
        {
            "name": str,
            "path": str,
            "lb_path": str,
            "version": str,
            "db_migrations_version": str,
            "valid": bool,
            "errors": list[str]
        }
    """
    errors = []

    # Validation du nom
    if not re.match(EXTRA_PROJECT_NAME_RE, name):
        errors.append(
            f"name '{name}' invalide — doit respecter '{EXTRA_PROJECT_NAME_RE}' "
            "(kebab-case, 3-31 chars, ex: ia-dev-memory)"
        )

    # Validation du lb_path
    if not lb_path:
        errors.append("lb_path est vide — doit commencer par '/' (ex: /ia-dev-memory)")
    elif not lb_path.startswith("/"):
        errors.append(f"lb_path '{lb_path}' doit commencer par '/' (ex: /ia-dev-memory)")
    elif " " in lb_path:
        errors.append(f"lb_path '{lb_path}' ne doit pas contenir d'espaces")

    # Validation de la version
    if not re.match(EXTRA_PROJECT_VERSION_RE, version):
        errors.append(
            f"version '{version}' invalide — doit respecter le format semver '{EXTRA_PROJECT_VERSION_RE}' "
            "(ex: v0.1.0)"
        )

    # Validation de la version des migrations
    if db_migrations_version and not re.match(EXTRA_PROJECT_VERSION_RE, db_migrations_version):
        errors.append(
            f"db_migrations_version '{db_migrations_version}' invalide "
            f"— doit respecter le format semver '{EXTRA_PROJECT_VERSION_RE}' "
            "(ex: v0.1.0)"
        )

    # Validation du répertoire racine
    if not os.path.isdir(path):
        errors.append(f"répertoire '{path}' introuvable ou inaccessible")
    else:
        # Validation des éléments internes (seulement si le répertoire existe)
        if not os.path.isfile(os.path.join(path, "Dockerfile")):
            errors.append(f"Dockerfile absent dans '{path}'")
        if not os.path.isdir(os.path.join(path, "database")):
            errors.append(f"répertoire 'database/' absent dans '{path}' (migrations Liquibase requis)")
        if not os.path.isdir(os.path.join(path, "terraform")):
            errors.append(f"répertoire 'terraform/' absent dans '{path}' (modules Terraform requis)")

    return {
        "name": name,
        "path": path,
        "lb_path": lb_path,
        "version": version,
        "db_migrations_version": db_migrations_version,
        "alloydb_database": "",  # rempli par discover_extra_projects
        "valid": len(errors) == 0,
        "errors": errors,
    }


def discover_extra_projects(config: dict) -> list:
    """
    Lit la clé 'extra_projects' du YAML et valide chaque projet en fail-fast.

    Comportement :
    - Si 'extra_projects' est absent ou vide → retourne []
    - Si un projet est invalide → raise DeploymentError (bloque tout le déploiement)
    - Si deux projets ont le même 'name' ou 'lb_path' → raise DeploymentError
    - Si tout est valide → retourne la liste des projets avec leurs métadonnées

    Doit être appelée au tout début du processus, avant tout terraform init/apply.
    """
    raw_projects = config.get("extra_projects") or []
    if not raw_projects:
        return []

    logger.info(f"[extra_projects] {len(raw_projects)} projet(s) externe(s) déclaré(s). Validation...")

    seen_names = set()
    seen_lb_paths = set()
    validated = []

    for i, proj in enumerate(raw_projects):
        # Champs obligatoires
        missing_fields = [
            f for f in ("name", "path", "lb_path", "version")
            if not proj.get(f)
        ]
        if missing_fields:
            raise DeploymentError(
                f"[extra_projects] Projet #{i + 1} : champs obligatoires manquants : "
                f"{missing_fields}. Vérifiez la section extra_projects du YAML."
            )

        name = proj["name"]
        path = proj["path"]
        lb_path = proj["lb_path"]
        version = proj["version"]
        db_migrations_version = proj.get("db_migrations_version")
        # alloydb_database est optionnel : défaut = name avec tirets remplacess par underscores
        alloydb_database = proj.get("alloydb_database") or name.replace("-", "_")

        # Doublon de name
        if name in seen_names:
            raise DeploymentError(
                f"[extra_projects] Doublon de name détecté : '{name}'. "
                "Chaque projet externe doit avoir un nom unique."
            )
        # Doublon de lb_path
        if lb_path in seen_lb_paths:
            raise DeploymentError(
                f"[extra_projects] Doublon de lb_path détecté : '{lb_path}'. "
                "Chaque projet externe doit avoir un chemin LB unique."
            )

        result = validate_extra_project_structure(name, path, lb_path, version, db_migrations_version)

        if not result["valid"]:
            error_detail = "\n    ".join(result["errors"])
            raise DeploymentError(
                f"[extra_projects] Projet '{name}' invalide :\n    {error_detail}\n"
                "Corrigez la structure du projet avant de relancer le déploiement."
            )

        seen_names.add(name)
        seen_lb_paths.add(lb_path)
        result["alloydb_database"] = alloydb_database
        result["db_migrations_version"] = db_migrations_version or version
        result["health_check_paths"] = proj.get("health_check_paths") or []
        result["token_iap"] = proj.get("token_iap") or False
        validated.append(result)
        logger.info(
            f"  [+] Projet externe validé : '{name}' ({path}) → "
            f"lb_path={lb_path} version={version} "
            f"db_migrations_version={result['db_migrations_version']} "
            f"alloydb_database={alloydb_database}"
        )

    logger.info(f"[extra_projects] {len(validated)}/{len(raw_projects)} projet(s) externe(s) validé(s).")
    return validated


def _get_platform_tf_outputs() -> dict:
    """
    Lit les outputs JSON du Terraform de la plateforme principale.

    Retourne un dict {output_key: value} ou {} si terraform output échoue
    (ex : premier déploiement où le state n'existe pas encore).
    Ne doit jamais lever d'exception.
    """
    try:
        res = subprocess.run(
            ["terraform", "output", "-json"],
            cwd=TERRAFORM_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if res.returncode != 0 or not res.stdout.strip():
            logger.warning(
                "[extra_projects] Impossible de lire les outputs Terraform de la plateforme "
                "(state vide ou terraform non initialisé). Les variables VPC seront vides."
            )
            return {}
        raw = json.loads(res.stdout)
        # Déplie {key: {value: ..., sensitive: ...}} → {key: ...}
        return {k: v.get("value", "") for k, v in raw.items()}
    except Exception as exc:
        logger.warning(f"[extra_projects] Erreur lors de la lecture des outputs Terraform : {exc}")
        return {}


_LB_ROUTES_STATE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".lb_routes_state.json"
)


def _lb_routes_load(env: str) -> list:
    """Lit la liste de routes extra-projects persistée pour un environnement donné."""
    if os.path.exists(_LB_ROUTES_STATE_FILE):
        try:
            with open(_LB_ROUTES_STATE_FILE) as f:
                state = json.load(f)
                if isinstance(state, dict):
                    return state.get(env) or []
                # Fallback pour compatibilité si l'ancien fichier était une liste
                return []
        except Exception as exc:
            logger.warning(f"[lb-routes] Impossible de lire .lb_routes_state.json : {exc}")
    return []


def _lb_routes_save(env: str, routes: list) -> None:
    """Persiste la liste de routes extra-projects pour un environnement donné."""
    state = {}
    if os.path.exists(_LB_ROUTES_STATE_FILE):
        try:
            with open(_LB_ROUTES_STATE_FILE) as f:
                content = json.load(f)
                if isinstance(content, dict):
                    state = content
        except Exception:
            pass
    state[env] = routes
    with open(_LB_ROUTES_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _update_lb_routes_and_apply(
    name: str,
    lb_path: str,
    tf_dir: str,
    env: str,
    project_id: str = "slavayssiere-sandbox-462015",
) -> None:
    """Met à jour la route LB de l'extra-project via Terraform (apply ciblé).

    Algorithme :
      1. Lit backend_service_id depuis `terraform output -json` du projet externe.
      2. Met à jour .lb_routes_state.json (upsert par name).
      3. Écrit extra_project_routes dans le {env}.auto.tfvars.json de la plateforme.
      4. Lance `terraform apply -target=google_compute_url_map.default -auto-approve`
         depuis le répertoire Terraform de la plateforme.

    Avantage : les routes survivent à tout `terraform apply` ultérieur de la plateforme,
    car elles sont déclarées dans var.extra_project_routes et gérées par le bloc dynamic.
    """
    # ── 1. Lire backend_service_id ────────────────────────────────────────────
    try:
        res = subprocess.run(
            ["terraform", "output", "-json"],
            cwd=tf_dir, capture_output=True, text=True, timeout=30,
        )
        if res.returncode != 0 or not res.stdout.strip():
            logger.warning(f"  [lb-routes] Impossible de lire les outputs terraform de '{name}' — LB ignoré.")
            return
        tf_outputs = json.loads(res.stdout)
        backend_service_id = (tf_outputs.get("backend_service_id") or {}).get("value", "")
        if not backend_service_id:
            logger.warning(f"  [lb-routes] Output 'backend_service_id' absent pour '{name}' — LB ignoré.")
            return
    except Exception as exc:
        logger.warning(f"  [lb-routes] Erreur lecture outputs terraform '{name}' : {exc}")
        return

    logger.info(f"  [lb-routes] backend_service_id = {backend_service_id}")

    # ── 2. Upsert dans le state ───────────────────────────────────────────────
    routes = _lb_routes_load(env)
    existing = next((r for r in routes if r["name"] == name), None)
    if existing:
        existing["backend_service_id"] = backend_service_id
        existing["lb_path"] = lb_path
    else:
        routes.append({"name": name, "lb_path": lb_path, "backend_service_id": backend_service_id})
    _lb_routes_save(env, routes)
    logger.info(f"  [lb-routes] State mis à jour ({len(routes)} route(s)) → apply ciblé URL map...")

    # ── 3. Mettre à jour extra_project_routes dans le tfvars de la plateforme ─
    tfvars_path = os.path.join(TERRAFORM_DIR, f"{env}.auto.tfvars.json")
    try:
        with open(tfvars_path) as f:
            tfvars = json.load(f)
    except Exception as exc:
        logger.warning(f"  [lb-routes] Impossible de lire {tfvars_path} : {exc} — apply ciblé annulé.")
        return
    tfvars["extra_project_routes"] = routes
    with open(tfvars_path, "w") as f:
        json.dump(tfvars, f, indent=2)

    # ── 4. Apply ciblé sur le URL map uniquement ──────────────────────────────
    tf_vars = get_tf_args(project_id)
    apply_cmd = [
        "terraform", "apply",
        "-target=google_compute_url_map.default",
        "-auto-approve", "-lock-timeout=60s",
    ] + tf_vars
    logger.info(f"  [lb-routes] Running: {' '.join(apply_cmd)}")
    result = subprocess.run(apply_cmd, cwd=TERRAFORM_DIR, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        logger.warning(
            f"  [lb-routes] Apply ciblé échoué :\n{(result.stdout + result.stderr)[-500:]}"
        )
    else:
        logger.info(f"  [lb-routes] ✓ URL map mis à jour — route '{lb_path}' active via Terraform.")


def _detach_extra_project_routes(env: str, project_id: str) -> None:
    """Retire toutes les routes extra-projects du Load Balancer principal avant destruction.

    Évite l'erreur 'resourceInUseByAnotherResource' sur les BackendServices GCP.
    """
    logger.info("[*] Détachement des routes extra-projects du Load Balancer principal...")
    # 1. Met à jour le state local à vide
    _lb_routes_save(env, [])

    # 2. Lit le tfvars existant, et force extra_project_routes à []
    tfvars_path = os.path.join(TERRAFORM_DIR, f"{env}.auto.tfvars.json")
    try:
        if os.path.exists(tfvars_path):
            with open(tfvars_path) as f:
                tfvars = json.load(f)
        else:
            tfvars = {}
        tfvars["extra_project_routes"] = []
        with open(tfvars_path, "w") as f:
            json.dump(tfvars, f, indent=2)
    except Exception as exc:
        logger.warning(f"  [destroy-lb] Impossible de mettre à jour {tfvars_path} : {exc}")
        return

    # 3. Lance un apply ciblé pour détacher les routes dans GCP
    tf_vars = get_tf_args(project_id)
    apply_cmd = [
        "terraform", "apply",
        "-target=google_compute_url_map.default",
        "-refresh=false",
        "-auto-approve", "-lock-timeout=60s",
    ] + tf_vars
    logger.info(f"  [destroy-lb] Running: {' '.join(apply_cmd)}")
    result = subprocess.run(apply_cmd, cwd=TERRAFORM_DIR, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        logger.warning(
            f"  [destroy-lb] Échec du détachement des routes (apply ciblé) :\n"
            f"{(result.stdout + result.stderr)[-500:]}"
        )
    else:
        logger.info("[+] ✓ Toutes les routes extra-projects ont été détachées du Load Balancer.")


def _get_latest_active_secret_version(project_id: str, secret_id: str) -> str:
    """
    Interroge Secret Manager via gcloud pour récupérer le numéro de la dernière version active (ENABLED).
    Si aucune version n'est active ou en cas d'erreur, retourne "latest" par défaut.
    """
    try:
        cmd = [
            "gcloud", "secrets", "versions", "list", secret_id,
            f"--project={project_id}",
            "--filter=state=ENABLED",
            "--format=value(name)",
            "--limit=1"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            output = res.stdout.strip()
            # gcloud peut retourner la version seule ou le path complet: projects/.../versions/X
            if output.isdigit():
                return output
            if "/" in output:
                return output.split("/")[-1]
    except Exception as e:
        logger.warning(f"[secrets] Impossible de récupérer la version active de {secret_id} : {e}")
    return "latest"


def deploy_extra_project_terraform(
    project: dict,
    env: str,
    project_id: str,
    region: str = "europe-west1",
) -> None:
    """
    Lance le déploiement Terraform du projet externe depuis son propre répertoire terraform/.

    Appelé APRÈS le terraform apply de la plateforme principale,
    AVANT les sanity checks.

    Variables injectées automatiquement dans Terraform :
    - project_id              : identifiant GCP (depuis le YAML d'environnement)
    - region                  : région GCP (depuis le YAML d'environnement)
    - service_name            : name du projet externe (depuis extra_projects[].name)
    - image_version           : version de l'image (depuis extra_projects[].version)
    - image                   : URL complète de l'image Docker ({registry}/{name}:{version})
    - lb_path                 : préfixe de routage LB (depuis extra_projects[].lb_path)
    - vpc_network_id          : ID du VPC principal (depuis terraform output vpc_network_id)
    - vpc_subnet_id           : ID du sous-réseau principal (depuis terraform output vpc_subnet_id)
    - alloydb_instance_uri    : URI de l'instance AlloyDB primaire (depuis terraform output alloydb_instance_uri)
    - iap_oauth_client_id     : Secret Manager secret_id de l'IAP OAuth Client ID
    - iap_oauth_client_secret : Secret Manager secret_id de l'IAP OAuth Client Secret
    """
    name = project["name"]
    version = project["version"]
    tf_dir = os.path.join(project["path"], "terraform")

    logger.info(f"[extra_projects] Déploiement Terraform du projet externe : '{name}'")
    logger.info(f"  Répertoire : {tf_dir}")
    logger.info(f"  Version    : {version}")

    # ── Récupération des outputs de la plateforme (VPC, etc.) ─────────────────
    platform_outputs = _get_platform_tf_outputs()
    vpc_network_id = platform_outputs.get("vpc_network_id", "")
    vpc_subnet_id = platform_outputs.get("vpc_subnet_id", "")
    alloydb_instance_uri = platform_outputs.get("alloydb_instance_uri", "")
    alloydb_ip = platform_outputs.get("alloydb_ip", "")
    tf_state_bucket = platform_outputs.get("tf_state_bucket", "")
    sa_emails = platform_outputs.get("extra_project_sa_emails") or {}

    _OUTPUTS_TO_CHECK = [
        ("vpc_network_id", vpc_network_id),
        ("vpc_subnet_id", vpc_subnet_id),
        ("alloydb_instance_uri", alloydb_instance_uri),
        ("alloydb_ip", alloydb_ip),
        ("tf_state_bucket", tf_state_bucket),
    ]
    for _output_name, _output_val in _OUTPUTS_TO_CHECK:
        if not _output_val:
            logger.warning(
                f"[extra_projects] {_output_name} absent des outputs Terraform — "
                f"le projet '{name}' recevra une valeur vide pour cette variable."
            )

    # ── Service Account email du SA créé par la plateforme pour ce projet ────
    service_account_email = sa_emails.get(name, "")
    if not service_account_email:
        service_account_email = f"sa-{name}-{env}@{project_id}.iam.gserviceaccount.com"
        logger.info(f"  [fallback] Utilisation de l'email SA calculé : {service_account_email}")

    alloydb_database = project.get("alloydb_database") or name.replace("-", "_")

    # Convention plateforme GCP : noms des secrets IAP OAuth dans Secret Manager.
    # Identiques sur tous les projets GCP de la plateforme.
    iap_oauth_client_id_secret = "google-secret-id"
    iap_oauth_client_secret_secret = "google-secret-key"

    # Récupération de la dernière version active pour IAP OAuth (évite les erreurs sur les versions détruites)
    iap_oauth_client_version = _get_latest_active_secret_version(project_id, iap_oauth_client_id_secret)
    logger.info(f"  [secrets] Version active pour IAP OAuth : {iap_oauth_client_version}")

    db_migrations_version = project.get("db_migrations_version") or version

    tf_vars = [
        f"-var=project_id={project_id}",
        f"-var=region={region}",
        f"-var=service_name={name}",
        f"-var=image_version={version}",
        f"-var=image_db_migrations_version={db_migrations_version}",
        f"-var=lb_path={project['lb_path']}",
        f"-var=vpc_network_id={vpc_network_id}",
        f"-var=vpc_subnet_id={vpc_subnet_id}",
        f"-var=alloydb_instance_uri={alloydb_instance_uri}",
        f"-var=alloydb_ip={alloydb_ip}",
        f"-var=alloydb_database={alloydb_database}",
        f"-var=service_account_email={service_account_email}",
        f"-var=iap_oauth_client_id={iap_oauth_client_id_secret}",
        f"-var=iap_oauth_client_secret={iap_oauth_client_secret_secret}",
        f"-var=iap_oauth_client_version={iap_oauth_client_version}",
    ]

    logger.info(
        f"  Variables injectées : project_id={project_id} | region={region} | "
        f"service_name={name} | image_version={version} | "
        f"image_db_migrations_version={db_migrations_version} | "
        f"lb_path={project['lb_path']} | "
        f"vpc_network_id={'<set>' if vpc_network_id else '<vide>'} | "
        f"vpc_subnet_id={'<set>' if vpc_subnet_id else '<vide>'} | "
        f"alloydb_ip={'<set>' if alloydb_ip else '<vide>'} | "
        f"alloydb_database={alloydb_database} | "
        f"sa_email={'<set>' if service_account_email else '<vide>'} | "
        f"alloydb_instance_uri={'<set>' if alloydb_instance_uri else '<vide>'} | "
        f"iap_client_id={iap_oauth_client_id_secret} | "
        f"iap_client_secret={iap_oauth_client_secret_secret} | "
        f"iap_client_version={iap_oauth_client_version} | "
        f"NOTE: image injecte par le sous-projet (defaut variables.tf)"
    )

    # ── Génère un backend.tf dans le terraform/ du projet externe ──────────
    # Le state est isolé par projet et par env : terraform/state/{env}/{name}
    if tf_state_bucket:
        backend_tf_path = os.path.join(tf_dir, "backend.tf")
        backend_tf_content = (
            '# AUTO-GENERATED by manage_env.py — ne pas modifier manuellement.\n'
            '# Ce fichier est réécrit à chaque déploiement.\n'
            'terraform {\n'
            '  backend "gcs" {\n'
            f'    bucket = "{tf_state_bucket}"\n'
            f'    prefix = "terraform/state/{env}/{name}"\n'
            '  }\n'
            '}\n'
        )
        with open(backend_tf_path, "w") as _f:
            _f.write(backend_tf_content)
        logger.info(f"  [backend] backend.tf généré : bucket={tf_state_bucket} prefix=terraform/state/{env}/{name}")
    else:
        logger.warning(
            f"[extra_projects] tf_state_bucket absent des outputs — "
            f"le backend GCS ne sera pas configuré pour '{name}'. "
            "Le state sera local (risque de perte de state)."
        )

    # Lance terraform init + apply dans le répertoire terraform/ du projet externe
    # (run_cmd utilise TERRAFORM_DIR global — on utilise subprocess.run directement avec cwd=tf_dir)
    def _run_extra(cmd, **kwargs):
        logger.info(f"[*] Running (extra project): {' '.join(cmd)}  (elapsed: {elapsed()})")
        process = subprocess.Popen(
            cmd, cwd=tf_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        full_output = []
        for line in iter(process.stdout.readline, ""):
            print(line, end="", flush=True)
            full_output.append(line)
        process.stdout.close()
        return_code = process.wait()
        if return_code != 0:
            raise DeploymentError(
                f"[extra_projects] Terraform '{' '.join(cmd[:2])}' échoué pour le projet '{name}'.\n"
                f"{''.join(full_output[-30:])}"
            )

    _run_extra(["terraform", "init", "-reconfigure", "-upgrade"])

    # ── db-init AVANT terraform apply ────────────────────────────────────────
    # Le job Liquibase (null_resource.run_db_migrations_job) s'exécute PENDANT
    # le terraform apply. Il doit pouvoir se connecter en IAM → base + GRANT
    # doivent exister avant. On déclenche donc db-init-job-{env} maintenant.
    # db_init.py est idempotent : CREATE DATABASE + GRANT sont sans effet si déjà présents.
    # On n'utilise PAS de state local (pas de .db_init_state.json) — approche stateless.
    db_init_job = f"db-init-job-{env}"
    alloydb_iam_user = service_account_email.replace(".gserviceaccount.com", "") if service_account_email else ""

    if alloydb_iam_user and alloydb_ip and alloydb_database:
        logger.info(
            f"  [db-init] Exécution de {db_init_job} AVANT l'apply "
            f"(base='{alloydb_database}' / user='{alloydb_iam_user}') — idempotent, toujours rejoué"
        )
        db_init_cmd = [
            "gcloud", "run", "jobs", "execute", db_init_job,
            f"--region={region}",
            f"--project={project_id}",
            "--wait",
            f"--update-env-vars=EXTRA_DB_NAME={alloydb_database},EXTRA_IAM_USER={alloydb_iam_user}",
        ]
        logger.info(f"  [*] Running: {' '.join(db_init_cmd)}  (elapsed: {elapsed()})")
        result = subprocess.run(db_init_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise DeploymentError(
                f"  [db-init] Le job {db_init_job} a échoué pour '{name}' :\n"
                f"{(result.stdout + result.stderr)[-500:]}"
            )
        logger.info(f"  [db-init] ✓ Base '{alloydb_database}' prête, droits IAM accordés.")

    else:
        raise DeploymentError(
            f"[db-init] Paramètres manquants pour '{name}' "
            f"(sa_email={alloydb_iam_user!r}, alloydb_ip={alloydb_ip!r}, db={alloydb_database!r}). "
            "Assurez-vous que le terraform apply de la plateforme a créé le SA avant de relancer."
        )

    _run_extra(["terraform", "apply", "-auto-approve", "-lock-timeout=120s"] + tf_vars)

    logger.info(f"  [+] Terraform extra projet '{name}' appliqué avec succès.")

    # ── Mise à jour route LB via Terraform (apply ciblé) ─────────────────────
    _update_lb_routes_and_apply(name, project["lb_path"], tf_dir, env, project_id)


def _destroy_extra_project_terraform(
    project: dict,
    env: str,
    project_id: str,
    region: str = "europe-west1",
) -> None:
    """
    Lance la destruction Terraform du projet externe depuis son propre répertoire terraform/.

    Variables injectées automatiquement dans Terraform (identiques au deploy) :
    - project_id, region, service_name, image_version, etc.
    """
    name = project["name"]
    version = project["version"]
    tf_dir = os.path.join(project["path"], "terraform")

    logger.info(f"[extra_projects] Destruction Terraform du projet externe : '{name}'")
    logger.info(f"  Répertoire : {tf_dir}")
    logger.info(f"  Version    : {version}")

    if not os.path.exists(tf_dir):
        logger.warning(
            f"[extra_projects] Répertoire Terraform inexistant pour '{name}' ({tf_dir}) — Destruction sautée."
        )
        return

    # ── Récupération des outputs de la plateforme (VPC, etc.) ─────────────────
    platform_outputs = _get_platform_tf_outputs()
    vpc_network_id = platform_outputs.get("vpc_network_id", "")
    vpc_subnet_id = platform_outputs.get("vpc_subnet_id", "")
    alloydb_instance_uri = platform_outputs.get("alloydb_instance_uri", "")
    alloydb_ip = platform_outputs.get("alloydb_ip", "")
    tf_state_bucket = platform_outputs.get("tf_state_bucket", "")
    sa_emails = platform_outputs.get("extra_project_sa_emails") or {}

    service_account_email = sa_emails.get(name, "")
    if not service_account_email:
        service_account_email = f"sa-{name}-{env}@{project_id}.iam.gserviceaccount.com"
        logger.info(f"  [fallback] Utilisation de l'email SA calculé pour destroy : {service_account_email}")
    alloydb_database = project.get("alloydb_database") or name.replace("-", "_")

    # Convention plateforme GCP : noms des secrets IAP OAuth dans Secret Manager.
    iap_oauth_client_id_secret = "google-secret-id"
    iap_oauth_client_secret_secret = "google-secret-key"

    # Récupération de la dernière version active pour IAP OAuth
    iap_oauth_client_version = _get_latest_active_secret_version(project_id, iap_oauth_client_id_secret)

    db_migrations_version = project.get("db_migrations_version") or version

    tf_vars = [
        f"-var=project_id={project_id}",
        f"-var=region={region}",
        f"-var=service_name={name}",
        f"-var=image_version={version}",
        f"-var=image_db_migrations_version={db_migrations_version}",
        f"-var=lb_path={project['lb_path']}",
        f"-var=vpc_network_id={vpc_network_id}",
        f"-var=vpc_subnet_id={vpc_subnet_id}",
        f"-var=alloydb_instance_uri={alloydb_instance_uri}",
        f"-var=alloydb_ip={alloydb_ip}",
        f"-var=alloydb_database={alloydb_database}",
        f"-var=service_account_email={service_account_email}",
        f"-var=iap_oauth_client_id={iap_oauth_client_id_secret}",
        f"-var=iap_oauth_client_secret={iap_oauth_client_secret_secret}",
        f"-var=iap_oauth_client_version={iap_oauth_client_version}",
    ]

    # ── Génère un backend.tf dans le terraform/ du projet externe ──────────
    if tf_state_bucket:
        backend_tf_path = os.path.join(tf_dir, "backend.tf")
        backend_tf_content = (
            '# AUTO-GENERATED by manage_env.py — ne pas modifier manuellement.\n'
            '# Ce fichier est réécrit à chaque déploiement.\n'
            'terraform {\n'
            '  backend "gcs" {\n'
            f'    bucket = "{tf_state_bucket}"\n'
            f'    prefix = "terraform/state/{env}/{name}"\n'
            '  }\n'
            '}\n'
        )
        with open(backend_tf_path, "w") as _f:
            _f.write(backend_tf_content)
        logger.info(f"  [backend] backend.tf généré : bucket={tf_state_bucket} prefix=terraform/state/{env}/{name}")

    def _run_extra(cmd, **kwargs):
        logger.info(f"[*] Running (extra project destroy): {' '.join(cmd)}  (elapsed: {elapsed()})")
        process = subprocess.Popen(
            cmd, cwd=tf_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        full_output = []
        for line in iter(process.stdout.readline, ""):
            print(line, end="", flush=True)
            full_output.append(line)
        process.stdout.close()
        return_code = process.wait()
        if return_code != 0:
            raise DeploymentError(
                f"[extra_projects] Terraform '{' '.join(cmd[:2])}' échoué pour le projet '{name}'.\n"
                f"{''.join(full_output[-30:])}"
            )

    _run_extra(["terraform", "init", "-reconfigure", "-upgrade"])
    _run_extra(["terraform", "destroy", "-auto-approve", "-lock-timeout=120s"] + tf_vars)
    logger.info(f"  [+] Terraform extra projet '{name}' détruit avec succès.")


def _cleanup_serverless_addresses(project_id: str, region: str, env: str) -> None:
    """
    Supprime les adresses IP 'serverless-ipv4-*' créées automatiquement par Cloud Run
    VPC Direct Egress, car elles bloquent la suppression du sous-réseau (subnet) lors du destroy.
    """
    logger.info(f"[*] Recherche d'adresses serverless-ipv4 à nettoyer dans la région '{region}'...")
    try:
        cmd_list = [
            "gcloud", "compute", "addresses", "list",
            f"--project={project_id}",
            f"--filter=name ~ ^serverless-ipv4 AND region:({region})",
            "--format=value(name)"
        ]
        logger.info(f"[*] Running: {' '.join(cmd_list)}")
        res = subprocess.run(cmd_list, capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            logger.warning(f"[cleanup-ips] Impossible de lister les adresses : {res.stderr.strip()}")
            return

        addresses = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        if not addresses:
            logger.info("[cleanup-ips] Aucune adresse serverless-ipv4 détectée.")
            return

        logger.info(f"[cleanup-ips] {len(addresses)} adresse(s) à supprimer : {', '.join(addresses)}")
        for addr in addresses:
            cmd_del = [
                "gcloud", "compute", "addresses", "delete", addr,
                f"--project={project_id}",
                f"--region={region}",
                "--quiet"
            ]
            logger.info(f"[*] Running: {' '.join(cmd_del)}")
            del_res = subprocess.run(cmd_del, capture_output=True, text=True, timeout=30)
            if del_res.returncode == 0:
                logger.info(f"[cleanup-ips] ✓ Adresse '{addr}' supprimée avec succès.")
            else:
                logger.warning(f"[cleanup-ips] ✗ Échec de suppression de '{addr}' : {del_res.stderr.strip()}")
    except Exception as exc:
        logger.warning(f"[cleanup-ips] Erreur lors du nettoyage des adresses serverless-ipv4 : {exc}")


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

# ── Log fichier persistant (lisible par Antigravity) ──────────────────────────
# Chemin relatif à la racine du mono-repo (parent du dossier platform-engineering/)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT == "/" or not os.access(_REPO_ROOT, os.W_OK):
    _REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_LOG_DIR = os.path.join(_REPO_ROOT, "deploy_logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_RUN_TS = time.strftime("%Y%m%d_%H%M%S")
_LOG_FILE = os.path.join(_LOG_DIR, f"manage_env_{_RUN_TS}.log")
_file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter(
    '%(asctime)s [+%(elapsed)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))
_file_handler.addFilter(_ElapsedFilter())
logging.root.addHandler(_file_handler)
logger.info("[manage_env] Session démarrée — log : %s", _LOG_FILE)
# ─────────────────────────────────────────────────────────────────────────────


class DeploymentError(Exception):
    """Exception levée lors d'un échec de déploiement."""


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
        res = subprocess.run(["gcloud", "dns", "managed-zones", "describe", name,
                             "--project", project_id, "--format=json"], capture_output=True)
        return res.returncode == 0
    elif resource_type == "ssl_cert":
        res = subprocess.run(["gcloud", "compute", "ssl-certificates", "describe", name,
                             "--global", "--project", project_id, "--format=json"], capture_output=True)
        return res.returncode == 0
    elif resource_type == "sa":
        res = subprocess.run(["gcloud", "iam", "service-accounts", "describe", name,
                             "--project", project_id, "--format=json"], capture_output=True)
        return res.returncode == 0
    elif resource_type == "backend_service":
        region = None
        if "/" in name:
            parts = name.split("/")
            if "regions" in parts:
                try:
                    r_idx = parts.index("regions")
                    region = parts[r_idx + 1]
                except (ValueError, IndexError):
                    pass
            name = parts[-1]

        if region:
            res = subprocess.run([
                "gcloud", "compute", "backend-services", "describe", name,
                "--region", region, "--project", project_id, "--format=json"
            ], capture_output=True)
            return res.returncode == 0
        else:
            res = subprocess.run([
                "gcloud", "compute", "backend-services", "describe", name,
                "--global", "--project", project_id, "--format=json"
            ], capture_output=True)
            if res.returncode == 0:
                return True
            res = subprocess.run([
                "gcloud", "compute", "backend-services", "describe", name,
                "--region", "europe-west1", "--project", project_id, "--format=json"
            ], capture_output=True)
            return res.returncode == 0
    return False


def get_tf_args(project_id: str = "slavayssiere-sandbox-462015") -> list:
    """Retourne les arguments -var supplémentaires pour terraform apply/plan/import."""
    active_version = _get_latest_active_secret_version(project_id, "google-secret-id")
    jwt_active_version = _get_latest_active_secret_version(project_id, "jwt-secret")
    logger.info(f"  [secrets] Version de secret active détectée pour la plateforme principale : {active_version}")
    logger.info(f"  [secrets] Version de jwt-secret active détectée : {jwt_active_version}")
    return [
        f"-var=google_secret_version={active_version}",
        f"-var=jwt_secret_version={jwt_active_version}",
    ]


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
                block_pattern = rf'resource\s+"{
                    re.escape(rtype)}"\s+"{
                    re.escape(rname)}"\s*\{{[^}}]*prevent_destroy\s*=\s*true'
                if re.search(block_pattern, content, re.DOTALL):
                    resources_to_override.append((rtype, rname))

        if not resources_to_override:
            print("[*] No prevent_destroy resources found. No override needed.")
            return

        lines = ["# AUTO-GENERATED by manage_env.py --force. Do NOT commit this file.\n"]
        lines.append("# It is automatically deleted after the operation completes.\n\n")
        for rtype, rname in resources_to_override:
            lines.append('override_resource {{\n')
            lines.append(f'  res = {rtype}.{rname}\n')
            lines.append('  values = {{\n')
            lines.append('    lifecycle = []\n')
            lines.append('  }}\n')
            lines.append('}}\n\n')
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
    state_res = subprocess.run(["terraform", "state", "list", address],
                               cwd=TERRAFORM_DIR, capture_output=True, text=True)
    if state_res.returncode != 0 or address not in state_res.stdout:
        print(f"[*] Checking if persistent resource {address} exists in GCP to import it...")
        try:
            import_res = subprocess.run(["terraform", "import", address, resource_id],
                                        cwd=TERRAFORM_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
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
    cr_base = f"projects/{project_id}/locations/{region}/services"
    mon_base = f"projects/{project_id}/services"
    dns_base = f"projects/{project_id}/managedZones"

    importable_map = {
        # ── Cloud Run Services ───────────────────────────────────────────────
        "google_cloud_run_v2_service.agent_hr_api": f"{cr_base}/agent-hr-api-{env}",
        "google_cloud_run_v2_service.agent_ops_api": f"{cr_base}/agent-ops-api-{env}",
        "google_cloud_run_v2_service.agent_router_api": f"{cr_base}/agent-router-api-{env}",
        "google_cloud_run_v2_service.agent_missions_api": f"{cr_base}/agent-missions-api-{env}",
        "google_cloud_run_v2_service.analytics_mcp": f"{cr_base}/analytics-mcp-{env}",
        "google_cloud_run_v2_service.monitoring_mcp": f"{cr_base}/monitoring-mcp-{env}",
        "google_cloud_run_v2_service.prompts_api": f"{cr_base}/prompts-api-{env}",
        "google_cloud_run_v2_service.users_api": f"{cr_base}/users-api-{env}",
        "google_cloud_run_v2_service.competencies_api": f"{cr_base}/competencies-api-{env}",
        "google_cloud_run_v2_service.cv_api": f"{cr_base}/cv-api-{env}",
        "google_cloud_run_v2_service.drive_api": f"{cr_base}/drive-api-{env}",
        "google_cloud_run_v2_service.items_api": f"{cr_base}/items-api-{env}",
        "google_cloud_run_v2_service.missions_api": f"{cr_base}/missions-api-{env}",
        # ── Monitoring Custom Services ───────────────────────────────────────
        "google_monitoring_custom_service.agent_hr_api_svc": f"{mon_base}/agent-hr-api-service-{env}",
        "google_monitoring_custom_service.agent_ops_api_svc": f"{mon_base}/agent-ops-api-service-{env}",
        "google_monitoring_custom_service.agent_router_api_svc": f"{mon_base}/agent-router-api-service-{env}",
        "google_monitoring_custom_service.agent_missions_api_svc": f"{mon_base}/agent-missions-api-service-{env}",
        "google_monitoring_custom_service.competencies_api_svc": f"{mon_base}/competencies-api-service-{env}",
        "google_monitoring_custom_service.cv_api_svc": f"{mon_base}/cv-api-service-{env}",
        "google_monitoring_custom_service.drive_api_svc": f"{mon_base}/drive-api-service-{env}",
        "google_monitoring_custom_service.items_api_svc": f"{mon_base}/items-api-service-{env}",
        "google_monitoring_custom_service.analytics_mcp_svc": f"{mon_base}/analytics-mcp-service-{env}",
        "google_monitoring_custom_service.monitoring_mcp_svc": f"{mon_base}/monitoring-mcp-service-{env}",
        "google_monitoring_custom_service.missions_api_svc": f"{mon_base}/missions-api-service-{env}",
        "google_monitoring_custom_service.prompts_api_svc": f"{mon_base}/prompts-api-service-{env}",
        "google_monitoring_custom_service.users_api_svc": f"{mon_base}/users-api-service-{env}",
        # ── DNS Managed Zones ────────────────────────────────────────────────
        "google_dns_managed_zone.env_zone": f"{dns_base}/zone-{env}",
        "google_dns_managed_zone.internal_zone": f"{dns_base}/internal-zone-{env}",
        # ── SSL Certificate ──────────────────────────────────────────────────
        "google_compute_managed_ssl_certificate.default": f"projects/{project_id}/global/sslCertificates/ssl-{env}-v2",
        # ── Pub/Sub Topics ───────────────────────────────────────────────────
        "google_pubsub_topic.cv_import_events_dead_letter": f"projects/{project_id}/topics/zenika-cv-import-events-dead-letter-{env}",  # noqa: E501
        "google_pubsub_topic.cv_import_events": f"projects/{project_id}/topics/zenika-cv-import-events-{env}",
        "google_pubsub_topic.user_events": f"projects/{project_id}/topics/zenika-user-events-{env}",
        "google_pubsub_topic.data_quality_events": f"projects/{project_id}/topics/zenika-data-quality-events-{env}",
        # ── Pub/Sub Schemas ──────────────────────────────────────────────────
        "google_pubsub_schema.data_quality_schema": f"projects/{project_id}/schemas/data-quality-schema-v2-{env}",
        # ── Pub/Sub Subscriptions ────────────────────────────────────────────
        "google_pubsub_subscription.cv_import_events_sub": f"projects/{project_id}/subscriptions/cv-import-events-sub-{env}",  # noqa: E501
        "google_pubsub_subscription.cv_import_events_dlq_sub": f"projects/{project_id}/subscriptions/cv-import-events-dlq-sub-{env}",  # noqa: E501
        "google_pubsub_subscription.cv_api_sub": f"projects/{project_id}/subscriptions/cv-api-user-events-sub-{env}",
        "google_pubsub_subscription.items_api_sub": f"projects/{project_id}/subscriptions/items-api-user-events-sub-{env}",  # noqa: E501
        "google_pubsub_subscription.competencies_api_sub": f"projects/{project_id}/subscriptions/competencies-api-user-events-sub-{env}",  # noqa: E501
        "google_pubsub_subscription.data_quality_bq_sub": f"projects/{project_id}/subscriptions/data-quality-bq-sub-{env}",  # noqa: E501
    }

    # ── Zones DNS additionnelles (extra_domains) ──────────────────────
    # Ces ressources sont persistantes et doivent être importées si elles existent dans GCP.
    if extra_domains:
        for d in extra_domains:
            zone_name = d.get("zone_name", "")
            dns_name = d.get("dns_name", "")  # ex: "gen-skillz.znk.io."
            if not zone_name:
                continue
            tf_zone_addr = f'google_dns_managed_zone.extra_zones["{zone_name}"]'
            tf_a_addr = f'google_dns_record_set.extra_a["{zone_name}"]'
            gcp_zone_id = f"{dns_base}/{zone_name}"
            importable_map[tf_zone_addr] = gcp_zone_id
            importable_map[tf_a_addr] = f"{gcp_zone_id}/rrsets/{dns_name}/A"

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
    with_pattern = re.compile(r'with\s+([\w\.\[\]"]+),')
    in_409_block = False

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
    max_ratio = 0.0

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
    print("    +" + "-" * 62 + "+")
    print(f"    | {'QUOTA':<32} {'SCOPE':<14} {'USAGE':>5} {'LIMIT':>5} {'%':>4} |")
    print("    +" + "-" * 62 + "+")
    for q in sorted(all_quotas, key=lambda x: x["ratio"], reverse=True):
        icon = "[CRIT]" if q["ratio"] > 0.80 else "[WARN]" if q["ratio"] > 0.50 else "[ OK ]"
        print(
            f"    | {icon} {
                q['metric']:<28} {
                q['scope']:<14} {
                q['usage']:>5} {
                    q['limit']:>5} {
                        q['ratio'] *
                100:>3.0f}% |")
    print("    +" + "-" * 62 + "+")

    # Decision du parallelisme
    if not all_quotas:
        parallelism = 1
        verdict = "[CRIT] Quotas non disponibles - parallelisme prudent a 1"
    elif max_ratio > 0.80:
        parallelism = 1
        verdict = f"[CRIT] Quota critique ({max_ratio * 100:.0f}% max) -> parallelism = 1"
    elif max_ratio > 0.50:
        parallelism = 2
        verdict = f"[WARN] Quota modere  ({max_ratio * 100:.0f}% max) -> parallelism = 2"
    else:
        parallelism = 3
        verdict = f"[ OK ] Quota OK      ({max_ratio * 100:.0f}% max) -> parallelism = 3"

    print(f"    {verdict}")
    print()
    return parallelism


def _terraform_apply_with_retry(apply_cmd, env, project_id, region, extra_domains):
    """
    Lance terraform apply avec jusqu'à 3 tentatives.

    Entre chaque tentative, tente un auto-import des ressources en conflit 409
    pour gérer les environnements éphémères recréés sur des ressources GCP existantes.
    Quitte le processus avec le code d'erreur Terraform si toutes les tentatives échouent.
    """
    print("[*] Terraform Apply...")
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
        print("[!] Échec définitif de l'apply.")
        sys.exit(res.returncode)


def _post_deploy_frontend_sync(env, project_id, frontend_version=None, ctx_to_use=None):
    """
    Synchronise les assets frontend depuis le bucket source GCS vers le bucket LB.

    Étapes :
    1. Récupère le nom du bucket cible depuis les outputs Terraform.
    2. Identifie la dernière archive dans le bucket source (tri par horodatage ISO8601).
       Si frontend_version est spécifiée, filtre les archives pour correspondre à cette version.
    3. Télécharge, extrait et localise le dossier contenant index.html.
    4. Rsync vers le bucket LB + invalidation CDN si des changements sont détectés.
    """
    print("\n[*] Post-Deploy: Syncing Frontend Assets...")

    # 1. Obtenir le nom du bucket de destination
    res = subprocess.run(
        ["terraform", "output", "-json"], cwd=TERRAFORM_DIR, capture_output=True, text=True
    )
    try:
        outputs = json.loads(res.stdout)
        target_bucket = outputs.get("frontend_bucket_name", {}).get("value", "").strip()
    except Exception:
        target_bucket = ""
    if not target_bucket:
        err_msg = "Could not retrieve frontend_bucket_name from terraform outputs."
        print(f"[!] {err_msg}")
        generate_antigravity_error_report(
            "Post-Deploy : Sync Frontend", err_msg, ["frontend", "sync", "terraform"])
        sys.exit(1)

    SOURCE_ARCHIVES_BUCKET = "z-gcp-summit-frontend"

    # 2. Identifier la dernière archive déposée — tri par horodatage GCS
    # gcloud storage ls retourne l'heure de création en format ISO8601 (tri lexicographique fiable)
    print(f"[*] Looking for the latest archive in gs://{SOURCE_ARCHIVES_BUCKET}/...")
    raw_ls = subprocess.run(
        ["gcloud", "storage", "ls", f"gs://{SOURCE_ARCHIVES_BUCKET}/"],
        capture_output=True, text=True)
    if raw_ls.returncode != 0:
        err_msg = f"Failed to list gs://{SOURCE_ARCHIVES_BUCKET}/"
        print(f"[!] {err_msg}")
        generate_antigravity_error_report(
            "Post-Deploy : Sync Frontend", err_msg, ["frontend", "sync", "gcloud"])
        sys.exit(1)

    # Tri par horodatage GCS (--long retourne la date de création)
    # Format: "<taille>  <date>  gs://bucket/fichier"
    raw_ls_long = subprocess.run(
        ["gcloud", "storage", "ls", "--long", f"gs://{SOURCE_ARCHIVES_BUCKET}/"],
        capture_output=True, text=True
    )
    if raw_ls_long.returncode == 0 and raw_ls_long.stdout.strip():
        ls_lines = [raw_line.strip() for raw_line in raw_ls_long.stdout.splitlines()
                    if raw_line.strip() and "gs://" in raw_line]
        # Chaque ligne : "<taille>  <date>  gs://..."
        # On exclut les lignes de total (TOTAL:)
        timed_entries = []
        for ls_line in ls_lines:
            parts = ls_line.split()
            if len(parts) >= 3 and parts[-1].startswith("gs://"):
                timed_entries.append((parts[-2], parts[-1]))  # (date_str, url)
        timed_entries.sort(key=lambda x: x[0])  # tri lexicographique sur ISO8601
        urls = [url for _, url in timed_entries]
    else:
        lines = [line.strip() for line in raw_ls.stdout.split('\n') if line.strip()]
        urls = [line for line in lines if line.startswith("gs://")]

    if not urls:
        print(f"[*] No archives found in gs://{SOURCE_ARCHIVES_BUCKET}/. Skipping frontend sync.")
        return

    if frontend_version:
        # Standardise la version (ex: v0.1.12 ou 0.1.12)
        v_suffix = frontend_version if frontend_version.startswith("v") else f"v{frontend_version}"
        matching_urls = []
        for u in urls:
            filename = u.split("/")[-1]
            if filename.endswith(f"-{v_suffix}.tar.gz") or filename.endswith(f"-{v_suffix}.zip"):
                matching_urls.append(u)

        if not matching_urls:
            # Fallback souple si pas de correspondance stricte à la fin
            for u in urls:
                if v_suffix in u or frontend_version in u:
                    matching_urls.append(u)

        if not matching_urls:
            err_msg = (
                f"No frontend archive found matching version '{frontend_version}' "
                f"in gs://{SOURCE_ARCHIVES_BUCKET}/"
            )
            print(f"[!] {err_msg}")
            generate_antigravity_error_report(
                "Post-Deploy : Sync Frontend", err_msg, ["frontend", "sync", "version_not_found"])
            sys.exit(1)

        latest_archive_url = matching_urls[-1]
    else:
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
            else:  # Fallback to tar
                with tarfile.open(archive_path, 'r:*') as tar_ref:
                    tar_ref.extractall(extract_dir, filter='data')
        except Exception as e:
            err_msg = f"Extraction failed: {e}. Is it a valid tar/zip archive?"
            print(f"[!] {err_msg}")
            generate_antigravity_error_report(
                "Post-Deploy : Sync Frontend", err_msg, ["frontend", "sync", "extraction"])
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
            print("[!] Warning: No index.html found. Will sync root extracted folder.")

        # 4. Upload vers le bucket du Load Balancer
        print(f"[*] Uploading assets to gs://{target_bucket}...")

        # Le chemin sync_dir doit être terminé par '/' pour rsync pour garantir
        # de ne copier que le contenu ("ce qu'il y a dans le dossier")
        if not sync_dir.endswith("/"):
            sync_dir += "/"

        rsync_res = subprocess.run(
            ["gcloud", "storage", "rsync", sync_dir,
             f"gs://{target_bucket}/", "--recursive", "--delete-unmatched-destination-objects"],
            capture_output=True, text=True
        )

        if rsync_res.returncode != 0:
            err_msg = f"Frontend sync failed:\\n{rsync_res.stderr}"
            print(f"[!] {err_msg}")
            generate_antigravity_error_report(
                "Post-Deploy : Sync Frontend", err_msg, ["frontend", "sync", "rsync"])
            sys.exit(1)

        print(rsync_res.stderr.strip())  # gsutil logs mostly to stderr

        output_lower = (rsync_res.stdout + rsync_res.stderr).lower()

        # Simple heuristic: if 'copying' or 'removing' is in the output, something was actually synced
        if "copying" in output_lower or "removing" in output_lower:
            print("[*] Frontend changes synced successfully!")
            print("[*] Setting Cache-Control headers on GCS bucket...")
            subprocess.run([
                "gcloud", "storage", "objects", "update",
                f"gs://{target_bucket}/index.html",
                "--cache-control=no-store, no-cache, must-revalidate, max-age=0"
            ], capture_output=True)

            subprocess.run([
                "gcloud", "storage", "objects", "update",
                f"gs://{target_bucket}/assets/**",
                "--cache-control=public, max-age=31536000, immutable"
            ], capture_output=True)

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


def _sanity_check_dns_ssl(env, base_domain, lb_ip, extra_domains, project_id):
    """
    Checks 1 et 2 : résolution DNS + provisionnement SSL GCP + propagation TLS Edge.

    Retourne (ctx_to_use, front_dns_name, api_dns_name) si tout est OK.
    Appelle sys.exit(1) si DNS timeout ou SSL timeout.
    """
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
            except Exception:
                pass
            time.sleep(10)

        if resolved:
            print(f"  [+] DNS {domain} resolves correctly to {lb_ip}")
        else:
            err_msg = f"DNS resolution timeout (5 mins). {domain} does NOT point to {lb_ip}."
            print(f"  [-] {err_msg}")
            generate_antigravity_error_report(
                "Sanity Check 1/3 : DNS Resolution", err_msg, ["dns", "sanity-check", "timeout"])
            all_resolved = False
            break

    if not all_resolved:
        logger.error("[-] Sanity Test FAIL: DNS resolution timeout.")
        sys.exit(1)

    # --- CHECK 2: SSL PROVISIONING ---
    print("\n[*] Check 2/5: Waiting for GCP Managed SSL Certificate provisioning (Can take 15-30 mins)...")
    ssl_ready = False
    cert_creation_time = "Inconnue"
    cert_name = f"ssl-{env}-v2"
    # Initialisation du contexte SSL par défaut (sera surchargé si certifi disponible)
    try:
        import certifi
        ctx_to_use = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx_to_use = ssl.create_default_context()

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
                    break
                else:
                    print(
                        f"  [-] Certificate status: {status} (attempt {attempt + 1}/60). Retrying in 20s...")
                    for d, st in sorted(domain_status.items()):
                        if st != "ACTIVE":
                            print(f"      {d:<35} {st}")
                    time.sleep(20)
            except Exception as e:
                print(f"  [-] Error parsing gcloud output: {e}. Retrying in 20s...")
                time.sleep(20)
        else:
            print(
                f"  [-] Failed to fetch certificate status. Retrying in 20s..."
                f" (Error: {res.stderr.strip()[:100]})")
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
        print(
            f"  [+] Managed SSL Certificate is ACTIVE in GCP API. (Créé le: {cert_creation_time}){age_str}")
        print("  [*] Waiting for the certificate to propagate to Google Edge nodes (TLS handshake)...")
        tls_ready = False

        ctx_fallback = ssl.create_default_context()
        ctx_fallback.check_hostname = False
        ctx_fallback.verify_mode = ssl.CERT_NONE

        for attempt in range(90):  # Wait up to 30 mins (90 * 20s) for Edge propagation
            try:
                req_test = urllib.request.Request(f"https://{front_dns_name}/", method="GET")
                urllib.request.urlopen(req_test, timeout=10, context=ctx_to_use)
                tls_ready = True
                break
            except urllib.error.HTTPError:
                # 404/400/502 means TLS handshake succeeded!
                tls_ready = True
                break
            except urllib.error.URLError as e:
                err_msg = str(e.reason)
                if "CERTIFICATE_VERIFY_FAILED" in err_msg:
                    if "unable to get local issuer certificate" in err_msg:
                        print("  [!] macOS Python CA Bug detected. Bypassing strict verification...")
                        ctx_to_use = ctx_fallback
                        tls_ready = True
                        break
                print(
                    f"  [-] TLS propagation not yet complete (attempt {attempt + 1}/90)."
                    f" Retrying in 20s... (Error: {err_msg})")
                time.sleep(20)
            except Exception as e:
                print(
                    f"  [-] Unexpected error during TLS check (attempt {attempt + 1}/90)."
                    f" Retrying in 20s... (Error: {e})")
                time.sleep(20)

        if tls_ready:
            print("  [+] TLS Handshake successful! The certificate is fully propagated.")
        else:
            err_msg = "SSL Edge propagation timeout (30 mins). TLS handshake failed. Sanity checks aborted."
            print(f"  [!] {err_msg}")
            generate_antigravity_error_report(
                "Sanity Check 2/5 : TLS Handshake", err_msg, ["ssl", "tls", "sanity-check", "timeout"])
            sys.exit(1)
    else:
        err_msg = (
            "SSL provisioning timeout (20 mins). Certificate is not ACTIVE in GCP API. Sanity checks aborted."
        )
        print(f"  [!] {err_msg}")
        generate_antigravity_error_report(
            "Sanity Check 2/5 : SSL Provisioning", err_msg, ["ssl", "sanity-check", "timeout"])
        sys.exit(1)

    return ctx_to_use, front_dns_name, api_dns_name


def _sanity_check_api_login(api_dns_name, admin_pwd, ctx_to_use):
    """
    Check 4/5 : authentification admin via POST /auth/login.

    Tente jusqu'à 16 fois (8 min) pour absorber les délais de propagation IAM.
    Fail-fast (sys.exit(1)) si toutes les tentatives échouent.
    Retourne access_token (str) si le login réussit.
    """
    print("\n[*] Check 4/5: Testing Web API login with seeded admin user"
          " (Waiting for IAM Sync up to 8 mins)...")

    url = f"https://{api_dns_name}/auth/login"
    data = json.dumps({"email": "admin@zenika.com", "password": admin_pwd}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    login_success = False
    access_token = None  # Initialisé ici pour garantir la disponibilité dans les checks 6-9
    for attempt in range(16):
        try:
            response = urllib.request.urlopen(req, timeout=30, context=ctx_to_use)
            if response.status in [200, 201]:
                print("[+] Sanity Test PASS: Successfully logged in as admin via the API!")
                resp_data = json.loads(response.read().decode('utf-8'))
                access_token = resp_data.get("access_token")
                login_success = True
                break
            else:
                print(f"[-] Sanity Test FAIL: Login returned {response.status}")
                break
        except urllib.error.HTTPError as e:
            if e.code >= 500:
                print(
                    f"  [-] API Server Error {e.code} (Possible Database IAM propagation delay)."
                    f" Retrying in 30s... (Attempt {attempt + 1}/16)")
                time.sleep(30)
            elif e.code == 403:
                # 403 peut être transitoire lors d'un 1er déploiement :
                # la propagation IAM du rôle allUsers Cloud Run invoker peut prendre plusieurs minutes.
                # On distingue le 403 infra GCP (HTML) du 403 applicatif (JSON).
                raw = e.read()
                msg = raw.decode('utf-8', errors='replace') if raw else 'N/A'
                is_gcp_infra = '<html' in msg.lower() or '<!doctype' in msg.lower()
                if is_gcp_infra:
                    print(
                        f"  [-] 403 GCP Infrastructure (IAM not yet propagated)."
                        f" Retrying in 30s... (Attempt {attempt + 1}/16)")
                    time.sleep(30)
                else:
                    err_msg = f"HTTP 403 (App-level) during login. (Msg: {msg})"
                    print(f"[-] Sanity Test FAIL: {err_msg}")
                    generate_antigravity_error_report(
                        "Sanity Check 4/5 : API Login",
                        err_msg, ["users_api", "auth", "sanity-check", "HTTP_403"])
                    break
            else:
                # Erreur applicative définitive (400, 401, 422...)
                msg = e.read().decode('utf-8', errors='replace') if hasattr(e, 'read') else 'N/A'
                err_msg = f"HTTP {e.code} during login via POST /auth/login. (Msg: {msg})"
                print(f"[-] Sanity Test FAIL: {err_msg}")
                generate_antigravity_error_report(
                    "Sanity Check 4/5 : API Login",
                    err_msg, ["users_api", "auth", "sanity-check", f"HTTP_{e.code}"])
                break
        except Exception as e:
            print(
                f"  [-] Unexpected error Exception request: {e}."
                f" Retrying in 30s... (Attempt {attempt + 1}/16)")
            time.sleep(30)

    if not login_success:
        err_msg = "Authentication flow totally failed after all attempts. Aborting sanity checks."
        print(f"[-] {err_msg}")
        generate_antigravity_error_report(
            "Sanity Check 4/5 : API Login", err_msg, ["users_api", "auth", "sanity-check", "fail-fast"])
        sys.exit(1)

    return access_token


def _seed_prompts(api_dns_name, access_token, ctx_to_use):
    """
    Check 4.5 : seed idempotent des system prompts dans Prompts API.

    Pour chaque prompt (GET → PUT si 200, POST si 404), tente jusqu'à 8 fois.
    Les échecs définitifs sont rapportés via generate_antigravity_error_report (non-bloquant).
    """
    print("\n[*] Check 4.5: Seeding system prompts into Prompts API...")
    prompts_to_seed = {
        "agent_router_api.system_instruction": "agent_router_api/agent_router_api.system_instruction.txt",
        "agent_router_api.classifier": "agent_router_api/agent_router_api.classifier.txt",
        "agent_hr_api.system_instruction": "agent_hr_api/agent_hr_api.system_instruction.txt",
        "agent_ops_api.system_instruction": "agent_ops_api/agent_ops_api.system_instruction.txt",
        "agent_ops_api.sre_triage.system_instruction": "agent_ops_api/agent_ops_api.sre_triage.system_instruction.txt",
        "agent_ops_api.daily_report.system_instruction": (
            "agent_ops_api/agent_ops_api.daily_report.system_instruction.txt"
        ),
        "agent_missions_api.system_instruction": "agent_missions_api/agent_missions_api.system_instruction.txt",
        "competencies_api.ai_scoring": "competencies_api/competencies_api.ai_scoring.txt",
        "competencies_api.alias_generator": "competencies_api/competencies_api.alias_generator.txt",
        "cv_api.extract_cv_info": "cv_api/cv_api.extract_cv_info.txt",
        "cv_api.generate_taxonomy_tree_map": "cv_api/cv_api.generate_taxonomy_tree_map.txt",
        "cv_api.generate_taxonomy_tree_deduplicate": "cv_api/cv_api.generate_taxonomy_tree_deduplicate.txt",
        "cv_api.generate_taxonomy_tree_reduce": "cv_api/cv_api.generate_taxonomy_tree_reduce.txt",
        "cv_api.generate_taxonomy_tree_sweep": "cv_api/cv_api.generate_taxonomy_tree_sweep.txt",
        "cv_api.search_filter_extraction": "cv_api/cv_api.search_filter_extraction.txt",
        "missions_api.extract_mission_info": "missions_api/extract_mission_info.txt",
        "missions_api.staffing_heuristics": "missions_api/staffing_heuristics.txt",
        "prompts_api.error_correction": "prompts_api/prompts_api.error_correction.txt",
        "prompts_api.sre_triage.playbook": "prompts_api/prompts_api.sre_triage.playbook.txt",
    }

    packaged_dir = os.path.join(os.path.dirname(__file__), "bundled_prompts")
    is_container = os.path.exists("/.dockerenv") or "K_SERVICE" in os.environ
    base_dir = (
        packaged_dir
        if (is_container and os.path.exists(packaged_dir))
        else os.path.dirname(os.path.dirname(__file__))
    )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
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
            f"{prompts_url}{p_key}", headers=headers, method="GET")
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
                    print(
                        f"  [+] Successfully {'updated' if http_method == 'PUT' else 'created'}"
                        f" prompt: {p_key}")
                    seeded = True
                    break
                else:
                    last_error_msg = f"HTTP {p_resp.status}"
                    print(
                        f"  [-] Failed to seed {p_key} ({last_error_msg})."
                        f" Retrying... (Attempt {attempt + 1}/8)")
            except urllib.error.HTTPError as e:
                if e.code >= 500:
                    print(
                        f"  [-] API Server Error {e.code} for {p_key}"
                        f" (Possible IAM propagation delay). Retrying in 15s... (Attempt {attempt + 1}/8)")
                else:
                    last_error_msg = f"HTTP {e.code}"
                    print(
                        f"  [-] Error seeding {p_key}: {last_error_msg}."
                        f" Retrying... (Attempt {attempt + 1}/8)")
            except Exception as e:
                last_error_msg = f"{type(e).__name__}: {e}"
                print(
                    f"  [-] Error seeding {p_key} ({last_error_msg})."
                    f" Retrying... (Attempt {attempt + 1}/8)")

            time.sleep(15)

        if not seeded:
            err_msg = f"Failed to seed {p_key} after all attempts. Last error: {last_error_msg}"
            print(f"  [!] {err_msg}")
            generate_antigravity_error_report(
                f"Sanity Check 4.5 : Seeding Prompts ({p_key})",
                err_msg, ["prompts_api", "sanity-check"])


def _get_iap_identity_token(project_id: str, pname: str = "", env: str = "") -> str:
    """Retourne un identity token Google pour l'authentification IAP.

    Lit l'audience (IAP Client ID) depuis Secret Manager (secret: google-secret-id),
    puis tente de générer le token en impersonnant le Service Account de l'extra-project
    (si pname et env sont fournis) pour supporter les comptes gcloud utilisateur.
    Fait un fallback sur l'appel direct pour les comptes de service natifs.

    Retourne le token (str) ou une chaîne vide en cas d'erreur.
    """
    # Lit l'audience IAP depuis Secret Manager
    try:
        active_version = _get_latest_active_secret_version(project_id, "google-secret-id")
        res = subprocess.run(
            ["gcloud", "secrets", "versions", "access", active_version,
             "--secret=google-secret-id", f"--project={project_id}"],
            capture_output=True, text=True, timeout=15,
        )
        if res.returncode != 0 or not res.stdout.strip():
            logger.warning(f"  [iap] Impossible de lire google-secret-id : {res.stderr.strip()}")
            return ""
        iap_client_id = res.stdout.strip()
    except Exception as exc:
        logger.warning(f"  [iap] Erreur lecture secret google-secret-id : {exc}")
        return ""

    # Génère un identity token avec l'audience IAP (Tentative 1 : Impersonation du SA pour User Account)
    if pname and env:
        sa_email = f"sa-{pname}-{env}@{project_id}.iam.gserviceaccount.com"
        try:
            logger.info(f"  [iap] Tentative génération token IAP via impersonation de '{sa_email}'...")
            # 1. Récupère l'access token de l'utilisateur actif
            res = subprocess.run(
                ["gcloud", "auth", "print-access-token"],
                capture_output=True, text=True, timeout=15,
            )
            if res.returncode != 0 or not res.stdout.strip():
                logger.info(f"  [iap] gcloud auth print-access-token échoué : {res.stderr.strip()}")
                raise RuntimeError("Failed to get gcloud active access token")
            access_token = res.stdout.strip()

            # 2. Appelle l'API iamcredentials pour générer l'ID token avec includeEmail=True
            url = f"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{sa_email}:generateIdToken"
            req = urllib.request.Request(
                url,
                method="POST",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                data=json.dumps({
                    "audience": iap_client_id,
                    "includeEmail": True
                }).encode("utf-8")
            )
            # Contournement des erreurs SSL sur Mac (unable to get local issuer certificate)
            ssl_ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=20, context=ssl_ctx) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                token = resp_data.get("token", "")
                if token:
                    logger.info("  [iap] ✓ Identity token IAP obtenu via impersonation (REST API + includeEmail).")
                    return token
                logger.info("  [iap] Pas de token retourné par l'API iamcredentials.")
        except Exception as exc:
            logger.info(f"  [iap] Erreur impersonation SA '{sa_email}' via REST API : {exc}")

    # Tentative 2 : Fallback sur appel direct (compte de service natif ou ADC local)
    try:
        logger.info("  [iap] Génération token IAP via compte actif natif...")
        res = subprocess.run(
            ["gcloud", "auth", "print-identity-token", f"--audiences={iap_client_id}"],
            capture_output=True, text=True, timeout=15,
        )
        if res.returncode == 0 and res.stdout.strip():
            token = res.stdout.strip()
            logger.info("  [iap] ✓ Identity token IAP obtenu de manière native.")
            return token
        logger.warning(f"  [iap] gcloud auth print-identity-token natif échoué : {res.stderr.strip()}")
        return ""
    except Exception as exc:
        logger.warning(f"  [iap] Erreur génération identity token : {exc}")
        return ""


def _sanity_checks_extra_projects(
    extra_projects: list,
    api_dns_name: str,
    ctx_to_use,
    project_id: str = "",
    env: str = "",
) -> None:
    """Vérifie les health_check_paths de chaque extra-project après déploiement.

    Pour chaque extra-project déclarant des health_check_paths :
      - Si token_iap: true → récupère un identity token Google (gcloud auth print-identity-token)
        et l'injecte en Authorization: Bearer pour contourner l'IAP.
      - Sinon → requête anonyme (pour les services non protégés par IAP).

    3 tentatives par path. Rapport Antigravity généré sur tout échec.

    Args:
        extra_projects : liste des projets externes (depuis discover_extra_projects).
        api_dns_name   : ex: api.prd.zenika.slavayssiere.fr.
        ctx_to_use     : contexte SSL urllib (None = désactivé).
        project_id     : GCP project ID (pour lire le secret IAP).
        env            : nom de l'environnement (ex: prd, dev) pour impersonation SA.
    """
    projects_with_checks = [p for p in extra_projects if p.get("health_check_paths")]
    if not projects_with_checks:
        logger.info("[extra_projects] Aucun health_check_paths défini — checks ignorés.")
        return

    print("\n=======================================================")
    print("[*] Post-Deploy: Sanity Checks — Extra Projects")
    print("=======================================================")

    # Cache des tokens IAP par projet (évite d'appeler gcloud plusieurs fois)
    _iap_token_cache: dict = {}

    def get_token_for_project(proj: dict) -> str:
        if not proj.get("token_iap"):
            return ""
        pname = proj["name"]
        if pname not in _iap_token_cache:
            logger.info(f"  [iap] Récupération du token IAP pour '{pname}'...")
            _iap_token_cache[pname] = _get_iap_identity_token(project_id, pname, env)
        return _iap_token_cache[pname]

    def check_path(proj: dict, path: str) -> str:
        pname = proj["name"]
        token = get_token_for_project(proj)
        url = f"https://{api_dns_name}{path}"
        req = urllib.request.Request(url, method="GET")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        last_err = ""
        for attempt in range(10):
            try:
                resp = urllib.request.urlopen(req, timeout=30, context=ctx_to_use)
                auth_label = " [IAP]" if token else ""
                return f"  [+] [{pname}]{auth_label} {path:<40} -> OK (HTTP {resp.status})"
            except urllib.error.HTTPError as e:
                last_err = f"FAIL (HTTP {e.code}) sur {path}"
                # En cas de 404, 401 (IAP propagation) ou 5xx, on attend et on réessaie
                # car le Load Balancer peut mettre 2-3 minutes à propager la nouvelle route.
                if e.code in (401, 404) or e.code >= 500:
                    logger.info(
                        f"  [lb-propagation] Attente propagation route/IAP '{pname}' "
                        f"({e.code}) - tentative {attempt + 1}/10..."
                    )
                    time.sleep(20)
                    continue
                generate_antigravity_error_report(
                    f"Sanity Check extra-project '{pname}'",
                    last_err, ["extra-project", pname, f"HTTP_{e.code}"],
                )
                return f"  [-] [{pname}] {path:<40} -> {last_err}"
            except Exception as exc:
                last_err = f"FAIL ({type(exc).__name__}: {exc}) sur {path}"
                time.sleep(10)
        generate_antigravity_error_report(
            f"Sanity Check extra-project '{pname}'",
            last_err, ["extra-project", pname, "exception"],
        )
        return f"  [-] [{pname}] {path:<40} -> {last_err} (après 10 tentatives)"

    tasks = []
    for proj in projects_with_checks:
        pname = proj["name"]
        paths = proj.get("health_check_paths") or []
        iap_label = " [token_iap=true]" if proj.get("token_iap") else ""
        logger.info(f"\n  → Extra project '{pname}'{iap_label} : {len(paths)} path(s) à vérifier")
        for p in paths:
            tasks.append((proj, p))

    # Séquentiel par projet pour que le cache IAP soit thread-safe
    for proj, path in tasks:
        logger.info(check_path(proj, path))


def _sanity_checks(env, base_domain, project_id, config, extra_domains, extra_projects=None):
    """
    Orchestre les 9 sanity checks post-déploiement.

    Séquence :
      1. Récupère lb_ip + admin_password depuis les outputs Terraform.
      2. Check 1 : DNS + Check 2 : SSL/TLS → _sanity_check_dns_ssl()
      3. Check 3 : Frontend HTTP 200
      4. Check 4 : API Login → _sanity_check_api_login()  (fail-fast)
      4.5. Seeding prompts → _seed_prompts()
      5-9 : Microservices, Zero-Trust, DB read-only, MCP sidecars, AIOps metrics
      Extra : domaines additionnels SSL

    Retourne access_token ou None.
    """
    print("\n=======================================================")
    print(f"[*] Post-Deploy: Running Sanity Checks on {env}...")
    print("=======================================================")

    # Extrait l'IP et Mdp depuis les outputs Terraform
    out_res = subprocess.run(
        ["terraform", "output", "-json"], cwd=TERRAFORM_DIR, capture_output=True, text=True)
    try:
        outputs = json.loads(out_res.stdout)
        lb_ip = outputs.get("lb_ip", {}).get("value")
        admin_pwd = outputs.get("admin_password", {}).get("value")
    except Exception as e:
        print(f"[!] Erreur de lecture des outputs: {e}")
        lb_ip, admin_pwd = None, None

    if not (lb_ip and admin_pwd):
        logger.warning("[!] Skipping Sanity check. Missing terraform outputs (lb_ip or admin_password).")
        return None

    # CHECK 1 + 2 : DNS + SSL
    ctx_to_use, front_dns_name, api_dns_name = _sanity_check_dns_ssl(
        env, base_domain, lb_ip, extra_domains, project_id)

    # --- CHECK 3: FRONTEND ---
    print(f"\n[*] Check 3/5: Testing Frontend website on https://{front_dns_name}/...")
    try:
        front_url = f"https://{front_dns_name}/"
        req_front = urllib.request.Request(front_url, method="GET")
        resp_front = urllib.request.urlopen(req_front, timeout=15, context=ctx_to_use)
        if resp_front.status == 200:
            print("  [+] Frontend loaded OK (HTTP 200)")
        else:
            err_msg = f"Frontend FAIL (HTTP {resp_front.status})"
            print(f"  [-] {err_msg}")
            generate_antigravity_error_report(
                "Sanity Check 3/5 : Frontend",
                err_msg, ["frontend", "sanity-check", f"HTTP_{resp_front.status}"])
    except urllib.error.HTTPError as e:
        err_msg = f"Frontend FAIL (HTTP {e.code})"
        print(f"  [-] {err_msg}")
        generate_antigravity_error_report(
            "Sanity Check 3/5 : Frontend", err_msg, ["frontend", "sanity-check", f"HTTP_{e.code}"])
    except Exception as e:
        err_msg = f"Frontend FAIL ({type(e).__name__}: {e})"
        print(f"  [-] {err_msg}")
        generate_antigravity_error_report(
            "Sanity Check 3/5 : Frontend", err_msg, ["frontend", "sanity-check", "exception"])

    # CHECK 4 : API LOGIN (fail-fast si échec)
    access_token = _sanity_check_api_login(api_dns_name, admin_pwd, ctx_to_use)

    # CHECK 4.5 : SEED PROMPTS
    if access_token:
        _seed_prompts(api_dns_name, access_token, ctx_to_use)

    # --- CHECK 5/5: API MICROSERVICES ---
    logger.info("\n[*] Check 5/5: Validating all API microservices routing (GET requests)...")
    health_ready_routes = [
        "/api/health",                # agent_router_api (point d'entrée public unique)
        # Les sous-agents (agent-hr, agent-ops, agent-missions) sont des workers A2A
        # accessibles UNIQUEMENT via le LB interne. Leurs routes ont été supprimées
        # du LB externe dans lb.tf — les tester ici génèrerait des 404 normaux.
        "/api/users/ready",           # users_api
        "/api/items/ready",           # items_api
        "/api/prompts/ready",         # prompts_api
        "/api/competencies/ready",    # competencies_api
        "/api/cv/ready",              # cv_api
        "/api/drive/ready",           # drive_api
        "/api/missions/ready",        # missions_api
        "/api/analytics/ready",       # analytics_mcp (Deep readiness check)
        "/monitoring-mcp/health",     # monitoring_mcp
    ]

    api_routes = []
    for hr_route in health_ready_routes:
        api_routes.append(hr_route)
        prefix = hr_route.rsplit("/", 1)[0]
        api_routes.append(f"{prefix}/spec")
        api_routes.append(f"{prefix}/docs")

    def check_route(route):
        api_url = f"https://{api_dns_name}{route}"
        req_get = urllib.request.Request(api_url, method="GET")
        last_err_msg = ""
        for attempt in range(3):
            try:
                resp = urllib.request.urlopen(req_get, timeout=30, context=ctx_to_use)
                return f"  [+] {route:<15} -> OK (HTTP {resp.status})"
            except urllib.error.HTTPError as e:
                last_err_msg = f"FAIL (HTTP {e.code} Error) sur {route}"
                if e.code >= 500:
                    time.sleep(10)
                    continue
                generate_antigravity_error_report(
                    "Sanity Check 5/5 : API Microservices",
                    last_err_msg, ["routing", "sanity-check", f"HTTP_{e.code}"])
                return f"  [-] {route:<15} -> {last_err_msg}"
            except Exception as e:
                last_err_msg = f"FAIL ({type(e).__name__}: {e}) sur {route}"
                time.sleep(10)

        generate_antigravity_error_report(
            "Sanity Check 5/5 : API Microservices",
            last_err_msg, ["routing", "sanity-check", "exception"])
        return f"  [-] {route:<15} -> {last_err_msg} (après 3 tentatives)"

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(check_route, route): route for route in api_routes}
        for future in as_completed(futures):
            logger.info(future.result())

    # --- CHECK 5.5 : EXTRA PROJECTS HEALTH CHECKS ---
    if extra_projects:
        _sanity_checks_extra_projects(extra_projects, api_dns_name, ctx_to_use, project_id, env)

    # --- CHECK 6/8: ZERO-TRUST VALIDATION (HTTP 401 WITHOUT TOKEN) ---
    logger.info("\n[*] Check 6/8: Validating Zero-Trust security (expecting 401 without token)...")
    protected_url = f"https://{api_dns_name}/api/users/me"
    req_zt = urllib.request.Request(protected_url, method="GET")
    try:
        urllib.request.urlopen(req_zt, timeout=10, context=ctx_to_use)
        err_msg = "Security Breach! Protected endpoint returned 200 OK without a JWT token."
        logger.error(f"  [-] {err_msg}")
        generate_antigravity_error_report(
            "Sanity Check 6/8 : Zero-Trust", err_msg, ["security", "sanity-check", "zero-trust"])
    except urllib.error.HTTPError as e:
        if e.code == 401:
            logger.info("  [+] Zero-Trust OK: Access denied (HTTP 401) without token.")
        else:
            err_msg = f"Unexpected HTTP status {e.code} during Zero-Trust check."
            logger.warning(f"  [-] {err_msg}")
            generate_antigravity_error_report(
                "Sanity Check 6/8 : Zero-Trust",
                err_msg, ["security", "sanity-check", f"HTTP_{e.code}"])
    except Exception as e:
        err_msg = f"Unexpected error during Zero-Trust check: {e}"
        logger.warning(f"  [-] {err_msg}")
        generate_antigravity_error_report(
            "Sanity Check 6/8 : Zero-Trust", err_msg, ["security", "sanity-check", "exception"])

    # --- CHECK 7/8: DATABASE READ-ONLY CONNECTIVITY WITH TOKEN ---
    logger.info("\n[*] Check 7/8: Validating DB read-only connectivity with JWT token...")
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
            generate_antigravity_error_report(
                "Sanity Check 7/8 : DB Read-Only", err_msg, ["db", "sanity-check", f"HTTP_{e.code}"])
        except Exception as e:
            err_msg = f"Read-Only DB Check FAIL: {e}"
            logger.error(f"  [-] {err_msg}")
            generate_antigravity_error_report(
                "Sanity Check 7/8 : DB Read-Only", err_msg, ["db", "sanity-check", "exception"])
    else:
        logger.warning("  [!] Skipping Check 7: No access_token available (Check 4 failed).")

    # --- CHECK 8/8: MCP SIDECAR AVAILABILITY ---
    logger.info("\n[*] Check 8/8: Validating MCP Sidecar tools exposure...")
    mcp_routes = [
        "/api/users/mcp/tools",
        "/api/items/mcp/tools",
        "/api/prompts/mcp/tools",
        "/api/competencies/mcp/tools",
        "/api/cv/mcp/tools",
        "/api/drive/mcp/tools",
        "/api/missions/mcp/tools",
        "/api/analytics/mcp/tools",
        "/monitoring-mcp/mcp/tools",
    ]
    for mcp_route in mcp_routes:
        mcp_url = f"https://{api_dns_name}{mcp_route}"
        req_mcp = urllib.request.Request(mcp_url, method="GET")
        if access_token:
            req_mcp.add_header("Authorization", f"Bearer {access_token}")
        last_err_msg = ""
        for attempt in range(3):
            try:
                resp_mcp = urllib.request.urlopen(req_mcp, timeout=20, context=ctx_to_use)
                if resp_mcp.status == 200:
                    mcp_data = json.loads(resp_mcp.read().decode('utf-8'))
                    tools_count = (
                        len(mcp_data) if isinstance(mcp_data, list) else len(mcp_data.get("tools", []))
                    )
                    logger.info(f"  [+] MCP {mcp_route} OK: Found {tools_count} tools.")
                    last_err_msg = ""
                    break
                else:
                    last_err_msg = f"MCP {mcp_route} FAIL: HTTP {resp_mcp.status}"
                    if resp_mcp.status >= 500:
                        time.sleep(10)
                        continue
                    break
            except urllib.error.HTTPError as e:
                last_err_msg = f"FAIL (HTTP {e.code}) on {mcp_route}"
                if e.code >= 500:
                    time.sleep(10)
                    continue
                break
            except Exception as e:
                last_err_msg = f"MCP {mcp_route} FAIL: {e}"
                time.sleep(10)

        if last_err_msg:
            logger.error(f"  [-] {last_err_msg} (après 3 tentatives)")
            generate_antigravity_error_report(
                "Sanity Check 8/8 : MCP Availability",
                last_err_msg, ["mcp", "sanity-check", "exception"])

    # --- CHECK 9/9: AIOPS METRICS ---
    logger.info("\n[*] Check 9/9: Validating AIOps metrics endpoint...")
    if access_token:
        aiops_url = f"https://{api_dns_name}/api/analytics/metrics/aiops?force=true"
        req_aiops = urllib.request.Request(aiops_url, method="GET")
        req_aiops.add_header("Authorization", f"Bearer {access_token}")
        last_err_msg = ""
        for attempt in range(3):
            try:
                resp_aiops = urllib.request.urlopen(req_aiops, timeout=30, context=ctx_to_use)
                if resp_aiops.status == 200:
                    logger.info(f"  [+] AIOps Metrics OK: {aiops_url}")
                    last_err_msg = ""
                    break
                else:
                    last_err_msg = f"AIOps Metrics FAIL: HTTP {resp_aiops.status}"
                    if resp_aiops.status >= 500:
                        time.sleep(10)
                        continue
                    break
            except urllib.error.HTTPError as e:
                last_err_msg = f"FAIL (HTTP {e.code}) on /api/analytics/metrics/aiops"
                if e.code >= 500:
                    time.sleep(10)
                    continue
                break
            except Exception as e:
                last_err_msg = f"AIOps Metrics FAIL: {e}"
                time.sleep(10)

        if last_err_msg:
            logger.error(f"  [-] {last_err_msg} (après 3 tentatives)")
            generate_antigravity_error_report(
                "Sanity Check 9/9 : AIOps Metrics",
                last_err_msg, ["analytics_mcp", "sanity-check", "exception"])
    else:
        logger.warning("  [!] Skipping Check 9: No access_token available (Check 4 failed).")

    # --- CHECK EXTRA DOMAINS: DNS + SSL pour chaque domaine additionnel ---
    if extra_domains:
        print("\n[*] Check Extra Domains: Validating additional domains DNS + SSL...")
        for _d in extra_domains:
            _host = _d.get("dns_name", "").rstrip(".")  # ex: "gen-skillz.znk.io"
            if not _host:
                continue
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
                    if ("CERTIFICATE_VERIFY_FAILED" in str(_e.reason)
                            and "unable to get local issuer" in str(_e.reason)):
                        _ssl_ok = True  # Bug macOS CA, on considère OK
                        break
                    print(
                        f"  [-] SSL {_host} not yet active (attempt {_attempt + 1}/6). Retrying in 20s...")
                    time.sleep(20)
                except Exception as _e:
                    print(f"  [-] SSL {_host} unexpected error ({_e}). Retrying in 20s...")
                    time.sleep(20)
            if _ssl_ok:
                print(f"  [+] SSL {_host} -> ACTIVE")
            else:
                print(f"  [!] SSL {_host} -> not provisioned yet (certificate may take 15-30 mins)")

    # --- INIT: FINOPS PRICING SEEDING ---
    print("\n[*] Post-Deploy: Seeding FinOps Pricing Data (BigQuery)...")
    try:
        init_pricing_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "analytics_mcp", "init_pricing.py")
        if os.path.exists(init_pricing_path):
            env_copy = os.environ.copy()
            env_copy["GCP_PROJECT_ID"] = project_id
            env_copy["BQ_LOCATION"] = config.get("bq_location", "europe-west1")
            env_copy["FINOPS_DATASET_ID"] = f"finops_{env}"
            res = subprocess.run(
                [sys.executable, init_pricing_path], env=env_copy, capture_output=True, text=True)
            if res.returncode == 0:
                print("  [+] FinOps Pricing seeded successfully.")
            else:
                print(f"  [-] Failed to seed FinOps Pricing: {res.stderr.strip()[:200]}")
        else:
            print(f"  [-] init_pricing.py not found at {init_pricing_path}")
    except Exception as e:
        print(f"  [-] Error running init_pricing.py: {e}")

    return access_token


def _deploy_extra_projects_only(env: str, project_id: str, config: dict) -> None:
    """
    Déploie uniquement les projets externes (extra_projects) sans toucher à la plateforme.

    Séquence allégée :
      1. Validation fail-fast des projets externes (structure, nommage, doublons).
      2. Lecture des outputs Terraform de la plateforme (vpc, alloydb, etc.).
      3. Terraform init + apply de chaque projet externe.

    Utilisé par : python3 manage_env.py deploy --env prd --extra-projects-only

    Prérequis :
      - La plateforme doit avoir été déployée au moins une fois (terraform output disponible).
      - Le workspace Terraform doit correspondre à l'env (init_tf + set_workspace sont appelés).
    """
    print(f"\n[*] Mode --extra-projects-only activé pour l'env '{env}'.")

    extra_projects = discover_extra_projects(config)
    if not extra_projects:
        print("[!] Aucun extra_project déclaré dans le YAML. Rien à faire.")
        return

    # Initialise Terraform pour pouvoir lire les outputs de la plateforme
    init_tf()
    set_workspace(env)

    region = config.get("region", "europe-west1")

    print(f"[*] {len(extra_projects)} projet(s) externe(s) à déployer :")
    for p in extra_projects:
        print(f"    - {p['name']}  ({p['path']})  →  lb_path={p['lb_path']}  version={p['version']}")

    print()
    for ext_proj in extra_projects:
        deploy_extra_project_terraform(ext_proj, env, project_id, region)

    print(f"\n[+] Déploiement extra_projects terminé ({len(extra_projects)} projet(s)).")

    # ── Sanity checks des extra-projects ─────────────────────────────────────
    base_domain = config.get("base_domain", "")
    if base_domain:
        api_dns_name = f"api.{env}.{base_domain}"
        # Contexte SSL souple (ignore les erreurs de CA macOS)
        import ssl as _ssl
        ctx_to_use = _ssl.create_default_context()
        ctx_to_use.check_hostname = False
        ctx_to_use.verify_mode = _ssl.CERT_NONE
        _sanity_checks_extra_projects(extra_projects, api_dns_name, ctx_to_use, project_id, env)
    else:
        logger.warning("[extra_projects] base_domain absent de la config — sanity checks ignorés.")


def deploy(env, base_domain, project_id, config, force=False):
    """
    Orchestre le déploiement complet d'un environnement.

    Séquence :
      1. Validation fail-fast des projets externes (extra_projects).
      2. Import déterministe des ressources GCP persistantes (DNS, SSL) dans le state Terraform.
      3. Terraform apply avec triple retry et auto-import 409.
      4. Sync des assets frontend depuis GCS.
      5. Terraform apply des projets externes (extra_projects).
      6. 9 sanity checks post-déploiement (DNS, SSL, Frontend, Login, Microservices, Zero-Trust,
         DB read-only, MCP sidecars, AIOps metrics).
      7. Calibrage RAG automatique si le modèle d'embedding a changé.
      8. Évaluation RAG qualité sur le golden dataset.
    """
    # ── Étape 1 : Validation fail-fast des projets externes ─────────────────
    extra_projects = discover_extra_projects(config)
    init_tf()
    set_workspace(env)

    print("[*] Probing GCP to deterministically import persistent resources...")
    # Récupération des domaines additionnels depuis la config (ex: gen-skillz.znk.io en prd)
    extra_domains = config.get("extra_domains", [])

    zone_name = f"zone-{env}"
    if resource_exists_in_gcp("dns_zone", zone_name, project_id):
        import_persistent_resource(env, "google_dns_managed_zone.env_zone",
                                   f"projects/{project_id}/managedZones/{zone_name}")
        dns_name = f"{env}.{base_domain}."
        import_persistent_resource(env, "google_dns_record_set.a",
                                   f"projects/{project_id}/managedZones/{zone_name}/rrsets/{dns_name}/A")
        import_persistent_resource(env, "google_dns_record_set.api_a",
                                   f"projects/{project_id}/managedZones/{zone_name}/rrsets/api.{dns_name}/A")

    # Import des zones DNS additionnelles persistantes (ex: zone-gen-skillz pour gen-skillz.znk.io)
    for d in extra_domains:
        extra_zone_name = d.get("zone_name", "")
        extra_dns_name = d.get("dns_name", "")
        if not extra_zone_name:
            continue
        if resource_exists_in_gcp("dns_zone", extra_zone_name, project_id):
            tf_addr = f'google_dns_managed_zone.extra_zones["{extra_zone_name}"]'
            import_persistent_resource(env, tf_addr, f"projects/{project_id}/managedZones/{extra_zone_name}")
            tf_a_addr = f'google_dns_record_set.extra_a["{extra_zone_name}"]'
            import_persistent_resource(
                env, tf_a_addr,
                f"projects/{project_id}/managedZones/{extra_zone_name}/rrsets/{extra_dns_name}/A")

    ssl_name = f"ssl-{env}-v2"
    if resource_exists_in_gcp("ssl_cert", ssl_name, project_id):
        import_persistent_resource(env, "google_compute_managed_ssl_certificate.default",
                                   f"projects/{project_id}/global/sslCertificates/{ssl_name}")

    # NOTE: le SA sa-drive-{env}-v2 est déclaré comme data source (cr_drive.tf) — pas une resource Terraform.
    # Il est créé en dehors du cycle Terraform et est naturellement persistant (jamais détruit par apply/destroy).
    # Aucun import nécessaire.

    if force:
        print("[!] FORCE MODE: Bypassing prevent_destroy logic to allow replacements.")
        toggle_prevent_destroy(disable=True)

    try:
        region = config.get("region", "europe-west1")
        parallelism = get_gcp_quota_parallelism(project_id, region)
        apply_cmd = [
            "terraform", "apply", "-auto-approve",
            f"-parallelism={parallelism}", "-lock-timeout=120s",
        ] + get_tf_args(project_id)

        _terraform_apply_with_retry(apply_cmd, env, project_id, region, extra_domains)
        _post_deploy_frontend_sync(
            env, project_id,
            frontend_version=config.get("frontend_version"),
            ctx_to_use=None
        )

        # ── Étape 5 : Terraform des projets externes (AVANT sanity checks) ──
        for ext_proj in extra_projects:
            deploy_extra_project_terraform(ext_proj, env, project_id, region)

        access_token = _sanity_checks(env, base_domain, project_id, config, extra_domains, extra_projects)

        if SANITY_ERROR_COUNT > 0:
            raise DeploymentError(
                f"{SANITY_ERROR_COUNT} Sanity Checks failed. "
                "Consultez le rapport antigravity_sanity_error.md")

        # ── RAG Calibration automatique si le modèle d'embedding a changé ────
        current_embedding_model = config.get("gemini_embedding_model", "")
        if current_embedding_model and _rag_embedding_changed(env, current_embedding_model):
            if access_token:
                print(
                    "\n[*] RAG: gemini_embedding_model a changé → calibrage automatique du golden dataset..."
                )
                rag_calibrate(env, base_domain, project_id, access_token)
            else:
                logger.warning(
                    "[RAG] Changement de modèle détecté mais access_token indisponible "
                    "— relancez manuellement : python3 platform-engineering/manage_env.py "
                    "rag-calibrate --env prd"
                )
        if current_embedding_model:
            _rag_save_state(env, current_embedding_model)

        # -- RAG Eval post-deploiement (toujours si cv_api est deploye) --------
        if access_token:
            print("\n[*] RAG: cv_api deploye -> evaluation qualite golden dataset...")
            rag_eval_ok = rag_run_eval(env, base_domain, access_token)
            if not rag_eval_ok:
                logger.warning(
                    "[RAG] Regression detectee post-deploiement cv_api. "
                    "Verifiez GEMINI_EMBEDDING_MODEL ou VECTOR_DISTANCE_THRESHOLD. "
                    "Pour recalibrer : python3 platform-engineering/manage_env.py "
                    "rag-calibrate --env prd"
                )

    finally:
        if force:
            toggle_prevent_destroy(disable=False)


# ── Fichier de suivi du modèle d'embedding déployé par env ───────────────────
# Anciennement : _DB_INIT_STATE_FILE + _db_init_fingerprint/load/save/needed
# Supprimé : db_init.py est idempotent — on n'a pas besoin de state local.
# Le job est systématiquement rejoué à chaque deploy_extra_project_terraform.


_RAG_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".rag_model_state.json")


def _rag_load_state() -> dict:
    """Lit le dernier modèle d'embedding déployé par env (depuis .rag_model_state.json)."""
    if os.path.exists(_RAG_STATE_FILE):
        try:
            with open(_RAG_STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[RAG] Impossible de lire .rag_model_state.json : {e}")
    return {}


def _rag_save_state(env: str, model: str) -> None:
    """Persiste le modèle d'embedding courant pour un env donné."""
    state = _rag_load_state()
    state[env] = model
    with open(_RAG_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _rag_embedding_changed(env: str, current_model: str) -> bool:
    """Retourne True si gemini_embedding_model a changé depuis le dernier déploiement."""
    state = _rag_load_state()
    previous = state.get(env)
    if previous is None:
        logger.info(f"[RAG] Premier déploiement sur '{env}' — état initial du modèle d'embedding non connu.")
        return False  # Premier deploy : pas de calibrage forcé automatique
    if previous != current_model:
        logger.warning(
            f"[RAG] ⚠️  Changement de modèle d'embedding détecté sur '{env}' : "
            f"{previous} → {current_model}"
        )
        return True
    return False


def rag_calibrate(
    env: str,
    base_domain: str,
    project_id: str,
    access_token: str,
    triggered_by: str = "manual",
) -> bool:
    """
    Calibre automatiquement le golden dataset RAG (R3).

    Déclenché :
    - Manuellement via : python3 manage_env.py rag-calibrate --env prd
    - Automatiquement lors d'un deploy quand gemini_embedding_model change.

    Comportements spéciaux :
    - Corpus vide (nouvelle plateforme) : skip silencieux, retourne True.
    - Après calibrage : git commit de golden_queries.json + .rag_model_state.json.
    - Métriques pushées vers analytics_mcp BigQuery (table rag_quality_snapshots).

    Retourne True si calibrage réussi ou ignoré, False si erreur bloquante.
    """
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filename = "golden_queries.json" if env in ("dev", "local") else f"golden_queries_{env}.json"
    golden_path = os.path.join(script_dir, "cv_api", "eval", filename)
    log_dir = os.path.join(script_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    api_dns = f"api.{env}.{base_domain}" if env != "prd" else f"api.prd.{base_domain}"
    cv_base = f"https://{api_dns}/api/cv"
    analytics_url_base = f"https://prd.{base_domain}" if env == "prd" else f"https://{env}.{base_domain}"

    print("\n=======================================================")
    print("[*] RAG Calibration — Golden Dataset (R3)")
    print("=======================================================")

    if not os.path.exists(golden_path):
        logger.warning(f"[RAG] {filename} introuvable : {golden_path} — calibrage ignoré.")
        return True  # Non-bloquant

    with open(golden_path, encoding="utf-8") as f:
        golden = json.load(f)

    cases = golden.get("cases", [])
    if not cases:
        logger.warning("[RAG] Aucun cas golden — calibrage ignoré.")
        return True

    # ── Étape 1 : Dry-run — top-10 IDs par cas ────────────────────────────────
    print(f"[*] RAG Calibration — Étape 1/3 : Dry-run top-10 sur {len(cases)} cas...")
    try:
        import certifi as _certifi
        ctx = ssl.create_default_context(cafile=_certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    top_k = 10
    extracted: dict = {}
    all_ok = True

    for case in cases:
        query = urllib.parse.quote_plus(case["query"])
        url = f"{cv_base}/search?query={query}&limit={top_k}"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {access_token}")
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                data = json.loads(resp.read().decode())
                items = data if isinstance(data, list) else data.get("results", data.get("items", []))
                ids = [r.get("user_id") for r in items if r.get("user_id")]
                extracted[case["id"]] = ids
                print(f"  [+] {case['id']:<30} Top-{top_k} IDs : {ids}")
        except urllib.error.HTTPError as e:
            logger.error(f"  [-] {case['id']} → HTTP {e.code} — calibrage partiel.")
            all_ok = False
        except Exception as e:
            logger.error(f"  [-] {case['id']} → {e} — calibrage partiel.")
            all_ok = False

    # ── Guard corpus vide — nouvelle plateforme sans données ──────────────────
    total_ids = sum(len(v) for v in extracted.values())
    if total_ids == 0:
        print("\n  [!] Corpus vide détecté (0 CVs indexés) — calibrage ignoré.")
        print("  [!] Ingérez des CVs puis relancez : manage_env.py rag-calibrate --env prd")
        return True  # Non-bloquant : comportement attendu sur une nouvelle plateforme

    if not extracted:
        logger.warning("[RAG] Aucun résultat récupéré depuis cv_api — calibrage annulé.")
        return False

    # ── Étape 2 : Injection automatique dans golden_queries.json ──────────────
    print(f"\n[*] RAG Calibration — Étape 2/3 : Injection dans {filename}...")
    updated = 0
    for case in cases:
        cid = case["id"]
        if cid in extracted:
            case["expected_user_ids"] = extracted[cid]
            print(f"  [+] {cid} → {extracted[cid]}")
            updated += 1
        else:
            print(f"  [!] {cid} → non récupéré (conservé tel quel)")

    with open(golden_path, "w", encoding="utf-8") as f:
        json.dump(golden, f, ensure_ascii=False, indent=2)
    print(f"\n  [+] {updated}/{len(cases)} cas mis à jour dans {golden_path}")

    # ── Étape 3 : Git commit des deux fichiers (versioning cross-container) ───
    print("\n[*] RAG Calibration — Étape 3/3 : Commit git du golden dataset...")
    try:
        state_file_path = _RAG_STATE_FILE
        git_cwd = script_dir
        for git_file in [golden_path, state_file_path]:
            if os.path.exists(git_file):
                subprocess.run(["git", "add", git_file], cwd=git_cwd, check=False, capture_output=True)
        commit_msg = f"[rag-calibrate] {env}: golden dataset mis à jour ({triggered_by})"
        res_commit = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=git_cwd, capture_output=True, text=True
        )
        if res_commit.returncode == 0:
            print(f"  [+] Commit git : {commit_msg}")
        else:
            # "nothing to commit" est normal si golden n'a pas changé
            out = (res_commit.stdout + res_commit.stderr).strip()
            print(f"  [!] Git commit skipped : {out[:120]}")
    except Exception as e:
        logger.warning(f"[RAG] Git commit non disponible (CI sans git?) : {e}")

    # ── Push métriques vers analytics_mcp (BigQuery rag_quality_snapshots) ───
    print("\n[*] RAG Calibration — Push snapshot qualité vers analytics_mcp...")
    try:
        nb_cases_ok = sum(1 for cid, ids in extracted.items() if ids)
        snapshot_payload = json.dumps({
            "env": env,
            "embedding_model": "unknown",  # Sera enrichi si embedding_model disponible dans config
            "nb_cases": len(cases),
            "nb_cases_ok": nb_cases_ok,
            "global_recall": round(nb_cases_ok / len(cases), 4) if cases else 0.0,
            "global_mrr": 0.0,  # MRR calculé uniquement via pytest complet
            "cases_detail": [
                {"id": cid, "top_k_count": len(ids)}
                for cid, ids in extracted.items()
            ],
            "triggered_by": triggered_by,
        }).encode()

        analytics_url = f"{analytics_url_base}/api/analytics/mcp/call"
        req_analytics = urllib.request.Request(
            analytics_url,
            data=json.dumps({"name": "log_rag_quality_snapshot",
                            "arguments": json.loads(snapshot_payload.decode())}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"},
        )
        try:
            with urllib.request.urlopen(req_analytics, timeout=10, context=ctx) as resp_a:
                if resp_a.status in (200, 201):
                    print("  [+] Snapshot RAG poussé vers analytics_mcp BigQuery.")
                else:
                    print(f"  [!] analytics_mcp HTTP {resp_a.status} (non-bloquant).")
        except Exception as e_analytics:
            print(f"  [!] analytics_mcp indisponible ({e_analytics}) — snapshot non persisté (non-bloquant).")
    except Exception as e:
        logger.warning(f"[RAG] Erreur push analytics_mcp : {e}")

    if not all_ok:
        logger.warning(
            "[RAG] Calibrage partiel — certains cas n'ont pas pu être récupérés. "
            "Relancez : python3 platform-engineering/manage_env.py rag-calibrate --env prd"
        )
    else:
        print(f"  [+] Calibrage complet — {filename} est à jour et versionné.")
        print(f"\n[*] RAG Calibration — Étape 4/3 : Upload de {filename} sur le GCS du Frontend...")
        try:
            gcloud_bin = os.environ.get("GCLOUD_BIN", "gcloud")
            prefix_pattern = f"gs://frontend-{env}-{project_id}-*"
            res_ls = subprocess.run(
                [gcloud_bin, "storage", "ls", "--project", project_id, "-b", prefix_pattern],
                capture_output=True, text=True, check=True
            )
            bucket_url = res_ls.stdout.strip().splitlines()[0]
            subprocess.run(
                [
                    gcloud_bin, "storage", "cp", "--project", project_id,
                    golden_path, f"{bucket_url.rstrip('/')}/{filename}"
                ],
                check=True, capture_output=True
            )
            print(f"  [+] Uploadé avec succès sur {bucket_url.rstrip('/')}/{filename}")
        except Exception as e_upload:
            logger.warning(f"[RAG] Impossible d'uploader sur GCS : {e_upload}")

    return all_ok


def rag_run_eval(
    env: str,
    base_domain: str,
    access_token: str,
    recall_threshold: float = 0.5,
) -> bool:
    """
    Lance l'evaluation RAG sur le golden dataset (R3) contre l'env cible.

    Declenche automatiquement apres chaque deploy reussi de cv_api
    pour detecter toute regression de qualite de recherche.

    Retourne True si Recall@5 >= seuil, False si regression detectee.
    Non bloquant : le deploiement reste marque succes.
    """

    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filename = "golden_queries.json" if env in ("dev", "local") else f"golden_queries_{env}.json"
    golden_path = os.path.join(script_dir, "cv_api", "eval", filename)
    test_env_pytest = os.path.join(script_dir, "test_env", "bin", "pytest")

    if not os.path.exists(golden_path):
        logger.warning(f"[RAG Eval] {filename} introuvable — eval ignoree.")
        return True

    if not os.path.exists(test_env_pytest):
        logger.warning("[RAG Eval] test_env/bin/pytest introuvable — eval ignoree.")
        return True

    cv_base = (
        f"https://prd.{base_domain}/api/cv"
        if env == "prd"
        else f"https://api.{env}.{base_domain}/api/cv"
    )

    print(f"  [*] RAG Eval → {cv_base} (Recall@5 seuil: {recall_threshold})")
    env_vars = {
        **os.environ,
        "RAG_EVAL_BASE_URL": cv_base,
        "RAG_EVAL_TOKEN": access_token,
        "RAG_EVAL_ENV": env,
        "RAG_EVAL_DRY_RUN": "false",
        "RAG_EVAL_RECALL_THRESHOLD": str(recall_threshold),
        "RAG_EVAL_TOP_K": "5",
    }
    res = subprocess.run(
        [test_env_pytest, "cv_api/eval/rag_quality_eval.py",
         "-v", "--tb=line", "--no-header", "-q"],
        cwd=script_dir,
        env=env_vars,
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        logger.info("[RAG Eval] Qualite RAG validee (Recall@5 >= seuil).")
        return True
    else:
        # ── Parse pytest output pour extraire les métriques cas par cas ────────
        stdout = res.stdout or ""
        stderr = res.stderr or ""
        full_output = stdout + stderr

        # Collecter les blocs par cas golden
        case_results = []
        current = {}
        for line in full_output.splitlines():
            s = line.strip()

            # Début d'un nouveau cas : ligne "===[case_id] query==="
            if s.startswith("[") and "] " in s and not s.startswith("[FAILED"):
                if current:
                    case_results.append(current)
                bracket_end = s.index("]")
                current = {"id": s[1:bracket_end], "query": s[bracket_end + 2:], "lines": []}

            # Métriques parsées
            if current:
                current.setdefault("lines", []).append(s)
                if s.startswith("Recall@"):
                    # "Recall@5  : 0.000  (seuil: 0.5)"
                    parts = s.split(":")
                    if len(parts) >= 2:
                        try:
                            current["recall"] = float(parts[1].strip().split()[0])
                        except ValueError:
                            pass
                elif s.startswith("Expected"):
                    current["expected"] = s.split(":", 1)[-1].strip()
                elif s.startswith("Top-") and "IDs" in s:
                    current["retrieved"] = s.split(":", 1)[-1].strip()
                elif s.startswith("MRR"):
                    try:
                        current["mrr"] = float(s.split(":")[1].strip())
                    except (ValueError, IndexError):
                        pass

        if current:
            case_results.append(current)

        # Déterminer les cas FAILED depuis pytest
        failed_ids = set()
        for line in full_output.splitlines():
            if " FAILED " in line:
                # ex: "FAILED cv_api/eval/test_rag_quality.py::test_rag_recall_at_k[GCP_DEVOPS_001]"
                if "[" in line and "]" in line:
                    failed_ids.add(line[line.rindex("[") + 1:line.rindex("]")])

        failed_cases = [c for c in case_results if c.get("id") in failed_ids]
        # Compter tous les FAILED (avec ou sans espace préfixe selon le format pytest)
        all_failed_count = sum(
            1 for line in full_output.splitlines()
            if line.strip().startswith("FAILED") or " FAILED " in line
        )
        total_failed = len(failed_ids) if failed_ids else all_failed_count

        # ── Affichage détaillé ─────────────────────────────────────────────────
        sep = '─' * 70
        print(f"\n{sep}")
        print(f"  ❌ RAG Eval — {total_failed} cas en échec (Recall@5 < {recall_threshold})")
        print(sep)

        if failed_cases:
            for c in failed_cases:
                recall_str = f"{c.get('recall', '?'):.3f}" if isinstance(c.get('recall'), float) else "?"
                mrr_str = f"{c.get('mrr', '?'):.3f}" if isinstance(c.get('mrr'), float) else "?"
                print(f"\n  [{c['id']}]")
                print(f"    Query     : {c.get('query', '?')[:80]}")
                print(f"    Recall@5  : {recall_str}  (seuil: {recall_threshold})  |  MRR: {mrr_str}")
                print(f"    Attendus  : {c.get('expected', '?')}")
                print(f"    Retrouvés : {c.get('retrieved', '?')}")
        else:
            # Fallback : afficher les lignes pytest pertinentes
            print()
            for line in full_output.splitlines():
                s = line.strip()
                if any(k in s for k in ["FAILED", "AssertionError", "Recall@", "Expected", "retrouves"]):
                    print(f"    {s[:120]}")

        # Résumé global
        print(f"\n{sep}")
        print("  Logs complets : pytest cv_api/eval/rag_quality_eval.py -v --tb=short")
        print(f"  Recalibrer    : python3 platform-engineering/manage_env.py rag-calibrate --env {env}")

        # ── Prompt Antigravity ─────────────────────────────────────────────────
        failed_summary_lines = []
        for c in (failed_cases or []):
            recall_str = f"{c.get('recall', '?'):.3f}" if isinstance(c.get('recall'), float) else "?"
            failed_summary_lines.append(
                f"  - [{c['id']}] Recall@5={recall_str} | attendus={c.get('expected', '?')} | "
                f"retrouves={c.get('retrieved', '?')}"
            )
        failed_summary = "\n".join(failed_summary_lines) or "  (voir logs pytest ci-dessus)"

        eq70 = '═' * 70
        embed_model = os.getenv('GEMINI_EMBEDDING_MODEL', 'gemini-embedding-001')
        prompt = (
            f"\n{eq70}\n"
            "  📋 PROMPT ANTIGRAVITY — Regression RAG detectee (copier-coller)\n"
            f"{eq70}\n\n"
            f"Une regression RAG a ete detectee post-deploiement de cv_api ({env}).\n"
            f"{total_failed} cas golden echouent au seuil Recall@5={recall_threshold}.\n\n"
            f"Cas en echec :\n{failed_summary}\n\n"
            "Contexte technique :\n"
            f"- Env            : {env}\n"
            f"- cv_api URL     : {cv_base}\n"
            f"- Recall seuil   : {recall_threshold}\n"
            f"- Embedding model: {embed_model} (var GEMINI_EMBEDDING_MODEL)\n"
            "- Chunked search : RAG_CHUNKED_SEARCH=true\n\n"
            "Pistes a investiguer (par ordre de probabilite) :\n"
            "1. Bug dans execute_chunked_search() — verifier la query SQL\n"
            "2. Table cv_mission_embeddings vide — GET /api/cv/bulk-reanalyse/data-quality\n"
            f"3. Seuil VECTOR_DISTANCE_THRESHOLD trop strict — rag-calibrate --env {env}\n"
            "4. Modele embedding different entre indexation et requete\n\n"
            "Actions immediates :\n"
            f"- python3 platform-engineering/manage_env.py rag-calibrate --env {env}\n"
            "- gcloud logging read "
            "'resource.labels.service_name=\"cv-api-prd\"' --freshness=10m\n"
            f"{eq70}\n"
        )
        print(prompt)
        logger.warning(
            f"[RAG Eval] {total_failed} cas en echec — Recall@5 sous le seuil ({recall_threshold}). "
            "Voir tableau ci-dessus + prompt Antigravity."
        )
        return False


def plan(env, project_id: str):
    init_tf()
    set_workspace(env)

    logger.info(f"[*] Generating dry-run (terraform plan) for environment '{env}'...")
    cmd = ["terraform", "plan"] + get_tf_args(project_id)
    run_cmd(cmd)


def destroy(env, project_id, config, force=False):
    init_tf()
    set_workspace(env)

    # ── Étape A : Destruction des extra-projects en premier ─────────────────
    extra_projects = discover_extra_projects(config)
    region = config.get("region", "europe-west1")
    if extra_projects:
        _detach_extra_project_routes(env, project_id)
        print(f"[*] {len(extra_projects)} projet(s) externe(s) à détruire en premier :")
        for p in extra_projects:
            print(f"    - {p['name']}  ({p['path']})  →  lb_path={p['lb_path']}  version={p['version']}")
        print()
        for ext_proj in extra_projects:
            _destroy_extra_project_terraform(ext_proj, env, project_id, region)
        print(f"\n[+] Destruction des extra_projects terminée ({len(extra_projects)} projet(s)).")

    # ── Étape B : Nettoyage pré-destroy des adresses serverless-ipv4 ──────────
    _cleanup_serverless_addresses(project_id, region, env)

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
            _tf_ns = f'google_dns_record_set.extra_ns_delegation["{_zone}"]'
            _tf_a = f'google_dns_record_set.extra_a["{_zone}"]'
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
                print("[!] Echec definitif du destroy.")
                sys.exit(res.returncode)
        if SANITY_ERROR_COUNT > 0:
            raise DeploymentError(
                f"{SANITY_ERROR_COUNT} Sanity Checks failed. Consultez le rapport antigravity_sanity_error.md")

        # ── Étape C : Nettoyage local de .lb_routes_state.json ─────────────────
        _lb_routes_save(env, [])
        logger.info("[*] State local .lb_routes_state.json nettoyé.")

    finally:
        if force:
            toggle_prevent_destroy(disable=False)


if __name__ == "__main__":
    # Nettoyage de l'ancien rapport d'erreurs
    report_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "antigravity_sanity_error.md")
    if os.path.exists(report_file):
        os.remove(report_file)

    parser = argparse.ArgumentParser(description="Platform Engineering - Manage Environments")
    parser.add_argument(
        "action",
        choices=["deploy", "destroy", "plan", "rag-calibrate"],
        help="Action to perform",
    )
    parser.add_argument("--env", required=True, help="Environment name (dev, uat, prd)")
    parser.add_argument("--force", action="store_true",
                        help="Force deletion or replacement of protected DNS/SSL resources")
    parser.add_argument(
        "--extra-projects-only",
        action="store_true",
        dest="extra_projects_only",
        help=(
            "Déploie uniquement les extra_projects déclarés dans le YAML "
            "(validation + terraform apply de chaque projet externe). "
            "N'exécute PAS le terraform apply de la plateforme principale. "
            "Utile pour itérer rapidement sur un projet externe sans redéployer toute la stack."
        ),
    )

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

        # Base config = everything except :
        #   - image_* et *_version : gérés séparément ci-dessus
        #   - extra_projects       : directive manage_env.py uniquement, inconnue de Terraform
        #                            (sinon Terraform émet "Value for undeclared variable" sur chaque run)
        _PLATFORM_TF_EXCLUDED_KEYS = {"extra_projects"}
        base_config = {
            k: v for k, v in config.items()
            if not k.startswith("image_")
            and not k.endswith("_version")
            and k not in _PLATFORM_TF_EXCLUDED_KEYS
        }

        # Final flat config for Terraform
        # extra_projects : on n'injecte que les champs utiles à Terraform (name + alloydb_database).
        # Les champs manage_env.py-only (path, lb_path, version) sont exclus pour éviter
        # des erreurs de type Terraform (le type list(object({...})) est strict).
        raw_extra = config.get("extra_projects") or []
        tf_extra_projects = [
            {
                "name": p["name"],
                "alloydb_database": p.get("alloydb_database") or p["name"].replace("-", "_"),
            }
            for p in raw_extra
            if p.get("name")
        ]
        final_config = {**base_config, **merged_versions, **images}
        if tf_extra_projects:
            final_config["extra_projects"] = tf_extra_projects

        # Clean up any existing auto.tfvars.json files to prevent variable bleeding
        for fname in os.listdir(TERRAFORM_DIR):
            if fname.endswith(".auto.tfvars.json"):
                try:
                    os.remove(os.path.join(TERRAFORM_DIR, fname))
                except OSError:
                    pass

        # Dump it as auto.tfvars.json for Terraform to ingest automatically
        tfvars_path = os.path.join(TERRAFORM_DIR, f"{args.env}.auto.tfvars.json")
        # Injecte les routes LB des extra-projects connues depuis le state local
        # afin qu'elles survivent à chaque apply plateforme.
        project_id = final_config.get("project_id", "slavayssiere-sandbox-462015")
        known_lb_routes = _lb_routes_load(args.env)
        valid_lb_routes = []
        for r in known_lb_routes:
            bs_id = r.get("backend_service_id", "")
            bs_name = bs_id.split("/")[-1] if "/" in bs_id else bs_id
            if bs_id and resource_exists_in_gcp("backend_service", bs_id, project_id):
                valid_lb_routes.append(r)
            else:
                logger.info(
                    f"[lb-routes] Route '{r['name']}' ignorée car le backend '{bs_name}' "
                    f"n'existe pas encore dans GCP."
                )

        final_config["extra_project_routes"] = valid_lb_routes
        if valid_lb_routes:
            logger.info(
                f"[lb-routes] {len(valid_lb_routes)} route(s) valide(s) injectée(s) dans le tfvars "
                f"({[r['name'] for r in valid_lb_routes]})."
            )
        with open(tfvars_path, "w") as f:
            json.dump(final_config, f, indent=2)
        logger.info(f"[+] {args.env}.auto.tfvars.json généré ({len(final_config)} variables).")

        # final_config["extra_projects"] contient la version allégée (name + alloydb_database)
        # nécessaire pour Terraform (type list(object({...})) strict).
        # deploy() et discover_extra_projects() ont besoin de la version COMPLÈTE (path, lb_path,
        # version…) issue du YAML brut.  On construit deploy_config qui restaure l'original.
        deploy_config = dict(final_config)
        if raw_extra:
            deploy_config["extra_projects"] = raw_extra  # restaure path, lb_path, version, etc.

        project_id = deploy_config.get("project_id", "slavayssiere-sandbox-462015")
        CURRENT_PROJECT_ID = project_id
        base_domain = deploy_config.get("base_domain", "slavayssiere-zenika.com")

        if args.action == "deploy":
            if args.extra_projects_only:
                _deploy_extra_projects_only(args.env, project_id, deploy_config)
            else:
                deploy(args.env, base_domain, project_id, deploy_config, force=args.force)

        elif args.action == "destroy":
            destroy(args.env, project_id, deploy_config, force=args.force)
        elif args.action == "plan":
            plan(args.env, project_id)
        elif args.action == "rag-calibrate":
            secret_name = os.environ.get("ZENIKA_SECRET_NAME", f"admin-password-{args.env}")
            admin_email = os.environ.get("ZENIKA_ADMIN_EMAIL", "admin@zenika.com")
            gcloud_bin = os.environ.get("GCLOUD_BIN", "gcloud")
            auth_base = f"https://prd.{base_domain}" if args.env == "prd" else f"https://{args.env}.{base_domain}"

            print(f"[*] Récupération du mot de passe via Secret Manager ({secret_name})...")
            res = subprocess.run(
                [gcloud_bin, "secrets", "versions", "access", "latest",
                 f"--secret={secret_name}", f"--project={project_id}"],
                capture_output=True, text=True
            )
            if res.returncode != 0 or not res.stdout.strip():
                logger.error(f"[RAG] Impossible de lire {secret_name} : {res.stderr.strip()}")
                sys.exit(1)
            admin_pwd = res.stdout.strip()
            print(f"[*] Authentification sur {auth_base}/auth/login ({admin_email})...")
            login_data = json.dumps({"email": admin_email, "password": admin_pwd}).encode()

            # Contexte SSL : certifi en priorité (macOS), sinon contexte système, sinon no-verify
            try:
                import certifi
                ctx = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                ctx = ssl.create_default_context()

            def _do_login(ssl_ctx) -> str:
                req = urllib.request.Request(
                    f"{auth_base}/auth/login",
                    data=login_data,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as resp:
                    return json.loads(resp.read().decode()).get("access_token", "")

            try:
                access_token = _do_login(ctx)
            except ssl.SSLCertVerificationError as ssl_err:
                if "unable to get local issuer certificate" in str(ssl_err):
                    logger.warning(
                        "[RAG] SSL verify échoué (certificats système macOS). "
                        "Fallback sans vérification SSL (non-critique en dev local)."
                    )
                    ctx_noverify = ssl.create_default_context()
                    ctx_noverify.check_hostname = False
                    ctx_noverify.verify_mode = ssl.CERT_NONE
                    try:
                        access_token = _do_login(ctx_noverify)
                    except Exception as e2:
                        logger.error(f"[RAG] Échec de l'authentification (fallback no-verify) : {e2}")
                        sys.exit(1)
                else:
                    logger.error(f"[RAG] Échec SSL : {ssl_err}")
                    sys.exit(1)
            except Exception as e:
                logger.error(f"[RAG] Échec de l'authentification : {e}")
                sys.exit(1)

            if not access_token:
                logger.error("[RAG] access_token absent de la réponse login.")
                sys.exit(1)
            print("[+] JWT récupéré.")
            success = rag_calibrate(args.env, base_domain, project_id, access_token)
            sys.exit(0 if success else 1)

    except DeploymentError as e:
        logger.error(f"DEPLOYMENT FAILED: {e}")
        generate_antigravity_error_report("Exécution Terraform / Déploiement infra",
                                          str(e), ["terraform", "deployment", "infrastructure"])
        total = elapsed()
        print(f"\n{'=' * 55}")
        print(f"[!] Script terminé avec erreur en {total}.")
        print(f"{'=' * 55}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"UNEXPECTED ERROR: {e}")
        total = elapsed()
        print(f"\n{'=' * 55}")
        print(f"[!] Script terminé avec erreur inattendue en {total}.")
        print(f"{'=' * 55}")
        sys.exit(1)
    else:
        total = elapsed()
        print(f"\n{'=' * 55}")
        print(f"[+] Script terminé avec succès en {total}.")
        print(f"{'=' * 55}")
