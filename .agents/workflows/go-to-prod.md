---
description: Assistant expert de mise en production (Analyse versions, changelog, Terraform plan, Audit Zéro-Trust, Bilan de migrations).
---

Ce workflow guide l'agent pour vérifier et préparer de manière experte une release en production.
Toutes les étapes d'audit expertes définies ci-dessous sont **BLOQUANTES**. En cas d'échec sur l'une des vérifications de sécurité ou de conformité, l'agent doit l'imposer à l'utilisateur et proposer une correction immédiate avant de continuer.

### Étape 1 : Analyse des Versions et Détection (`prd.yaml`)
1. Lit le fichier `platform-engineering/envs/prd.yaml`.
2. Utilise `list_dir` et/ou `view_file` pour lire les fichiers `VERSION` locaux de tous les microservices détectés.
3. Identifie les différences entre les versions locales et celles définies dans `prd.yaml`.
4. **Action** : Propose un bloc YAML mis à jour pour `prd.yaml` (prêt à être copié-collé par l'humain ou auto-édité par toi si demandé) pour épingler avec certitude les services concernés.

### Étape 2 : Bilan Fonctionnel (`changelog.md`)
1. Scanne avec `view_file` les entrées les plus récentes du fichier `changelog.md` ou utilise `git status` / `git log`.
2. **Action** : Fais la synthèse sous la forme d'encarts : `Features Ajoutées`, `Fixes`, `Spécificités Techniques` et surtout met en évidence en ROUGE (`🔴`) les `Breaking Changes` possibles.

### Étape 3 : Audit Zéro-Trust et Contrat Conteneur (BLOQUANT)
1. **Zéro-Trust** : L'agent DOIT rechercher l'existence de fuites de dépendances FASTAPI. Demande à l'utilisateur de valider que la CI est verte, ou lance un audit rapide (par exemple `python3 scripts/run_tests.sh` via le tool de `run_command` s'il est compatible, ou une recherche statique de router sans `dependencies=[Depends(verify_jwt)]`).
2. **Container Contract** : Vérifie de manière aléatoire/statique sur les API ciblées par la MEP que leurs `Dockerfile` comportent la directive `USER` pour éviter le run root et que le point d'entrée est robuste (`CMD ["python3"...]`).
> 🛑 Si cet audit montre une régression de sécurité flagrante, **interrompt l'assistance au déploiement et propose le correctif.**

### Étape 4 : Validation des Migrations Liquibase (BLOQUANT)
1. Liste le répertoire des migrations : `db_migrations/changelogs/`.
2. Analyse les `changelog.yaml` modifiés ou nouvellement créés qui impacteront la DB de production.
3. 🛑 **Point d'arrêt expert** : Vérifie systématiquement que chaque nouveau changeset contient un champ ou une instruction de `rollback`. S'il est absent (pour une altération de schéma lourde comme `dropColumn`), bloque et justifie le danger à l'humain.

### Étape 5 : Exécution du Plan d'Impact Infra
1. **Commande de Plan** : Tente d'exécuter l'analyse d'infrastructure dans le terminal de l'utilisateur avec `run_command` :
   `python3 platform-engineering/manage_env.py plan --env prd`
   *(Note : Si une erreur de dépendances comme "yaml missing" survient, notifie l'utilisateur d'activer son environnement virtuel Python associé au projet en cours, ou utilise `.antigravity_env/bin/python` de manière proactive si disponible).*
2. **Analyse du résultat Terraform** : Ne copie pas les longs logs, fournis un tableau vulgarisé :
   - 🟢 Piliers Cloud créés.
   - 🔵 Modifications légères (Ex: scale param, env vars modifiée).
   - 🔴 Piliers Cloud détruits (WARNING !).

### Étape 6 : Finalisation - Smoke Tests
Avant de donner la commande complète `deploy` pour la PROD, donne un résumé des *Smoke Tests* attendus post-MEP :
- Cible API à faire pinger en healthcheck direct et URLs Cloud Run.
- Requête/Commande à utiliser pour invalider le cache Redis si la BDD a subit de grosses altérations.
- Vérification que la télémétrie (`test_zero_trust` / traces) remonte bien dans `market_mcp`/Cloud Logging.
