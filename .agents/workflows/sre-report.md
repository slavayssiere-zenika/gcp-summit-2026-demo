---
description: Workflow d'automatisation SRE pour identifier, analyser et proposer des remédiations aux erreurs de production via l'API Prompts.
---

Ce workflow permet de générer un rapport SRE automatisé à partir des erreurs loggées et de nettoyer les erreurs traitées.

### Étape 1 : Récupération des erreurs
Exécute le script Python `sre_report_runner.py` situé à la racine du projet (`python3 sre_report_runner.py`). Ce script va s'authentifier et récupérer tous les prompts d'erreur commençant par `error_correction:`.

### Étape 2 : Analyse et Remédiation
Le script vérifie le code source existant pour s'assurer que l'erreur n'a pas déjà été résolue. S'il trouve des erreurs non corrigées, il produit un rapport détaillé.

### Étape 3 : Nettoyage
Le script appelle l'endpoint `DELETE /prompts/{key}` de `prompts_api` pour supprimer de la base Redis les erreurs qui ont été traitées ou qui sont obsolètes.

### Étape 4 : Consultation du Rapport
Lis le fichier généré `sre_report.md` à la racine pour appliquer le plan d'implémentation et corriger les bugs restants.
