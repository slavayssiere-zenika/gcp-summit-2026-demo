# Rapport d'analyse Agent Zenika — 2026-04-15T21:21:12.597Z

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
| Tests exécutés | 8 |
| Succès | 8 |
| Échecs | 0 |
| Erreurs de schéma | 0 |
| Alertes qualité | 0 |
| Durée moyenne | 13021ms |
| Total tokens (in/out) | 80791 / 2763 |
| Ratio in/out | 29.2x |
| Coût total estimé | $0.006888 |
| Horodatage | 2026-04-15T21:21:12.597Z |

### Fréquence des tools appelés

| Tool | Appels |
|------|--------|
| `ask_hr_agent` | 8 |
| `hr_agent:get_user_availability` | 8 |
| `hr_agent:get_candidate_rag_context` | 6 |
| `hr_agent:search_best_candidates` | 5 |
| `hr_agent:search_users` | 5 |
| `hr_agent:list_missions` | 3 |
| `hr_agent:get_user_cv` | 2 |
| `hr_agent:search_competencies` | 1 |
| `hr_agent:list_competency_users` | 1 |
| `hr_agent:get_users_bulk` | 1 |

---

## 3. Anomalies détectées

_Aucune anomalie détectée._

---

## 4. Détail par test

#### [STAFF-001] [Staffing] Trouver un expert Kubernetes disponible

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `staffing-persona` |
| Agent attendu | `hr` |
| Durée | `11200ms` |
| Tokens | `4581 in / 155 out` |
| Coût estimé | `$0.00039` |

**Prompt envoyé :**
```
J'ai une mission urgente qui démarre dans 2 semaines. J'ai besoin d'un consultant expert Kubernetes. Qui est disponible dans notre pool ?
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:search_best_candidates', 'hr_agent:get_user_availability', 'hr_agent:get_user_availability', 'hr_agent:get_user_availability']`
**Réponse agent (465 chars) :**
```
J'ai identifié trois consultants experts en Kubernetes au sein de notre base qui semblent disponibles :

*   **Alexandre GUÉRIN**
*   **Guillaume Le Floch**
*   **Ahmed KANOUN**

Les outils n'indiquent aucune indisponibilité programmée pour ces profils, ce qui suggère qu'ils sont disponibles pour une mission dans 2 semaines.

Souhaitez-vous que j'approfondisse l'analyse sur l'un de ces consultants (CV, historique de missions) ou que je prenne une autre action ?
```

#### [STAFF-002] [Staffing] Comparer deux profils Java senior pour une mission

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `staffing-persona` |
| Agent attendu | `hr` |
| Durée | `16955ms` |
| Tokens | `7049 in / 437 out` |
| Coût estimé | `$0.00066` |

**Prompt envoyé :**
```
J'hésite entre deux profils pour la mission Java FinTech : Alexandre PACAUD et Ahmed KANOUN. Lequel est le plus adapté pour un rôle de Tech Lead Java Spring Boot ?
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:search_best_candidates', 'hr_agent:search_users', 'hr_agent:search_users', 'hr_agent:get_user_availability', 'hr_agent:get_user_availability', 'hr_agent:get_user_availability', 'hr_agent:get_candidate_rag_context', 'hr_agent:get_candidate_rag_context']`
**Réponse agent (1206 chars) :**
```
Pour répondre à vos besoins :

### 1. Expert Kubernetes (Mission urgente sous 2 semaines)
Le profil recommandé est **Ahmed KANOUN**. Il possède une solide expérience en systèmes cloud-native, microservices et maîtrise l'écosystème **Kubernetes**, Docker, Kafka ainsi que l'observabilité (Grafana/Prometheus). Il est actuellement disponible.

### 2. Tech Lead Java Spring Boot (Mission FinTech)
**Ahmed KANOUN est nettement plus adapté** pour ce rôle qu'Alexandre PACAUD. Voici une comparaison rapide pour éclairer votre choix :

| Critère | Alexandre PACAUD | Ahmed KANOUN |
| :--- | :--- | :--- |
| **Profil dominant** | Lead Developer Frontend (React/Angular) | Dév. Full-Stack Senior (Backend Java) |
| **Expertise Java** | Limitée (ponctuelle) | **Expertise forte** (8 ans, Spring Boot, microserv...[tronqué]
```

