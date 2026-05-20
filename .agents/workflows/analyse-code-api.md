---
description: Audit complet de toutes les APIs et du Frontend pour vérifier le respect des Golden Rules de l'architecture Zenika Cloud Run.
---

Ce workflow permet à l'agent de scanner automatiquement toutes les APIs et le Frontend du projet pour vérifier leur conformité aux "Golden Rules" du projet Zenika.

### Étape 0 : Lecture des README.md (OBLIGATOIRE)

Avant d'inspecter le moindre fichier de code, lire le `README.md` de chaque service détecté. Le README est la source de vérité sur l'architecture, les dépendances critiques et les points d'attention du service.

```bash
for d in *_api *_mcp agent_*; do [ -d "$d" ] && { echo "=== $d ==="; [ -f "$d/README.md" ] && head -25 "$d/README.md" || echo ">>> MANQUANT — à créer avant d'auditer"; }; done
```

Si un README est absent pour un service → le créer conformément au template §13 AGENTS.md **avant** de démarrer l'audit de ce service.

### Étape 1 : Détection et Catégorisation des Services
Utilise l'outil `list_dir` ou `run_command` (ex: `find . -maxdepth 1 -name "*_api" -o -name "*_mcp" -type d`) pour identifier tous les dossiers de services dans le répertoire courant.
Classe chaque service selon la typologie définie dans `AGENTS.md` :
- **APIs Data 🔵** (producteurs MCP avec DB) : ex. `users_api`, `items_api`, `cv_api`, `competencies_api`, `missions_api`, `drive_api`, `prompts_api`
- **Agents 🟣** (consommateurs MCP sans DB) : ex. `agent_router_api`, `agent_hr_api`, `agent_ops_api`, `agent_missions_api`
- **MCP Natif 🟤** (sans DB) : ex. `analytics_mcp`

### Étape 2 : Analyse de configuration de `db_init_job.tf`
Inspecte le fichier `platform-engineering/terraform/db_init_job.tf`.
Vérifie la variable `services = [...]`. Compare cette liste avec la liste des **APIs Data** détectées (qui nécessitent une base de données). Note quelles APIs sont correctement enregistrées pour la création de leur logique DB et IAM.

### Étape 2b : Audit Terraform LB (NOUVEAU — issu de l'audit 2026-05)

Inspecter `platform-engineering/terraform/lb.tf` et `lb-internal.tf` pour détecter les incohérences de routage.

```bash
# 1. Vérifier que les sous-agents ne sont PAS exposés directement sur le LB externe
#    (seul agent_router_api doit être le point d'entrée public via le catch-all /api/)
echo "=== Routes directes sous-agents sur LB externe (doit être vide) ==="
grep -n "agent.hr.backend\|agent.ops.backend\|agent.missions.backend" platform-engineering/terraform/lb.tf \
  | grep -v "^#" | grep -v "NOTE:" || echo "✅ Aucune route directe sous-agent sur LB externe"

# 2. Vérifier la cohérence des path_prefix_rewrite entre LB externe et LB interne
echo "=== Réécriture /auth/ — LB externe ==="
grep -A5 'prefix_match = "/auth/"' platform-engineering/terraform/lb.tf | grep path_prefix_rewrite

echo "=== Réécriture /auth/ — LB interne (doit être '/' comme le LB externe) ==="
grep -A5 'prefix_match = "/auth/"' platform-engineering/terraform/lb-internal.tf | grep path_prefix_rewrite

# 3. Détecter les backend_service externes orphelins (définis dans cr_*.tf mais plus référencés dans lb.tf)
echo "=== Backend services externes définis dans cr_*.tf ==="
grep -rn 'resource "google_compute_backend_service"' platform-engineering/terraform/cr_*.tf | grep -v "NOTE:"

echo "=== Backend services externes référencés dans lb.tf ==="
grep -n 'google_compute_backend_service\.' platform-engineering/terraform/lb.tf | grep -v "^#"
```

Violations à signaler :
- ❌ Route directe `/api/agent-hr/`, `/api/agent-ops/`, `/api/agent-missions/` sur le LB externe → réduire la surface d'attaque, supprimer et router tout via `agent_router_api`
- ❌ `path_prefix_rewrite = "/users/"` sur `/auth/` dans le LB interne → bug de routage, corriger en `"/"`
- ❌ `google_compute_backend_service` défini dans `cr_*.tf` mais non référencé dans `lb.tf` → ressource orpheline, à supprimer

### Étape 2c : Audit Automatisé des Dépendances (Requirements.txt)

> **Objectif** : Détecter les packages obsolètes, les dépendances interdites, les versions non-harmonisées entre services et les opportunités d'optimisation FinOps (context caching, SDK upgrade).

Exécuter le script d'audit des dépendances standardisé :
```bash
python3 scripts/audit/audit_dependencies.py
```

