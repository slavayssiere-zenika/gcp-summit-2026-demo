---
description: Automatisation de la préparation au push Git (Tests, Specs, Changelog, Commit)
---

Voici les étapes strictes à suivre pour l'exécution d'un workflow de préparation `/git-push` :

### Étape 0 : Lire les README.md des services modifiés
Avant de lancer les tests, identifier les services modifiés depuis le dernier commit et lire leur `README.md`.
Si un README est obsolète ou manquant pour un service modifié, le mettre à jour **maintenant** (avant le commit).

// turbo
```bash
git diff --name-only HEAD 2>/dev/null | grep -E "^[a-z_]+_api/|^agent_[a-z_]+/|^[a-z_]+_mcp/" | cut -d/ -f1 | sort -u | while read svc; do echo "=== $svc ==="; [ -f "$svc/README.md" ] && head -10 "$svc/README.md" || echo "MANQUANT"; done
```

1. **Relancer les tests unitaires via script parallèle**
   Exécute le script bash dédié pour effectuer la couverture en simultané sur chaque environnement. L'arrêt est requis si le script est en erreur.
   > ⚠️ **Note** : Ce script exécute uniquement les tests présents dans chaque répertoire de service.
   > Il n'effectue PAS de vérification de couverture minimale (voir étape 1b ci-dessous).
// turbo
```bash
bash scripts/run_tests.sh
```

2. **Tester la logique d'infrastructure (`manage_env.py`)**
   Valide les fonctions critiques de déploiement : construction des URLs d'images, priorité des versions (YAML > VERSION local), cohérence des fichiers `envs/*.yaml`.
   L'arrêt est requis si les tests échouent.
// turbo
```bash
test_env/bin/pytest platform-engineering/tests/test_manage_env.py -v --tb=short
```


3. **Synchronisation des System Prompts vers `prompts_api`**
   Met à jour tous les system prompts des agents en base (AlloyDB via `prompts_api`) pour que GCP dev reçoive les dernières instructions. Invalide les caches Redis associés.
   Pré-requis : la variable `$DEV_BASE_URL` doit être définie. Le mot de passe admin est récupéré via Terraform output.
// turbo
```bash
export PATH="/opt/homebrew/bin:$PATH"
if [ -n "$DEV_BASE_URL" ]; then
  ADMIN_PWD=$(cd platform-engineering/terraform && terraform output -raw admin_password 2>/dev/null || echo "")
  if [ -n "$ADMIN_PWD" ]; then
    test_env/bin/python scripts/sync_prompts.py \
      --url "$DEV_BASE_URL/api/prompts" \
      --email "admin@zenika.com" \
      --password "$ADMIN_PWD"
  else
    echo "[!] ADMIN_PWD introuvable via terraform output — sync_prompts ignoré."
  fi
else
  echo "[!] DEV_BASE_URL non défini — sync_prompts ignoré (mode local)."
fi
```

4. **Génération automatique ou mise à jour des spécifications techniques (`spec.md`)**
   Régénère le document API via OpenAPI.
// turbo
```bash
test_env/bin/python scripts/generate_specs.py
```

5. **Génération et mise à jour dynamique du `changelog.md`**
   Insère les nouveaux bilans de couverture.
// turbo
```bash
test_env/bin/python scripts/generate_changelog.py
```

6. **Mise à jour de la documentation des pipelines (`docs/pipelines.md`)**
   Régénère la documentation complète des pipelines CI/CD : services déployables, options de versioning, matrice des environnements (`dev/uat/prd`), flux `deploy.sh` et `manage_env.py`.
// turbo
```bash
test_env/bin/python scripts/generate_pipeline_docs.py
```

7. **Révision des README.md (Services, Agents, APIs)**
   Met à jour la documentation (fichiers `README.md`) de l'ensemble des microservices, agents et APIs pour s'assurer de leur cohérence avec l'implémentation actuelle.
   > ⚠️ **IMPORTANT** : `generate_readmes.py` DOIT effectuer une **mise à jour partielle** — uniquement les sections générées automatiquement (ex: liste des routes, variables d'environnement extraites du Dockerfile).
   > Il est **strictement interdit** d'écraser les sections rédigées manuellement (`## Architecture`, `## Points d'attention`, `## Dernière modification`). Ces sections contiennent la mémoire opérationnelle du service et ne doivent pas être régénérées.
// turbo
```bash
test_env/bin/python scripts/generate_readmes.py
```

8. **Formater le code Terraform**
   Applique le formatage standard HashiCorp sur les fichiers d'infrastructure du dossier bootstrap.
// turbo
```bash
export PATH="/opt/homebrew/bin:$PATH"
terraform -chdir=bootstrap fmt -recursive
terraform -chdir=platform-engineering/terraform fmt -recursive
```

9. **Nettoyer les fichiers temporaires**
   Supprime les archives, logs et gros exécutables obsolètes avant le commit pour éviter les rejets de push.
   > ⚠️ **ATTENTION** : Ne jamais supprimer les fichiers `test_*.py` —
   > ce sont les tests unitaires, leur suppression serait catastrophique pour la CI.
// turbo
```bash
rm -rf frontend/dist frontend/node_modules
rm -f */pytest.log */coverage.json *_test.db
rm -f *.tar.gz otelcol-contrib output.log *.patch patch_*.py
```

10. **Ajouter les fichiers via git add**
   Ajoute l'ensemble des fichiers modifiés (y compris le nouveau `changelog.md`, `docs/pipelines.md` et les scripts modifiés) au staging Git.
// turbo
```bash
git add .
```

11. **Vérifier la non-divulgation des secrets**
   Parse le fichier `secrets.sh` et s'assure qu'aucune des valeurs des variables secrètes n'est introduite dans les fichiers prêts à être commités. Arrête le script en erreur si une faille est détectée.
// turbo
```bash
if [ -f "secrets.sh" ]; then
  SECRETS=$(grep "export " secrets.sh | awk -F '=' '{print $2}' | tr -d '"'\'' ')
  for SECRET in $SECRETS; do
    if [ ${#SECRET} -gt 12 ]; then
      if git diff --cached HEAD 2>/dev/null | grep '^+' | grep -v '^+++' | grep -Fq "$SECRET"; then
        echo "[!] ERREUR CRITIQUE : Une valeur extraite de secrets.sh est sur le point d'être commitée. Opération annulée."
        exit 1
      fi
    fi
  done
  echo "[+] SÉCURITÉ : Aucun ajout de secret provenant de secrets.sh détecté, le commit est autorisé."
fi
```

12. **Ajouter les fichiers via git commit**
   Rédige un message de commit très court résumant la fonctionnalité.
   **Contrainte stricte :** Le texte du commit doit faire **entre 5 et 8 mots maximum**.
```bash
# Remplace <MESSAGE> par ton court message de commit :
git commit -m "<MESSAGE>"
```

13. **Informer l'utilisateur**
   Indiquer à l'utilisateur que le commit est prêt et qu'il peut faire `git push` manuellement depuis son terminal (l'agent n'a pas les droits SSH nécessaires).



