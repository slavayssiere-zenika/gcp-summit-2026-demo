#!/usr/bin/env python3
"""Script d'audit de conformité statique pour le frontend Vue.js.

Ce script vérifie le respect des Golden Rules spécifiques au frontend, notamment
la gestion sécurisée des dépendances npm (package.json) et la validation des
contrats d'API paginées via parsePaginated().
"""

import json
import os
import sys
from pathlib import Path

FRONTEND_DEPENDENCIES = ["vue", "vite", "vitest", "pinia", "vue-router"]
VIOLATIONS = []


def audit_npm_packages(frontend_path: Path):
    """Vérifie que les paquets clés dans package.json ne sont pas inutilement figés."""
    pkg_json_path = frontend_path / "package.json"
    if not pkg_json_path.exists():
        print("  ⚠️ package.json du frontend INTROUVABLE")
        return

    try:
        data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
    except Exception as e:
        VIOLATIONS.append({
            "file": "frontend/package.json",
            "line": 0,
            "rule": "Frontend §7 (npm)",
            "detail": f"Erreur lors du parsing de package.json : {e}",
            "severity": "CRITIQUE"
        })
        return

    dependencies = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

    for pkg in FRONTEND_DEPENDENCIES:
        if pkg in dependencies:
            version = dependencies[pkg]
            # Les Golden Rules imposent d'utiliser le caret ^ ou le tilde ~ pour les dépendances
            if not (version.startswith("^") or version.startswith("~")):
                VIOLATIONS.append({
                    "file": "frontend/package.json",
                    "line": 0,
                    "rule": "Frontend §7 (npm)",
                    "detail": (
                        f"La dépendance '{pkg}' est bloquée sur une version exacte '{version}'. "
                        f"Utiliser '^' (ex: '^{version}') pour bénéficier des patchs de sécurité."
                    ),
                    "severity": "MAJEUR"
                })


def audit_api_contract(filepath: Path):
    """S'assure que les appels paginés utilisent parsePaginated()."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return

    lines = content.splitlines()

    # Détection simplifiée : si le fichier fait référence à des structures paginées
    # (ex: total, skip, limit, items) mais n'importe ni n'utilise parsePaginated.
    if any(keyword in content for keyword in ["skip", "limit", "total"]) and "parsePaginated" not in content:
        # Analyser si le fichier fait un appel HTTP (fetch ou axios ou api)
        if any(call in content for call in ["fetch(", "axios.get(", "api.get(", "client.get("]):
            # Trouver la ligne contenant l'appel
            for idx, line in enumerate(lines, 1):
                if any(call in line for call in ["fetch", "axios", "api.", "client."]):
                    VIOLATIONS.append({
                        "file": str(filepath),
                        "line": idx,
                        "rule": "Frontend §7 (Contrats d'interface)",
                        "detail": (
                            "Appel d'API potentiellement paginé détecté sans validation via parsePaginated(). "
                            "Le non-respect de ce contrat d'interface inter-services rompt la résilience."
                        ),
                        "severity": "MAJEUR"
                    })


def audit_localhost_endpoints(filepath: Path):
    """Vérifie l'absence d'URL d'API vers localhost en dur dans le code de production."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return

    lines = content.splitlines()

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            continue
        if "http://localhost:" in line and "import.meta.env" not in line and "process.env" not in line:
            VIOLATIONS.append({
                "file": str(filepath),
                "line": idx,
                "rule": "Configuration API §3.1",
                "detail": f"URL d'API localhost codée en dur : '{stripped}' (utiliser des variables d'environnement)",
                "severity": "CRITIQUE"
            })


def run_audit() -> bool:
    """Exécute l'audit global du frontend."""
    print("====== AUDIT DE CONFORMITÉ FRONTEND VUE.JS ======")
    base_dir = Path(os.getcwd())
    frontend_path = base_dir / "frontend"

    if not frontend_path.is_dir():
        print("  ⚠️ Dossier frontend INTROUVABLE à la racine.")
        return True

    # 1. Vérification package.json
    print("  🔍 Audit de package.json...")
    audit_npm_packages(frontend_path)

    # 2. Analyse statique des sources
    print("  🔍 Analyse statique du code source frontend...")
    for src_file in (frontend_path / "src").rglob("*"):
        if src_file.is_file() and src_file.suffix in [".vue", ".ts", ".js"]:
            audit_api_contract(src_file)
            audit_localhost_endpoints(src_file)

    print("\n====== RÉSULTATS DE L'AUDIT FRONTEND ======")
    if VIOLATIONS:
        print(f"❌ ÉCHEC : {len(VIOLATIONS)} violation(s) identifiée(s).\n")
        # Trier par sévérité (CRITIQUE d'abord)
        VIOLATIONS.sort(key=lambda x: x["severity"] == "CRITIQUE", reverse=True)

        for v in VIOLATIONS:
            icon = "🔴" if v["severity"] == "CRITIQUE" else "🟠"
            print(f"{icon} [{v['severity']}] {v['file']}:{v['line']} -> {v['rule']}")
            print(f"     Détail : {v['detail']}\n")
        return False

    print("🎉 SUCCÈS : Le frontend Vue.js respecte 100% des Golden Rules !")
    return True


if __name__ == "__main__":
    success = run_audit()
    sys.exit(0 if success else 1)
