# Rapport d'analyse Agent Zenika — 2026-04-15T20:53:48.707Z

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
| Tests exécutés | 7 |
| Succès | 6 |
| Échecs | 1 |
| Erreurs de schéma | 1 |
| Alertes qualité | 0 |
| Durée moyenne | 9809ms |
| Total tokens (in/out) | 100271 / 2276 |
| Ratio in/out | 44.1x |
| Coût total estimé | $0.008203 |
| Horodatage | 2026-04-15T20:53:48.707Z |

### Fréquence des tools appelés

| Tool | Appels |
|------|--------|
| `ask_hr_agent` | 6 |
| `hr_agent:list_missions` | 5 |
| `hr_agent:list_users` | 3 |
| `hr_agent:get_mission_candidates` | 3 |
| `hr_agent:get_mission` | 3 |
| `ask_ops_agent` | 2 |
| `ops_agent:check_all_components_health` | 1 |
| `ops_agent:get_finops_report` | 1 |

---

## 3. Anomalies détectées

### 🔴 Sur-routage (Multi-dispatch non justifié)
Le Router a appelé plusieurs sous-agents sur des requêtes mono-domaine.

- **[ROUTE-002]** `Quel est l'état de santé de la plateforme ?` → dispatché vers `['ask_hr_agent', 'ask_ops_agent']` (attendu: `ops`) en `14515ms`

---

## 4. Détail par test

#### [ROUTE-001] Question RH simple → doit router vers l'agent HR

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `hr` |
| Durée | `14447ms` |
| Tokens | `19239 in / 430 out` |
| Coût estimé | `$0.001572` |

**Prompt envoyé :**
```
Qui sont les consultants Zenika disponibles ?
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:list_missions', 'hr_agent:list_users', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission']`
**Réponse agent (990 chars) :**
```
Voici le rapport sur la situation actuelle des consultants Zenika :

### 1. Consultants en mission
*   **Mission : Modernisation et Migration Cloud Native de la Plateforme Transactionnelle**
    *   **Consultant :** Ahmed KANOUN (ID: 4)

*   **Mission : Conception et Développement du MVP "Moteur de Rapprochement Factures"**
    *   **Statut :** Aucune équipe n'est actuellement staffée. La recherche n'a pas abouti car aucun profil disponible ne possède l'expertise en gestion de projet (Directeur de Projet) requise.

### 2. Consultants disponibles
Les consultants suivants sont actuellement disponibles (sans indisponibilité notée ni mission en cours) :
*   Alexandre PACAUD (ID: 3)
*   Guillaume Le Floch (ID: 5)
*   Anon JCT (ID: 6)
*   Anon MSO (ID: 7)
*   Anon AGU (ID: 8)
*   Alexandre GUÉRI...[tronqué]
```

#### [ROUTE-002] Question Ops simple → doit router vers l'agent Ops

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `ops` |
| Durée | `14515ms` |
| Tokens | `19366 in / 472 out` |
| Coût estimé | `$0.001594` |

**Prompt envoyé :**
```
Quel est l'état de santé de la plateforme ?
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent', 'ask_ops_agent']`
**Tools sous-agents** : `['hr_agent:list_missions', 'hr_agent:list_users', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission', 'ops_agent:check_all_components_health']`
**Réponse agent (1217 chars) :**
```
Voici un point complet sur la situation actuelle :

### 1. Rapport sur les missions et les consultants
*   **Missions en cours :**
    *   **Modernisation et Migration Cloud Native (Plateforme Transactionnelle) :** Ahmed KANOUN (ID 4) est actuellement staffé en tant que Développeur Java Senior.
    *   **MVP "Moteur de Rapprochement Factures" :** Aucune équipe n'est actuellement staffée, car le profil nécessaire (Directeur de Projet) n'est pas disponible parmi les candidats actuels.

*   **Consultants disponibles :**
    Les consultants suivants sont libres et sans indisponibilité déclarée :
    *   Alexandre PACAUD (ID 3)
    *   Guillaume Le Floch (ID 5)
    *   Anon JCT (ID 6)
    *   Anon MSO (ID 7)
    *   Anon AGU (ID 8)
    *   Alexandre GUÉRIN (ID 9)
    *   Melek SOUAI (ID 10)
   ...[tronqué]
```