#### [STAFF-003] [Staffing] Un consultant déjà staffé ne doit pas être reproposé

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `staffing-persona` |
| Agent attendu | `hr` |
| Durée | `17504ms` |
| Tokens | `15744 in / 540 out` |
| Coût estimé | `$0.001343` |

**Prompt envoyé :**
```
Ahmed KANOUN est-il disponible pour rejoindre la mission Moteur de Rapprochement Factures (PR-2026-ZEN-FIN-04) ?
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:search_best_candidates', 'hr_agent:search_users', 'hr_agent:search_users', 'hr_agent:list_missions', 'hr_agent:get_user_cv', 'hr_agent:get_user_cv', 'hr_agent:get_candidate_rag_context', 'hr_agent:get_candidate_rag_context', 'hr_agent:get_user_availability']`
**Réponse agent (1503 chars) :**
```
Voici les éléments concernant votre demande :

### 1. Expertise Kubernetes
Les consultants suivants sont identifiés comme experts Kubernetes au sein de notre base :
*   **Ahmed KANOUN**
*   **Alexandre GUÉRIN**
*   **Guillaume Le Floch**
*   **RMI RMI**

*Note : Bien qu'ils apparaissent comme disponibles dans nos données générales, je vous recommande de faire valider leur disponibilité immédiate pour une mission dans 2 semaines auprès de leur responsable de compte respectif.*

### 2. Comparaison : Alexandre PACAUD vs Ahmed KANOUN
Pour votre rôle de **Tech Lead Java Spring Boot en contexte FinTech**, **Ahmed KANOUN** est le profil le plus adapté.
*   **Ahmed KANOUN** possède une expertise solide en **Java / Spring Boot** et a déjà travaillé sur des systèmes financiers et des architectures m...[tronqué]
```

#### [STAFF-004] [Staffing] Mission sans équipe : qui peut démarrer maintenant ?

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `staffing-persona` |
| Agent attendu | `hr` |
| Durée | `9858ms` |
| Tokens | `18823 in / 562 out` |
| Coût estimé | `$0.00158` |

**Prompt envoyé :**
```
La mission PR-2026-ZEN-FIN-04 n'a pas encore d'équipe. Qui parmi nos consultants peut démarrer immédiatement sur ce type de mission Java ?
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:list_missions']`
**Réponse agent (1306 chars) :**
```
La mission **PR-2026-ZEN-FIN-04** nécessite une équipe de 4 personnes expertes en Java, Spring Boot, architecture microservices et tests automatisés.

Voici les consultants disponibles immédiatement qui correspondent aux besoins :

| Consultant | Seniorité | Compétences clés pour la mission |
| :--- | :--- | :--- |
| **Ahmed KANOUN** | Senior | Java, Spring Boot, Kubernetes, Docker, Kafka, Hibernate, Agile |
| **Anon RMO** | Mid | Java, Spring, API REST, Jenkins, SonarQube, Kubernetes, Hibernate |
| **Melek SOUAI** | Mid | Java, Spring Boot, Micro-services, Docker, CI/CD, Kubernetes |
| **Anon JCT** | Mid | Java, Spring Boot, TDD, GitLab CI |

### Recommandation pour le staffing :
Pour cette mission de type "commando", la structure suivante est préconisée :

*   **Directeur de Projet : Ahm...[tronqué]
```

#### [STAFF-005] [Staffing] Candidats React.js disponibles pour AO e-commerce

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `staffing-persona` |
| Agent attendu | `hr` |
| Durée | `9700ms` |
| Tokens | `4675 in / 109 out` |
| Coût estimé | `$0.000383` |

**Prompt envoyé :**
```
On a un appel d'offre e-commerce qui nécessite 3 développeurs React.js. Quels consultants disponibles ont cette compétence ?
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:search_competencies', 'hr_agent:list_competency_users', 'hr_agent:get_users_bulk']`
**Réponse agent (315 chars) :**
```
Pour votre appel d'offre e-commerce, voici trois consultants disponibles possédant la compétence **React** :

1. **Alexandre PACAUD**
2. **Anon JCT**
3. **Anon MSO**

Souhaitez-vous que j'approfondisse l'analyse de ces profils (résumé des compétences, missions passées) pour valider leur adéquation avec le projet ?
```

