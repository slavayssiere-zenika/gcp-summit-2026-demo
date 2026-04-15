# Rapport d'analyse Agent Zenika — 2026-04-15T18:50:31.327274Z

> Ce document est généré automatiquement par `agent_prompt_tests.py`.
> Il est structuré pour être passé directement à un LLM d'analyse.

---

## 1. Contexte système

La plateforme Zenika est une architecture multi-agent basée sur Google ADK :
- **Router** (`agent_router_api`) : dispatche via tools `ask_hr_agent` ou `ask_ops_agent`.
- **HR Agent** (`agent_hr_api`) : utilisateurs, CVs, compétences, missions, staffing.
- **Ops Agent** (`agent_ops_api`) : health checks, FinOps, Drive sync, logs.
- **Guardrail** : warning `GUARDRAIL` si sous-agent répond sans appeler de tool.
- **Protocole A2A** : Router → sous-agent via HTTP POST `/a2a/query`.

---

## 2. Résumé global

| Métrique | Valeur |
|----------|--------|
| Tests exécutés | 5 |
| Succès | 4 |
| Échecs | 1 |
| Erreurs de schéma | 1 |
| Alertes qualité | 1 |
| Durée moyenne | 8962ms |
| Total tokens (in/out) | 38920 / 1225 |
| Ratio in/out | 31.8x |
| Coût total estimé | $0.003286 |
| Horodatage | 2026-04-15T18:50:31.327274Z |

### Fréquence des tools appelés

| Tool | Appels |
|------|--------|
| `ask_ops_agent` | 4 |
| `hr_agent:get_mission_candidates` | 4 |
| `ops_agent:check_all_components_health` | 3 |
| `ask_hr_agent` | 2 |
| `hr_agent:list_missions` | 2 |
| `hr_agent:get_mission` | 2 |
| `hr_agent:list_users` | 1 |
| `ops_agent:get_finops_report` | 1 |

---

## 3. Anomalies détectées

### 🔴 Sur-routage (Multi-dispatch non justifié)
Le Router a appelé plusieurs sous-agents sur des requêtes mono-domaine.

- **[ROUTE-001]** `Qui sont les consultants Zenika disponibles ?` → dispatché vers `['ask_ops_agent', 'ask_hr_agent']` (attendu: `hr`) en `9895ms`
- **[ROUTE-003]** `Donne-moi un rapport sur les consultants actifs sur des missions` → dispatché vers `['ask_ops_agent', 'ask_hr_agent']` (attendu: `hr`) en `13141ms`