#### [ROUTE-003] Formulation ambiguë RH proche Ops → doit rester sur HR

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `hr` |
| Durée | `11693ms` |
| Tokens | `16965 in / 208 out` |
| Coût estimé | `$0.001335` |

**Prompt envoyé :**
```
Donne-moi un rapport sur les consultants actifs sur des missions
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:list_missions', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission']`
**Réponse agent (949 chars) :**
```
Voici le rapport sur les consultants actuellement actifs sur des missions :

### Mission : Modernisation et Migration Cloud Native de la Plateforme Transactionnelle
*   **Consultant staffé :** Ahmed KANOUN (Senior)
*   **Rôle :** Développeur Java Senior (Cloud Native / GCP)
*   **Justification :** Ahmed a été sélectionné pour son expertise technique approfondie (Java, Spring Boot, Kubernetes, Docker, Kafka) et sa capacité à répondre aux exigences complexes de migration vers une architecture Cloud Native sur GCP. Son profil correspond parfaitement à la séniorité et aux compétences requises pour cette mission stratégique.

Concernant la mission **"Conception et Développement du MVP 'Moteur de Rapprochement Factures'"**, aucune équipe n'a pu être staffée à ce jour, car le profil critique de *...[tronqué]
```

#### [ROUTE-004] Formulation en anglais → doit router correctement malgré la langue

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `hr` |
| Durée | `6300ms` |
| Tokens | `5903 in / 240 out` |
| Coût estimé | `$0.000515` |

**Prompt envoyé :**
```
Show me the list of all consultants
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:list_users']`
**Réponse agent (571 chars) :**
```
Voici la liste des consultants (utilisateurs) actuellement enregistrés dans le système :

*   **Alexandre PACAUD** (apacaud145)
*   **Ahmed KANOUN** (akanoun595)
*   **Guillaume Le Floch** (gle floch787)
*   **Anon JCT** (ajct281)
*   **Anon MSO** (amso947)
*   **Anon AGU** (aagu368)
*   **Alexandre GUÉRIN** (aguérin744)
*   **Sébastien LAVAYSSIERE** (sebastien.lavayssiere) - *Note : actuellement en période d'indisponibilité.*
*   **Melek SOUAI** (msouai708)
*   **RMI RMI** (rrmi636)
*   **Anon RMI** (armi711)
*   **Anon RMO** (armo550)
*   **Zenika Admin** (admin)
```

#### [ROUTE-005] Question sur les coûts IA → doit router vers Ops/FinOps

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `ops` |
| Durée | `7017ms` |
| Tokens | `3270 in / 323 out` |
| Coût estimé | `$0.000342` |

**Prompt envoyé :**
```
Combien de tokens Gemini avons-nous consommé cette semaine ?
```

**Dispatches Router** (`ask_*`) : `['ask_ops_agent']`
**Tools sous-agents** : `['ops_agent:get_finops_report']`
**Réponse agent (744 chars) :**
```
Pour la semaine en cours (au 15 avril 2026), voici le détail de la consommation de tokens Gemini :

*   **Total Input :** 3 568 221 tokens
*   **Total Output :** 71 271 tokens
*   **Coût estimé total :** ~0,298 $ USD

**Répartition par type d'action :**

| Action | Total Tokens (In + Out) | Coût estimé (USD) |
| :--- | :--- | :--- |
| **orchestrator_routing** | 2 235 927 | 0,2253 $ |
| **hr_agent_execution** | 623 171 | 0,0512 $ |
| **analyze_cv** | 55 936 | 0,0082 $ |
| **ops_agent_execution** | 94 646 | 0,0089 $ |
| **recalculate_tree** | 35 061 | 0,0037 $ |
| **Autres (recherche/embedding)** | 19 651 | 0,0010 $ |

Les opérations d'orchestration (`orchestrator_routing`) constituent la majeure partie de la consommation cette semaine.
```

#### [ROUTE-006] Question missions → doit router vers l'agent Missions (PAS HR)

| Champ | Valeur |
|-------|--------|
| Statut | ❌ FAIL |
| Catégorie | `routing` |
| Agent attendu | `missions` |
| Durée | `6575ms` |
| Tokens | `17615 in / 225 out` |
| Coût estimé | `$0.001389` |

