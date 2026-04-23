---
description: Exécute la suite de tests de prompts sur l'environnement GCP dev, lit le rapport LLM généré et propose des améliorations concrètes sur les system prompts, les cas de test et l'architecture multi-agent.
---

// turbo-all

Ce workflow permet à l'agent d'auditer automatiquement le comportement des agents IA sur GCP dev, puis de proposer et d'appliquer des corrections ciblées.

> **Chaînage recommandé** : `/generate-gcp-summit-fake` → `/analyse-prompt`
> Les données de peuplement (consultants, missions) doivent être présentes avant les tests
> pour que les cas de test basés sur des données réelles passent correctement.

---

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

**Catégories disponibles :** `hr`, `ops`, `routing`, `schema`, `anti-hallucination`, `edge-cases`, `finops`, `multi-domain`, `missions`, `hr-persona`, `staffing-persona`, `commercial-persona`, `dir-commerciale-persona`, `agence-niort-persona`, `tech-manager-persona`, `consultant-persona`, `security`, `robustness`, `semantic-cache`, `knowledge-analytics`

> Le rapport LLM est généré automatiquement dans `reports/llm_analysis_<catégorie>_<timestamp>.md` à la fin de chaque run.
> Le log brut est toujours sauvegardé dans `reports/run_<catégorie>_<timestamp>.log` pour consultation post-mortem.

---

### Étape 1bis : Vérification pré-test (données de peuplement)

**OBLIGATOIRE si le workflow est chaîné après `/generate-gcp-summit-fake`.**
Vérifie que la plateforme est peuplée avant de lancer les 109 tests.
Si `total < 10` consultants ou `missions < 5`, les tests data-dépendants échoueront massivement — ne pas lancer `/analyse-prompt` et demander à relancer `/generate-gcp-summit-fake`.

```bash
# // turbo
ADMIN_PASSWORD='<ADMIN_PASSWORD>' PYTHONPATH=/tmp/py_deps \
  /opt/homebrew/bin/python3.13 -u -c "
import httpx, os, sys
base = 'https://dev.zenika.slavayssiere.fr'
pwd = os.environ['ADMIN_PASSWORD']
try:
    tok = httpx.post(f'{base}/api/auth/login', json={'email':'admin@zenika.com','password':pwd}, timeout=10).json()['access_token']
    h = {'Authorization': f'Bearer {tok}'}
    users = httpx.get(f'{base}/api/users/', headers=h, timeout=10).json()
    missions = httpx.get(f'{base}/api/missions/missions', headers=h, timeout=10).json()
    nb_users = users.get('total', 0) if isinstance(users, dict) else len(users)
    nb_missions = len(missions) if isinstance(missions, list) else 0
    print(f'Consultants : {nb_users}')
    print(f'Missions    : {nb_missions}')
    if nb_users < 10:
        print('⚠️  AVERTISSEMENT : moins de 10 consultants — lancer /generate-gcp-summit-fake d\\'abord')
        sys.exit(1)
    if nb_missions < 5:
        print('⚠️  AVERTISSEMENT : moins de 5 missions — lancer /generate-gcp-summit-fake d\\'abord')
        sys.exit(1)
    print('✅ Données suffisantes — tests peuvent démarrer')
except Exception as e:
    print(f'❌ Erreur de connexion à la plateforme : {e}')
    sys.exit(1)
"
```

---

### Étape 2 : Lancement de la suite de tests

Lance la suite complète ou filtrée selon les arguments passés à `/analyse-prompt`.
Utilise `/opt/homebrew/bin/python3.13 -u` comme interpréteur (Python système, `-u` = unbuffered pour flush immédiat).

**Politique de logs** :
- Le flag `-u` de Python garantit que chaque ligne est flushée immédiatement sur stdout → visible en temps réel.
- Le flag `--log-file` enregistre simultanement dans un fichier (line-buffered).
- Le flag `--fail-fast` arrête la suite dès le premier test en échec.
- La progression `[N/total]` est affichée sur chaque ligne résultat.

Calcule le nom du fichier de log AVANT de lancer les tests :
```bash
# // turbo
mkdir -p reports && echo "reports/run_$(date +%Y%m%d_%H%M%S).log"
```

