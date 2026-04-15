---
description: Exécute la suite de tests de prompts sur l'environnement GCP dev, lit le rapport LLM généré et propose des améliorations concrètes sur les system prompts, les cas de test et l'architecture multi-agent.
---

// turbo-all

Ce workflow permet à l'agent d'auditer automatiquement le comportement des agents IA sur GCP dev, puis de proposer et d'appliquer des corrections ciblées.

### Étape 1 : Récupération du mot de passe admin

L'agent s'exécute dans un shell non-interactif avec `PATH=/usr/bin:/bin:/usr/sbin:/sbin` — `gcloud` n'est **pas** dans ce PATH.

> **Chemin gcloud confirmé** : `/Users/sebastien.lavayssiere/Apps/google-cloud-sdk/bin/gcloud`

**Solution : lecture depuis `.antigravity_env`** (fichier local gitignore) :

```bash
# // turbo
[ -f .antigravity_env ] && cat .antigravity_env || echo "ANTIGRAVITY_ENV_NOT_FOUND"
```

Si le fichier existe, extraire `ADMIN_PASSWORD` et `GCLOUD_BIN` depuis son contenu.
Si le fichier **n'existe pas**, afficher ce message à l'utilisateur et **s'arrêter** :

```
❌ Fichier .antigravity_env manquant. Crée-le une fois depuis ton terminal :

  echo "GCLOUD_BIN=$(which gcloud)" > .antigravity_env
  echo "ADMIN_PASSWORD=$(gcloud secrets versions access latest --secret=admin-password-dev)" >> .antigravity_env

Ce fichier est gitignore — tes credentials ne seront pas commités.
```

Une fois le mot de passe obtenu, vérifie que `httpx` est disponible :
```bash
# // turbo
pip3 install --target=/tmp/py_deps httpx 2>&1 | tail -1 && PYTHONPATH=/tmp/py_deps /opt/homebrew/bin/python3.13 -c "import httpx; print('httpx OK')"
```

**Catégories disponibles :** `hr`, `ops`, `routing`, `schema`, `anti-hallucination`, `edge-cases`, `finops`, `multi-domain`, `missions`

> Le rapport LLM est généré automatiquement dans `reports/llm_analysis_<catégorie>_<timestamp>.md` à la fin de chaque run.


### Étape 2 : Lancement de la suite de tests

Lance la suite complète ou filtrée selon les arguments passés à `/analyse-prompt`.
Utilise `/opt/homebrew/bin/python3.13` comme interpréteur (Python système disponible sur cette machine).

**Sans argument** → tous les tests :
```bash
# // turbo
ADMIN_PASSWORD=$(gcloud secrets versions access latest --secret=admin-password-dev 2>/dev/null) PYTHONPATH=/tmp/py_deps /opt/homebrew/bin/python3.13 scripts/agent_prompt_tests.py --verbose 2>&1
```

**Avec catégorie** (ex: `/analyse-prompt missions`) → filtre sur la catégorie :
```bash
# // turbo
ADMIN_PASSWORD=$(gcloud secrets versions access latest --secret=admin-password-dev 2>/dev/null) PYTHONPATH=/tmp/py_deps /opt/homebrew/bin/python3.13 scripts/agent_prompt_tests.py --filter <catégorie> --verbose 2>&1
```

### Étape 3 : Lecture du rapport LLM généré

Identifie le fichier de rapport le plus récent dans `reports/` :
```bash
# // turbo
ls -t reports/llm_analysis_*.md 2>/dev/null | head -1
```

Lis l'intégralité du fichier rapport généré avec l'outil `view_file`.

### Étape 4 : Analyse et application des corrections

Analyse le rapport section par section et **applique directement** les corrections identifiées dans la section 5 (Propositions d'amélioration) :

#### 4.1. Proposition 1 — Contamination de session
Si détectée (0 output tokens + réponse non vide) :
- Vérifier que `_clear_session()` est bien appelé dans `run_test()` dans `scripts/agent_prompt_tests.py`.
- Vérifier que `DELETE /api/history` répond correctement avec le token admin.
- Proposer le correctif côté `agent_router_api/main.py` pour utiliser le `session_id` du body.

#### 4.2. Proposition 2 — Sur-routage
Si des dispatches multi-agents non justifiés sont détectés :
- Lire le fichier `agent_router_api/agent_router_api.system_instruction.txt`.
- Identifier la règle manquante ou ambiguë qui provoque le sur-routage.
- Modifier le prompt directement avec `write_to_file` ou `multi_replace_file_content`.
- Lancer le sync du prompt vers GCP dev :
```bash
python3 scripts/sync_prompts.py \
  --url "https://dev.zenika.slavayssiere.fr/api/prompts" \
  --email "admin@zenika.com" \
  --password "<ADMIN_PASSWORD>"
```

#### 4.3. Proposition 3 — Tools attendus non appelés
Si des warnings `Tool attendu non appelé` sont détectés :
- Distinguer les deux cas :
  - **Faux positif** (le tool appelé est équivalent) → corriger `expected_tools` dans `scripts/agent_prompt_tests.py`.
  - **Vrai problème** (tool absent du prompt agent) → lire `agent_hr_api/agent.py` ou `agent_ops_api/agent.py`, identifier le tool manquant et mettre à jour la docstring ou le `KNOWN_TOOLS_RESULT`.

#### 4.4. Proposition 4 — Tests trop lents
Si des tests dépassent 10s :
- Identifier si le cause est le sur-routage (voir 4.2) ou un nombre de tools excessif.
- Si le cache sémantique Redis n'est pas en place, ouvrir `agent_router_api/main.py` et proposer le snippet d'implémentation.

#### 4.5. Proposition 5 — Ratio tokens in/out anormal
Si le ratio dépasse 80x :
- Vérifier la taille du system prompt actuel (nombre de caractères).
- Proposer une version allégée si le prompt dépasse 3000 caractères.

#### 4.6. Proposition 6 — Golden behaviors
Lister les tests golden identifiés et vérifier qu'ils ont `data_quality_strict=True` dans le cas de test.
Ajouter le flag si manquant.

### Étape 5 : Rapport d'intervention

Génère un artifact `walkthrough.md` résumant :
- Les anomalies trouvées (avec leur ID de Proposition)
- Les corrections effectuées (fichier modifié, ligne, nature du changement)
- Les actions manuelles restantes (sync de prompt, déploiement Cloud Run)
- Le score avant/après (`X/Y tests → X'/Y' tests`)
