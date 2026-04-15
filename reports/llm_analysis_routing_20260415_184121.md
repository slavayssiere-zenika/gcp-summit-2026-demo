# Rapport d'analyse Agent Zenika — 2026-04-15T18:41:21.183693Z

> Ce document est généré automatiquement par `agent_prompt_tests.py`.
> Il est structuré pour être passé directement à un LLM d'analyse.

---

## 1. Contexte système

La plateforme Zenika est une architecture multi-agent basée sur Google ADK :
- **Router** (`agent_router_api`) : reçoit toutes les requêtes, dispatche via tools `ask_hr_agent` ou `ask_ops_agent`.
- **HR Agent** (`agent_hr_api`) : gère utilisateurs, CVs, compétences, missions, staffing.
- **Ops Agent** (`agent_ops_api`) : health checks, FinOps, Google Drive sync, logs.
- **Guardrail** : déclenche un warning `GUARDRAIL` si un sous-agent répond sans appeler de tool (signal d’hallucination).
- **Protocole A2A** : le Router envoie la requête au sous-agent via HTTP POST `/a2a/query`.

---

## 2. Résumé global de la session de tests

| Métrique | Valeur |
|----------|--------|
| Tests exécutés | 5 |
| Succès | 3 |
| Échecs | 2 |
| Erreurs de schéma | 0 |
| Alertes qualité | 0 |
| Durée moyenne | 7267ms |
| Total tokens (in/out) | 190264 / 946 |
| Coût total estimé | $0.014554 |
| Horodatage | 2026-04-15T18:41:21.183693Z |

### Frequence des tools appelés

| Tool | Appels |
|------|--------|
| `ask_ops_agent` | 2 |
| `ask_hr_agent` | 2 |
| `hr_agent:list_missions` | 2 |
| `hr_agent:get_mission_candidates` | 2 |
| `hr_agent:get_mission` | 2 |
| `ops_agent:check_all_components_health` | 1 |
| `ops_agent:get_finops_report` | 1 |

---

## 3. Anomalies détectées

### 🔴 Sur-routage (Multi-dispatch non justifié)Le Router a appelé plusieurs sous-agents (`ask_hr_agent` + `ask_ops_agent`) sur des requêtes qui n'impliquent qu'un seul domaine.
- **[ROUTE-002]** `Quel est l'état de santé de la plateforme ?` → dispatched to: `['ask_ops_agent', 'ask_hr_agent']` (attendu: `ops`) en `11750ms`
### ⚠️ Warnings comportementaux- **[ROUTE-001]** Tool attendu non appelé : 'list_users' (appelés: [])- **[ROUTE-001]** Tool attendu non appelé : 'search_users' (appelés: [])

---

## 4. Détail par test


#### [ROUTE-001] Question RH simple → doit router vers l'agent HR

| Champ | Valeur |
|-------|--------|
| Statut | ❌ FAIL |
| Catégorie | `routing` |
| Agent attendu | `hr` |
| Durée | `3526ms` |
| Tokens | `31324 in / 0 out` |
| Coût estimé | `$0.002349` |

**Prompt envoyé :**
```
Qui sont les consultants Zenika disponibles ?
```

**Dispatches du Router** (appels `ask_*`) : `[]`  
**Tools sous-agents** : `[]`  
**Réponse agent (2076 chars) :**
```
Voici un récapitulatif complet de l'état de santé de la plateforme et de la situation des consultants.

### 1. État de santé de la plateforme
L'état de santé actuel de la plateforme est **nominal**. Tous les composants critiques sont opérationnels :
*   **Redis Cache** : Fonctionnel (PING successful).
*   **AlloyDB** : Les API de données GCP répondent correctement.
*   **BigQuery** : Les API de données GCP répondent correctement.
*   **Agent Router** : En ligne (code HTTP 200).

---

### 2. Consultants Zenika disponibles
Les consultants suivants ne présentent actuellement aucune période d'indisponibilité dans le système et sont donc disponibles pour de nouvelles missions :
*   **Alexandre PACAUD** (apacaud145)
*   **Ahmed KANOUN** (akanoun595)
*   **Guillaume Le Floch** (gle floch787)
*   ...[tronqué]
```
**Erreurs bloquantes :**
- `Trop peu de tool calls : 0 < 1 attendus`
**Warnings comportementaux :**
- Tool attendu non appelé : 'list_users' (appelés: [])
- Tool attendu non appelé : 'search_users' (appelés: [])

