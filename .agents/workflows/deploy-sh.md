---
description: Lance ./scripts/deploy.sh all db_migrations et analyse le résultat pour Antigravity (état, erreurs, versions déployées).
---

Ce workflow lance le déploiement complet et exploite les rapports enrichis générés automatiquement.

> ⚠️ **RÈGLE §11** : L'agent ne peut PAS exécuter `deploy.sh` lui-même (build/deploy interdits). Ce workflow est **déclenché par l'utilisateur**. Le rôle de l'agent est d'analyser le résultat une fois le run terminé.

---

### Étape 1 : Lancer le déploiement

Communiquer à l'utilisateur la commande exacte à exécuter dans son terminal :

```bash
# Depuis la racine du mono-repo :
./scripts/deploy.sh all db_migrations
```

> 💡 **Options utiles :**
> - `--skip-tests` : bypass des tests unitaires (hotfix uniquement, déconseillé)
> - `--force-all` : force le rebuild de tous les services même sans changement détecté
> - `all db_migrations minor` : bump de version mineur au lieu de patch

**Attendre que l'utilisateur confirme la fin du run avant de continuer.**

---

### Étape 2 : Lire le rapport Antigravity enrichi (§19 AGENTS.md)

Le script génère automatiquement un rapport complet à la fin de chaque run.
Lire systématiquement les **deux fichiers** dans cet ordre :

// turbo
```bash
# 1. État machine-readable (services, versions, status global)
cat deploy_logs/last_deploy.json | python3 -m json.tool
```

// turbo
```bash
# 2. Rapport Antigravity enrichi (git, tables, stack traces, commandes MCP)
PROMPT=$(python3 -c "import json; print(json.load(open('deploy_logs/last_deploy.json'))['antigravity_prompt'])" 2>/dev/null)
if [ -n "$PROMPT" ] && [ -f "$PROMPT" ]; then
  cat "$PROMPT"
else
  echo "Rapport introuvable — chercher manuellement dans deploy_logs/"
  ls -t deploy_logs/*/antigravity_prompt.md 2>/dev/null | head -3
fi
```

// turbo
```bash
# 3. Rapport d'erreur manage_env (si une opération Terraform a eu lieu)
if [ -f platform-engineering/antigravity_sanity_error.md ]; then
  echo "=== Rapport manage_env ==="
  cat platform-engineering/antigravity_sanity_error.md
else
  echo "[OK] Aucun rapport d'erreur manage_env détecté."
fi
```

---

### Étape 3 : Analyser et agir

Le rapport Antigravity enrichi (étape 2.2) contient déjà toutes les informations nécessaires :

- **§1 Contexte opérationnel** : branche git, commit, durée, PROJECT_ID, SKIP_TESTS
- **§2 Résumé des services** : tableau déployés / skippés / en échec avec versions
- **§3 Détail des erreurs** : stack traces filtrées + résumé pytest + contexte autour de la première erreur
- **§4 Couverture** : tableau de couverture avec indicateurs ✅⚠️❌
- **§5 Prochaines étapes** : actions recommandées avec commandes MCP pré-remplies

**Si `overall_status = failure`** :
1. Lire la section §3 du rapport pour identifier la cause racine
2. Chercher en mémoire : `mcp_antigravity-memory_search_past_errors(query="<service> <type d'erreur>")`
3. Utiliser les commandes MCP du rapport (pré-remplies par service en échec)
4. Proposer un fix précis (fichier + ligne)

**Si `overall_status = success`** :

// turbo
```bash
python3 -c "
import json
d = json.load(open('deploy_logs/last_deploy.json'))
print('✅ Déploiement réussi —', d['timestamp'])
print()
for svc in d.get('deployed', []):
    print(f'  ✅ {svc}')
for svc in d.get('skipped', []):
    print(f'  ⏭️  {svc}')
"
```

---

### Étape 4 : Vérification production (si cible prd)

// turbo
```bash
# Health check global via MCP CLI
python3 scripts/mcp_cli.py health
```

---

### Étape 5 : Mémoriser les erreurs résolues (§20 AGENTS.md)

Si des erreurs ont été rencontrées et corrigées, les enregistrer **avant** de clore la session :

```
→ mcp_antigravity-memory_log_error_and_solution(
    task_context="deploy.sh all db_migrations — <service>",
    error_message="<message exact depuis le rapport>",
    successful_solution="<fix précis : fichier, ligne, changement>",
    tags=["deploy", "<service>"]
  )
```

---

### Résumé attendu en fin de workflow

```
✅/❌ Déploiement — <timestamp>
  Branche  : <git branch>
  Commit   : <hash> — <message>
Déployés  : <liste avec versions>
Skippés   : <liste>
En échec  : <liste ou "aucun">
Prochaine action : <fix suggéré ou health check>
```

