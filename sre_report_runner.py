#!/usr/bin/env python3
"""
sre_report_runner.py — Génère un rapport SRE depuis les erreurs loggées dans prompts_api.

Usage : python3 sre_report_runner.py

Étapes :
  1. S'authentifie sur la prd via mcp_cli.get_jwt()
  2. Récupère tous les prompts commençant par 'error_correction:' depuis prompts_api
  3. Génère sre_report.md avec analyse et plan de remédiation
  4. Supprime les erreurs obsolètes (DELETE /prompts/{key})
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import httpx

# ── Configuration ──────────────────────────────────────────────────────────────
BASE_URL = os.getenv("ZENIKA_BASE_URL", "https://prd.zenika.slavayssiere.fr")
REPORT_FILE = Path("sre_report.md")

# Réutilise l'auth de mcp_cli pour ne pas dupliquer la logique
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from mcp_cli import get_jwt  # noqa: E402


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def fetch_error_prompts(token: str) -> list[dict]:
    """Récupère tous les prompts error_correction:* depuis prompts_api."""
    resp = httpx.get(
        f"{BASE_URL}/api/prompts/",
        headers=_headers(token),
        timeout=60.0,
    )
    if resp.status_code == 401:
        # Token cache périmé → forcer un nouveau login
        from pathlib import Path
        TOKEN_CACHE = Path.home() / ".cache" / "zenika_mcp_cli_token.json"
        TOKEN_CACHE.unlink(missing_ok=True)
        from mcp_cli import get_jwt as _get_fresh_jwt
        token = _get_fresh_jwt()
        resp = httpx.get(f"{BASE_URL}/api/prompts/", headers=_headers(token), timeout=60.0)
    if resp.status_code != 200:
        print(f"❌ GET /api/prompts/ → {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    # prompts_api retourne {"prompts": [...], "total": N, "skip": N, "limit": N}
    prompts = data.get("prompts", data.get("items", data)) if isinstance(data, dict) else data
    if not isinstance(prompts, list):
        print(f"❌ Format inattendu : {type(data)}", file=sys.stderr)
        sys.exit(1)

    errors = [p for p in prompts if str(p.get("key", "")).startswith("error_correction:")]
    print(f"📋 {len(errors)} erreur(s) error_correction trouvée(s) sur {len(prompts)} prompts total.")
    return errors


def delete_prompt(key: str, token: str) -> bool:
    """Supprime un prompt par sa clé."""
    resp = httpx.delete(
        f"{BASE_URL}/api/prompts/{key}",
        headers=_headers(token),
        timeout=10.0,
    )
    return resp.status_code in (200, 204, 404)


def generate_report(errors: list[dict]) -> str:
    """Génère le contenu Markdown du rapport SRE."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Rapport SRE — {now}",
        "",
        f"**Source** : `prompts_api` prd | **Erreurs analysées** : {len(errors)}",
        "",
    ]

    if not errors:
        lines += [
            "## ✅ Aucune erreur active",
            "",
            "Aucun prompt `error_correction:*` trouvé en production.",
            "La plateforme est stable.",
        ]
        return "\n".join(lines)

    lines += ["## Erreurs détectées", ""]

    for i, err in enumerate(errors, 1):
        key = err.get("key", "?")
        value = err.get("value", "")
        # Extraire service depuis la clé: error_correction:missions_api:xxx
        parts = key.split(":")
        service = parts[1] if len(parts) > 1 else "inconnu"

        lines += [
            f"### [{i}] `{key}`",
            "",
            f"**Service** : `{service}`",
            "",
            "**Message d'erreur** :",
            "```",
            value[:2000] if value else "(vide)",
            "```",
            "",
        ]

    lines += [
        "## Plan de remédiation",
        "",
        "> Analyse des erreurs ci-dessus et propositions de correction.",
        "",
    ]

    # Analyse automatique des patterns connus
    for err in errors:
        key = err.get("key", "")
        value = err.get("value", "")
        parts = key.split(":")
        service = parts[1] if len(parts) > 1 else "inconnu"

        if "string indices must be integers" in value:
            lines += [
                f"#### `{key}` — TypeError: string indices must be integers",
                "",
                "**Cause probable** : itération sur une chaîne au lieu d'un dict/list.",
                "Souvent dû à un `.get()` ou `for x in response` où `response` est une `str`",
                "plutôt qu'un objet JSON parsé.",
                "",
                "**Actions** :",
                f"- Vérifier les parsings JSON dans `{service}/` (réponses httpx non `.json()`-ées)",
                "- Chercher les `for item in data` sans vérification de type préalable",
                "- Vérifier que `response.json()` n'est pas appelé sur une erreur HTTP",
                "",
            ]

        elif "401" in value or "Unauthorized" in value:
            lines += [
                f"#### `{key}` — Erreur d'authentification 401",
                "",
                f"**Actions** : Vérifier la propagation JWT dans `{service}/`.",
                "",
            ]

        elif "404" in value or "Not Found" in value:
            lines += [
                f"#### `{key}` — Ressource introuvable 404",
                "",
                f"**Actions** : Vérifier les routes et les IDs dans `{service}/`.",
                "",
            ]

        else:
            lines += [
                f"#### `{key}` — Erreur générique",
                "",
                f"**Actions** : Analyser manuellement le message d'erreur dans `{service}/`.",
                "",
            ]

    return "\n".join(lines)


def main():
    print(f"🔐 Authentification sur {BASE_URL}...")
    token = get_jwt()
    print("✅ Token obtenu.\n")

    # Étape 1 : Récupérer les erreurs
    errors = fetch_error_prompts(token)

    # Étape 2 : Générer le rapport
    report = generate_report(errors)
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(f"\n📄 Rapport généré : {REPORT_FILE}")

    # Étape 3 : Afficher le résumé
    if errors:
        print("\n🚨 Erreurs actives :")
        for e in errors:
            key = e.get("key", "?")
            val_preview = str(e.get("value", ""))[:120].replace("\n", " ")
            print(f"  • {key}")
            print(f"    → {val_preview}")
        print(f"\n⚠️  {len(errors)} erreur(s) à corriger — voir {REPORT_FILE}")
    else:
        print("✅ Aucune erreur active — plateforme stable.")

    # Étape 4 : Nettoyage optionnel (erreurs déjà traitées)
    # Pour l'instant on n'auto-supprime pas — l'agent doit valider manuellement
    print("\n💡 Pour supprimer une erreur traitée :")
    print(f"   curl -X DELETE {BASE_URL}/api/prompts/<key> -H 'Authorization: Bearer $TOKEN'")


if __name__ == "__main__":
    main()
