#!/usr/bin/env python3
"""
scripts/test_local.py — Runner de tests locaux sans Docker.

Installe le module `shared` en mode editable (pip install -e),
puis exécute pytest sur chaque service sélectionné.

Usage :
    python3 scripts/test_local.py                    # Tous les services
    python3 scripts/test_local.py users_api cv_api   # Services spécifiques
    python3 scripts/test_local.py --list             # Lister les services disponibles
    python3 scripts/test_local.py --install-only     # Installer shared sans lancer les tests

Prérequis :
    - Python 3.11+
    - Un virtualenv activé (recommandé) ou pip accessible

Variables d'environnement injectées automatiquement :
    SECRET_KEY    : Clé JWT factice (>= 32 chars) pour les tests locaux
    REDIS_URL     : URL Redis factice (remplacée par fakeredis dans les conftest)
    GOOGLE_API_KEY: Clé API factice
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent

ALL_SERVICES = [
    "agent_router_api",
    "agent_hr_api",
    "agent_ops_api",
    "agent_missions_api",
    "agent_commons",
    "cv_api",
    "missions_api",
    # Les services suivants nécessitent `shared` installé (pip install -e ./shared)
    "users_api",
    "items_api",
    "competencies_api",
    "drive_api",
    "prompts_api",
    "analytics_mcp",
    "monitoring_mcp",
]

# Variables d'environnement minimales pour les tests locaux
TEST_ENV = {
    **os.environ,
    "SECRET_KEY": os.environ.get(
        "SECRET_KEY", "local-test-secret-key-minimum-32-chars-long"
    ),
    "REDIS_URL": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    "GOOGLE_API_KEY": os.environ.get("GOOGLE_API_KEY", "test-key-local"),
    "GEMINI_MODEL": os.environ.get("GEMINI_MODEL", "gemini-test"),
    "GEMINI_ROUTER_MODEL": os.environ.get("GEMINI_ROUTER_MODEL", "gemini-test"),
    "SEMANTIC_CACHE_ENABLED": "false",
    "PYTHONDONTWRITEBYTECODE": "1",
}


# ── Fonctions utilitaires ──────────────────────────────────────────────────────

def run(cmd: list, cwd: Path = BASE_DIR, check: bool = True) -> subprocess.CompletedProcess:
    """Exécute une commande shell et retourne le résultat."""
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, cwd=cwd, env=TEST_ENV, check=check)


def install_shared() -> bool:
    """Installe le module `shared` en mode editable."""
    shared_dir = BASE_DIR / "shared"
    if not shared_dir.is_dir():
        print("  ⚠️  Dossier shared/ introuvable — skip installation.")
        return False

    print("\n📦 Installation de shared/ en mode editable...")
    try:
        run([sys.executable, "-m", "pip", "install", "-e", str(shared_dir), "--quiet"])
        print("  ✅ shared installé.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Erreur lors de l'installation de shared : {e}")
        return False


def run_tests(service: str) -> tuple[str, bool, str]:
    """Lance pytest pour un service donné.

    Returns:
        (service_name, success, summary_line)
    """
    svc_dir = BASE_DIR / service
    tests_dir = svc_dir / "tests"

    if not svc_dir.is_dir():
        return service, False, "⚠️ Dossier service introuvable"
    if not tests_dir.is_dir():
        return service, False, "⚠️ Pas de dossier tests/"

    print(f"\n{'=' * 60}")
    print(f"🧪 Tests : {service}")
    print(f"{'=' * 60}")

    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "tests/",
                "-v",
                "--tb=short",
                "--no-header",
                "-q",
            ],
            cwd=svc_dir,
            env=TEST_ENV,
            capture_output=False,
            check=False,
        )
        success = result.returncode == 0
        status = "✅ PASS" if success else f"❌ FAIL (exit={result.returncode})"
        return service, success, status
    except Exception as e:
        return service, False, f"❌ Erreur : {e}"


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Runner de tests locaux — installe shared puis lance pytest.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "services",
        nargs="*",
        help="Services à tester (défaut : tous)",
        metavar="SERVICE"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="Lister les services disponibles"
    )
    parser.add_argument(
        "--install-only",
        action="store_true",
        help="Installer shared sans lancer les tests"
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Ne pas réinstaller shared (si déjà installé)"
    )
    args = parser.parse_args()

    if args.list:
        print("Services disponibles :")
        for svc in ALL_SERVICES:
            svc_dir = BASE_DIR / svc
            has_tests = (svc_dir / "tests").is_dir()
            icon = "✅" if has_tests else "⚠️ "
            print(f"  {icon} {svc}")
        return 0

    # Installation de shared
    if not args.skip_install:
        install_shared()

    if args.install_only:
        print("\n✅ Installation terminée. Tests non lancés (--install-only).")
        return 0

    # Sélection des services
    services_to_test = args.services if args.services else ALL_SERVICES
    unknown = [s for s in services_to_test if s not in ALL_SERVICES]
    if unknown:
        print(f"⚠️  Services inconnus ignorés : {unknown}")
        services_to_test = [s for s in services_to_test if s in ALL_SERVICES]

    if not services_to_test:
        print("❌ Aucun service valide à tester.")
        return 1

    # Exécution des tests
    results = []
    for svc in services_to_test:
        service, success, summary = run_tests(svc)
        results.append((service, success, summary))

    # Rapport final
    print(f"\n{'=' * 60}")
    print("📊 RAPPORT FINAL")
    print(f"{'=' * 60}")
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed

    for service, success, summary in results:
        print(f"  {summary:<12} {service}")

    print(f"\n  Résultat : {passed}/{len(results)} services passent les tests")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
