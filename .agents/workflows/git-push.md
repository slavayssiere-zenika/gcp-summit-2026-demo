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
rm -f *.tar.gz otelcol-contrib output.log *.patch
```

6. **Ajouter les fichiers via git add**
   Ajoute l'ensemble des fichiers modifiés (y compris le nouveau `changelog.md` et les scripts modifiés) au staging Git.
// turbo
```bash
git add .
```

7. **Ajouter les fichiers via git commit**
   Rédige un message de commit très court résumant la fonctionnalité.
   **Contrainte stricte :** Le texte du commit doit faire **entre 5 et 8 mots maximum**.
```bash
# Remplace <MESSAGE> par ton court message de commit :
git commit -m "<MESSAGE>"
```

8. **Push vers le dépôt distant (git push)**
   Envoie les modifications commitées vers la branche distante.
// turbo
```bash
git push
```