Le script vérifie de manière résiliente et robuste :
- [ ] **Zéro dépendance interdite** : `python-jose`, `jose` absents.
- [ ] **Versions minimales requises** : `PyJWT>=2.12.0`, `uvicorn>=0.47.0`, `google-genai>=2.0.0`, `pydantic>=2.13.0`.
- [ ] **Cohérence interne** : Alignement transverse des versions entre les 13 microservices.
- [ ] **Context caching Gemini activé** : Vérifie la présence de `gemini_cache.py` dans `competencies_api` et `cv_api`.

---

### Étape 2d : Audit de Conformité Frontend Vue.js (NOUVEAU)

> **Objectif** : Valider le respect des contrats d'interface, la sécurité des packages npm et la configuration du client API du frontend.

Exécuter le script d'audit du frontend :
```bash
python3 scripts/audit/audit_frontend.py
```

Le script vérifie :
- [ ] **Sécurité npm** : Absence de dépendances clés inutilement figées dans `package.json` (usage du caret `^` obligatoire).
- [ ] **Contrats d'interface** : S'assure que les appels API paginés utilisent bien `parsePaginated()` pour valider le typage.
- [ ] **Zéro Endpoint Localhost** : Détecte les URL codées en dur pointant vers `localhost` en dehors des variables d'environnement de dev.

---

### Étape 3 : Audit Automatisé de Conformité Architecturale (CHECKLIST AGENTS.md)

> **Objectif** : Analyser statiquement le code Python pour s'assurer du respect des règles complexes de la plateforme (Zero-Trust, Hardening Mémoire, Résilience HTTP, retry loops, guards 429).

Exécuter le script d'audit de conformité :
```bash
python3 scripts/audit/audit_compliance.py
```

Le script scanne l'intégralité du codebase pour s'assurer des règles suivantes :
- [ ] **Imports top-level** : Pas d'imports Python locaux dans les fonctions (violation PEP8 §8).
- [ ] **Hardening Mémoire** :
  - **Axe 1** : Sémaphores globaux acquis via `acquire_shielded()` (évite le deadlock par `CancelledError`).
  - **Axe 2** : Aucun client Redis synchrone bloquant l'event loop dans les services async.
  - **Axe 3** : Configuration adéquate du pool SQLAlchemy dans `shared/database.py` (`pool_recycle <= 300s`, `pool_reset_on_return="rollback"`).
  - **Axe 4** : State Machines Redis utilisant uniquement `shared.redis_state.get_state_redis_client()`.
- [ ] **CORS Sécurisé** : Pas d'utilisation de wildcard en dur (`allow_origins=["*"]`) dans `main.py`.
- [ ] **Résilience & Timeouts** : Tout client HTTP (`httpx`) ou appel SDK Google (Vertex AI, Pub/Sub) doit définir un timeout explicite.
- [ ] **Failfast / Exception swallowing** : Pas d'utilisation de `except Exception: pass` ou d'erreurs interceptées et étouffées sans log.

---

### Étape 4 : Analyse de la couverture des tests aux limites (edge-cases)

Pour chaque conteneur, vérifier que les "edge-cases" (cas limites, sécurité, résilience) sont bien testés. Un conteneur sans fichiers de tests spécifiques aux limites (`test_edge_cases.py`, `test_zero_trust.py`, `test_jwt*.py`, etc.) doit être signalé.

```bash
echo "=== Tests aux limites — coverage par service ==="
for d in *_api *_mcp agent_*; do
  if [ -d "$d" ] && [ -d "$d/tests" ]; then
    count=$(ls "$d/tests/"test_*.py 2>/dev/null | wc -l | tr -d ' ')
    edge=$(ls "$d/tests/"test_edge*.py "$d/tests/"test_zero_trust*.py "$d/tests/"test_jwt*.py 2>/dev/null | wc -l | tr -d ' ')
    echo "  $d: $count fichiers tests [$edge edge/security]"
    if [ "$edge" -eq 0 ]; then
      echo "  ⚠️ $d: AUCUN test spécifique edge-case/sécurité détecté"
    fi
  fi
done
```

### Étape 5 : Exécution des Tests
Pour chaque service détecté, exécute la suite de tests pour vérifier la robustesse du code :

```bash
for d in *_api *_mcp agent_*; do
  if [ -d "$d" ] && [ -d "$d/tests" ]; then
    echo "=== Tests : $d ==="
    cd "$d"
    echo "Exécution de pytest..."
    python3 -m pytest tests/ || echo "Erreur pytest dans $d"
    cd ..
  fi
done
```

### Étape 6 : Génération du Rapport
Une fois l'audit et les tests terminés, génère un rapport consolidé `rapport_audit_apis.md` résumant les diagnostics générés par les 3 scripts d'audit (`audit_dependencies.py`, `audit_frontend.py`, `audit_compliance.py`) ainsi que le statut des suites de tests unitaires, accompagné du plan d'action recommandé.
