---
description: Aide au diagnostic de bug — collecte structurée du contexte et proposition d'un plan de correction
---

Voici les étapes strictes à suivre pour l'exécution du workflow `/bug` :

### Étape 0 : Recherche en mémoire (OBLIGATOIRE)

// turbo
Avant toute analyse, rechercher dans la base de connaissance :
1. `search_past_errors` avec les mots-clés de l'erreur
2. `search_learnings` avec la technologie concernée

Si un résultat pertinent est trouvé (score RRF > 0), appliquer la solution mémorisée directement sans re-analyser.

1. **Collecter le contexte automatique**
   Récupère les informations disponibles dans l'environnement courant pour pré-remplir le template :
   - Fichier actif dans l'éditeur (service impacté)
   - Dernier output de commande échoué si disponible
   - Environnement cible (déduire depuis les variables d'environnement ou le contexte de la conversation)

2. **Afficher le template de rapport de bug**
   Présente le template suivant à l'utilisateur en pré-remplissant les champs déduits à l'étape 1. Les champs non déduits sont laissés vides avec une indication `[À COMPLÉTER]` :

```
🐛 RAPPORT DE BUG
─────────────────────────────────────────

[CONTEXTE]
  Service     : <nom du microservice ou composant impacté>
  Environnement : <dev | uat | prd>
  Fichier     : <chemin du fichier concerné si pertinent>

[SYMPTÔME]
  Description : [À COMPLÉTER — ce qui se passe concrètement]
  Log / Erreur :
  ```
  [À COMPLÉTER — coller ici le stacktrace ou message d'erreur complet]
  ```

[OBJECTIF]
  Succès = [À COMPLÉTER — ce qui doit fonctionner une fois le bug corrigé]

[CONTRAINTES]
  Ne pas toucher : [À COMPLÉTER — ressources ou fichiers à ne pas modifier]
  Priorité      : <haute | normale | basse>

─────────────────────────────────────────
```

3. **Demander à l'utilisateur de compléter les champs manquants**
   Indiquer clairement quels champs sont incomplets et demander à l'utilisateur de les fournir avant de procéder au diagnostic.

4. **Analyser et diagnostiquer**
   Une fois le template complété, effectuer le diagnostic :
   - Identifier la cause racine probable
   - Lister les fichiers susceptibles d'être impactés
   - Proposer un plan de correction en 2-3 étapes maximum

5. **Proposer le plan de correction**
   Présenter le plan sous cette forme :

```
🔧 PLAN DE CORRECTION
─────────────────────────────────────────
Cause racine probable : <explication concise>

Étapes :
1. <action précise sur fichier X>
2. <action précise sur fichier Y>
3. <commande de vérification>

Critère de validation : <comment vérifier que le bug est corrigé>
─────────────────────────────────────────
Procéder à la correction ? (oui / non / modifier le plan)
```

6. **Attendre la confirmation de l'utilisateur**
   Ne pas commencer la correction avant que l'utilisateur ait validé le plan ou demandé des modifications.

### Étape 7 : Post-Mortem Obligatoire

Une fois la correction confirmée et implémentée avec succès par l'agent, l'agent DOIT systématiquement mémoriser l'erreur.
**L'agent utilisera l'outil MCP `log_error_and_solution`** pour documenter la stacktrace originale, le contexte et la solution qui a fonctionné, AVANT d'annoncer à l'utilisateur que le bug est résolu.
