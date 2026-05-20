#!/usr/bin/env python3
"""Script d'audit des dépendances Python pour l'écosystème Zenika Console Agent.

Ce script vérifie la conformité des dépendances de chaque microservice par rapport
aux règles de sécurité et d'architecture définies dans AGENTS.md.
Il supporte un mode résilient offline en cas d'inaccessibilité de PyPI.
"""

import json
import os
import re
import ssl
import sys
import urllib.request
from pathlib import Path

SERVICES = [
    "agent_hr_api", "agent_ops_api", "agent_missions_api", "agent_router_api",
    "analytics_mcp", "monitoring_mcp", "competencies_api", "cv_api",
    "missions_api", "drive_api", "items_api", "users_api", "prompts_api"
]

KEY_PACKAGES = [
    "fastapi", "uvicorn", "google-adk", "google-genai", "mcp",
    "opentelemetry-api", "pydantic", "httpx", "redis", "sqlalchemy",
    "PyJWT", "bcrypt", "tenacity", "prometheus-fastapi-instrumentator",
    "google-cloud-pubsub", "google-cloud-storage", "google-cloud-alloydb-connector",
    "google-auth", "langchain-text-splitters", "json-repair", "grpcio",
    "testcontainers", "fakeredis", "pgvector", "python-docx"
]

# Dépendances interdites ou à contraindre fortement
FORBIDDEN = {
    "python-jose": "❌ INTERDIT — migré vers PyJWT>=2.12.0 (CVE-2022-29217)",
    "jose": "❌ INTERDIT — alias python-jose, utiliser PyJWT",
    "pyjwt<2.8": "❌ INTERDIT — vulnérabilité decode options (PyJWT<2.8)",
    "litellm": "⚠️ À contraindre — version non pinned = risque breaking change"
}

# Règles spécifiques à vérifier dans requirements.txt
RULES = [
    ("PyJWT", ">=2.12.0", "Version minimale requise pour corriger la vulnérabilité de signature"),
    ("uvicorn", ">=0.47.0", "Requis pour la gestion propre du SIGTERM sous Cloud Run"),
    ("google-genai", ">=2.0.0", "API unifiée genai.Client() et context caching requis (>=1.x interdit)"),
    ("pydantic", ">=2.13.0", "Harmonisation des performances de sérialisation et model_rebuild()"),
    ("prometheus-fastapi-instrumentator", ">=7.0.0", "Stabilité de l'instrumentation Prometheus sous charge")
]