**Sans argument** → tous les tests avec fail-fast et log :
```bash
# // turbo
LOG_FILE="reports/run_all_$(date +%Y%m%d_%H%M%S).log" && \
ADMIN_PASSWORD='<ADMIN_PASSWORD>' PYTHONPATH=/tmp/py_deps \
  /opt/homebrew/bin/python3.13 -u scripts/agent_prompt_tests.py \
  --verbose --fail-fast --log-file "$LOG_FILE" 2>&1 | tee "$LOG_FILE"
```

**Avec catégorie** (ex: `/analyse-prompt missions`) → filtre sur la catégorie :
```bash
# // turbo
LOG_FILE="reports/run_<catégorie>_$(date +%Y%m%d_%H%M%S).log" && \
ADMIN_PASSWORD='<ADMIN_PASSWORD>' PYTHONPATH=/tmp/py_deps \
  /opt/homebrew/bin/python3.13 -u scripts/agent_prompt_tests.py \
  --filter <catégorie> --verbose --fail-fast --log-file "$LOG_FILE" 2>&1 | tee "$LOG_FILE"
```

> **Note sur le suivi en temps réel** : la commande `tee` envoie le flux vers stdout (visible dans les logs de l'agent) ET vers `$LOG_FILE`. Si le workflow est lancé en mode background, l'utilisateur peut suivre la progression avec :
> ```bash
> tail -f reports/run_<...>.log
> ```

---

### Étape 3 : Lecture du rapport LLM généré

Identifie le fichier de rapport le plus récent dans `reports/` :
```bash
# // turbo
ls -t reports/llm_analysis_*.md 2>/dev/null | head -1
```

Lis l'intégralité du fichier rapport généré avec l'outil `view_file`.

---

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

#### 4.3. Proposition 3 — Tests en échec à cause de données manquantes
Si des tests échouent sur des mots-clés de données (consultants, missions, agences) **et** que la base est vide :

> ⚠️ **Ce pattern survient après un reset de la base de données.**
> Les tests qui attendent des données spécifiques (ex: `Ahmed KANOUN`, mission `id=2`) vont
> échouer si le peuplement `/generate-gcp-summit-fake` n'a pas été exécuté.

**Action** : ne pas modifier les tests — relancer `/generate-gcp-summit-fake` d'abord.

**Signal d'un problème de données vs problème de prompt :**
- Si `0 out tokens` → contamination de session (voir 4.1)
- Si `must_contain` échoue sur un nom propre → données manquantes (relancer peuplement)
- Si `must_contain` échoue sur un mot générique (`mission`, `consultant`) → problème de prompt

#### 4.4. Proposition 4 — Tools attendus non appelés
Si des warnings `Tool attendu non appelé` sont détectés :
- Distinguer les deux cas :
  - **Faux positif** (le tool appelé est équivalent) → corriger `expected_tools` dans `scripts/agent_prompt_tests.py`.
  - **Vrai problème** (tool absent du prompt agent) → lire `agent_hr_api/agent.py` ou `agent_ops_api/agent.py`, identifier le tool manquant et mettre à jour la docstring ou le `KNOWN_TOOLS_RESULT`.

#### 4.5. Proposition 5 — Tests trop lents
Si des tests dépassent 10s :
- Identifier si le cause est le sur-routage (voir 4.2) ou un nombre de tools excessif.
- Si le cache sémantique Redis n'est pas en place, ouvrir `agent_router_api/main.py` et proposer le snippet d'implémentation.

#### 4.6. Proposition 6 — Ratio tokens in/out anormal
Si le ratio dépasse 80x :
- Vérifier la taille du system prompt actuel (nombre de caractères).
- Proposer une version allégée si le prompt dépasse 3000 caractères.

#### 4.7. Proposition 7 — Golden behaviors
Lister les tests golden identifiés et vérifier qu'ils ont `data_quality_strict=True` dans le cas de test.
Ajouter le flag si manquant.

---

### Étape 5 : Rapport d'intervention

Génère un artifact `walkthrough.md` résumant :
- Les anomalies trouvées (avec leur ID de Proposition)
- Les corrections effectuées (fichier modifié, ligne, nature du changement)
- Les actions manuelles restantes (sync de prompt, déploiement Cloud Run)
- Le score avant/après (`X/Y tests → X'/Y' tests`)
- **Si échecs liés aux données** : indiquer explicitement `⚠️ Relancer /generate-gcp-summit-fake`