#### [ROUTE-002] Question Ops simple → doit router vers l'agent Ops

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `ops` |
| Durée | `11750ms` |
| Tokens | `46532 in / 513 out` |
| Coût estimé | `$0.003644` |

**Prompt envoyé :**
```
Quel est l'état de santé de la plateforme ?
```

**Dispatches du Router** (appels `ask_*`) : `['ask_ops_agent', 'ask_hr_agent']`  
**Tools sous-agents** : `['ops_agent:check_all_components_health', 'hr_agent:list_missions', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission']`  
**Réponse agent (1109 chars) :**
```
L'état de santé de la plateforme est **nominal**. Tous les composants principaux sont opérationnels (Redis, AlloyDB, BigQuery et l'Agent Router).

Voici le rapport sur les consultants actuellement associés aux missions :

### État des Missions et Staffing

La plateforme compte actuellement deux missions enregistrées :

#### 1. Modernisation et Migration Cloud Native de la Plateforme Transactionnelle
*   **Contexte :** Migration vers GCP et refonte de l'architecture Java EE.
*   **Équipe identifiée :** Ahmed KANOUN et Anon RMO ont été sélectionnés pour leur forte adéquation technique.

#### 2. Conception et Développement du MVP "Moteur de Rapprochement Factures"
*   **Contexte :** Automatisation des processus financiers via microservices.
*   **Statut :** **En attente de staffing**. L'algor...[tronqué]
```

#### [ROUTE-003] Formulation ambiguë RH proche Ops → doit rester sur HR

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `hr` |
| Durée | `12257ms` |
| Tokens | `45803 in / 293 out` |
| Coût estimé | `$0.003523` |

**Prompt envoyé :**
```
Donne-moi un rapport sur les consultants actifs sur des missions
```

**Dispatches du Router** (appels `ask_*`) : `['ask_hr_agent']`  
**Tools sous-agents** : `['hr_agent:list_missions', 'hr_agent:get_mission_candidates', 'hr_agent:get_mission']`  
**Réponse agent (982 chars) :**
```
Voici le rapport sur les consultants actuellement associés à des missions au sein de Zenika :

### Rapport d'affectation des missions

| Consultant | Mission | Statut / Rôle |
| :--- | :--- | :--- |
| **Ahmed KANOUN** | Modernisation et Migration Cloud Native de la Plateforme Transactionnelle | Développeur Java Senior Cloud GCP |
| **Anon RMO** | Modernisation et Migration Cloud Native de la Plateforme Transactionnelle | Développeur Java Senior Cloud GCP |

**Notes :**
*   **Mission "Modernisation et Migration Cloud Native" :** Cette mission est active et l'équipe ci-dessus a été retenue en raison de leur forte adéquation technique (Java, GCP, Kubernetes) et de leur disponibilité.
*   **Mission "MVP Moteur de Rapprochement Factures" :** Cette mission est actuellement répertoriée avec un st...[tronqué]
```

#### [ROUTE-004] Formulation en anglais → doit router correctement malgré la langue

| Champ | Valeur |
|-------|--------|
| Statut | ❌ FAIL |
| Catégorie | `routing` |
| Agent attendu | `hr` |
| Durée | `2294ms` |
| Tokens | `31996 in / 0 out` |
| Coût estimé | `$0.0024` |

**Prompt envoyé :**
```
Show me the list of all consultants
```

