# Agent API Specification (GEMINI)

## Présentation
Le composant **Agent API** est le cerveau orchestrateur ("The Conductor") du réseau Zenika.
Contrairement aux autres microservices, il ne possède aucune base de données (Stateless). Son rôle est d'héberger le modèle d'Intelligence Artificielle Google Gemini (via l'ADK Agent Development Kit) et d'orienter le raisonnement de ce dernier grâce au standard interopérable MCP (Model Context Protocol).

---

## 🏛️ Architecture et Modèle LLM
### 1. Le Cerveau (`agent.py`)
Ce moteur propulse un agent IA asynchrone défini par :
- **System Prompt** : Un encadrement délimitant son persona (l'Assistant de consultation expert Zenika) et son comportement linguistique (Poli, concis, direct).
- **Tooling Engine** : Une liste exhaustive de +20 fonctions (Wrappers) que l'IA peut appeler arbitrairement pour questionner l'architecture (Users, Items, Competencies) au travers de protocoles réseau SSE.

### 2. Connecteurs MCP (Server-Sent Events)
L'Agent charge `mcp.get_mcp_client()` vers 3 adresses indépendantes du réseau Docker (ex: `http://users_mcp:5000/mcp/sse`). Il maintient sa mémoire active afin d'agréger les retours distants.

---

## 🛠️ Endpoints Principaux
Cet API est l'unique canal d'interaction autorisé pour la Console Chat Front-End (Vue.js).

### Interaction avec le Modèle NLP
- `POST /query` : Exécute une prompt libre.
  - **Payload** : `{"query": "Liste moi les ordinateurs de tel salarié"}`
  - **Process** : L'Agent décode, interroge dynamiquement ses Servers MCP reliés, aggrège les résultats (ex: ordi HP + ID employé), puis renvoie formellement un condensé de l'historique de recherche + le texte naturel validant.

### Health & Supervision
- `GET /health` : Vérifie que le service Web Gemini est sous tension et que la clé _GOOGLE_API_KEY_ est valide.

---

## 🚨 Sécurité Cognitive (Stateless & Pass-through)
Bien que super-intelligent, cet Agent **n'avertit pas les règles structurelles**.
Si un Endpoint sous-jacent (Items) refuse une attribution ou lève un code HTTP 400 (Violation parentale de Compétence), c'est le Wrapper Python de l'Agent qui réceptionne l'exception. Gemini interprète alors vocalement cet "échec" vers l'utilisateur final.