def fetch_pypi_latest(pkg: str) -> str:
    """Interroge PyPI pour récupérer la dernière version stable d'un package."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = f"https://pypi.org/pypi/{pkg}/json"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AntigravityAudit/1.0"})
        with urllib.request.urlopen(req, timeout=3, context=ctx) as response:
            data = json.loads(response.read().decode())
            return data["info"]["version"]
    except Exception:
        return "N/A"


def parse_requirements(filepath: Path) -> dict:
    """Parse un fichier requirements.txt et extrait les packages et leurs contraintes."""
    dependencies = {}
    if not filepath.exists():
        return dependencies

    for line in filepath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Recherche du nom du package et de ses contraintes
        match = re.match(r"^([a-zA-Z0-9_\-\[\]]+)(.*)$", line)
        if match:
            pkg_name = match.group(1).lower().replace("_", "-")
            dependencies[pkg_name] = {
                "raw": line,
                "constraint": match.group(2).strip()
            }
    return dependencies


def audit_context_caching(base_dir: Path) -> list:
    """Vérifie la présence et le bon adressage du context caching Gemini."""
    caching_violations = []

    # Fichiers de cache attendus
    expected_caches = {
        "competencies_api": base_dir / "competencies_api/src/competencies/gemini_cache.py",
        "cv_api": base_dir / "cv_api/src/gemini_cache.py"
    }

    for service, path in expected_caches.items():
        if not path.exists():
            caching_violations.append(
                f"❌ {service} : gemini_cache.py ABSENT (perte potentielle de -30% à -50% FinOps sur Gemini)"
            )
    return caching_violations


def run_audit() -> bool:
    """Exécute l'audit global des dépendances microservices."""
    print("====== AUDIT DES DÉPENDANCES PYTHON ======")
    base_dir = Path(os.getcwd())

    # 1. Récupération des dernières versions PyPI (avec gestion offline)
    print("\n[1/5] Connexion à PyPI (validation du statut online)...")
    pypi_versions = {}
    is_offline = False

    # Test de connectivité sur un package clé
    if fetch_pypi_latest("fastapi") == "N/A":
        is_offline = True
        print("  ⚠️ Mode OFFLINE activé : PyPI injoignable ou pas de connexion réseau.")
        print("  -> L'audit se concentrera sur la cohérence interne et la sécurité statique.")
    else:
        print("  ✅ Connectivité PyPI établie. Récupération des dernières versions...")
        for pkg in KEY_PACKAGES:
            pypi_versions[pkg] = fetch_pypi_latest(pkg)

    # 2. Analyse des requirements.txt par service
    print("\n[2/5] Analyse des requirements.txt par service...")
    violations = []
    service_dependencies = {}

    for svc in SERVICES:
        req_path = base_dir / svc / "requirements.txt"
        if not req_path.exists():
            print(f"  ⚠️  {svc} : requirements.txt ABSENT")
            continue

        deps = parse_requirements(req_path)
        service_dependencies[svc] = deps
        svc_violations = []

        for pkg_name, dep_info in deps.items():
            raw_line = dep_info["raw"]

            # A. Détection des packages interdits
            for forbidden_pkg, msg in FORBIDDEN.items():
                if forbidden_pkg.lower() in pkg_name:
                    # Cas particulier : vérifier si pyjwt respecte la contrainte minimale
                    if forbidden_pkg == "pyjwt<2.8" and pkg_name == "pyjwt":
                        constraint = dep_info["constraint"]
                        if any(c in constraint for c in ["<2.8", "<=2.7", "==2.7"]):
                            svc_violations.append(f"   {msg} [{raw_line}]")
                    elif forbidden_pkg == "litellm":
                        constraint = dep_info["constraint"]
                        if "==" not in constraint:
                            svc_violations.append(f"   {msg} [{raw_line}]")
                    else:
                        svc_violations.append(f"   {msg} [{raw_line}]")

            # B. Détection de version exactement épinglée (interdit en prod, préférer >=)
            if "==" in dep_info["constraint"] and "test" not in svc:
                # Tolérer litellm si exigé, mais signaler si d'autres packages sont trop strictement figés
                if pkg_name != "litellm":
                    svc_violations.append(
                        f"   ⚠️ Contrainte exacte '==' détectée sur '{raw_line}' — "
                        f"préférer '>=' pour bénéficier des patchs de sécurité automatiques."
                    )

        if svc_violations:
            print(f"  ❌ {svc} : {len(svc_violations)} violation(s)")
            for v in svc_violations:
                print(v)
                violations.append((svc, v))
        else:
            print(f"  ✅ {svc} : Conforme")

    # 3. Validation des règles d'alignement minimales (PyJWT, google-genai, etc.)
    print("\n[3/5] Vérification des versions minimales obligatoires...")
    for svc, deps in service_dependencies.items():
        for pkg, min_ver, reason in RULES:
            pkg_lower = pkg.lower()
            if pkg_lower in deps:
                constraint = deps[pkg_lower]["constraint"]
                # Détection rapide de versions obsolètes ou inférieures
                # Version simplifiée de vérification sémantique
                match = re.search(r">=([0-9]+\.[0-9]+(?:\.[0-9]+)?)", constraint)
                if match:
                    version = match.group(1)
                    min_ver_clean = min_ver.replace(">=", "")
                    if version < min_ver_clean:
                        v_msg = (
                            f"❌ {svc} : {pkg} contraint à {constraint} alors que la Golden Rule exige "
                            f"{min_ver} ({reason})"
                        )
                        print(v_msg)
                        violations.append((svc, v_msg))
                elif not constraint:
                    v_msg = f"❌ {svc} : {pkg} sans aucune contrainte de version ({reason})"
                    print(v_msg)
                    violations.append((svc, v_msg))

    # 4. Audit de cohérence interne (Multi-services)
    print("\n[4/5] Analyse de la cohérence transverse...")
    internal_matrix = {}
    for svc, deps in service_dependencies.items():
        for pkg in KEY_PACKAGES:
            pkg_lower = pkg.lower()
            if pkg_lower in deps:
                if pkg not in internal_matrix:
                    internal_matrix[pkg] = {}
                internal_matrix[pkg][svc] = deps[pkg_lower]["raw"]

    # Signaler si des versions s'écartent trop entre les services
    for pkg, occurrences in internal_matrix.items():
        if len(occurrences) > 1:
            constraints = set(occurrences.values())
            if len(constraints) > 1:
                print(f"  ⚠️ Package partagé non harmonisé : '{pkg}'")
                for svc, raw_dep in occurrences.items():
                    print(f"     - {svc:<20} : {raw_dep}")

    # 5. Vérification du cache contextuel Gemini
    print("\n[5/5] Audit de la configuration du context caching...")
    caching_violations = audit_context_caching(base_dir)
    if caching_violations:
        for cv in caching_violations:
            print(cv)
            violations.append(("FinOps", cv))
    else:
        print("  ✅ Configuration du context caching conforme")

    print("\n====== FIN DE L'AUDIT DES DÉPENDANCES ======")
    if violations:
        print(f"\n❌ ÉCHEC : {len(violations)} violation(s) critique(s) identifiée(s).")
        return False

    if is_offline:
        print("\n🎉 SUCCÈS (Offline) : Cohérence transverse validée !")
    else:
        print("\n🎉 SUCCÈS : Toutes les dépendances analysées sont conformes !")
    return True


if __name__ == "__main__":
    success = run_audit()
    sys.exit(0 if success else 1)
