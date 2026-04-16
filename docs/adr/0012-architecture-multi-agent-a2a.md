# ADR 0012 : Architecture Multi-Agent A2A (Agent-to-Agent)

## Statut
Accepté

## Contexte

La complexité fonctionnelle de la plateforme Zenika Console couvre trois domaines métiers intrinsèquement distincts :

1. **RH & Staffing** (gestion de profils, CVs, compétences, recherche vectorielle)
2. **Missions & Matching** (cycle de vie des missions client, scoring, recommandation d'équipe)
3. **Ops & FinOps** (monitoring GCP, coûts IA, intégration Google Drive, logs)

Une architecture mono-agent classique — où un seul LLM orchestre l'ensemble des outils — atteignait rapidement ses limites :

- **Saturation du contexte Gemini** : exposer l'intégralité des outils MCP (~30+) à un seul agent alourdissait la fenêtre de contexte, dégradait les performances et augmentait le coût par token.
- **Hallucinations de routage** : un LLM généraliste ne distinguait pas fiablement entre une requête de staffing et une question FinOps, entraînant des appels d'outils incohérents.
- **Couplage fort** : un changement de prompt ou d'outil dans un domaine impactait le comportement global du système entier.
- **Tests et observabilité impossibles** : il était impossible d'isoler et de tester le raisonnement d'un domaine spécifique sans exécuter l'agent complet.

Il fallait une architecture permettant une **séparation claire des responsabilités entre agents**, la résilience individuelle, et une observabilité granulaire des chaînes de raisonnement.

## Décision

Adoption d'une architecture **Multi-Agent hiérarchique à deux niveaux** reposant sur le protocole **A2A (Agent-to-Agent) via HTTP REST** (et non SSE) :

### Niveau 1 — Router Agent (`agent_router_api`)

- **Rôle** : Front-desk unique, point d'entrée de toutes les requêtes utilisateur (interface Vue.js → `/query`).
- **Modèle LLM** : `GEMINI_MODEL` (env var), contexte volontairement réduit à 3 outils de délégation A2A.
- **Outils** : `ask_hr_agent`, `ask_ops_agent`, `ask_missions_agent` — aucun outil MCP métier direct.
- **Responsabilité de routage** : analyse l'intention de la requête, reformule le contexte pour le sous-agent cible, et agrège la réponse finale (texte + métadonnées `steps`, `thoughts`, `usage`).
- **Session** : maintient l'historique conversationnel long terme via `RedisSessionService` (TTL 30 jours, clé `adk:sessions:{session_id}`).

### Niveau 2 — Sous-Agents Spécialisés

| Agent | Service | Domaine | Outils MCP |
|---|---|---|---|
| `agent_hr_api` | Port 8080 | RH, CVs, compétences, recherche vectorielle | `users_mcp`, `items_mcp`, `competencies_mcp`, `cv_mcp`, `missions_mcp` |
| `agent_ops_api` | Port 8080 | Monitoring, FinOps, Drive, Cloud Logging | `drive_mcp`, `market_mcp` |
| `agent_missions_api` | Port 8080 | Missions client, staffing, scoring | `missions_mcp`, `cv_mcp`, `users_mcp` |

**Caractéristiques communes des sous-agents :**

- **Sessions éphémères** : chaque requête A2A génère un `ephemeral_session_id` (UUID4 frais). Le sous-agent ne voit jamais l'historique conversationnel du Router, évitant la contamination de contexte entre requêtes successives.
- **Détection d'hallucination** : guardrail actif — si le LLM produit une réponse sans avoir appelé aucun outil MCP, un avertissement `GUARDRAIL` est injecté dans les `steps` et le texte de réponse est préfixé d'une alerte visible.
- **Cache MCP** : les définitions de tools sont mises en cache 5 minutes (`_TOOLS_CACHE_TTL = 300s`) pour éviter 5 appels HTTP synchrones par requête.
- **FinOps** : chaque sous-agent log ses propres tokens consommés dans BigQuery (via `market_mcp:log_ai_consumption`) de façon asynchrone (fire-and-forget via `asyncio.create_task`), séparément du Router.

### Protocole A2A : HTTP REST (pas SSE)

La communication Router → Sous-agent se fait via `POST /a2a/query` avec un timeout adapté au domaine :

```
Router → HR Agent   : timeout=60s  (recherche RAG + LLM)
Router → Ops Agent  : timeout=60s  (logs + BigQuery)
Router → Missions   : timeout=90s  (pipeline staffing complet)
```

Le sous-agent retourne un objet JSON structuré :
```json
{
  "response": "...",
  "data": {...},
  "steps": [...],
  "thoughts": "...",
  "usage": {"total_input_tokens": N, "total_output_tokens": M, "estimated_cost_usd": X}
}
```

Le Router agrège ces métadonnées dans sa propre réponse finale, préfixant les `steps` avec le nom du sous-agent source (`hr_agent:search_best_candidates`) pour l'Expert Mode frontend.

### Proxy MCP centralisé (`/mcp/proxy`)

Le Router expose un proxy MCP générique permettant au frontend ou à des clients externes d'invoquer n'importe quel outil MCP de l'écosystème en un seul point d'entrée authentifié (`/mcp/proxy/{server_name}/{path}`), avec propagation du JWT et des headers OTel.

### Gestion des Prompts Système (`prompts_api`)

Les instructions système de tous les agents (Router, HR, Ops, Missions) sont externalisées dans `prompts_api`, lues dynamiquement au démarrage de chaque requête. Un fallback local sur fichier `.txt` est prévu en cas d'indisponibilité. Des instructions personnalisées par `session_id` (utilisateur) sont supportées (`user_{session_id}`).

## Conséquences

### Positives

- **Isolation des domaines** : un bug dans l'Agent Missions n'impacte pas l'Agent HR. Les prompts, outils et logiques métier sont encapsulés indépendamment.
- **Réduction du contexte LLM** : le Router ne voit que 3 outils ; chaque sous-agent ne vide que les outils de son domaine. Le coût par requête et le risque de confusion par le LLM sont minimisés.
- **Tests unitaires isolables** : on peut tester l'Agent HR en isolation via `/a2a/query` sans impliquer le Router ni les autres agents.
- **FinOps granulaire** : chaque agent log ses propres tokens séparément, permettant d'identifier quel sous-domaine est le plus coûteux.
- **Scalabilité indépendante** : sur Cloud Run, chaque agent peut scaler indépendamment selon sa charge (ex: l'Agent HR peut avoir 10 instances pendant une campagne de staffing, sans surcharger l'Agent Ops).
- **Observabilité distribuée** : les traces OTel sont propagées `Router → Sous-agent → MCP` via les headers `traceparent`/`tracestate`, permettant une topologie de trace complète dans Tempo/Cloud Trace.

### Négatives

- **Latence additionnelle** : chaque requête implique au minimum 2 appels LLM séquentiels (Router + Sous-agent) et 1 aller-retour HTTP inter-services supplémentaire (~50-200ms overhead réseau).
- **Complexité de debuggage** : le chemin d'exécution complet parcourt 2 agents, 1-5 outils MCP, et optionnellement AlloyDB/pgvector. Sans traces distribuées, le débogage devient opaque.
- **Duplication de code** : la logique de `run_agent_query` (extraction de métadonnées, guardrail, FinOps) est quasi-identique dans `agent_hr_api`, `agent_ops_api` et `agent_missions_api`. Un refactoring vers une librairie partagée est nécessaire.
- **Couplage via session Redis** : la session utilisateur est maintenue uniquement au niveau Router via Redis. Si le Router redémarre avant que Redis n'ait persisté, l'historique est perdu.

### Risques

- **Risque de dégradation silencieuse** : si un sous-agent échoue (timeout, crash), le Router retourne simplement "Échec de communication avec l'Agent HR" sans retry ni circuit-breaker. L'utilisateur n'a aucune information exploitable.
- **Guardrail non-exhaustif** : le guardrail d'hallucination vérifie l'absence d'appel d'outil, mais ne valide pas la cohérence des données retournées (ex: un profil fictif retourné par un outil réel).
- **Reformulation sous-optimale** : le Router reformule la requête dans son prompt avant délégation, mais cette reformulation n'est pas testée unitairement — une mauvaise reformulation peut mener le sous-agent sur une fausse piste.
- **Coût de la double inférence** : sur les requêtes simples (ex: "liste les missions"), payer deux inférences LLM (Router + Agent) est un surcoût injustifié. Un mécanisme de cache sémantique (`market_mcp`) pourrait court-circuiter ce chemin à terme.

---

## Axes d'Amélioration Proposés

### 🔴 Court Terme (Critique)

**1. Extraction de librairie partagée `agent_commons`**

La logique de `run_agent_query` (extraction des steps/thoughts depuis les events ADK, guardrail hallucination, FinOps BQ logging) est quasi-identique dans les 3 sous-agents (~300 lignes dupliquées). Créer un package interne `agent_commons/` avec :

```python
# agent_commons/runner.py
async def run_agent_and_collect(agent, runner, session_id, query, user_id) -> AgentResult:
    ...
# agent_commons/guardrail.py
def check_hallucination_guardrail(steps, response_text) -> tuple[list, str]:
    ...
# agent_commons/finops.py
async def log_tokens_to_bq(market_url, auth_header, user_email, action, model, input_tokens, output_tokens, query):
    ...
```

**2. Circuit-Breaker et Retry sur les appels A2A**

Actuellement, un sous-agent qui échoue renvoie une erreur opaque sans retry. Mettre en place :
- Retry avec backoff exponentiel (1 retry, délai 2s) via `httpx` ou `tenacity`
- Réponse dégradée structurée avec `{"degraded": true, "reason": "..."}` plutôt qu'une string d'erreur
- Métriques Prometheus dédiées : `a2a_call_duration_seconds{agent}` et `a2a_call_errors_total{agent}`

**3. Cache sémantique côté Router**

Pour les requêtes identiques ou très proches (même embedding), bypasser l'inférence LLM via le cache Redis sémantique existant dans `market_mcp`. Le Router doit vérifier ce cache avant de déléguer au sous-agent.

### 🟡 Moyen Terme (Amélioration Structurelle)

**4. Contrat d'Interface A2A formalisé (Pydantic)**

Définir un modèle Pydantic partagé pour le protocole A2A request/response :

```python
class A2ARequest(BaseModel):
    query: str
    user_id: str
    trace_context: Optional[dict] = None  # propagation OTel explicite

class A2AResponse(BaseModel):
    response: str
    data: Optional[Any] = None
    steps: list[AgentStep] = []
    thoughts: str = ""
    usage: UsageMetadata
    agent: str
    degraded: bool = False
```

Cela permettrait la validation automatique et une documentation OpenAPI précise sur `/a2a/query`.

**5. Health-Check A2A actif depuis le Router**

Le Router doit exposer un endpoint `/health/agents` qui sonde chacun des 3 sous-agents (`GET /health`) et retourne leur statut agrégé. Cela permettrait au frontend de désactiver dynamiquement les fonctionnalités en cas de sous-agent dégradé.

**6. Tests de contrat inter-agents (Consumer-Driven Contract Tests)**

Mettre en place des tests de contrat A2A avec `pact` ou équivalent :
- Le Router est le "Consumer" qui définit le contrat qu'il attend de chaque sous-agent
- Chaque sous-agent est le "Provider" qui doit respecter ce contrat
- Exécutés en CI pour détecter les régressions de protocole avant déploiement

### 🟢 Long Terme (Évolutivité)

**7. Agent Discovery dynamique**

Remplacer le câblage statique (`AGENT_HR_API_URL`, `AGENT_OPS_API_URL`) par un registre de services dynamique :
- Chaque sous-agent s'auto-enregistre au démarrage dans un registre Redis ou Consul
- Le Router découvre les agents disponibles dynamiquement, permettant l'ajout de nouveaux agents sans modifier le code du Router
- Compatible avec les déploiements multi-régions Cloud Run

**8. Ajout d'un Agent "Generalist" pour les requêtes triviales**

Pour les requêtes ne nécessitant pas d'outil spécifique (questions générales sur Zenika, navigation d'aide), introduire un 4ème agent `agent_general_api` avec un contexte minimal et un modèle moins coûteux, évitant de payer une double inférence Gemini Pro/Flash pour une simple FAQ.

**9. Parallélisation des appels A2A multi-domaine**

Pour les requêtes cross-domaine (ex: "Donne-moi le profil de Thomas ET les missions disponibles pour lui"), le Router pourrait paralléliser les appels HR et Missions via `asyncio.gather`, réduisant la latence totale de 3-5s à ~1.5s (meilleures réponses en parallèle).

```python
# Exemple de parallélisation future
results = await asyncio.gather(
    ask_hr_agent(hr_query, user_id),
    ask_missions_agent(missions_query, user_id),
    return_exceptions=True
)
```
