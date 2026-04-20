# Agent Missions API — Spécification Métier

> Version : voir `/version` | Service : `agent-missions-api` | Rôle : Staffing Director

## 🎯 Rôle

L'Agent Missions est le **directeur du staffing** de la plateforme Zenika.
Il se charge de la recherche des bons profils (consultants) pour les missions client, de l'orchestration des affectations et de l'analyse des besoins de staffing.

> ❌ **HORS PÉRIMÈTRE** : La modification d'un CV, l'ajout de compétences ou l'analyse technique d'un CV se fait par `agent_hr_api`. L'Agent Missions ne gère que l'affectation sur les missions.

---

## 🛠️ Outils MCP disponibles

| MCP | Outils principaux |
|-----|------------------|
| `missions_mcp` | `create_mission`, `list_missions`, `get_mission`, `search_missions`, `update_mission`, etc. |
| `cv_mcp` | `search_best_candidates`, `get_candidate_rag_context` (évaluation pour staffing) |
| `users_mcp` | `get_user`, `search_users` (pour associer le consultant formellement) |
| `competencies_mcp` | Consultatif (pour vérifier la taxonomie de compétences demandée par le client) |

---

## 🗺️ Cas d'usage couverts

1. **Staffing & Proposition** : "Trouve 3 candidats pour la mission React chez BNP" → `search_best_candidates` depuis cv_mcp.
2. **Gestion des missions** : "Crée une nouvelle mission Fullstack Java/Vue pour la SocGen" → `create_mission`.
3. **Recherche de capacité** : "Sur quelle mission est staffé Sébastien ?" → utilise les données de profils pour remonter l'affectation.

---

## 🚨 Règle anti-hallucination

Tous les noms de consultants ou propositions de profils DOIVENT s'appuyer sur des données réelles issues de l'API. Ne pas inventer de CVs ni de collaborateurs.

---

## ⚙️ Configuration

- **Redis DB** : 12 (isolation sessions Missions)
- **Session** : éphémère par requête (UUID frais)
- **Modèle** : `GEMINI_MODEL` (env var)
- **OTel** : `OTEL_SERVICE_NAME=agent-missions-api`
- **Anti-hallucination** : guardrail actif (0 tool call → warning dans les steps)

## 📡 Schema OpenAPI Auto-Généré

- **GET** `/metrics` : Metrics
- **GET** `/health` : Health
- **GET** `/version` : Version
- **POST** `/query` : Query Agent
- **POST** `/a2a/query` : A2A Query Agent
- **GET** `/history` : Get History
- **DELETE** `/history` : Delete History
- **GET** `/spec` : Get Spec
- **GET** `/mcp/registry` : Mcp Registry
