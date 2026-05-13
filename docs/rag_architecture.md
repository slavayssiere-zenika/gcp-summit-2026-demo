# Architecture RAG — Zenika Console Agent

> Ce document décrit l'ensemble des mécanismes mis en place pour rendre le moteur de recherche sémantique le plus précis et le plus robuste possible, du pipeline d'extraction des CVs jusqu'à l'utilisation par l'agent HR.

---

## Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PIPELINE RAG ZENIKA                               │
│                                                                             │
│  ① INGESTION         ② DISTILLATION        ③ EMBEDDING        ④ STOCKAGE  │
│  Drive PDF/Doc  ──▶  LLM Structured  ──▶  Gemini Embedding ──▶  pgvector  │
│                       Extraction           (3072 dimensions)   (HNSW index)│
│                                                                             │
│  ⑤ RECHERCHE         ⑥ FILTRAGE           ⑦ ENRICHISSEMENT   ⑧ AGENT HR  │
│  Query ──▶ embed ──▶  cosine distance ──▶  users_api       ──▶  Réponse   │
│            (Gemini)   + threshold R2        + source_url                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## ① Pipeline d'ingestion des CVs

**Service** : `cv_api` | **Déclencheur** : Google Drive Pub/Sub

```
Google Drive
    │  (PDF/DOCX/Google Doc)
    ▼
drive_api ──▶ Pub/Sub topic:cv-import
    │
    ▼
cv_api worker (pubsub_handler.py)
    │  ① Téléchargement du document (URL Drive)
    │  ② Export texte brut (Google Docs API)
    │  ③ Extraction LLM → JSON structuré (cv_extraction_service.py)
    │  ④ Résolution identité Zenika (users_api)
    │  ⑤ Stockage cv_profiles (cv_storage_service.py)
    │  ⑥ Embedding vectoriel (embedding_service.py)
    ▼
PostgreSQL (cv_profiles) + pgvector index
```

### Ce qui est extrait par le LLM

Le prompt d'extraction (`prompts_api → cv_api.extract_cv_info`) produit un JSON structuré avec :

| Champ | Usage RAG |
|---|---|
| `current_role` | Titre du consultant — ancre sémantique principale |
| `summary` | Résumé libre — capte le style et la spécialité |
| `years_of_experience` | Filtre de séniorité |
| `competencies[]` | Mots-clés techniques indexés |
| `missions[]` | Jusqu'à 6 dernières missions avec skills + description |
| `educations[]` | Formation — signal complémentaire |

---

## ② Distillation du contenu vectorisé

**Fichier** : `cv_api/src/services/utils.py` → `_build_distilled_content()`

Au lieu de vectoriser le texte brut du PDF (bruité, répétitif, mal formaté), on construit un texte sémantique normalisé :

```
ROLE: Lead DevOps Engineer
EXPERIENCE: 8 years
SUMMARY: Expert infrastructure cloud GCP/AWS, spécialiste Kubernetes et CI/CD...
COMPETENCIES: Kubernetes, Terraform, GCP, CI/CD, Helm, Docker, ArgoCD, ...
EDUCATIONS: Ingénieur @ INSA Lyon
RECENT_MISSIONS:
Mission (2022-2024): Tech Lead @ BNP Paribas | Kubernetes, GKE, Terraform | Migration infra...
Mission (2020-2022): DevOps Engineer @ Société Générale | Jenkins, Docker, Ansible | ...
```

**Pourquoi c'est important** : Ce format garantit que le modèle d'embedding reçoit un signal sémantique dense et structuré, sans le bruit des mises en page PDF.

---

## ③ Embedding vectoriel

