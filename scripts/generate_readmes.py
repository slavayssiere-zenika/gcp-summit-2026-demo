#!/usr/bin/env python3
"""
generate_readmes.py — Mise à jour partielle des README.md des microservices.

Sections AUTO-GÉNÉRÉES (remplacées à chaque run) :
  - ## Fichiers clés
  - ## Variables d'environnement
  - ## Endpoints clés
  - ## MCP tools exposés  (APIs data uniquement)
  - ## MCP APIs consommées  (agents uniquement)

Sections PROTÉGÉES (jamais touchées) :
  - ## Rôle
  - ## Type
  - ## Architecture *
  - ## Redis
  - ## GCS *
  - ## Gotchas connus
  - ## Dernière modification
  - Toute section non listée ci-dessus

Usage :
  python3 scripts/generate_readmes.py           # tous les services
  python3 scripts/generate_readmes.py cv_api    # un service uniquement
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Services connus — (dossier, type)
SERVICES = {
    # APIs data
    "users_api": "data_api",
    "items_api": "data_api",
    "competencies_api": "data_api",
    "cv_api": "data_api",
    "missions_api": "data_api",
    "drive_api": "data_api",
    "prompts_api": "data_api",
    # Agents
    "agent_router_api": "agent",
    "agent_hr_api": "agent",
    "agent_ops_api": "agent",
    "agent_missions_api": "agent",
    # MCP natifs
    "analytics_mcp": "mcp_native",
    "monitoring_mcp": "mcp_native",
}

# Sections auto-générables (en minuscules pour la détection)
AUTO_SECTIONS = {
    "fichiers clés",
    "variables d'environnement",
    "endpoints clés",
    "mcp tools exposés",
    "mcp apis consommées",
}

GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
RED = "\033[0;31m"
RESET = "\033[0m"


# ─── Extraction depuis Dockerfile ────────────────────────────────────────────

def extract_env_vars(service_dir: Path) -> list[dict]:
    """Extrait les variables ENV du Dockerfile."""
    dockerfile = service_dir / "Dockerfile"
    if not dockerfile.exists():
        return []

    env_vars = []
    for line in dockerfile.read_text().splitlines():
        line = line.strip()
        if line.startswith("ENV "):
            parts = line[4:].split("=", 1)
            if len(parts) == 2:
                name, value = parts[0].strip(), parts[1].strip()
                # Classifier le type
                if any(k in name.lower() for k in ("secret", "key", "password", "token", "jwt")):
                    var_type = "Secret"
                elif any(k in name.lower() for k in ("url", "host", "port", "database", "redis", "gcp", "project")):
                    var_type = "Infra"
                else:
                    var_type = "Comportement"
                env_vars.append({"name": name, "type": var_type, "value": value})

    return env_vars


def format_env_table(env_vars: list[dict]) -> str:
    """Formate les variables d'env en tableau Markdown."""
    if not env_vars:
        return "_Aucune variable ENV définie dans le Dockerfile._\n"

    lines = ["| Var | Type | Valeur dev |", "|---|---|---|"]
    for v in env_vars:
        lines.append(f"| `{v['name']}` | {v['type']} | `{v['value']}` |")
    return "\n".join(lines) + "\n"


# ─── Extraction depuis mcp_server.py ─────────────────────────────────────────

def extract_mcp_tools(service_dir: Path) -> list[str]:
    """Extrait les noms des tools MCP depuis mcp_server.py."""
    mcp_server = service_dir / "mcp_server.py"
    if not mcp_server.exists():
        return []

    content = mcp_server.read_text()
    # Cherche name="tool_name" dans les Tool() ou add_tool()
    tools = re.findall(r'name=["\']([a-z_]+)["\']', content)
    return sorted(set(tools))


# ─── Extraction des endpoints depuis main.py / routers ───────────────────────

