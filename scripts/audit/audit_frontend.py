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


# Endpoints connus comme non-paginés (retournent des objets métier scalaires, pas des listes)
# Ces chemins d'URL sont exclus de la vérification parsePaginated()
NON_PAGINATED_ENDPOINTS = {
    "/bulk-reanalyse/data-quality",
    "/data-quality",
    "/health",
    "/version",
    "/ready",
    "/stats",
    "/summary",
    "/me",
    "/finops",
}


def audit_api_contract(filepath: Path):
    """S'assure que les appels paginés utilisent parsePaginated().

    Un appel est considéré paginement UNIQUEMENT si le fichier contient
    simultanément les mots-clés 'items' ET ('skip' OU 'limit') dans un
    contexte de liste. Les réponses métier scalaires (data-quality, stats,
    etc.) sont explicitement exclues.
    """
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return

    lines = content.splitlines()

    # Un appel est paginné seulement si le fichier manipule explicitement
    # des structures paginées (items + pagination params)
    has_pagination_structure = (
        "items" in content
        and any(kw in content for kw in ["skip", "limit", "page"])
        and "total" in content
    )

    if not has_pagination_structure:
        return  # Pas de structure paginée dans ce fichier — pas de violation

    if "parsePaginated" in content:
        return  # Contrat déjà respecté

    # Vérifier que les appels HTTP ne ciblent pas exclusivement des endpoints non-paginés
    for idx, line in enumerate(lines, 1):
        if not any(call in line for call in ["fetch(", "axios.get(", "api.get(", "client.get("]):
            continue

        # Exclure les lignes ciblant des endpoints non-paginés connus
        if any(ep in line for ep in NON_PAGINATED_ENDPOINTS):
            continue

        # Exclure les commentaires
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue

        VIOLATIONS.append({
            "file": str(filepath),
            "line": idx,
            "rule": "Frontend §7 (Contrats d'interface)",
            "detail": (
                "Appel d'API retournant une liste paginée sans validation via parsePaginated(). "
                "Utiliser parsePaginated<T>(response) de @/utils/apiContract.ts."
            ),
            "severity": "MAJEUR"
        })
        break  # Une seule violation par fichier pour éviter le bruit


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
