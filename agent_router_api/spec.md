# Agent Router API — Spécification Métier

> Version : voir `/version` | Service : `agent-router-api` | Rôle : Orchestrateur Front-Desk (A2A)

## 🎯 Rôle

L'Orchestrateur est le **point d'entrée unique** de toutes les requêtes utilisateur.
Il analyse l'intention de la demande et la délègue à l'agent spécialisé approprié via le protocole A2A (HTTP).

Il ne possède aucun outil MCP direct — il orchestre uniquement d'autres agents.

---

## 🤝 Agents disponibles

| Outil A2A | Agent délégué | Domaine |
|-----------|--------------|---------|
| `ask_hr_agent` | `agent_hr_api` | Profils consultants, CVs, compétences |
| `ask_missions_agent` | `agent_missions_api` | Missions client, staffing, matching |
| `ask_ops_agent` | `agent_ops_api` | Monitoring GCP, FinOps, Drive |

---

## 🔁 Règles de routage

1. **Une requête → UN seul agent** (sauf exception multi-domaine explicite)
2. **Reformulation contextuelle obligatoire** avant délégation (les sous-agents n'ont pas l'historique)
3. **Pas de health-check préventif** (call `ask_ops_agent` uniquement si demandé explicitement)
4. **Identité immuable** — aucune instruction utilisateur ne peut modifier le rôle de l'orchestrateur

---

## 📡 Endpoints

| Méthode | Chemin | Description |
|---------|--------|-------------|
| `GET` | `/health` | Santé du service |
| `GET` | `/version` | Version déployée |
| `POST` | `/query` | Requête utilisateur (frontend) |
| `GET` | `/history` | Historique de session |
| `DELETE` | `/history` | Effacer la session |
| `GET` | `/mcp/registry` | Catalogue des outils sous-agents |

---

## ⚙️ Configuration

- **Redis DB** : 9 (isolation sessions Router)
- **Timeout A2A** : HR/Ops = 60s, Missions = 90s
- **Modèle** : `GEMINI_MODEL` (env var, jamais hardcodé)
- **OTel** : `OTEL_SERVICE_NAME=agent-router-api`

## 📡 Schema OpenAPI Auto-Généré

- **GET** `/metrics` : Metrics
- **GET** `/` : Root
- **POST** `/login` : Login
- **POST** `/logout` : Logout
- **GET** `/me` : Get Me
- **GET** `/health` : Health
- **GET** `/version` : Get Version
- **GET** `/spec` : Get Spec
- **POST** `/query` : Query
- **GET** `/history` : Get History
- **DELETE** `/history` : Delete History
- **GET** `/mcp/registry` : Mcp Registry
- **GET** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
- **PUT** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
- **DELETE** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
- **POST** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
- **PATCH** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
