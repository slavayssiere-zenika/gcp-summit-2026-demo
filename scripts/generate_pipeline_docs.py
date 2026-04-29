#!/usr/bin/env python3
"""
generate_pipeline_docs.py
Génère automatiquement docs/pipelines.md en documentant les pipelines
CI/CD du projet : deploy.sh, manage_env.py et la matrice d'environnements.
"""

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DOCS_DIR = ROOT / "docs"
OUTPUT_FILE = DOCS_DIR / "pipelines.md"

ENVS_DIR = ROOT / "platform-engineering" / "envs"
DEPLOY_SH = ROOT / "scripts" / "deploy.sh"
MANAGE_ENV_PY = ROOT / "platform-engineering" / "manage_env.py"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _last_git_date(path: Path) -> str:
    """Retourne la date du dernier commit affectant ce fichier."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ci", str(path)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        date_str = result.stdout.strip()
        if date_str:
            return date_str[:10]  # YYYY-MM-DD
    except Exception:
        pass
    return "–"


# ──────────────────────────────────────────────────────────────────────────────
# Section 1 : Matrice des environnements (envs/*.yaml)
# ──────────────────────────────────────────────────────────────────────────────

_ENV_LABELS = {
    "dev.yaml": ("DEV", "Développement éphémère (Sandbox)"),
    "uat.yaml": ("UAT", "Validation pré-production"),
    "prd.yaml": ("PRD", "Production"),
}

_INTERESTING_KEYS = [
    "project_id",
    "base_domain",
    "image_registry",
    "cloudrun_min_instances",
    "cloudrun_max_instances",
    "alloydb_cpu",
    "waf_rate_limit",
    "gemini_router_model",
    "gemini_hr_model",
    "gemini_ops_model",
    "gemini_missions_model",
    "gemini_cv_model",
    "gemini_pro_model",
    "gemini_embedding_model",
    "trace_sampling_rate",
]


def _parse_yaml_simple(content: str) -> dict:
    """Parseur minimaliste de YAML clé: valeur (sans dépendance PyYAML)."""
    result = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^([\w_]+)\s*:\s*(.+)$', line)
        if m:
            key = m.group(1).strip()
            value = m.group(2).strip().strip('"').strip("'")
            # Ignorer les commentaires inline
            value = re.sub(r'\s+#.*$', '', value).strip()
            result[key] = value
    return result


def build_env_matrix_section() -> str:
    rows_by_key: dict[str, dict] = {k: {} for k in _INTERESTING_KEYS}
    env_files = sorted(ENVS_DIR.glob("*.yaml"))

    columns = []
    for f in env_files:
        label, desc = _ENV_LABELS.get(f.name, (f.stem.upper(), ""))
        columns.append((f.name, label, desc))
        data = _parse_yaml_simple(_read(f))
        for key in _INTERESTING_KEYS:
            rows_by_key[key][f.name] = data.get(key, "–")

    header_cols = " | ".join(f"**{label}**" for _, label, _ in columns)
    sep = " | ".join(["---"] * (1 + len(columns)))

    lines = [
        "## 🌐 Matrice des Environnements\n",
        f"| Paramètre | {header_cols} |",
        f"| --- | {sep} |",
    ]

    _section_headers = {
        "project_id": ("### ☁️ GCP", True),
        "image_registry": ("### 🐳 Registre d'images", True),
        "cloudrun_min_instances": ("### 🚀 Cloud Run", True),
        "alloydb_cpu": ("### 🗄️ AlloyDB", True),
        "waf_rate_limit": ("### 🛡️ Sécurité", True),
        "gemini_router_model": ("### 🤖 Modèles IA", True),
        "trace_sampling_rate": ("### 📊 Observabilité", True),
    }

    for key in _INTERESTING_KEYS:
        if key in _section_headers:
            section_title, _ = _section_headers[key]
            lines.append(f"\n{section_title}\n")
            lines.append(f"| Paramètre | {header_cols} |")
            lines.append(f"| --- | {sep} |")
        values = " | ".join(f"`{rows_by_key[key].get(fn, '–')}`" for fn, _, _ in columns)
        lines.append(f"| `{key}` | {values} |")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Section 2 : Pipeline deploy.sh
# ──────────────────────────────────────────────────────────────────────────────

# Liste des microservices data + agents
_APP_MICROSERVICES = [
    "users_api", "items_api", "competencies_api", "cv_api",
    "prompts_api", "drive_api", "missions_api", "analytics_mcp", "monitoring_mcp",
]
_AGENTS = [
    "agent_router_api", "agent_hr_api", "agent_ops_api", "agent_missions_api",
]
_SPECIAL = ["frontend", "db_migrations", "db_init", "sync_prompts"]

_SERVICE_DESCRIPTIONS = {
    "users_api": "Gestion des utilisateurs, authentification JWT",
    "items_api": "Gestion des items et catégories",
    "competencies_api": "Arbre de compétences",
    "cv_api": "Analyse et stockage multimodale des CVs",
    "prompts_api": "Gestion des system prompts des agents",
    "drive_api": "Synchronisation Google Drive",
    "missions_api": "Gestion des missions client",
    "analytics_mcp": "FinOps & BigQuery analytics (MCP natif)",
    "monitoring_mcp": "Monitoring Cloud Run / Logs (MCP natif)",
    "agent_router_api": "Orchestrateur A2A — routeur principal (Gemini Pro)",
    "agent_hr_api": "Sous-agent RH — CVs, compétences, utilisateurs",
    "agent_ops_api": "Sous-agent Ops — items, missions, opérationnel",
    "agent_missions_api": "Sous-agent Missions — gestion documentaire staffing",
    "frontend": "SPA Vue.js — build npm + upload GCS + invalidation CDN",
    "db_migrations": "Liquibase — migration du schéma AlloyDB (Cloud Run Job)",
    "db_init": "Initialisation AlloyDB (Cloud Run Job, accès VPC uniquement)",
    "sync_prompts": "Synchronisation des system prompts vers prompts_api",
}

_OPTIONS = [
    ("`patch` (défaut)", "Incrémente la version `Z` en `vX.Y.Z`"),
    ("`minor`", "Incrémente la version `Y`, remet `Z` à 0"),
    ("`major`", "Incrémente la version `X`, remet `Y.Z` à 0"),
    ("`none`", "Utilise la version actuelle sans modification"),
    ("`--no-deploy`", "Build et push Docker uniquement — ne déploie pas sur Cloud Run"),
    ("`--skip-unchanged`", "Ignore le build des services sans changement (basé sur le hash SHA1)"),
]


def build_deploy_section() -> str:
    last_modified = _last_git_date(DEPLOY_SH)

    # Extraire le PROJECT_ID et REGION du fichier
    content = _read(DEPLOY_SH)
    project_id = re.search(r'^PROJECT_ID="([^"]+)"', content, re.M)
    region = re.search(r'^REGION="([^"]+)"', content, re.M)
    registry = re.search(r'^REGISTRY="([^"]+)"', content, re.M)

    project_id = project_id.group(1) if project_id else "–"
    region = region.group(1) if region else "–"
    registry = registry.group(1) if registry else "–"

    lines = [
        "## 🚀 Pipeline de Déploiement — `scripts/deploy.sh`\n",
        f"> Dernière modification : `{last_modified}` · Cible : `{project_id}` / `{region}` · Registre : `{registry}`\n",
        "### Utilisation\n",
        "```bash",
        "# Déployer tous les services (bump patch)",
        "bash scripts/deploy.sh all",
        "",
        "# Déployer des services spécifiques avec bump minor",
        "bash scripts/deploy.sh users_api cv_api minor",
        "",
        "# Build Docker uniquement (sans déploiement Cloud Run)",
        "bash scripts/deploy.sh all --no-deploy",
        "",
        "# Ignorer les services sans modification",
        "bash scripts/deploy.sh all --skip-unchanged",
        "```\n",
        "### Options de versioning (SemVer)\n",
        "| Option | Effet |",
        "| --- | --- |",
    ]
    for opt, desc in _OPTIONS:
        lines.append(f"| {opt} | {desc} |")

    lines += [
        "\n### Services disponibles\n",
        "#### 🔵 APIs Data (exposent un sidecar MCP)\n",
        "| Service | Description | Cible Cloud Run |",
        "| --- | --- | --- |",
    ]
    for svc in _APP_MICROSERVICES:
        cr_name = svc.replace("_", "-") + "-dev"
        lines.append(f"| `{svc}` | {_SERVICE_DESCRIPTIONS.get(svc, '–')} | `{cr_name}` |")

    lines += [
        "\n#### 🟣 Agents IA (build depuis la racine avec `agent_commons`)\n",
        "| Service | Description | Cible Cloud Run |",
        "| --- | --- | --- |",
    ]
    for svc in _AGENTS:
        cr_name = svc.replace("_", "-") + "-dev"
        lines.append(f"| `{svc}` | {_SERVICE_DESCRIPTIONS.get(svc, '–')} | `{cr_name}` |")

    lines += [
        "\n#### ⚙️ Services Spéciaux\n",
        "| Service | Description |",
        "| --- | --- |",
    ]
    for svc in _SPECIAL:
        lines.append(f"| `{svc}` | {_SERVICE_DESCRIPTIONS.get(svc, '–')} |")

    lines += [
        "\n### Flux d'exécution\n",
        "```",
        "deploy.sh [SERVICE] [BUMP_TYPE] [OPTIONS]",
        "     │",
        "     ├─► Compute hash SHA1 du service (--skip-unchanged)",
        "     ├─► Bump version dans SERVICE/VERSION",
        "     ├─► docker build --platform linux/amd64",
        "     ├─► docker push → Artifact Registry (europe-west1)",
        "     ├─► gcloud run services update (ou jobs update + execute)",
        "     └─► sync_system_prompts() si service impacté",
        "```\n",
        "> **Sync automatique des prompts** : après tout déploiement impactant",
        "> `prompts_api`, `agent_*`, `cv_api` ou `missions_api`, le script",
        "> appelle automatiquement `sync_system_prompts()` via `scripts/sync_prompts.py`.",
    ]
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Section 3 : Pipeline manage_env.py
# ──────────────────────────────────────────────────────────────────────────────

_MANAGE_COMMANDS = [
    ("plan", "`--env <dev|uat|prd>`", "Exécute `terraform plan` sur l'environnement cible sans appliquer"),
    ("apply", "`--env <dev|uat|prd>`", "⚠️ Interdit à l'agent — déploiement Terraform (réservé au développeur)"),
    ("sanity", "`--env <dev|uat|prd>`", "Vérifie la disponibilité de chaque endpoint Cloud Run + MCP"),
    ("sync-frontend", "`--env <dev|uat|prd>`", "Upload les assets frontend depuis le bucket GCS vers le bucket de l'env"),
    ("seed-finops", "`--env <dev|uat|prd>`", "Initialise les tables BigQuery FinOps (`model_pricing`, `ai_usage`)"),
    ("status", "`--env <dev|uat|prd>`", "Affiche les versions déployées par service et leur statut Cloud Run"),
]


def build_manage_env_section() -> str:
    last_modified = _last_git_date(MANAGE_ENV_PY)

    lines = [
        "## ⚙️ Pipeline d'Infrastructure — `platform-engineering/manage_env.py`\n",
        f"> Dernière modification : `{last_modified}`\n",
        "### Description\n",
        "`manage_env.py` est l'outil de gestion des environnements GCP.",
        "Il lit la configuration depuis `platform-engineering/envs/<env>.yaml`",
        "et pilote Terraform, les validations de santé et le seeding FinOps.\n",
        "### Commandes disponibles\n",
        "| Commande | Arguments | Description |",
        "| --- | --- | --- |",
    ]
    for cmd, args, desc in _MANAGE_COMMANDS:
        lines.append(f"| `{cmd}` | {args} | {desc} |")

    lines += [
        "\n### Priorité des versions d'images\n",
        "```",
        "YAML (envs/<env>.yaml)  >  VERSION (fichier local du service)",
        "```",
        "Si une version est explicitement définie dans le fichier YAML de l'environnement,",
        "elle prend le dessus sur le fichier `VERSION` local du microservice.\n",
        "### Flux d'exécution (plan/apply)\n",
        "```",
        "manage_env.py plan --env dev",
        "     │",
        "     ├─► Lecture de platform-engineering/envs/dev.yaml",
        "     ├─► Calcul des URLs d'images : {image_registry}/{service}:{version}",
        "     ├─► Sélection workspace Terraform : tf workspace select dev",
        "     ├─► terraform plan -var-file=... (variables injectées depuis YAML)",
        "     └─► Rapport des changements détectés",
        "```",
    ]
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Section 4 : Scripts auxiliaires
# ──────────────────────────────────────────────────────────────────────────────

_AUX_SCRIPTS = [
    ("scripts/run_tests.sh", "Lance tous les `pytest` en parallèle pour chaque microservice"),
    ("scripts/generate_specs.py", "Régénère `spec.md` dans chaque service via l'OpenAPI FastAPI"),
    ("scripts/generate_changelog.py", "Met à jour `changelog.md` avec les rapports de couverture"),
    ("scripts/sync_prompts.py", "Pousse les system prompts vers `prompts_api` (AlloyDB)"),
    ("scripts/generate_pipeline_docs.py", "Régénère ce document `docs/pipelines.md` (auto)"),
    ("scripts/async_manage_env.sh", "Wrapper asynchrone pour `manage_env.py` (runs en background)"),
    ("platform-engineering/manage_env.py", "Gestion complète des environnements GCP (plan/apply/sanity/seed)"),
]


def build_aux_scripts_section() -> str:
    lines = [
        "## 🔧 Scripts Auxiliaires\n",
        "| Script | Rôle |",
        "| --- | --- |",
    ]
    for script, desc in _AUX_SCRIPTS:
        lines.append(f"| `{script}` | {desc} |")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Assemblage final
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sections = [
        f"# 📦 Documentation des Pipelines CI/CD\n",
        f"> ⚙️ Document auto-généré le **{now}** par `scripts/generate_pipeline_docs.py`.\n",
        "> Ne pas éditer manuellement — vos modifications seront écrasées au prochain `/git-push`.\n",
        "---\n",
        build_env_matrix_section(),
        "\n---\n",
        build_deploy_section(),
        "\n---\n",
        build_manage_env_section(),
        "\n---\n",
        build_aux_scripts_section(),
        "\n---\n",
        "## 📚 Ressources complémentaires\n",
        "- [AGENTS.md](../AGENTS.md) — Golden Rules de l'architecture",
        "- [spec.md](../platform-engineering/spec.md) — Spécifications API auto-générées",
        "- [changelog.md](../changelog.md) — Historique des versions et couvertures",
        "- [todo.md](../todo.md) — Backlog technique (ADRs)",
    ]

    content = "\n".join(sections) + "\n"
    OUTPUT_FILE.write_text(content, encoding="utf-8")
    print(f"✅ docs/pipelines.md généré ({len(content)} caractères)")


if __name__ == "__main__":
    main()
