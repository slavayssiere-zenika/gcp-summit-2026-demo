#!/usr/bin/env python3
"""validate_openapi.py — Valide les schémas OpenAPI et la compatibilité descendante.

Ce script :
  1. Charge dynamiquement l'application FastAPI de chaque micro-service.
  2. Valide la structure OpenAPI via openapi-spec-validator.
  3. Compare le schéma courant avec le schéma de référence (Golden Master).
  4. Bloque le déploiement en cas de rupture de contrat d'interface (breaking changes).
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Any

SERVICES = [
    "competencies_api",
    "cv_api",
    "drive_api",
    "items_api",
    "missions_api",
    "prompts_api",
    "users_api",
    "agent_router_api",
    "agent_hr_api",
    "agent_ops_api",
    "agent_missions_api",
]

REFERENCE_DIR = "docs/openapi/reference"


def generate_spec_for_service(service: str) -> dict[str, Any] | None:
    """Génère le schéma OpenAPI JSON d'un service en l'important de façon isolée."""
    extractor_code = """
import json
import os
import sys

try:
    sys.path.insert(0, os.getcwd())
    sys.path.insert(0, os.path.dirname(os.getcwd()))
    try:
        from main import app
    except ImportError:
        from src.main import app
    schema = app.openapi()
    print(json.dumps(schema))
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
"""
    env = os.environ.copy()
    env.setdefault("SECRET_KEY", "spec-validation-dummy-key-unsafe")
    env.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./spec_val.db")
    env.setdefault("REDIS_URL", "redis://localhost:6379/0")
    env.setdefault("GOOGLE_API_KEY", "dummy-api-key")
    env.setdefault("GEMINI_MODEL", "gemini-2.5-flash")

    try:
        p = subprocess.run(
            ["../test_env/bin/python", "-c", extractor_code],
            cwd=service,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(p.stdout)
    except Exception as e:
        print(f"❌ Impossible de charger {service}: {e}", file=sys.stderr)
        if hasattr(e, "stderr") and e.stderr:  # type: ignore[attr-defined]
            print(f"   Stderr : {e.stderr}", file=sys.stderr)  # type: ignore[attr-defined]
        return None


def compare_specs(reference: dict[str, Any], current: dict[str, Any], service: str) -> list[str]:
    """Compare deux schémas OpenAPI pour détecter d'éventuels breaking changes.

    Règles de rupture détectées :
      1. Suppression de route (ex: GET /users/{id}).
      2. Suppression de méthode sur route existante.
      3. Ajout de paramètre requis (query/path/header) non présent auparavant.
    """
    errors = []

    ref_paths = reference.get("paths", {})
    curr_paths = current.get("paths", {})

    for path, ref_methods in ref_paths.items():
        if path not in curr_paths:
            errors.append(f"Route supprimée : '{path}'")
            continue

        curr_methods = curr_paths[path]
        for method, ref_details in ref_methods.items():
            if method not in curr_methods:
                errors.append(f"Méthode supprimée : {method.upper()} '{path}'")
                continue

            curr_details = curr_methods[method]

            # Vérifier les paramètres requis
            ref_params = {p["name"]: p for p in ref_details.get("parameters", []) if p.get("required")}
            curr_params = {p["name"]: p for p in curr_details.get("parameters", []) if p.get("required")}

            # Ajout d'un paramètre requis non présent avant = BREAKING CHANGE
            for p_name, p_details in curr_params.items():
                if p_name not in ref_params:
                    # C'est une rupture de contrat sauf si le paramètre existait déjà en optionnel
                    # et est devenu requis (ce qui est quand même risqué).
                    errors.append(
                        f"Nouveau paramètre requis détecté sur {method.upper()} '{path}' : '{p_name}'"
                    )

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validateur de contrat OpenAPI")
    parser.add_argument(
        "--generate", action="store_true", help="Génère ou rafraîchit les schémas de référence"
    )
    args = parser.parse_args()

    os.makedirs(REFERENCE_DIR, exist_ok=True)
    has_errors = False

    # Validation structurelle (optionnelle si openapi-spec-validator est dispo)
    try:
        from openapi_spec_validator import validate_spec
        has_validator = True
    except ImportError:
        print("⚠️  openapi-spec-validator non installé. Validation structurelle ignorée.")
        has_validator = False

    for service in SERVICES:
        if not os.path.isdir(service):
            print(f"⏭️  {service} : non présent localement.")
            continue

        print(f"🔍 Traitement de {service}...")
        current_spec = generate_spec_for_service(service)
        if current_spec is None:
            has_errors = True
            continue

        ref_file = os.path.join(REFERENCE_DIR, f"{service}_openapi.json")

        if args.generate:
            with open(ref_file, "w", encoding="utf-8") as f:
                json.dump(current_spec, f, indent=2)
            print(f"   💾 Schéma de référence sauvegardé : {ref_file}")
            continue

        # 1. Validation structurelle
        if has_validator:
            try:
                validate_spec(current_spec)
                print("   ✅ Structure OpenAPI : Valide")
            except Exception as e:
                print(f"   ❌ Structure OpenAPI : Invalide : {e}", file=sys.stderr)
                has_errors = True
                continue

        # 2. Validation de compatibilité descendante (Breaking Changes)
        if not os.path.exists(ref_file):
            print(f"   ⚠️  Aucun schéma de référence trouvé. Génération automatique pour {service}.")
            with open(ref_file, "w", encoding="utf-8") as f:
                json.dump(current_spec, f, indent=2)
            continue

        with open(ref_file, "r", encoding="utf-8") as f:
            ref_spec = json.load(f)

        breaking_changes = compare_specs(ref_spec, current_spec, service)
        if breaking_changes:
            print(f"   ❌ Rupture de contrat détectée pour {service} :", file=sys.stderr)
            for bc in breaking_changes:
                print(f"      - {bc}", file=sys.stderr)
            has_errors = True
        else:
            print("   ✅ Rétrocompatibilité : OK")

    if has_errors and not args.generate:
        print("\n❌ Échec de la validation des spécifications OpenAPI (Rupture de contrat détectée).", file=sys.stderr)
        sys.exit(1)
    elif args.generate:
        print("\n✅ Tous les schémas de référence ont été générés avec succès.")
    else:
        print("\n✅ Tous les contrats d'interface OpenAPI sont valides.")


if __name__ == "__main__":
    main()