### ⚠️ Warnings comportementaux
- **[ROUTE-001]** Tool attendu non appelé : 'search_users' (appelés: ['ask_ops_agent', 'ask_hr_agent', 'ops_agent:check_all_components_health', 'hr_agent:list_missions', 'hr_agent:list_users', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission_candidates'])

### 🟡 Alertes qualité / cohérence
- **[ROUTE-004]** [schema:usage] Bloc usage absent ou vide

---

## 4. Détail par test

#### [ROUTE-001] Question RH simple → doit router vers l'agent HR

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `hr` |
| Durée | `9895ms` |
| Tokens | `14031 in / 456 out` |
| Coût estimé | `$0.001189` |

**Prompt envoyé :**
```
Qui sont les consultants Zenika disponibles ?
```

**Dispatches Router** (`ask_*`) : `['ask_ops_agent', 'ask_hr_agent']`
**Tools sous-agents** : `['ops_agent:check_all_components_health', 'hr_agent:list_missions', 'hr_agent:list_users', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission_candidates']`
**Réponse agent (922 chars) :**
```
Voici les informations demandées :

### État de santé de la plateforme
La plateforme est dans un état **optimal**. Tous les composants critiques (Redis Cache, AlloyDB, BigQuery, Agent-Router) sont opérationnels et répondent normalement.

### Rapport sur les consultants
*   **Consultants sur mission :**
    *   **Ahmed KANOUN** (ID 4) : Mission "Modernisation et Migration Cloud Native"
    *   **Anon RMO** (ID 13) : Mission "Modernisation et Migration Cloud Native"
    *(Note : Ces affectations sont confirmées par les plans de staffing des propositions de mission validées.)*

*   **Consultants disponibles :**
    *   Alexandre PACAUD (ID 3)
    *   Guillaume Le Floch (ID 5)
    *   Anon JCT (ID 6)
    *   Anon MSO (ID 7)
    *   Anon AGU (ID 8)
    *   Alexandre GUÉRIN (ID 9)
    *   Melek ...[tronqué]
```
**Warnings comportementaux :**
- Tool attendu non appelé : 'search_users' (appelés: ['ask_ops_agent', 'ask_hr_agent', 'ops_agent:check_all_components_health', 'hr_agent:list_missions', 'hr_agent:list_users', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission_candidates'])

#### [ROUTE-002] Question Ops simple → doit router vers l'agent Ops

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `ops` |
| Durée | `6566ms` |
| Tokens | `1919 in / 93 out` |
| Coût estimé | `$0.000172` |

**Prompt envoyé :**
```
Quel est l'état de santé de la plateforme ?
```

**Dispatches Router** (`ask_*`) : `['ask_ops_agent']`
**Tools sous-agents** : `['ops_agent:check_all_components_health']`
**Réponse agent (308 chars) :**
```
L'état de santé actuel de la plateforme est **optimal**.

Voici le détail de la vérification des composants critiques :
* **Redis-cache** : Fonctionnel (PING réussi).
* **AlloyDB** : Les APIs GCP sont réactives.
* **BigQuery** : Les APIs GCP sont réactives.
* **Agent-router** : Opérationnel (code HTTP 200).
```

#### [ROUTE-003] Formulation ambiguë RH proche Ops → doit rester sur HR

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `hr` |
| Durée | `13141ms` |
| Tokens | `20069 in / 440 out` |
| Coût estimé | `$0.001637` |

**Prompt envoyé :**
```
Donne-moi un rapport sur les consultants actifs sur des missions
```

**Dispatches Router** (`ask_*`) : `['ask_ops_agent', 'ask_hr_agent']`
**Tools sous-agents** : `['ops_agent:check_all_components_health', 'hr_agent:list_missions', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission', 'hr_agent:get_mission']`
**Réponse agent (1149 chars) :**
```
L'état de santé de la plateforme est **optimal** (diagnostic complet au 15 avril 2026, 18:50 UTC). Tous les composants (Redis, AlloyDB, BigQuery, Agent Router) sont opérationnels.

Concernant les consultants, bien que deux missions soient enregistrées, le système n'a actuellement **aucune équipe explicitement staffée** (erreur 404 lors de la récupération des assignations).

Voici le point sur les missions en cours :

1.  **Modernisation et Migration Cloud Native de la Plateforme Transactionnelle (Ref: PR-2024-ZEN-GCP)**
    *   **Statut :** Active.
    *   **Candidats potentiels identifiés :** Ahmed KANOUN, Anon RMO, RMI RMI, Anon RMI, Anon AGU, et Guillaume Le Floch.

2.  **Conception et Développement du MVP "Moteur de Rapprochement Factures" (Ref: PR-2026-ZEN-FIN-04)**
    *   **Statut :...[tronqué]
```

#### [ROUTE-004] Formulation en anglais → doit router correctement malgré la langue

| Champ | Valeur |
|-------|--------|
| Statut | ❌ FAIL |
| Catégorie | `routing` |
| Agent attendu | `hr` |
| Durée | `7520ms` |
| Tokens | `0 in / 0 out` |
| Coût estimé | `$0` |

**Prompt envoyé :**
```
Show me the list of all consultants
```

**Dispatches Router** (`ask_*`) : `[]`
**Tools sous-agents** : `[]`
**Réponse agent (77 chars) :**
```
Erreur: No function call event found for function responses ids: {'sr4yz63q'}
```
**Erreurs bloquantes :**
- `Trop peu de tool calls : 0 < 1 attendus`
- `Mot-clé attendu absent de la réponse : 'consultant'`
- `Mot-clé attendu absent de la réponse : 'Zenika'`
- `[schema:envelope] Champ obligatoire manquant : 'steps'`
- `[schema:envelope] Champ obligatoire manquant : 'usage'`
- `[schema:envelope.usage.total_input_tokens] Champ FinOps manquant`
- `[schema:envelope.usage.total_output_tokens] Champ FinOps manquant`
- `[schema:envelope.usage.estimated_cost_usd] Champ FinOps manquant`
**Alertes qualité :**
- [schema:usage] Bloc usage absent ou vide

#### [ROUTE-005] Question sur les coûts IA → doit router vers Ops/FinOps

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `ops` |
| Durée | `7690ms` |
| Tokens | `2901 in / 236 out` |
| Coût estimé | `$0.000288` |

**Prompt envoyé :**
```
Combien de tokens Gemini avons-nous consommé cette semaine ?
```

**Dispatches Router** (`ask_*`) : `['ask_ops_agent']`
**Tools sous-agents** : `['ops_agent:get_finops_report']`
**Réponse agent (597 chars) :**
```
Pour cette semaine (au 15 avril 2026), la consommation totale de tokens Gemini sur la plateforme est de **2 616 628 tokens**, avec un coût estimé à environ **0,23 $ USD**.

Voici la répartition détaillée :

*   **Total Input (Entrée) :** 2 572 484 tokens
*   **Total Output (Sortie) :** 44 144 tokens

**Détail par action :**
*   **Orchestrator Routing :** 2 466 284 tokens
*   **HR Agent Execution :** 235 370 tokens
*   **Ops Agent Execution :** 60 642 tokens
*   **Analyse CV :** 55 936 tokens
*   **Recalculate Tree :** 35 061 tokens
*   **Autres (Embedding, Logs, Extraction) :** 6 637 tokens
```


---

## 5. Propositions d'amélioration

> Ces propositions sont **générées automatiquement** à partir des anomalies observées.
> Chaque proposition inclut la cause racine identifiée et le correctif recommandé.

### 🔴 Proposition 2 — Sur-routage multi-agent non justifié ([ROUTE-001], [ROUTE-003])

**Cause racine :** Le system prompt du Router ne contenait pas d'interdiction
explicite des dispatches préventifs. Le modèle appelait `ask_ops_agent` de façon
proactive (health-check automatique) même sur des requêtes purement RH.

**Tests impactés :**
- **[ROUTE-001]** `Qui sont les consultants Zenika disponibles ?` → dispatché vers `['ask_ops_agent', 'ask_hr_agent']` (attendu : `hr`)
- **[ROUTE-003]** `Donne-moi un rapport sur les consultants actifs sur des missions` → dispatché vers `['ask_ops_agent', 'ask_hr_agent']` (attendu : `hr`)

**Correctif appliqué** dans `agent_router_api.system_instruction.txt` :
```
### Règle 1 — Dispatch unique et strict
Chaque requête → UN SEUL agent.
INTERDIT : appeler ask_ops_agent pour une question RH.

### Règle 4 — Interdiction des checks préventifs
INTERDIT : health-check de précaution sans demande explicite.
```

**Action requise :** synchroniser le prompt vers GCP :
```bash
python3 scripts/sync_prompts.py \
  --url "https://dev.zenika.slavayssiere.fr/api/prompts" \
  --email "admin@zenika.com" \
  --password "$ADMIN_PASSWORD"
```

### 🟠 Proposition 3 — Tools attendus non appelés ([ROUTE-001])

**Détail :**
- **[ROUTE-001]** Tool attendu non appelé : 'search_users' (appelés: ['ask_ops_agent', 'ask_hr_agent', 'ops_agent:check_all_components_health', 'hr_agent:list_missions', 'hr_agent:list_users', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission_candidates'])

**Correctifs recommandés :**
1. Si lié à la session → Proposition 1 résout ce point.
2. Si le nom du tool a changé → mettre à jour `expected_tools` dans le cas de test :
```python
expected_tools=['list_users'],  # vérifier le nom exact dans mcp_server.py
```
3. Vérifier que le tool est documenté dans la docstring de `agent.py` du sous-agent.

### 🟡 Proposition 4 — Tests trop lents : 1 test(s) > 10s ([ROUTE-003])

**Durée moyenne sur les tests lents :** 13141ms

**Causes identifiées :**
- Appels A2A séquentiels (Router → sous-agent → tools un par un)
- Sur-routage multi-agent (voir Proposition 2) = double latence A2A
- Contexte de session Redis volumineux rechargé à chaque appel

**Optimisations recommandées :**

1. **Cache sémantique Redis** (priorité haute) :
```python
cache_key = f'semantic:{hashlib.md5(query.encode()).hexdigest()}'
cached = await redis.get(cache_key)
if cached: return json.loads(cached)
await redis.setex(cache_key, 300, json.dumps(response))
```

2. **Parallélisation** des dispatches multi-domaines :
```python
hr_res, ops_res = await asyncio.gather(ask_hr_agent(q), ask_ops_agent(q))
```

3. **Historique tronqué** (max N derniers tours) :
```python
MAX_HISTORY_TURNS = 5
history = history[-MAX_HISTORY_TURNS * 2:]
```

### ✅ Proposition 6 — Comportements golden à consolider ([ROUTE-002], [ROUTE-003], [ROUTE-005])

Ces tests passent parfaitement : routing correct, tools appropriés, 0 warning.

- **[ROUTE-002]** `Quel est l'état de santé de la plateforme ?` → `['ask_ops_agent', 'ops_agent:check_all_components_health']` en 6566ms
- **[ROUTE-003]** `Donne-moi un rapport sur les consultants actifs sur des missions` → `['ask_ops_agent', 'ask_hr_agent', 'ops_agent:check_all_components_health', 'hr_agent:list_missions', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission', 'hr_agent:get_mission']` en 13141ms
- **[ROUTE-005]** `Combien de tokens Gemini avons-nous consommé cette semaine ?` → `['ask_ops_agent', 'ops_agent:get_finops_report']` en 7690ms

**Action recommandée :** Activer `data_quality_strict=True` pour bloquer toute régression :
```python
TestCase(id="ROUTE-002", ..., data_quality_strict=True),
```


---
*Rapport généré par `agent_prompt_tests.py` — Zenika Platform Engineering*