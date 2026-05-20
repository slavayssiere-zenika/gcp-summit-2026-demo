#!/usr/bin/env python3
"""Script d'analyse statique et d'audit de conformité architectural (Python).

Ce script valide le respect des Golden Rules de la plateforme Zenika, notamment
le Zero-Trust, l'isolation Redis, la résilience HTTP (timeouts/retries),
les guards 429 et le hardening mémoire (sémaphores shielded, Redis async).
"""

import argparse
import os
import re
import sys
from pathlib import Path

SERVICES = [
    "users_api", "items_api", "competencies_api", "cv_api",
    "missions_api", "drive_api", "prompts_api", "analytics_mcp",
    "monitoring_mcp", "agent_hr_api", "agent_ops_api",
    "agent_missions_api", "agent_router_api"
]

VIOLATIONS = []


def check_local_imports(filepath: Path, lines: list):
    """Vérifie que les imports ne sont pas faits localement dans des fonctions."""
    if filepath.name == "__init__.py" or "tests" in filepath.parts or filepath.name == "conftest.py":
        return
    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Détection d'un import indenté de 4 espaces ou plus
        if re.match(r"^ {4,}(from|import) ", line):
            VIOLATIONS.append({
                "file": str(filepath),
                "line": idx,
                "rule": "PEP8 §8 / E402",
                "detail": f"Import local détecté: '{stripped}' (remonter au top-level)",
                "severity": "MAJEUR"
            })


def check_cors_security(filepath: Path, lines: list):
    """S'assure que CORS n'utilise pas d'origine wildcard en dur."""
    if filepath.name != "main.py":
        return
    for idx, line in enumerate(lines, 1):
        if "allow_origins" in line and '"*"' in line.replace(" ", ""):
            VIOLATIONS.append({
                "file": str(filepath),
                "line": idx,
                "rule": "CORS Sécurisé §3.1",
                "detail": "Wildcard '*' détecté dans allow_origins (doit charger CORS_ORIGINS)",
                "severity": "CRITIQUE"
            })


def check_service_version(filepath: Path, lines: list):
    """Vérifie que SERVICE_VERSION n'est pas codé en dur."""
    if filepath.name != "main.py":
        return
    for idx, line in enumerate(lines, 1):
        if re.search(r"SERVICE_VERSION\s*=\s*['\"][0-9]", line):
            VIOLATIONS.append({
                "file": str(filepath),
                "line": idx,
                "rule": "Versioning §3.1",
                "detail": "SERVICE_VERSION codé en dur (doit utiliser os.getenv('APP_VERSION', 'dev'))",
                "severity": "MAJEUR"
            })


def check_redis_clients(filepath: Path, lines: list):
    """Valide l'absence de client Redis synchrone bloquant."""
    if "shared" in filepath.parts or "tests" in filepath.parts:
        return
    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or "noqa" in line:
            continue
        if any(p in line for p in ["redis.Redis(", "redis.from_url(", "redis.StrictRedis("]):
            if "redis.asyncio" not in line and "redis.asyncio" not in "".join(lines):
                VIOLATIONS.append({
                    "file": str(filepath),
                    "line": idx,
                    "rule": "Hardening Mémoire §3.7 (Axe 2)",
                    "detail": "Client Redis synchrone bloquant détecté dans un service async",
                    "severity": "CRITIQUE"
                })


def check_sqlalchemy_pool(filepath: Path, lines: list):
    """Vérifie la robustesse du pool de connexions SQLAlchemy."""
    if filepath.name != "database.py" or "shared" not in filepath.parts:
        return
    content = "".join(lines)
    if "pool_recycle" not in content:
        VIOLATIONS.append({
            "file": str(filepath),
            "line": 1,
            "rule": "Hardening Mémoire §3.7 (Axe 3)",
            "detail": "pool_recycle ABSENT dans shared/database.py (risque de connexions TCP mortes)",
            "severity": "CRITIQUE"
        })
    if "pool_reset_on_return" not in content:
        VIOLATIONS.append({
            "file": str(filepath),
            "line": 1,
            "rule": "Hardening Mémoire §3.7 (Axe 3)",
            "detail": "pool_reset_on_return ABSENT dans shared/database.py (risque de transactions orphelines)",
            "severity": "CRITIQUE"
        })


def check_state_machines(filepath: Path, lines: list):
    """S'assure que les state machines passent par shared.redis_state."""
    if not (filepath.name.endswith("task_state.py") or filepath.name.endswith("bulk_task_state.py")):
        return
    content = "".join(lines)
    if "get_state_redis_client" not in content:
        VIOLATIONS.append({
            "file": str(filepath),
            "line": 1,
            "rule": "Hardening Mémoire §3.7 (Axe 4)",
            "detail": "Tâche asynchrone / State Machine sans get_state_redis_client()",
            "severity": "MAJEUR"
        })


