# Agent HR API — Spécification Métier

> Version : voir `/version` | Service : `agent-hr-api` | Rôle : Expert RH, Talent & Compétences

## 🎯 Rôle

L'Agent HR est le **spécialiste des ressources humaines** de la plateforme Zenika.
Il gère exclusivement les profils consultants, leurs CVs et leurs compétences.

> ❌ **HORS PÉRIMÈTRE** : Toute demande de missions ou de staffing → déléguer à `agent_missions_api`

---

## 🛠️ Outils MCP disponibles

| MCP | Outils principaux |
|-----|------------------|
| `users_mcp` | `list_users`, `get_user`, `search_users`, `get_users_by_tag` |
| `competencies_mcp` | `get_competency_tree`, `get_user_competencies`, `list_user_competencies` |
| `cv_mcp` | `search_best_candidates`, `get_candidate_rag_context`, `analyze_cv`, `get_user_missions` |
| `items_mcp` | `list_items`, `get_item` (équipements, tags) |
| `missions_mcp` | `get_user_missions` — lecture seule pour enrichissement de profil uniquement |
| `drive_mcp` | `sync_drive_folder`, `list_drive_files` (import CVs) |

---

## 🗺️ Cas d'usage couverts

1. **Recherche sémantique** : "Qui maîtrise React + TypeScript ?" → `search_best_candidates`
2. **Profil utilisateur** : "Donne-moi le profil de Jean Martin" → `search_users` + `get_user`
3. **Compétences** : "Quelles sont les compétences de [nom] ?" → `get_user_competencies`
4. **Import CV** : "Import les CVs du dossier Drive" → `sync_drive_folder` + `analyze_cv`
5. **Historique consultant** : "Quelles missions a faites Sophie ?" → `get_user_missions` (lecture seule)

---

## 🚨 Règle anti-hallucination

Chaque consultant cité **doit avoir un ID entier** issu d'un appel outil.  
Il est strictement interdit de citer un profil sans ID vérifié.

---

## 📡 Endpoints

| Méthode | Chemin | Description |
|---------|--------|-------------|
| `GET` | `/health` | Santé du service |
| `GET` | `/version` | Version déployée |
| `POST` | `/query` | Requête directe |
| `POST` | `/a2a/query` | Point d'entrée A2A (appelé par le Router) |
| `GET` | `/history` | Historique de session |
| `DELETE` | `/history` | Effacer la session |
| `GET` | `/mcp/registry` | Catalogue des outils MCP chargés |
| `GET` | `/spec` | Cette spécification |

---

## ⚙️ Configuration

- **Redis DB** : 10 (isolation sessions HR)
- **Session** : éphémère par requête (UUID frais)
- **Modèle** : `GEMINI_MODEL` (env var)
- **OTel** : `OTEL_SERVICE_NAME=agent-hr-api`
- **Anti-hallucination** : guardrail actif (0 tool call → warning dans les steps)

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
- **POST** `/a2a/query` : A2A Query
- **GET** `/history` : Get History
- **DELETE** `/history` : Delete History
- **GET** `/mcp/registry` : Mcp Registry
- **PATCH** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
- **GET** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
- **POST** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
- **PUT** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
- **DELETE** `/mcp/proxy/{server_name}/{path}` : Proxy Mcp
