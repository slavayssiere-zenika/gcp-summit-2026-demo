#!/usr/bin/env python3
import os
import json
import httpx
from datetime import datetime, timezone

PROMPTS_API = "https://prd.zenika.slavayssiere.fr/api/prompts"
TOKEN_CACHE = os.path.expanduser("~/.cache/zenika_mcp_cli_token.json")

def get_token():
    with open(TOKEN_CACHE, "r") as f:
        return json.load(f)["token"]

def main():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # 1. Update Sweep Prompt (Anti-Faux-Positifs)
    sweep_name = "cv_api.generate_taxonomy_tree_sweep"
    res_sweep = httpx.get(f"{PROMPTS_API}/{sweep_name}", headers=headers)
    res_sweep.raise_for_status()
    sweep_text = res_sweep.json()["value"]
    
    anti_fp_rule = """
**RÈGLE ANTI-FAUX-POSITIFS (DROPS) :**
Interdiction absolue de rejeter (drop) des compétences contenant des termes techniques IT clés (ex: API, Data, Cloud, Dev, Ops, Security, Machine Learning, Architecture, etc.).
Si la compétence vous semble générique mais contient un terme IT valide, ASSIGNEZ-LA systématiquement à la racine du pilier le plus pertinent. Ne droppez que les termes purement inutiles (ex: "Développement", "Outils", acronymes inconnus de 2 lettres).
"""
    if "RÈGLE ANTI-FAUX-POSITIFS" not in sweep_text:
        sweep_text += "\n" + anti_fp_rule
        httpx.put(f"{PROMPTS_API}/{sweep_name}", headers=headers, json={"value": sweep_text}).raise_for_status()
        print("✅ Sweep prompt updated")
    else:
        print("ℹ️ Sweep prompt already updated")
        
    # 2. Update Deduplicate Prompt (Constraint)
    dedup_name = "cv_api.generate_taxonomy_tree_deduplicate"
    res_dedup = httpx.get(f"{PROMPTS_API}/{dedup_name}", headers=headers)
    res_dedup.raise_for_status()
    dedup_text = res_dedup.json()["value"]
    
    valid_nodes_rule = """
Vous DEVEZ utiliser la liste des piliers existants : {{VALID_NODES}}.
Ne renommez pas les piliers finaux. Regroupez les éléments sous l'un des {{VALID_NODES}}.
"""
    if "{{VALID_NODES}}" not in dedup_text:
        dedup_text += "\n" + valid_nodes_rule
        httpx.put(f"{PROMPTS_API}/{dedup_name}", headers=headers, json={"value": dedup_text}).raise_for_status()
        print("✅ Deduplicate prompt updated")
    else:
        print("ℹ️ Deduplicate prompt already updated")

if __name__ == "__main__":
    main()