def check_http_timeouts(filepath: Path, lines: list):
    """Vérifie que les requêtes httpx ont un timeout explicite.

    Un timeout est considéré valide si :
      1. Il est présent dans l'appel direct (block multiline), OU
      2. Un httpx.AsyncClient(timeout=...) parent est déclaré dans les 30 lignes précédentes.
    """
    if "tests" in filepath.parts:
        return
    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or "noqa" in line:
            continue
        if "client." not in line or not any(verb in line for verb in [".get(", ".post(", ".put(", ".delete("]):
            continue
        # Exclure les appels Gemini SDK (client.aio.*) — pas des appels httpx
        if "client.aio." in line:
            continue

        # 1. Scan the call block (multiline) for inline timeout
        block_lines = []
        paren_count = 0
        started = False
        for j in range(idx - 1, len(lines)):
            line_text = lines[j]
            block_lines.append(line_text)
            if not started:
                for verb in [".get(", ".post(", ".put(", ".delete("]:
                    pos = line_text.find(verb)
                    if pos != -1:
                        paren_count += 1
                        started = True
                        for char in line_text[pos + len(verb):]:
                            if char == '(':
                                paren_count += 1
                            elif char == ')':
                                paren_count -= 1
                        break
            else:
                for char in line_text:
                    if char == '(':
                        paren_count += 1
                    elif char == ')':
                        paren_count -= 1
            if started and paren_count <= 0:
                break

        block_text = "".join(block_lines)
        if "timeout" in block_text or "noqa" in block_text:
            continue

        # 2. Scan backward (up to 30 lines) for a parent AsyncClient with timeout
        context_start = max(0, idx - 30)
        context_block = "\n".join(lines[context_start:idx - 1])
        if "AsyncClient(" in context_block and "timeout" in context_block:
            continue

        VIOLATIONS.append({
            "file": str(filepath),
            "line": idx,
            "rule": "Résilience §3.4",
            "detail": f"Appel HTTP sans timeout explicite : '{stripped}'",
            "severity": "CRITIQUE"
        })


def check_swallowed_exceptions(filepath: Path, lines: list):
    """Détecte les exceptions interceptées puis passées sous silence."""
    for idx, line in enumerate(lines, 1):
        if "except Exception" in line or "except" in line and "Exception" in line:
            # Vérifier si la ligne suivante contient "pass"
            if idx < len(lines):
                next_line = lines[idx].strip()
                if next_line == "pass":
                    VIOLATIONS.append({
                        "file": str(filepath),
                        "line": idx,
                        "rule": "Failfast §1.10",
                        "detail": "Swallow silencieux d'exception détecté ('pass' dans except)",
                        "severity": "MAJEUR"
                    })


def check_global_semaphores(filepath: Path, lines: list):
    """Valide l'utilisation de acquire_shielded() pour les sémaphores globaux."""
    if "tests" in filepath.parts:
        return
    content = "".join(lines)
    # Chercher les sémaphores déclarés au niveau du module (ex: _ENDPOINT_SEM)
    module_semaphores = re.findall(r"^(_[A-Za-z0-9_]*[Ss][Ee][Mm])\s*:", content, re.MULTILINE)
    module_semaphores += re.findall(r"^(_[A-Za-z0-9_]*[Ss][Ee][Mm])\s*=", content, re.MULTILINE)

    if not module_semaphores:
        return

    for idx, line in enumerate(lines, 1):
        for sem in module_semaphores:
            if f"async with {sem}" in line and "acquire_shielded" not in line:
                VIOLATIONS.append({
                    "file": str(filepath),
                    "line": idx,
                    "rule": "Hardening Mémoire §3.7 (Axe 1)",
                    "detail": f"Sémaphore global '{sem}' acquis sans acquire_shielded() (risque de deadlock)",
                    "severity": "CRITIQUE"
                })


def audit_file(filepath: Path):
    """Lance toutes les vérifications d'audit sur un fichier."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return
    lines = content.splitlines()

    check_local_imports(filepath, lines)
    check_cors_security(filepath, lines)
    check_service_version(filepath, lines)
    check_redis_clients(filepath, lines)
    check_sqlalchemy_pool(filepath, lines)
    check_state_machines(filepath, lines)
    check_http_timeouts(filepath, lines)
    check_swallowed_exceptions(filepath, lines)
    check_global_semaphores(filepath, lines)


def is_excluded_path(path: Path) -> bool:
    """Détermine si le chemin doit être exclu de l'analyse (venv, packages tiers, etc.)."""
    for part in path.parts:
        part_lower = part.lower()
        if part_lower.startswith("."):
            # Exclure les dossiers cachés sauf .agents
            if part_lower != ".agents":
                return True
        if "venv" in part_lower:
            return True
        if part_lower in ["build", "dist", "lib", "site-packages", "node_modules", "egg-info"]:
            return True
    return False