#### [STAFF-006] [Staffing] Mix junior/senior pour optimiser le budget d'une mission

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `staffing-persona` |
| Agent attendu | `hr` |
| Durée | `10804ms` |
| Tokens | `18659 in / 414 out` |
| Coût estimé | `$0.001524` |

**Prompt envoyé :**
```
Pour optimiser le budget de la mission Java FinTech, propose-moi un mix de consultants : 1 senior Tech Lead + 2 juniors/confirmés avec des compétences Java Spring Boot.
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:list_missions']`
**Réponse agent (1365 chars) :**
```
Pour optimiser le budget tout en garantissant la réussite de votre mission Java FinTech, voici la composition d'équipe idéale que je vous recommande, basée sur nos consultants disponibles :

### Équipe recommandée : "Java FinTech"

| Rôle | Consultant | Séniorité | Justification |
| :--- | :--- | :--- | :--- |
| **Tech Lead** | **Ahmed KANOUN** | Senior | Expertise Java/Spring Boot confirmée, spécialisé en microservices et architecture robuste. |
| **Dév. Java** | **Anon RMO** | Mid | Maîtrise des APIs REST, architecture hexagonale et outils de qualité (SonarQube/Jenkins). |
| **Dév. Java** | **Melek SOUAI** | Mid | Expérience solide en Java/Spring Boot, Docker et pipelines CI/CD (GitLab). |

### Pourquoi ce mix ?
*   **Performance technique :** En confiant le leadership à **Ahmed KANOUN**...[tronqué]
```

#### [STAFF-007] [Staffing] Qui peut remplacer un consultant sur une mission ?

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `staffing-persona` |
| Agent attendu | `hr` |
| Durée | `19159ms` |
| Tokens | `7104 in / 441 out` |
| Coût estimé | `$0.000665` |

**Prompt envoyé :**
```
Si Ahmed KANOUN devait quitter la mission de modernisation Cloud Native GCP, qui parmi nos consultants pourrait le remplacer avec un profil similaire Java + GCP ?
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:search_users', 'hr_agent:get_user_missions', 'hr_agent:search_best_candidates', 'hr_agent:get_candidate_rag_context', 'hr_agent:get_candidate_rag_context']`
**Réponse agent (1285 chars) :**
```
Pour remplacer Ahmed KANOUN sur une mission de modernisation Cloud Native GCP, le candidat le plus pertinent parmi nos consultants est **Guillaume Le Floch**.

Voici pourquoi Guillaume est le choix idéal par rapport aux autres profils identifiés :

*   **Expertise technique alignée :** Guillaume possède une expertise senior en Java (Java 21, Spring Boot 3, Quarkus) et une solide expérience sur les environnements conteneurisés et les architectures microservices.
*   **Compétence Cloud GCP :** Contrairement à d'autres profils, Guillaume a une expérience concrète sur **GCP** ainsi qu'une maîtrise confirmée des outils de conteneurisation (Kubernetes, Helm) et de l'automatisation CI/CD, essentiels pour une modernisation Cloud Native.
*   **Profil Senior :** Son expérience de Lead Dev/Architecte...[tronqué]
```

#### [STAFF-008] [Staffing] Consultants data engineering disponibles pour un projet BigQuery

| Champ | Valeur |
|-------|--------|
| Statut | ✅ PASS |
| Catégorie | `staffing-persona` |
| Agent attendu | `hr` |
| Durée | `8995ms` |
| Tokens | `4156 in / 105 out` |
| Coût estimé | `$0.000343` |

**Prompt envoyé :**
```
J'ai besoin d'un data engineer maîtrisant BigQuery et Spark pour une mission analytics. Qui est disponible dans le pool ?
```

**Dispatches Router** (`ask_*`) : `['ask_hr_agent']`
**Tools sous-agents** : `['hr_agent:search_best_candidates', 'hr_agent:get_user_availability']`
**Réponse agent (331 chars) :**
```
Pour cette mission, **Guillaume Le Floch** (Data Engineer) a été identifié comme le profil le plus pertinent maîtrisant BigQuery et Spark.

Il semble disponible, aucune indisponibilité n'étant enregistrée. Souhaitez-vous que je vérifie ses missions précédentes pour confirmer son adéquation ou que j'approfondisse ses compétences ?
```


