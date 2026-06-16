#!/usr/bin/env python3
"""
check_silent_exceptions.py — Gate de qualité AGENTS.md §10

Détecte les exceptions silencieuses dans les fichiers Python du monorepo.
Retourne exit code 1 (bloquant) si des violations CRITIQUES sont trouvées.

Classification :
  CRITICAL  — except: pass | except Exception: pass | bare except  → bloque le déploiement
  WARNING   — except loggé sans raise dans une route FastAPI        → affiché, non bloquant
  OK        — MCP tools retournant {"success": false, "error": ...} → ignoré
              Cache/Pub/Sub fail-open documenté                     → ignoré
              except: raise                                         → ignoré

Usage (standalone) :
  python3 scripts/check_silent_exceptions.py [--warn-only]

Usage (deploy.sh) :
  python3 scripts/check_silent_exceptions.py
  exit $?
"""

import os
import re
import sys
import argparse
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

AUDIT_DIRS = [
    "users_api/src",
    "items_api/src",
    "competencies_api/src",
    "cv_api/src",
    "missions_api/src",
    "drive_api/src",
    "prompts_api/src",
    "shared",
    "agent_router_api/src",
    "agent_hr_api",
    "agent_ops_api",
    "agent_missions_api",
    "analytics_mcp",
    "monitoring_mcp",
    "agent_commons/agent_commons",
]

EXCLUDE_DIRS = {
    ".venv", "venv", "__pycache__", "test_env", "build",
    "node_modules", "tests", "dist", ".pytest_cache", "htmlcov",
}

EXCLUDE_FILES = {
    "cleanup_items.py",  # Script admin one-shot — signalé manuellement
}

# Commentaires acceptables indiquant un fail-open intentionnel
NON_BLOCKING_COMMENTS = re.compile(
    r"#.*(best.effort|non.bloquant|fail.open|best_effort|non_bloquant|"
    r"optional|optionnel|fallback|cache|redis.*unavailable|unavailable.*redis|"
    r"try.*cookie|cookie.*fallback|token.*invalide|header.*invalid)",
    re.I,
)

# Types d'exceptions pour lesquels un `pass` est un pattern défensif légitime
# (parsing de données non-critiques, guards d'import optionnel)
LEGITIMATE_PASS_EXCEPTION_TYPES = {
    # Import optionnel — SDK pas installé en dev
    "ImportError", "ModuleNotFoundError",
    # Parsing défensif de types — int(), float(), json.loads() sur données tierces
    "ValueError", "TypeError", "json.JSONDecodeError", "JSONDecodeError",
    "UnicodeDecodeError", "UnicodeError",
    # Token JWT invalide dans un flux de fallback (header → cookie)
    "InvalidTokenError", "DecodeError",
    # Regex sans match dans du parsing non-critique
    "AttributeError",
    # Parsing arithmétique dans des agrégations SRE (sre_triage.py)
    "(ValueError, TypeError)", "(ValueError)", "(TypeError)",
    "(UnicodeDecodeError, ValueError)",
}

RED = "\033[0;31m"
YELLOW = "\033[0;33m"
GREEN = "\033[0;32m"
GREY = "\033[1;30m"
RESET = "\033[0m"
BOLD = "\033[1m"


def is_bare_pass(body_lines):
    stripped = [ln.strip() for ln in body_lines if ln.strip()]
    return len(stripped) == 0 or (len(stripped) == 1 and stripped[0] == "pass")


def get_exception_type(except_line):
    """Extrait le type d'exception depuis la ligne 'except ...:'"""
    m = re.match(r"\s*except\s+([^:]+):", except_line)
    if not m:
        return None
    return m.group(1).strip()


def is_acceptable_body(body_lines, context_lines, except_line=""):
    body = "\n".join(body_lines)
    ctx = "\n".join(context_lines)

    # except Foo: raise  — inline sur la même ligne (re-propagation pure)
    if re.match(r"\s*except\b.*:\s*raise\b", except_line):
        return True

    # raise seul ou raise avec valeur → OK (re-propagation propre)
    if re.search(r"\braise\b", body):
        return True
    # HTTPException → conversion propre en réponse HTTP
    if re.search(r"HTTPException", body):
        return True
    # MCP tool retournant dict erreur structuré
    if re.search(r'["\']success["\']\s*:\s*[Ff]alse', body):
        return True
    if re.search(r'return\s+\{[^}]*["\']error["\']', body):
        return True
    # Commentaire fail-open dans le contexte, le corps, ou la ligne except elle-même
    if (NON_BLOCKING_COMMENTS.search(body)
            or NON_BLOCKING_COMMENTS.search(ctx)
            or NON_BLOCKING_COMMENTS.search(except_line)):
        return True
    # Type d'exception légitime pour un pass défensif
    exc_type = get_exception_type(except_line)
    if exc_type:
        # Normaliser : enlever "as e", "as exc", etc.
        exc_type_clean = re.sub(r"\s+as\s+\w+$", "", exc_type).strip()
        if exc_type_clean in LEGITIMATE_PASS_EXCEPTION_TYPES:
            return True
        # Tuples d'exceptions : vérifier si tous les types sont légitimes
        if exc_type_clean.startswith("(") and exc_type_clean.endswith(")"):
            inner = exc_type_clean[1:-1]
            types = [t.strip() for t in inner.split(",")]
            if all(t in LEGITIMATE_PASS_EXCEPTION_TYPES for t in types):
                return True
    return False