def extract_endpoints(service_dir: Path) -> list[str]:
    """Extrait les routes HTTP depuis les fichiers Python du service."""
    endpoints = []
    route_pattern = re.compile(
        r'@(?:router|app|protected_router)\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']'
    )

    search_dirs = [service_dir / "src", service_dir]
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for py_file in sorted(search_dir.rglob("*.py")):
            # Ignorer tests, __pycache__, mcp_server
            if any(p in py_file.parts for p in ("test_", "__pycache__", "tests")):
                continue
            if py_file.name == "mcp_server.py":
                continue
            try:
                content = py_file.read_text()
                for match in route_pattern.finditer(content):
                    method = match.group(1).upper()
                    path = match.group(2)
                    # Ignorer /health, /metrics, /ready, /mcp/{path:path}
                    if any(skip in path for skip in ("/health", "/metrics", "/ready", "/mcp/{path")):
                        continue
                    endpoints.append(f"`{method} {path}`")
            except Exception:
                continue

    # Dédupliquer en gardant l'ordre
    seen = set()
    unique = []
    for e in endpoints:
        if e not in seen:
            seen.add(e)
            unique.append(e)
    return unique[:20]  # Limiter à 20 endpoints max


def format_endpoints(endpoints: list[str]) -> str:
    if not endpoints:
        return "_Aucun endpoint détecté automatiquement._\n"
    return "\n".join(f"- {e}" for e in endpoints) + "\n"


# ─── Extraction des fichiers clés ────────────────────────────────────────────

def extract_key_files(service_dir: Path, svc_type: str) -> list[dict]:
    """Identifie les fichiers clés du service."""
    key_files = []

    # Fichiers racine standards
    for fname in ["main.py", "mcp_server.py", "conftest.py", "metrics.py", "agent.py"]:
        fpath = service_dir / fname
        if fpath.exists():
            lines = len(fpath.read_text().splitlines())
            labels = {
                "main.py": "Point d'entrée FastAPI, middlewares, Prometheus",
                "mcp_server.py": "Sidecar MCP stdio — exposition des tools",
                "conftest.py": "Fixtures pytest partagées",
                "metrics.py": "Compteurs Prometheus",
                "agent.py": "Définition de l'agent ADK et ses tools",
            }
            key_files.append({
                "file": fname,
                "lines": lines,
                "label": labels.get(fname, ""),
                "status": "✅" if lines < 400 else "⚠️"
            })

    # Routers
    router_dirs = [
        service_dir / "src" / "routers",
        service_dir / "src",
    ]
    for search_dir in router_dirs:
        if not search_dir.exists():
            continue
        for py_file in sorted(search_dir.rglob("*router*.py")):
            rel = py_file.relative_to(service_dir)
            lines = len(py_file.read_text().splitlines())
            key_files.append({
                "file": str(rel),
                "lines": lines,
                "label": "Router HTTP",
                "status": "✅" if lines < 500 else "⚠️"
            })
        break  # Seulement le premier niveau de routers

    return key_files[:10]


def format_key_files(key_files: list[dict]) -> str:
    if not key_files:
        return "_Aucun fichier clé détecté._\n"
    lines = ["| Fichier | Lignes | État |", "|---|---|---|"]
    for f in key_files:
        lines.append(f"| `{f['file']}` | {f['lines']} | {f['status']} |")
    return "\n".join(lines) + "\n"


# ─── Extraction de la version ─────────────────────────────────────────────────

def get_version(service_dir: Path) -> str:
    version_file = service_dir / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return "N/A"


# ─── Moteur de mise à jour partielle du README ───────────────────────────────

def split_readme_sections(content: str) -> list[tuple[str, str]]:
    """
    Découpe le README en sections (titre_h2, contenu).
    Retourne une liste de tuples (header_line, body).
    Le premier élément peut être ("__preamble__", texte_avant_première_section).
    """
    sections = []
    current_header = "__preamble__"
    current_body = []

    for line in content.splitlines(keepends=True):
        if line.startswith("## "):
            sections.append((current_header, "".join(current_body)))
            current_header = line.rstrip()
            current_body = []
        else:
            current_body.append(line)

    sections.append((current_header, "".join(current_body)))
    return sections


def is_auto_section(header: str) -> bool:
    """Vérifie si une section doit être régénérée automatiquement."""
    title = header.lstrip("#").strip().lower()
    return title in AUTO_SECTIONS