---

## 5. Propositions d'amélioration

> Ces propositions sont **générées automatiquement** à partir des anomalies observées.
> Chaque proposition inclut la cause racine identifiée et le correctif recommandé.

### 🟡 Proposition 4 — Tests trop lents : 5 test(s) > 10s ([STAFF-001], [STAFF-002], [STAFF-003], [STAFF-006], [STAFF-007])

**Durée moyenne sur les tests lents :** 15124ms

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

### ✅ Proposition 6 — Comportements golden à consolider ([STAFF-001], [STAFF-002], [STAFF-003], [STAFF-004], [STAFF-005], [STAFF-006], [STAFF-007], [STAFF-008])

Ces tests passent parfaitement : routing correct, tools appropriés, 0 warning.

- **[STAFF-001]** `J'ai une mission urgente qui démarre dans 2 semaines. J'ai besoin d'un consultant expert Kubernetes. Qui est disponible dans notre pool ?` → `['ask_hr_agent', 'hr_agent:search_best_candidates', 'hr_agent:get_user_availability', 'hr_agent:get_user_availability', 'hr_agent:get_user_availability']` en 11200ms
- **[STAFF-002]** `J'hésite entre deux profils pour la mission Java FinTech : Alexandre PACAUD et Ahmed KANOUN. Lequel est le plus adapté pour un rôle de Tech Lead Java Spring Boot ?` → `['ask_hr_agent', 'hr_agent:search_best_candidates', 'hr_agent:search_users', 'hr_agent:search_users', 'hr_agent:get_user_availability', 'hr_agent:get_user_availability', 'hr_agent:get_user_availability', 'hr_agent:get_candidate_rag_context', 'hr_agent:get_candidate_rag_context']` en 16955ms
- **[STAFF-003]** `Ahmed KANOUN est-il disponible pour rejoindre la mission Moteur de Rapprochement Factures (PR-2026-ZEN-FIN-04) ?` → `['ask_hr_agent', 'hr_agent:search_best_candidates', 'hr_agent:search_users', 'hr_agent:search_users', 'hr_agent:list_missions', 'hr_agent:get_user_cv', 'hr_agent:get_user_cv', 'hr_agent:get_candidate_rag_context', 'hr_agent:get_candidate_rag_context', 'hr_agent:get_user_availability']` en 17504ms
- **[STAFF-004]** `La mission PR-2026-ZEN-FIN-04 n'a pas encore d'équipe. Qui parmi nos consultants peut démarrer immédiatement sur ce type de mission Java ?` → `['ask_hr_agent', 'hr_agent:list_missions']` en 9858ms
- **[STAFF-005]** `On a un appel d'offre e-commerce qui nécessite 3 développeurs React.js. Quels consultants disponibles ont cette compétence ?` → `['ask_hr_agent', 'hr_agent:search_competencies', 'hr_agent:list_competency_users', 'hr_agent:get_users_bulk']` en 9700ms
- **[STAFF-006]** `Pour optimiser le budget de la mission Java FinTech, propose-moi un mix de consultants : 1 senior Tech Lead + 2 juniors/confirmés avec des compétences Java Spring Boot.` → `['ask_hr_agent', 'hr_agent:list_missions']` en 10804ms
- **[STAFF-007]** `Si Ahmed KANOUN devait quitter la mission de modernisation Cloud Native GCP, qui parmi nos consultants pourrait le remplacer avec un profil similaire Java + GCP ?` → `['ask_hr_agent', 'hr_agent:search_users', 'hr_agent:get_user_missions', 'hr_agent:search_best_candidates', 'hr_agent:get_candidate_rag_context', 'hr_agent:get_candidate_rag_context']` en 19159ms
- **[STAFF-008]** `J'ai besoin d'un data engineer maîtrisant BigQuery et Spark pour une mission analytics. Qui est disponible dans le pool ?` → `['ask_hr_agent', 'hr_agent:search_best_candidates', 'hr_agent:get_user_availability']` en 8995ms

**Action recommandée :** Activer `data_quality_strict=True` pour bloquer toute régression :
```python
TestCase(id="STAFF-001", ..., data_quality_strict=True),
```


---
*Rapport généré par `agent_prompt_tests.py` — Zenika Platform Engineering*