def fix_file(filepath: Path):
    """Corrige automatiquement les imports locaux et injecte les timeouts sur un fichier."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return

    lines = content.splitlines()
    modified = False

    # 1. Correction des imports locaux (E402) - Uniquement hors tests et __init__.py
    if filepath.name != "__init__.py" and "tests" not in filepath.parts:
        local_imports = []
        new_lines = []
        for line in lines:
            stripped = line.strip()
            # On cherche les imports locaux indentés
            if re.match(r"^ {4,}(from|import) ", line) and not stripped.startswith("#"):
                local_imports.append(line.lstrip())
                modified = True
            else:
                new_lines.append(line)

        if local_imports:
            # Dédoublonner les imports en préservant l'ordre
            unique_imports = []
            for imp in local_imports:
                if imp not in unique_imports:
                    unique_imports.append(imp)

            # Trouver l'endroit où insérer les nouveaux imports au niveau top-level
            last_import_idx = -1
            for idx, line in enumerate(new_lines):
                if re.match(r"^(import|from)\s", line):
                    last_import_idx = idx

            if last_import_idx != -1:
                # Insérer après le dernier import top-level
                new_lines[last_import_idx+1:last_import_idx+1] = unique_imports
            else:
                # Insérer au tout début, après le docstring de module s'il existe
                insert_idx = 0
                if new_lines and (new_lines[0].startswith('"""') or new_lines[0].startswith("'''")):
                    for idx, line in enumerate(new_lines):
                        if idx > 0 and (line.endswith('"""') or line.endswith("'''")):
                            insert_idx = idx + 1
                            break
                new_lines[insert_idx:insert_idx] = unique_imports

            lines = new_lines

    # 2. Injection des timeouts sur les requêtes HTTP sans timeout
    if "tests" not in filepath.parts:
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#") or "noqa" in line:
                new_lines.append(line)
                continue

            if "client." in line and any(verb in line for verb in [".get(", ".post(", ".put(", ".delete("]):
                if "timeout" not in line:
                    # Regex générale : match toute variable *_client ou client
                    match = re.search(r"(\w*client)\.(get|post|put|delete)\(", line)
                    if match:
                        client_var = match.group(1)
                        verb = match.group(2)
                        call_prefix = f"{client_var}.{verb}("
                        # Compter les parenthèses pour trouver la fin de l'appel
                        paren_count = 1
                        start_idx = line.find(call_prefix) + len(call_prefix)
                        j = start_idx
                        while j < len(line) and paren_count > 0:
                            if line[j] == '(':
                                paren_count += 1
                            elif line[j] == ')':
                                paren_count -= 1
                            j += 1

                        if paren_count == 0:
                            close_idx = j - 1
                            timeout_val = "10.0"
                            if "call_tool" in line:
                                timeout_val = "30.0"

                            # Si les parenthèses sont vides, pas de virgule
                            inner_content = line[start_idx:close_idx].strip()
                            if inner_content:
                                line = line[:close_idx] + f", timeout={timeout_val}" + line[close_idx:]
                            else:
                                line = line[:close_idx] + f"timeout={timeout_val}" + line[close_idx:]
                            modified = True
            new_lines.append(line)
        lines = new_lines

    if modified:
        try:
            filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"  🔧 Corrigé : {filepath}")
        except Exception as e:
            print(f"  ❌ Erreur lors de l'écriture de {filepath} : {e}")


def run_audit(fix: bool = False) -> bool:
    """Parcourt l'arborescence et exécute l'audit (ou la correction)."""
    if fix:
        print("====== AUTO-CORRECTION ARCHITECTURALE PYTHON ======")
    else:
        print("====== AUDIT DE CONFORMITÉ ARCHITECTURALE PYTHON ======")

    base_dir = Path(os.getcwd())

    for svc in SERVICES:
        svc_dir = base_dir / svc
        if not svc_dir.is_dir():
            continue

        if fix:
            print(f"  🔧 Correction du service : {svc}...")
            for py_file in svc_dir.rglob("*.py"):
                if is_excluded_path(py_file):
                    continue
                fix_file(py_file)
        else:
            print(f"  🔍 Audit du service : {svc}...")
            for py_file in svc_dir.rglob("*.py"):
                if is_excluded_path(py_file):
                    continue
                audit_file(py_file)

    if fix:
        print("\n🎉 Auto-correction terminée !")
        return True

    print("\n====== RÉSULTATS DE L'AUDIT ARCHITECTURALE ======")
    if VIOLATIONS:
        print(f"❌ ÉCHEC : {len(VIOLATIONS)} violation(s) identifiée(s).\n")
        # Trier par sévérité (CRITIQUE d'abord)
        VIOLATIONS.sort(key=lambda x: x["severity"] == "CRITIQUE", reverse=True)

        for v in VIOLATIONS:
            icon = "🔴" if v["severity"] == "CRITIQUE" else "🟠"
            print(f"{icon} [{v['severity']}] {v['file']}:{v['line']} -> {v['rule']}")
            print(f"     Détail : {v['detail']}\n")
        return False

    print("🎉 SUCCÈS : Le codebase Python respecte 100% des Golden Rules !")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit et correction de conformité.")
    parser.add_argument("--fix", action="store_true", help="Corriger automatiquement les violations statiques")
    args = parser.parse_args()

    success = run_audit(fix=args.fix)
    sys.exit(0 if success else 1)
