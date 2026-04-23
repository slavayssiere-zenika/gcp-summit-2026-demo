---
description: Enregistre rapidement un bug et sa solution dans la base de connaissances MCP (Post-Mortem d'urgence).
---

### Objectif
Ce workflow permet de forcer l'enregistrement d'un bug et de sa solution dans la mémoire MCP lorsque l'agent a résolu un problème de manière ad-hoc sans passer par le workflow `/bug`, et qu'il a oublié de le documenter.

### Actions de l'Agent

Dès que l'utilisateur invoque ce workflow, l'agent DOIT agir immédiatement et de manière autonome :

1. **Analyse du contexte récent** : L'agent scanne les derniers échanges de la conversation courante pour extraire :
   - Le message d'erreur ou le symptôme (stacktrace, log, exception).
   - Le contexte (service concerné, fichier impacté, technologie).
   - La solution technique qui a été implémentée avec succès (code exact, configuration, commande).

2. **Appel de l'outil MCP (OBLIGATOIRE)** : L'agent appelle immédiatement l'outil MCP `mcp_antigravity-memory_log_error_and_solution` avec les informations extraites.

3. **Confirmation** : L'agent informe brièvement l'utilisateur que le post-mortem a bien été enregistré.
