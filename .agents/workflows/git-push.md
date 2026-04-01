---
description: Automatisation de la préparation au push Git (Tests, Specs, Changelog, Commit)
---

Voici les étapes strictes à suivre pour l'exécution d'un workflow de préparation `/git-push` :

1. **Relancer les tests unitaires pour chaque projet avec calcul de la couverture (Coverage)**
   Exécute la suite de tests sur tous les microservices en calculant explicitement le code coverage pour générer les rapports finaux. (Ces données seront nécessaires pour le changelog).
// turbo
```bash
python -m pytest agent_api competencies_api cv_api items_api prompts_api users_api --cov=agent_api --cov=competencies_api --cov=cv_api --cov=items_api --cov=prompts_api --cov=users_api
```

2. **Relancer le build des specs**
   Si des spécifications techniques comme des fichiers `spec.md` (pour OpenAPI) ou de la documentation existante nécessitent d'être générés ou mis à jour via des scripts/outils existants, exécute-les. En l'absence de script de build, mets toi-même à jour les fichiers de spécification comme `users_api/spec.md` ou `cv_api/spec.md` avec les dernières fonctionnalités ajoutées en utilisant tes propres capacités d'analyse de code.

3. **Générer et ajouter les nouveautés et la couverture au `changelog.md`**
   - Analyse les modifications locales (`git diff`, `git status`, logs locaux) qui n'ont pas encore été pushées pour formuler un résumé clair des fonctionnalités ajoutées.
   - Extrait les statistiques de coverage issues de l'exécution précédente de pytest pour chaque API (`agent_api`, `competencies_api`, etc.).
   - Insère au sein du `changelog.md` (crée-le en racine s'il manque) ton résumé (avec la date du jour) **ET** ajoute systématiquement un tableau Markdown récapitulatif du taux de couverture (Code Coverage) pour chaque API.

4. **Ajouter les fichiers via git add**
   Ajoute l'ensemble des fichiers modifiés (y compris le nouveau ou l'ancien `changelog.md`) au staging Git.
// turbo
```bash
git add .
```

5. **Ajouter les fichiers via git commit**
   Rédige un message de commit très court résumant la fonctionnalité.
   **Contrainte stricte :** Le texte du commit doit faire **entre 5 et 8 mots maximum**.
```bash
# Remplace <MESSAGE> par ton court message de commit :
git commit -m "<MESSAGE>"
```

6. **Push vers le dépôt distant (git push)**
   Envoie les modifications commitées vers la branche distante.
// turbo
```bash
git push
```
