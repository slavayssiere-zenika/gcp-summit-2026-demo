# Rapport d'analyse Agent Zenika — 2026-04-15T18:54:13.186862+00:00Z

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
| Succès | 5 |
| Échecs | 0 |
| Erreurs de schéma | 0 |
| Alertes qualité | 0 |
| Durée moyenne | 9062ms |
| Total tokens (in/out) | 49849 / 1973 |
| Ratio in/out | 25.3x |
| Coût total estimé | $0.004331 |
| Horodatage | 2026-04-15T18:54:13.186862+00:00Z |

### Fréquence des tools appelés

| Tool | Appels |
|------|--------|
| `ask_hr_agent` | 4 |
| `hr_agent:list_users` | 4 |
| `ask_ops_agent` | 2 |
| `hr_agent:list_missions` | 2 |
| `hr_agent:get_mission_candidates` | 1 |
| `hr_agent:get_mission` | 1 |
| `ops_agent:check_all_components_health` | 1 |
| `ops_agent:get_finops_report` | 1 |

---

## 3. Anomalies détectées

### 🔴 Sur-routage (Multi-dispatch non justifié)
Le Router a appelé plusieurs sous-agents sur des requêtes mono-domaine.

- **[ROUTE-002]** `Quel est l'état de santé de la plateforme ?` → dispatché vers `['ask_hr_agent', 'ask_ops_agent']` (attendu: `ops`) en `12475ms`

### ⚠️ Warnings comportementaux
- **[ROUTE-001]** Tool attendu non appelé : 'search_users' (appelés: ['ask_hr_agent', 'hr_agent:list_users'])

---

## 4. Détail par test

#### [ROUTE-001] Question RH simple → doit router vers l'agent HR

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `hr` |
| Durée | `6901ms` |
| Tokens | `5905 in / 183 out` |
| Coût estimé | `$0.000498` |

**Prompt envoyé :**
```
Qui sont les consultants Zenika disponibles ?
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:list_users']`
**Réponse agent (274 chars) :**
```
Les consultants Zenika suivants sont actuellement disponibles :

*   **Alexandre PACAUD** (apacaud145)
*   **Ahmed KANOUN** (akanoun595)
*   **Guillaume Le Floch** (gle floch787)
*   **Alexandre GUÉRIN** (aguérin744)
*   **Melek SOUAI** (msouai708)
*   **RMI RMI** (rrmi636)
```
**Warnings comportementaux :**
- Tool attendu non appelé : 'search_users' (appelés: ['ask_hr_agent', 'hr_agent:list_users'])

#### [ROUTE-002] Question Ops simple → doit router vers l'agent Ops

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `ops` |
| Durée | `12475ms` |
| Tokens | `17786 in / 558 out` |
| Coût estimé | `$0.001501` |

**Prompt envoyé :**
```
Quel est l'état de santé de la plateforme ?
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent', 'ask_ops_agent']`
**Tools sous-agents** : `['hr_agent:list_missions', 'hr_agent:list_users', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission', 'ops_agent:check_all_components_health']`
**Réponse agent (1303 chars) :**
```
Voici les informations demandées concernant les consultants et la plateforme Zenika :

### 1. Disponibilité et Missions des Consultants
La plupart des consultants enregistrés sont actuellement disponibles pour de nouveaux projets, à l'exception de **Sébastien LAVAYSSIERE**, qui est en mission client jusqu'au 7 mai 2026.

**Consultants actuellement actifs sur des missions :**
*   **Ahmed KANOUN** : Mission de *Modernisation et Migration Cloud Native*.
*   **Anon RMO** : Mission de *Modernisation et Migration Cloud Native*.

**Rapport sur les missions en cours :**
*   **Mission 1 (Modernisation et Migration Cloud Native)** : En cours. Ahmed KANOUN et Anon RMO y sont affectés.
*   **Mission 2 (MVP "Moteur de Rapprochement Factures")** : En phase de planification/proposition. L'équipe n'est pa...[tronqué]
```

#### [ROUTE-003] Formulation ambiguë RH proche Ops → doit rester sur HR

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `hr` |
| Durée | `10498ms` |
| Tokens | `17186 in / 574 out` |
| Coût estimé | `$0.001461` |

**Prompt envoyé :**
```
Donne-moi un rapport sur les consultants actifs sur des missions
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:list_users', 'hr_agent:list_missions']`
**Réponse agent (1413 chars) :**
```
Voici un rapport sur la situation des consultants Zenika et leurs missions en cours :

### Synthèse des Consultants
La plupart de nos consultants sont actuellement disponibles. **Sébastien LAVAYSSIERE** est toutefois indisponible jusqu'au 7 mai 2026.

| Consultant | Statut |
| :--- | :--- |
| **Alexandre PACAUD** | Actif |
| **Ahmed KANOUN** | Actif |
| **Guillaume Le Floch** | Actif |
| **Anon JCT** | Actif |
| **Anon MSO** | Actif |
| **Anon AGU** | Actif |
| **Alexandre GUÉRIN** | Actif |
| **Melek SOUAI** | Actif |
| **RMI RMI** | Actif |
| **Sébastien LAVAYSSIERE** | Actif (Indisponible jusqu'au 07/05/2026) |

---

### Rapport des Missions Actives
Actuellement, deux missions sont enregistrées :

1.  **Mission : Modernisation et Migration Cloud Native de la Plateforme Transactionnelle ...[tronqué]
```