**Dispatches du Router** (appels `ask_*`) : `[]`  
**Tools sous-agents** : `[]`  
**Réponse agent (934 chars) :**
```
Voici la liste exhaustive de tous les consultants et membres enregistrés sur la plateforme Zenika :

| Nom complet | Email | Statut actuel |
| :--- | :--- | :--- |
| **Alexandre PACAUD** | alexandre.pacaud@zenika.com | Actif |
| **Ahmed KANOUN** | ahmed.kanoun@zenika.com | Actif |
| **Guillaume Le Floch** | guillaume.lefloch@zenika.com | Actif |
| **Anon JCT** | anon.jct@anonymous.zenika.com | Actif |
| **Anon MSO** | anon.mso@anonymous.zenika.com | Actif |
| **Anon AGU** | anon.agu@anonymous.zenika.com | Actif |
| **Alexandre GUÉRIN** | alexandre.guerin@zenika.com | Actif |
| **Sébastien LAVAYSSIERE** | sebastien.lavayssiere@zenika.com | Actif (En mission client) |
| **Melek SOUAI** | melek.souai@zenika.com | Actif |
| **RMI RMI** | rmi.rmi@zenika.com | Actif |
| **Anon RMI** | anon.rmi@a...[tronqué]
```
**Erreurs bloquantes :**
- `Trop peu de tool calls : 0 < 1 attendus`

#### [ROUTE-005] Question sur les coûts IA → doit router vers Ops/FinOps

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `routing` |
| Agent attendu | `ops` |
| Durée | `6511ms` |
| Tokens | `34609 in / 140 out` |
| Coût estimé | `$0.002638` |

**Prompt envoyé :**
```
Combien de tokens Gemini avons-nous consommé cette semaine ?
```

**Dispatches du Router** (appels `ask_*`) : `['ask_ops_agent']`  
**Tools sous-agents** : `['ops_agent:get_finops_report']`  
**Réponse agent (427 chars) :**
```
Pour cette semaine (au 15 avril 2026), voici le détail de la consommation de tokens Gemini :

*   **Total Input Tokens :** 2 494 874
*   **Total Output Tokens :** 44 406
*   **Consommation globale (Input + Output) :** **2 539 280 tokens**
*   **Coût estimé :** environ **0,2138 $**

La majeure partie de cette consommation est imputable aux actions d'orchestration (`orchestrator_routing`) effectuées par Sébastien Lavayssiere.
```


---

## 5. Questions de diagnostic à analyser

En tant qu’expert en prompt engineering et architecture multi-agent, analyse ce rapport et réponds aux questions suivantes :

1. **Sur-routage** : Pourquoi le Router dispatche-t-il vers `ask_ops_agent` sur des requêtes purement RH (ex: "consultants disponibles") ? Qu’est-ce qui dans le system prompt du Router pourrait provoquer ce comportement ? Propose une modification ciblée du prompt.

2. **Performance** : Certains tests dépassent 15 secondes. Quelles sont les causes structurelles (nombre de tools, séquentialité A2A) et quelles optimisations proposerais-tu (paralllélisation, cache sémantique, few-shot) ?

3. **Routing par défaut** : Le Router devrait-il avoir un agent "par défaut" (probablement HR) pour éviter les doubles dispatches ? Comment implémenter ce fallback sans casser le multi-domaine ?

4. **Qualité des réponses** : Les réponses sont en français même sur des prompts en anglais. Est-ce un comportement désirable ? Comment le configurer proprement via le system prompt ?

5. **FinOps** : Le ratio tokens in/out (190264/946 = 201.1x) est-il normal pour ce type d’architecture ? Quels sont les leviers d’optimisation (contexte de session, réduction du system prompt, cache sémantique Redis) ?

6. **Points forts à consolider** : Quels comportements observés sont à renforcer comme "golden behavior" dans les tests de régression ?

---
*Rapport généré par `agent_prompt_tests.py` — Zenika Platform Engineering*
