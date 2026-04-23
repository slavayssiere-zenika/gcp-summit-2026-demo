---
description: Analyse l'état de la dette technique et propose un plan de remboursement priorisé.
---

### Objectif
Analyser l'état de la dette technique et proposer un plan de remboursement priorisé.

### Étape 1 : Audit du todo.md
Lire le fichier `todo.md` à la racine, identifier tous les items non cochés `[ ]` et les classer par impact métier et technique (CRITIQUE / MOYEN / FAIBLE).

### Étape 2 : Audit des ADRs
Scanner `AGENTS.md` (particulièrement la section 11 et suivantes) pour identifier les mentions "À terme" et "Axe N". Vérifier si leur statut est répercuté et planifié dans `todo.md`.

### Étape 3 : Analyse des fichiers temporaires
// turbo
Rechercher les fichiers temporaires, archives obsolètes ou fichiers de debug :
```bash
find . -maxdepth 2 -name "*.tar.gz" -o -name "scratch_*.py" -o -name "*.patch"
```
Proposer leur suppression si aucune utilité n'est identifiée.

### Étape 4 : Rapport de dette
Générer un artefact `dette_technique_<date>.md` contenant un tableau priorisé des actions de remboursement de la dette technique (refactoring, mises à jour, documentation, nettoyage).
