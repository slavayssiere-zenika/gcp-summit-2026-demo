---
description: Automatisation de la préparation au push Git (Tests, Specs, Changelog, Commit)
---

Voici les étapes strictes à suivre pour l'exécution d'un workflow de préparation `/git-push` :

1. **Relancer les tests unitaires via script parallèle**
   Exécute le script bash dédié pour effectuer la couverture en simultané sur chaque environnement. L'arrêt est requis si le script est en erreur.
// turbo
```bash
bash scripts/run_tests.sh
```

2. **Génération automatique ou mise à jour des spécifications techniques (`spec.md`)**
   Régénère le document API via OpenAPI.
// turbo
```bash
test_env/bin/python scripts/generate_specs.py
```

3. **Génération et mise à jour dynamique du `changelog.md`**
   Insère les nouveaux bilans de couverture.
// turbo
```bash
test_env/bin/python scripts/generate_changelog.py
```

4. **Formater le code Terraform**
   Applique le formatage standard HashiCorp sur les fichiers d'infrastructure du dossier bootstrap.
// turbo
```bash
terraform -chdir=bootstrap fmt -recursive
terraform -chdir=platform-engineering/terraform fmt -recursive
```

5. **Nettoyer les fichiers temporaires**
   Supprime les archives, logs et gros exécutables obsolètes avant le commit pour éviter les rejets de push.
// turbo
```bash
rm -f *.tar.gz otelcol-contrib output.log *.patch patch_*.py test_*.py
```

6. **Ajouter les fichiers via git add**
   Ajoute l'ensemble des fichiers modifiés (y compris le nouveau `changelog.md` et les scripts modifiés) au staging Git.
// turbo
```bash
git add .
```

7. **Vérifier la non-divulgation des secrets**
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

8. **Ajouter les fichiers via git commit**
   Rédige un message de commit très court résumant la fonctionnalité.
   **Contrainte stricte :** Le texte du commit doit faire **entre 5 et 8 mots maximum**.
```bash
# Remplace <MESSAGE> par ton court message de commit :
git commit -m "<MESSAGE>"
```

9. **Push vers le dépôt distant (git push)**
   Envoie les modifications commitées vers la branche distante.
// turbo
```bash
git push
```

