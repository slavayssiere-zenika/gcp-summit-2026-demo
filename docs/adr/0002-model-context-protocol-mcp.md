# ADR 0002 : Adoption de Model Context Protocol (MCP)

## Statut
Accepté

## Contexte
Dans l'ère des agents autonomes (LLMs), interroger différentes APIs internes à l'aide de prompts et fonctions ("Function Calling") est verbeux. À mesure que les microservices Zenika évoluent, maintenir la liste colossale de schémas OpenAPI au sein du contexte de l'Agent Master devenait fragile. L'assistant nécessitait un contrat standard pour "découvrir" et "consommer" des capacités distribuées sans refactorisation centrale du LLM.

## Décision
- L'infrastructure expose les capacités à l'IA *uniquement* à travers la spécification standard **Model Context Protocol (MCP)**.
- Des "Compagnons MCP" (`market_mcp`, `cv_mcp`, `items_mcp`) sont construits sous forme d'images séparées pour se coupler à chaque backend ou groupe de domaine.
- L'orchestrateur (`agent_api`) agit en tant que Client MCP Unique ; il scrute son écosystème via des variables d'environnement (`*_MCP_URL`) et liste les outils (`Tools`) dynamiquement mis à disposition.
- On contraint fortement les appels asynchrones à repasser à `REST` là où le SSE (Server Sent Events) ajoute du statique non compatible avec notre infrastructure Cloud Run.

## Conséquences
- **Positives :**
  - **Découplage Total Agent / Métier :** Une équipe backend peut ajouter une compétence au bot IA via son conteneur `*_mcp`, sans modifier `agent_api`.
  - **Transparence Sémantique :** L'agent IA hérite directement des *Docstrings* pour savoir comment s'adresser au système.
- **Négatives :** 
  - La taxonomie des conteneurs double (ajout d'une empreinte processeur supplémentaire pour héberger chaque serveur MCP Python).
- **Risques :** L'authentification devient critique, car le routeur HTTP MCP doit relayer aveuglément les identités d'appel initiales.