**Prompt envoyé :**
```
Montre-moi toutes les missions actuellement actives
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:list_missions']`
**Réponse agent (830 chars) :**
```
Voici les missions actuellement actives dans notre système :

### 1. Conception et Développement du MVP "Moteur de Rapprochement Factures"
*   **Référence :** PR-2026-ZEN-FIN-04
*   **Client :** Secteur Retail / Grande Distribution (Direction Financière)
*   **Objectif :** Automatisation du rapprochement des factures fournisseurs via un microservice Java.
*   **Statut :** Équipe en cours de constitution (recherche active d'un Directeur de Projet).

### 2. Modernisation et Migration Cloud Native de la Plateforme Transactionnelle
*   **Référence :** PR-2024-ZEN-GCP
*   **Client :** Secteur Retail / E-commerce
*   **Objectif :** Migration d'un monolithe Java EE vers une architecture microservices sur Google Cloud Platform (GCP).
*   **Statut :** Équipe identifiée (Ahmed KANOUN proposé en tant...[tronqué]
```
**Erreurs bloquantes :**
- `[schema:data.id] Champ obligatoire manquant`
- `[schema:data.title] Champ obligatoire manquant`
- `[schema:data.description] Champ obligatoire manquant`

#### [ROUTE-007] Staffing d'une mission → doit router vers Missions (PAS HR)

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `missions` |
| Durée | `8121ms` |
| Tokens | `17913 in / 378 out` |
| Coût estimé | `$0.001457` |

**Prompt envoyé :**
```
Propose une équipe pour la mission Java FinTech en cours
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:list_missions']`
**Réponse agent (1358 chars) :**
```
Il n'existe pas de mission nommée explicitement "Java FinTech". Cependant, la mission **"Conception et Développement du MVP 'Moteur de Rapprochement Factures'" (Réf: PR-2026-ZEN-FIN-04)** correspond à votre demande dans le domaine FinTech.

Voici le point sur la constitution de l'équipe pour cette mission :

*   **Statut :** La constitution d'une équipe complète est actuellement **bloquée**.
*   **Problématique :** La mission requiert impérativement un **Directeur de Projet** pour le pilotage et la stratégie. Aucun des candidats disponibles dans notre base actuelle ne possède les compétences managériales et de pilotage nécessaires pour ce rôle critique ; ils sont tous fortement orientés vers le développement technique.
*   **Recommandation :** Sans ce profil de Directeur de Projet, la gouv...[tronqué]
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

### 🟡 Proposition 4 — Tests trop lents : 3 test(s) > 10s ([ROUTE-001], [ROUTE-002], [ROUTE-003])

**Durée moyenne sur les tests lents :** 13551ms

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

### ✅ Proposition 6 — Comportements golden à consolider ([ROUTE-001], [ROUTE-003], [ROUTE-004], [ROUTE-005], [ROUTE-007])

Ces tests passent parfaitement : routing correct, tools appropriés, 0 warning.

- **[ROUTE-001]** `Qui sont les consultants Zenika disponibles ?` → `['ask_hr_agent', 'hr_agent:list_missions', 'hr_agent:list_users', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission']` en 14447ms
- **[ROUTE-003]** `Donne-moi un rapport sur les consultants actifs sur des missions` → `['ask_hr_agent', 'hr_agent:list_missions', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission']` en 11693ms
- **[ROUTE-004]** `Show me the list of all consultants` → `['ask_hr_agent', 'hr_agent:list_users']` en 6300ms
- **[ROUTE-005]** `Combien de tokens Gemini avons-nous consommé cette semaine ?` → `['ask_ops_agent', 'ops_agent:get_finops_report']` en 7017ms
- **[ROUTE-007]** `Propose une équipe pour la mission Java FinTech en cours` → `['ask_hr_agent', 'hr_agent:list_missions']` en 8121ms

**Action recommandée :** Activer `data_quality_strict=True` pour bloquer toute régression :
```python
TestCase(id="ROUTE-001", ..., data_quality_strict=True),
```


---
*Rapport généré par `agent_prompt_tests.py` — Zenika Platform Engineering*