def build_auto_section(header: str, service_dir: Path, svc_type: str) -> str:
    """Génère le contenu d'une section auto-générée."""
    title = header.lstrip("#").strip().lower()

    if title == "fichiers clés":
        key_files = extract_key_files(service_dir, svc_type)
        return format_key_files(key_files) + "\n"

    elif title == "variables d'environnement":
        env_vars = extract_env_vars(service_dir)
        return format_env_table(env_vars) + "\n"

    elif title == "endpoints clés":
        endpoints = extract_endpoints(service_dir)
        return format_endpoints(endpoints) + "\n"

    elif title == "mcp tools exposés":
        tools = extract_mcp_tools(service_dir)
        if not tools:
            return "_Aucun tool MCP détecté dans `mcp_server.py`._\n\n"
        tools_str = ", ".join(f"`{t}`" for t in tools)
        return f"- {tools_str}\n\n"

    elif title == "mcp apis consommées":
        # Pour les agents : scanner les appels httpx dans mcp_client.py
        mcp_client = service_dir / "mcp_client.py"
        apis = []
        if mcp_client.exists():
            content = mcp_client.read_text()
            # Chercher les URLs de services
            urls = re.findall(r'os\.getenv\(["\']([A-Z_]+_URL)["\']', content)
            apis = sorted(set(urls))
        if not apis:
            return "_Voir `mcp_client.py` pour la liste complète._\n\n"
        return "\n".join(f"- `{a}`" for a in apis) + "\n\n"

    return "\n"


def update_readme(service_dir: Path, svc_type: str, dry_run: bool = False) -> bool:
    """Met à jour partiellement le README.md du service."""
    readme_path = service_dir / "README.md"
    svc_name = service_dir.name

    if not readme_path.exists():
        print(f"{YELLOW}[!] {svc_name}: README.md absent — ignoré{RESET}")
        return False

    original = readme_path.read_text()
    sections = split_readme_sections(original)

    new_parts = []
    changed = False

    for header, body in sections:
        if header == "__preamble__":
            new_parts.append(body)
            continue

        if is_auto_section(header):
            new_body = build_auto_section(header, service_dir, svc_type)
            new_parts.append(f"{header}\n")
            new_parts.append(new_body)
            if new_body.strip() != body.strip():
                changed = True
        else:
            # Section protégée — conserver intégralement
            new_parts.append(f"{header}\n")
            new_parts.append(body)

    new_content = "".join(new_parts)

    if not changed:
        print(f"{GREEN}[=] {svc_name}: README à jour — aucune modification{RESET}")
        return False

    if not dry_run:
        readme_path.write_text(new_content)
        print(f"{GREEN}[✓] {svc_name}: README mis à jour{RESET}")
    else:
        print(f"{YELLOW}[DRY] {svc_name}: README modifié (dry-run, non écrit){RESET}")

    return True


# ─── Entrypoint ──────────────────────────────────────────────────────────────

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    target = args[0] if args else None

    if dry_run:
        print(f"{YELLOW}Mode dry-run — aucun fichier ne sera modifié{RESET}\n")

    services_to_process = {}
    if target:
        if target in SERVICES:
            services_to_process[target] = SERVICES[target]
        else:
            print(f"{RED}[!] Service inconnu : {target}{RESET}")
            print(f"    Services disponibles : {', '.join(SERVICES.keys())}")
            sys.exit(1)
    else:
        services_to_process = SERVICES

    updated = 0
    skipped = 0
    errors = 0

    for svc_name, svc_type in services_to_process.items():
        service_dir = ROOT / svc_name
        if not service_dir.is_dir():
            print(f"{YELLOW}[!] {svc_name}: dossier absent — ignoré{RESET}")
            skipped += 1
            continue
        try:
            was_updated = update_readme(service_dir, svc_type, dry_run=dry_run)
            if was_updated:
                updated += 1
        except Exception as e:
            print(f"{RED}[✗] {svc_name}: erreur — {e}{RESET}")
            errors += 1

    total = len(services_to_process)
    print(f"\n{'─' * 50}")
    print(f"✅ {updated}/{total} README mis à jour | "
          f"= {total - updated - errors} inchangés | "
          f"✗ {errors} erreurs")


if __name__ == "__main__":
    main()