**Service** : `embedding_service.py`  
**Modèle** : `GEMINI_EMBEDDING_MODEL` (variable d'env — jamais hardcodé)  
**Dimensions** : 3072 (natif `gemini-embedding-001`)  
**Task type** : `RETRIEVAL_DOCUMENT` pour le stockage, `RETRIEVAL_QUERY` pour les requêtes

### R1 — Versionning du modèle d'embedding

```python
# cv_profiles.embedding_model (VARCHAR 100) — ajouté par migration #12
profile.embedding_model = os.getenv("GEMINI_EMBEDDING_MODEL")
```

**Problème résolu** : Sans versionning, changer de modèle d'embedding produit des vecteurs incompatibles. Les distances cosine entre vecteurs `gemini-embedding-001` et `gemini-embedding-002` sont sans signification.

**Comportement** : La recherche filtre par `embedding_model = current_model OR NULL` (tolérance des anciens profils non migrés).

### Re-indexation

```bash
# Via tool MCP (agent ou CLI) :
reindex_cv_embeddings  # Lance en arrière-plan via /reindex-embeddings

# Après un changement de GEMINI_EMBEDDING_MODEL, OBLIGATOIRE :
# 1. Déployer cv_api avec le nouveau modèle
# 2. Déclencher reindex_cv_embeddings (admin uniquement)
# 3. Valider avec calibrate_rag.sh --validate
```

---

## ④ Stockage vectoriel (pgvector + HNSW)

**Table** : `cv_profiles`  
**Index** : HNSW (`lists=100`, `probes=10`) sur `semantic_embedding`  
**Métrique** : Cosine distance

| Colonne | Type | Rôle |
|---|---|---|
| `semantic_embedding` | `vector(3072)` | Vecteur dense du profil distillé |
| `embedding_model` | `VARCHAR(100)` | Modèle ayant produit le vecteur (R1) |
| `source_url` | `TEXT` | URL Drive du CV source (R5 — citations) |
| `source_tag` | `VARCHAR` | Agence/ville pour filtrage géographique |

**Pourquoi HNSW** : Complexité `O(log N)` vs `O(N)` pour la recherche exacte. Pour 5000 CVs, la recherche est < 100ms.

---

## ⑤ Recherche vectorielle

**Endpoint** : `GET /search?query=...&limit=5&agency=Paris`  
**Fichier** : `cv_api/src/services/search_service.py`

### Pipeline de recherche

```
1. Vectorisation de la query
   embed(query, task_type=RETRIEVAL_QUERY, model=GEMINI_EMBEDDING_MODEL)

2. Recherche pgvector
   SELECT user_id, cosine_distance(semantic_embedding, query_vector) AS distance
   FROM cv_profiles
   WHERE embedding_model = current_model OR embedding_model IS NULL  -- R1
     AND cosine_distance(...) < VECTOR_DISTANCE_THRESHOLD            -- R2
   ORDER BY distance
   LIMIT MAX_VECTOR_CANDIDATES                                        -- Fix 2.12

3. Filtrage par compétences canoniques (optionnel)
   Si competencies_api disponible : croise les IDs avec la taxonomie

4. Déduplication + pagination (skip/limit)

5. Enrichissement users_api
   GET /users/{user_id} → full_name, email, is_active

6. Retour structuré avec source_url + embedding_model (R5)
```

---

## ⑥ Guardrails de pertinence

### R2 — Seuil de distance cosine (`VECTOR_DISTANCE_THRESHOLD`)

```
Distance cosine : 0.0 = identique, 1.0 = opposé
Seuil défaut    : 0.55 (soit ~0.45 de similarité)

  ┌────────────────────┬───────────────────────────┐
  │ distance < 0.3     │ Très pertinent (rare)     │
  │ distance 0.3-0.55  │ Zone de pertinence (GARDÉ)│
  │ distance > 0.55    │ Hors-sujet (FILTRÉ par R2)│
  └────────────────────┴───────────────────────────┘
```

**Calibrage** : Si trop peu de résultats → augmenter le seuil (0.65). Si résultats hors-sujet → réduire (0.45).

### Fix 2.12 — Pool vectoriel non tronqué (`MAX_VECTOR_CANDIDATES`)

```python
# AVANT (anti-pattern) : seuls 10 candidats explorés pour limit=5, skip=0
.limit((limit + skip) * 2)   # → max 10 candidats

# APRÈS : pool configurable, indépendant de la pagination
.limit(MAX_VECTOR_CANDIDATES) # → défaut 500 candidats
```

**Problème résolu** : Avec l'ancien pattern, des candidats très pertinents au rang 11+ étaient invisibles.

### Headers HTTP de monitoring (R6)

```
X-Threshold-Filtered-Count: 47   → candidats rejetés par R2 sur cette requête
X-Distance-Threshold: 0.55       → valeur active du seuil
X-Fallback-Full-Scan: false      → si true : recherche dégradée (pas de compétences)
```

---

## ⑦ Citations sources (R5)

Chaque résultat de recherche expose désormais `source_url` :

```json
{
  "user_id": 42,
  "similarity_score": 0.8731,
  "source_url": "https://docs.google.com/document/d/1abc...xyz",
  "embedding_model": "gemini-embedding-001"
}
```

**Usage agent** : Le tool MCP `search_best_candidates` indique explicitement à l'agent HR : *"IMPORTANT : si source_url est présent, toujours le mentionner dans la réponse finale comme référence du CV."*

---

## ⑧ Utilisation par l'agent HR

**Service** : `agent_hr_api` | **Tool MCP** : `cv_api.search_best_candidates`

### Flux de décision de l'agent

```
Question utilisateur : "Trouve-moi un expert Kubernetes à Paris"
        │
        ▼
agent_hr_api (ADK + Gemini)
  ├── Tool: search_best_candidates(query="expert Kubernetes", agency="Paris")
  │     └── cv_api /search → top-5 résultats avec scores + source_url
  │
  ├── Tool: get_candidate_rag_context(user_id=42)
  │     └── cv_api /user/42/rag-context → résumé distillé + missions
  │
  └── Génération de la réponse
        ├── Classement par similarity_score
        ├── Justification basée sur le contexte RAG
        └── Citation des sources Drive (R5)
```

### Tools MCP disponibles (ordre d'utilisation recommandé)

| Ordre | Tool | Usage |
|---|---|---|
| 1 | `search_best_candidates` | Requête sémantique large |
| 1bis | `search_candidates_multi_criteria` | Requête multi-critères pondérés |
| 1ter | `match_mission_to_candidates` | Quand `mission_id` connu — plus précis |
| 2 | `get_candidate_rag_context` | Enrichissement narratif du profil |
| 3 | `get_rag_snippet` | Passages textuels de justification |
| opt | `find_similar_consultants` | "Quelqu'un comme Jean Dupont" |

---

## ⑨ Évaluation et calibrage RAG

### Métriques calculées

| Métrique | Formule | Seuil OK |
|---|---|---|
| **Recall@K** | `|retrieved ∩ expected| / |expected|` | ≥ 0.5 |
| **MRR** | `1 / position du premier hit` | > 0.3 |
| **Precision@K** | `|retrieved ∩ expected| / K` | indicatif |

### Suite de tests (`cv_api/eval/test_rag_quality.py`)

25 tests répartis en 3 groupes, exécutés contre l'API réelle :

| Groupe | Tests | Ce qui est vérifié |
|---|---|---|
| `test_rag_recall_at_k` | 8 × cas golden | Recall@5 ≥ seuil par cas |
| `test_rag_results_have_source_url` | 8 × cas golden | Champ `source_url` présent **(R5)** |
| `test_rag_results_have_embedding_model` | 8 × cas golden | Champ `embedding_model` présent **(R1)** |
| `test_rag_threshold_header_present` | 1 | Header `X-Distance-Threshold` dans la réponse **(R6)** |

> **Diagnostic des échecs** : Si `source_url` ou `embedding_model` sont absents, la version déployée en PRD est **antérieure** aux changements R1/R5. Le code source local est correct — il faut déployer `cv_api`.

### Golden dataset (`cv_api/eval/golden_queries.json`)

8 cas représentatifs des profils Zenika :

| ID | Requête | Difficulté |
|---|---|---|
| `GCP_DEVOPS_001` | Expert DevOps GCP / Kubernetes / Terraform | Spécifique |
| `DATA_ENGINEER_001` | Data Engineer BigQuery / Spark / Python | Courant |
| `FULLSTACK_REACT_001` | Fullstack React / TypeScript / Node.js | Courant |
| `ARCHITECT_CLOUD_001` | Architecte multi-cloud AWS/GCP/Azure | Rare |
| `SECURITY_ZEROTRUST_001` | Expert IAM / Zero Trust / DevSecOps | Très spécifique |
| `AGILE_COACH_001` | Coach Agile / Scrum / SAFe | Soft skills |
| `MLOPS_001` | MLOps / Vertex AI / déploiement modèles | Émergent |
| `SENIOR_JAVA_001` | Java senior / Spring Boot / 10 ans XP | Courant |

### Pipeline de calibrage — `scripts/calibrate_rag.sh`

Le script est **entièrement automatisé** — aucune intervention manuelle requise.

```
./scripts/calibrate_rag.sh --env prd
          │
          ▼
ÉTAPE 1/3 — Dry-run (top-10 IDs par cas)
  → JWT récupéré via Secret Manager (project_id auto-détecté depuis envs/prd.yaml)
  → POST https://prd.zenika.slavayssiere.fr/auth/login
  → GET /api/cv/search?query=...&limit=10 × 8 cas
  → Affiche les scores et IDs dans le terminal

ÉTAPE 2/3 — Injection automatique
  → Parse les Top-10 IDs depuis le log dry-run (Python inline)
  → Patch golden_queries.json : "expected_user_ids": [710, 478, ...]
  → 8/8 cas mis à jour sans ouvrir un éditeur

ÉTAPE 3/3 — Validation Recall@5
  → pytest cv_api/eval/test_rag_quality.py (25 tests)
  → ✅ si tous passent → rappel commande deploy
  → ⚠️  si échecs → affiche les cas à investiguer
```

**Variables d'environnement supportées :**

```bash
ZENIKA_ADMIN_EMAIL=admin@zenika.com   # Email admin (défaut)
ZENIKA_SECRET_NAME=admin-password-prd # Nom du secret GCP (défaut)
GCLOUD_BIN=/path/to/gcloud            # Binaire gcloud (défaut: PATH)
```

### Intégration `manage_env.py`

Le calibrage est intégré comme **commande dédiée** et comme **hook automatique** dans le pipeline de déploiement :

#### Commande manuelle

```bash
python3 platform-engineering/manage_env.py rag-calibrate --env prd
# → JWT Secret Manager → dry-run top-10 → patch golden_queries.json
```

#### Déclenchement automatique lors d'un `deploy`

```
manage_env.py deploy --env prd
    │
    ├── ... (Terraform, sanity checks)
    │
    └── Détection changement embedding_model
          ├── gemini_embedding_model: "gemini-embedding-001" (inchangé)
          │     → Pas de calibrage (état persisté dans .rag_model_state.json)
          │
          └── gemini_embedding_model: "gemini-embedding-002" (CHANGÉ)
                → ⚠️  Changement détecté : gemini-embedding-001 → gemini-embedding-002
                → rag_calibrate() appelé automatiquement avec le JWT du sanity check
                → golden_queries.json mis à jour
                → .rag_model_state.json mis à jour (prd → gemini-embedding-002)
```

**Quand le calibrage est-il pertinent ?**

| Événement | Calibrage ? | Pourquoi |
|---|---|---|
| Changement de `gemini_embedding_model` | ✅ **Obligatoire** | Vecteurs incompatibles — top-K changent entièrement |
| Modification de `_build_distilled_content()` | ✅ Recommandé | Le texte vectorisé change → mêmes effets |
| Premier déploiement d'un env | ✅ Manuel une fois | `expected_user_ids` vide |
| Déploiement cv_api (bug fix, nouvelle route) | ❌ Inutile | Pas de changement d'embedding |
| Ajout massif de CVs (> 20%) | ⚠️ Optionnel | Nouveaux profils → top-K peut changer |

### Intégration CI/CD (`deploy.sh`)

```
./scripts/deploy.sh cv_api
    │
    ├── ① Tests unitaires (pytest --cov) — bloquant
    ├── ② Smoke test Docker — bloquant
    ├── ③ Cloud Run update — bloquant
    └── ④ RAG Eval (si RAG_EVAL_ENABLED=true) — NON bloquant
          └── scripts/run_rag_eval.sh --env <env>
                ├── Recall@5 ≥ 0.5 → "✅ Qualité RAG validée"
                └── Recall@5 < 0.5 → warning dans deploy summary (pas de rollback auto)
```

```bash
# Activer l'évaluation post-déploiement cv_api
RAG_EVAL_ENABLED=true ./scripts/deploy.sh cv_api
```

---

## ⑩ Monitoring en production (Grafana)

### Métriques Prometheus exposées

```promql
# Ratio de candidats filtrés par R2 (indicateur de pertinence des requêtes)
rate(cv_search_threshold_filtered_total[5m])

# Distribution des scores de similarité retournés
histogram_quantile(0.5, cv_search_result_similarity_score_bucket)
histogram_quantile(0.9, cv_search_result_similarity_score_bucket)

# Profils sans embedding (besoin de re-indexation)
cv_missing_embeddings_total
```

### Alertes recommandées

| Alerte | Condition | Action |
|---|---|---|
| Ratio filtrage > 80% | `threshold_filtered / (filtered + returned) > 0.8` | Augmenter `VECTOR_DISTANCE_THRESHOLD` |
| Score médian < 0.5 | `histogram_quantile(0.5, ...) < 0.5` | Vérifier la qualité des prompts / modèle |
| Embeddings manquants > 10 | `cv_missing_embeddings_total > 10` | Déclencher `reindex_cv_embeddings` |

---

## Variables d'environnement clés

| Variable | Service | Défaut | Description |
|---|---|---|---|
| `GEMINI_EMBEDDING_MODEL` | `cv_api` | *(requis)* | Modèle d'embedding — **ne jamais changer sans re-indexer** |
| `VECTOR_DISTANCE_THRESHOLD` | `cv_api` | `0.55` | Seuil de pertinence cosine (R2) |
| `MAX_VECTOR_CANDIDATES` | `cv_api` | `500` | Pool max de candidats explorés |
| `RAG_EVAL_ENABLED` | `deploy.sh` | `false` | Active l'évaluation post-déploiement |
| `RAG_EVAL_RECALL_THRESHOLD` | `run_rag_eval.sh` | `0.5` | Seuil Recall@K global |
| `RAG_EVAL_TOP_K` | `run_rag_eval.sh` | `5` | K pour les métriques d'évaluation |

---

## Procédures opérationnelles

### Changer de modèle d'embedding

```bash
# ⚠️  OPÉRATION CRITIQUE — produit une régression si mal exécutée
# 1. Mettre à jour GEMINI_EMBEDDING_MODEL dans envs/dev.yaml (ou prd.yaml)
# 2. Déployer cv_api
RAG_EVAL_ENABLED=true ./scripts/deploy.sh cv_api
# → L'évaluation va détecter la régression (normal à ce stade)

# 3. Déclencher la re-indexation (via l'agent ou la CLI MCP)
python3 scripts/mcp_cli.py call cv reindex_cv_embeddings

# 4. Attendre la fin de la re-indexation
python3 scripts/mcp_cli.py call cv get_reanalyze_status

# 5. Re-calibrer et valider
./scripts/calibrate_rag.sh --env dev --validate
```

### Diagnostiquer une régression RAG

```bash
# 1. Voir les métriques de filtrage
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.dev.zenika.slavayssiere.fr/api/cv/search?query=expert+cloud&limit=5" \
  -I | grep "X-Threshold\|X-Fallback"

# 2. Lancer l'évaluation en dry-run pour voir les scores actuels
RAG_EVAL_DRY_RUN=true ./scripts/run_rag_eval.sh --env dev

# 3. Vérifier les embeddings manquants
python3 scripts/mcp_cli.py call cv get_data_quality_report
```