#### [ROUTE-004] Formulation en anglais → doit router correctement malgré la langue

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `hr` |
| Durée | `6708ms` |
| Tokens | `5908 in / 249 out` |
| Coût estimé | `$0.000518` |

**Prompt envoyé :**
```
Show me the list of all consultants
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:list_users']`
**Réponse agent (612 chars) :**
```
Voici la liste des consultants (et administrateurs) actuellement enregistrés sur la plateforme :

*   **Alexandre PACAUD** (apacaud145)
*   **Ahmed KANOUN** (akanoun595)
*   **Guillaume Le Floch** (gle floch787)
*   **Anon JCT** (ajct281)
*   **Anon MSO** (amso947)
*   **Anon AGU** (aagu368)
*   **Alexandre GUÉRIN** (aguérin744)
*   **Sébastien LAVAYSSIERE** (sebastien.lavayssiere)
*   **Melek SOUAI** (msouai708)
*   **RMI RMI** (rrmi636)
*   **Anon RMI** (armi711)
*   **Anon RMO** (armo550)
*   **Zenika Admin** (admin)

Souhaitez-vous des détails sur l'un de ces profils ou une recherche plus spécifique ?
```

#### [ROUTE-005] Question sur les coûts IA → doit router vers Ops/FinOps

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `ops` |
| Durée | `8730ms` |
| Tokens | `3064 in / 409 out` |
| Coût estimé | `$0.000353` |

**Prompt envoyé :**
```
Combien de tokens Gemini avons-nous consommé cette semaine ?
```

**Dispatches Router** (`ask_*`) : `['ask_ops_agent']`
**Tools sous-agents** : `['ops_agent:get_finops_report']`
**Réponse agent (843 chars) :**
```
Pour cette semaine (au 15 avril 2026), voici le détail de la consommation de tokens Gemini par action :

| Action | Input Tokens | Output Tokens | Coût estimé (USD) |
| :--- | :--- | :--- | :--- |
| **orchestrator_routing** | 2 559 093 | 21 105 | 0,198 264 |
| **hr_agent_execution** | 299 412 | 13 834 | 0,026 606 |
| **analyze_cv** | 38 159 | 17 777 | 0,008 195 |
| **ops_agent_execution** | 68 634 | 4 923 | 0,006 625 |
| **recalculate_tree** | 30 369 | 4 692 | 0,003 685 |
| **search_embedding** | 6 386 | 0 | 0,000 479 |
| **recherche_logs_transaction** | 150 | 50 | 0,000 026 |
| **search_filter_extraction** | 65 | 36 | 0,000 016 |
| **TOTAL** | **3 002 268** | **62 417** | **~0,243 896** |

La majorité de la consommation est générée par l'action `orchestrator_routing`, principalement utili...[tronqué]
```


---

## 5. Propositions d'amélioration

> Ces propositions sont **générées automatiquement** à partir des anomalies observées.
> Chaque proposition inclut la cause racine identifiée et le correctif recommandé.

### 🔴 Proposition 2 — Sur-routage multi-agent non justifié ([ROUTE-002])

**Cause racine :** Le system prompt du Router ne contenait pas d'interdiction
explicite des dispatches préventifs. Le modèle appelait `ask_ops_agent` de façon
proactive (health-check automatique) même sur des requêtes purement RH.

**Tests impactés :**
- **[ROUTE-002]** `Quel est l'état de santé de la plateforme ?` → dispatché vers `['ask_hr_agent', 'ask_ops_agent']` (attendu : `ops`)

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
- **[ROUTE-001]** Tool attendu non appelé : 'search_users' (appelés: ['ask_hr_agent', 'hr_agent:list_users'])

**Correctifs recommandés :**
1. Si lié à la session → Proposition 1 résout ce point.
2. Si le nom du tool a changé → mettre à jour `expected_tools` dans le cas de test :
```python
expected_tools=['list_users'],  # vérifier le nom exact dans mcp_server.py
```
3. Vérifier que le tool est documenté dans la docstring de `agent.py` du sous-agent.

### 🟡 Proposition 4 — Tests trop lents : 2 test(s) > 10s ([ROUTE-002], [ROUTE-003])

**Durée moyenne sur les tests lents :** 11486ms

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

### ✅ Proposition 6 — Comportements golden à consolider ([ROUTE-002], [ROUTE-003], [ROUTE-004], [ROUTE-005])

Ces tests passent parfaitement : routing correct, tools appropriés, 0 warning.

- **[ROUTE-002]** `Quel est l'état de santé de la plateforme ?` → `['ask_hr_agent', 'ask_ops_agent', 'hr_agent:list_missions', 'hr_agent:list_users', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission', 'ops_agent:check_all_components_health']` en 12475ms
- **[ROUTE-003]** `Donne-moi un rapport sur les consultants actifs sur des missions` → `['ask_hr_agent', 'hr_agent:list_users', 'hr_agent:list_missions']` en 10498ms
- **[ROUTE-004]** `Show me the list of all consultants` → `['ask_hr_agent', 'hr_agent:list_users']` en 6708ms
- **[ROUTE-005]** `Combien de tokens Gemini avons-nous consommé cette semaine ?` → `['ask_ops_agent', 'ops_agent:get_finops_report']` en 8730ms

**Action recommandée :** Activer `data_quality_strict=True` pour bloquer toute régression :
```python
TestCase(id="ROUTE-002", ..., data_quality_strict=True),
```


---
*Rapport généré par `agent_prompt_tests.py` — Zenika Platform Engineering*