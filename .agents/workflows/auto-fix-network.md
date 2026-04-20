# Auto-Correction des Erreurs Réseau et Protocoles (MCP / API)

**Contexte** : Lors de l'exécution de scripts générés pour interagir avec des serveurs locaux (ex: serveurs MCP, API FastAPI, bases de données), tu peux rencontrer des erreurs de réseau ou de protocole (`ConnectionRefusedError`, `httpx.StreamConsumed`, `RemoteProtocolError`, ou des rejets de format JSON-RPC `Invalid request parameters`).

**Directives Strictes pour l'Agent Antigravity :**

1. **Autonomie Totale** : Ne demande JAMAIS à l'utilisateur d'investiguer un problème de port, de réseau ou de config API. Tu dois repérer, analyser et contourner le blocage par toi-même.
2. **Analyse de la Couche Transport (L4/L7)** :
   - En cas de `Connection Refused` : Vérifie immédiatement tous les bindings via `run_command` avec `lsof -i -P -n | grep LISTEN`. Ton environnement dockerise peut forcer l'usage d'IPv6 (`[::1]`) plutôt qu'IPv4 (`127.0.0.1`). Ajuste tes payloads.
3. **Contournement Actif par la Couche Données (Bypass Protocol)** :
   - Si l'interface de haut niveau (HTTP, SSE, client MCP) bloque ta requête à cause d'une structure malformée ou de spécifications inaccessibles, **abandonne la couche API**.
   - Cherche la source de données réelle (ex: port 5432 pour PostgreSQL, 6379 pour Redis).
   - Récris ton script interne de manière à interagir directement au niveau base de données ou librairie native (en installant automatiquement les dépendances `sqlalchemy`, `pgvector`, etc., dans un environnement `.venv` temporaire).
4. **Exécution Silencieuse** : Itère jusqu'à réussir l'objectif métier (insertion, lecture) avant de rendre la main à l'utilisateur avec le message de succès brut.

// turbo-all