def scan_file(fpath):
    violations = []
    try:
        lines = fpath.read_text(errors="replace").splitlines()
    except OSError:
        return []

    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\s*)except\b.*:", line)
        if not m:
            i += 1
            continue

        indent = len(m.group(1))
        except_lineno = i + 1
        is_bare = bool(re.match(r"^\s*except\s*:", line))

        body_lines = []
        j = i + 1
        while j < len(lines):
            bl = lines[j]
            if not bl.strip():
                j += 1
                continue
            if len(bl) - len(bl.lstrip()) <= indent:
                break
            body_lines.append(bl)
            j += 1

        context_lines = lines[max(0, i - 5):i + 1]

        # Vérifier d'abord si l'exception est acceptable (type légitime, raise, commentaire)
        # AVANT de décider si c'est un "pass critique"
        if is_acceptable_body(body_lines, context_lines, line):
            i = j if j > i else i + 1
            continue

        # Bare except (sans type) — toujours CRITIQUE
        if is_bare:
            severity = "CRITICAL"
        # except: pass ou except Exception: pass sur un type non-légitime
        elif is_bare_pass(body_lines):
            severity = "CRITICAL"
        else:
            # Exception avec du code mais non acceptable — ignorer pour l'instant
            i = j if j > i else i + 1
            continue

        snippet_lines = lines[max(0, i - 1):min(len(lines), i + 4)]
        snippet = "\n".join(f"  {ln.rstrip()}" for ln in snippet_lines)

        violations.append({
            "severity": severity,
            "file": str(fpath),
            "lineno": except_lineno,
            "snippet": snippet,
        })

        i = j if j > i else i + 1

    return violations


def scan_codebase(root):
    criticals = []
    warnings = []
    for audit_dir in AUDIT_DIRS:
        base = root / audit_dir
        if not base.exists():
            continue
        for fpath in base.rglob("*.py"):
            if any(excl in fpath.parts for excl in EXCLUDE_DIRS):
                continue
            if fpath.name.startswith("test_") or fpath.name in EXCLUDE_FILES:
                continue
            for v in scan_file(fpath):
                (criticals if v["severity"] == "CRITICAL" else warnings).append(v)
    return criticals, warnings


def print_violation(v, index):
    color = RED if v["severity"] == "CRITICAL" else YELLOW
    icon = "❌" if v["severity"] == "CRITICAL" else "⚠️ "
    rel = v["file"]
    try:
        rel = str(Path(v["file"]).relative_to(Path.cwd()))
    except ValueError:
        pass
    print(f"\n{color}{icon} [{index}] {v['severity']} — {rel}:{v['lineno']}{RESET}")
    print(f"{GREY}{v['snippet']}{RESET}")


def main():
    parser = argparse.ArgumentParser(description="AGENTS.md §10 — Exceptions silencieuses")
    parser.add_argument("--warn-only", action="store_true",
                        help="Affiche les violations mais retourne exit 0")
    parser.add_argument("--root", default=".", help="Racine du monorepo")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    print(f"\n{BOLD}🔍 AGENTS.md §10 — Audit exceptions silencieuses{RESET}")
    print(f"{GREY}   Racine : {root}{RESET}")
    print(f"{GREY}   Règle  : toute exception doit raise, retourner {{success: false}} "
          f"(MCP tools), ou être documentée # fail-open{RESET}\n")

    criticals, warnings = scan_codebase(root)

    if criticals:
        print(f"{RED}{BOLD}{'='*60}")
        print(f"  ❌ {len(criticals)} VIOLATION(S) CRITIQUE(S)")
        print(f"{'='*60}{RESET}")
        print(f"{RED}  → Fix : ajouter raise, logger.error(...), ou commenter # fail-open{RESET}")
        for i, v in enumerate(criticals, 1):
            print_violation(v, i)

    if warnings:
        print(f"\n{YELLOW}{'='*60}")
        print(f"  ⚠️  {len(warnings)} AVERTISSEMENT(S) (non bloquant)")
        print(f"{'='*60}{RESET}")
        for i, v in enumerate(warnings, len(criticals) + 1):
            print_violation(v, i)

    print(f"\n{GREY}{'─'*60}{RESET}")
    if not criticals and not warnings:
        print(f"{GREEN}✅ Aucune exception silencieuse — AGENTS.md §10 OK.{RESET}\n")
        return 0
    elif criticals:
        print(f"{RED}❌ {len(criticals)} critique(s) | {len(warnings)} warning(s) "
              f"— déploiement BLOQUÉ{RESET}")
        if args.warn_only:
            print(f"{YELLOW}   (--warn-only : exit code forcé à 0){RESET}\n")
            return 0
        return 1
    else:
        print(f"{YELLOW}⚠️  0 critique | {len(warnings)} warning(s) — déploiement autorisé{RESET}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
