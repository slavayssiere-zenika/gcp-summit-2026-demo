# 📦 Scripts — Plateforme Zenika Console Agent

Répertoire des scripts d'exploitation, de déploiement et de maintenance de la plateforme.
Tous les scripts supportent les environnements `dev`, `uat`, `prd` via les fichiers `platform-engineering/envs/{env}.yaml`.

---

## 🚀 Déploiement & Infrastructure

### `deploy.sh`
Script principal de CI/CD. Détecte les changements, bumpe les versions, build les images Docker et déploie sur GCP Cloud Run.

```bash
./scripts/deploy.sh cv_api            # Déploie uniquement cv_api
./scripts/deploy.sh                   # Déploie tous les services modifiés
RAG_EVAL_ENABLED=true ./scripts/deploy.sh cv_api  # Avec évaluation RAG post-déploiement
```

> ⚠️ Seul script autorisé à modifier les fichiers `VERSION` et `envs/*.yaml`.

---

### `async_manage_env.sh`
Lance `manage_env.py` (Terraform apply) de façon asynchrone via un Cloud Run Job. Évite les timeouts locaux sur les gros apply.

```bash
./scripts/async_manage_env.sh apply prd
./scripts/async_manage_env.sh list-versions   # Liste les versions du job dans Artifact Registry
```

---

## 🔧 Opérations & Maintenance

### `mcp_cli.py` ⭐
CLI d'administration principale. Interagit avec les services MCP (`analytics`, `monitoring`) via JWT récupéré automatiquement depuis Secret Manager.

```bash
GCLOUD_BIN=/path/to/gcloud python3 scripts/mcp_cli.py <commande>

python3 scripts/mcp_cli.py tools analytics          # Lister les tools analytics
python3 scripts/mcp_cli.py tools monitoring         # Lister les tools monitoring
python3 scripts/mcp_cli.py finops daily             # Rapport FinOps du jour
python3 scripts/mcp_cli.py finops weekly            # Rapport FinOps hebdo
python3 scripts/mcp_cli.py errors --hours 2         # Erreurs 5xx récentes
python3 scripts/mcp_cli.py redis --pattern 'items:*' # Inspecter clés Redis
python3 scripts/mcp_cli.py dlq                      # Inspecter DLQ Pub/Sub
python3 scripts/mcp_cli.py health                   # Health check global
python3 scripts/mcp_cli.py query 'SELECT ...'       # SQL SELECT sur AlloyDB
python3 scripts/mcp_cli.py --env dev finops daily   # Cibler dev
python3 scripts/mcp_cli.py --no-cache health        # Forcer nouveau login JWT
```

**Auth** : cache JWT dans `~/.cache/zenika_mcp_cli_token_{env}.json` (TTL 55 min). Mot de passe via Secret Manager (`admin-password-{env}`).

---

### `reindex_cv.py` ⭐
Déclenche et surveille la ré-indexation des CVs — **embeddings globaux** (vecteur unique par profil) et/ou **chunks de missions** (RAG multi-vecteur R7). Surveille la progression via les logs Cloud Run (`[REINDEX]` ou `[CHUNK_REINDEX]`) et affiche un rapport qualifié final avec stats SQL et FinOps.

> 🔄 **Remplace** l'ancien `reindex_embeddings.py` (supprimé).

```bash
GCLOUD_BIN=/path/to/gcloud python3 scripts/reindex_cv.py

# Modes
python3 scripts/reindex_cv.py                              # embeddings globaux (défaut)
python3 scripts/reindex_cv.py --mode chunks                # chunks de missions (RAG R7)
python3 scripts/reindex_cv.py --mode both                  # les deux en séquence

# Filtres
python3 scripts/reindex_cv.py --tag Paris                  # Seulement l'agence Paris
python3 scripts/reindex_cv.py --user-id 42                 # Un seul utilisateur

# Options
python3 scripts/reindex_cv.py --env dev                    # Sur dev
python3 scripts/reindex_cv.py --no-cache                   # Forcer nouveau login JWT
python3 scripts/reindex_cv.py --mode chunks --no-logs      # Déclencher sans surveiller
```

**Logs surveillés** : `[REINDEX]` pour les embeddings globaux, `[CHUNK_REINDEX]` pour les chunks.  
**Timeout** : 30 min pour embeddings, 90 min pour chunks (configurable via `REINDEX_TIMEOUT_S`).

> ⚠️ Après `--mode chunks`, activer `RAG_CHUNKED_SEARCH=true` dans Terraform pour que la recherche utilise les chunks.

---

### `sync_prompts.py`
Synchronise les system prompts des agents depuis des fichiers locaux vers la base de données via `prompts_api`. Utile pour les mises à jour batch de prompts sans passer par l'UI.

```bash
python3 scripts/sync_prompts.py --env prd --dry-run   # Prévisualisation
python3 scripts/sync_prompts.py --env prd             # Sync réelle
```

## 📊 Qualité & Évaluation RAG

### `run_rag_eval.sh`
Évalue la qualité du retrieval sémantique (Recall@5) sur le golden dataset `cv_api/eval/golden_queries.json`. Intégré dans `deploy.sh` si `RAG_EVAL_ENABLED=true`.

```bash
./scripts/run_rag_eval.sh --env prd
./scripts/run_rag_eval.sh --env dev --dry-run       # Ne bloque pas sur les métriques
./scripts/run_rag_eval.sh --env prd --fail-fast     # Stoppe au premier échec
./scripts/run_rag_eval.sh --env dev --tag cloud     # Cas golden filtrés par tag
```

---

### `calibrate_rag.sh`
Calibrage du golden dataset RAG en 3 étapes : dry-run des top-10 résultats réels → génération d'un rapport markdown → injection automatique des IDs pertinents dans `golden_queries.json`.

```bash
./scripts/calibrate_rag.sh --env dev    # Calibrage sur dev (recommandé)
./scripts/calibrate_rag.sh --env prd    # Calibrage sur prd
```

---

## 🧪 Tests

### `run_tests.sh`
Lance les tests unitaires et les tests d'intégration Testcontainers sur tous les services détectés, en parallèle.

```bash
./scripts/run_tests.sh              # Tous les services
./scripts/run_tests.sh cv_api       # Un service spécifique
```

---

## 🎭 Génération de données (Démo / GCP Summit)

### `generate_gcp_summit_data.py`
Génère le jeu de données complet pour la démo GCP Summit : agences, utilisateurs, CVs fictifs, missions. Orchestre l'ensemble de la chaîne d'ingestion.

```bash
python3 scripts/generate_gcp_summit_data.py
```

---

### `generate_fake_agencies.py`
Génère des CVs fictifs réalistes (via Gemini + Faker) et les upload dans Google Drive par agence. Utilisé pour peupler l'environnement de démo.

```bash
python3 scripts/generate_fake_agencies.py
```

---

### `generate_fake_missions.py`
Génère des missions client fictives et les injecte via `missions_api`.

```bash
python3 scripts/generate_fake_missions.py
```

---

## 📝 Génération de documentation

### `generate_changelog.py`
Génère un changelog structuré depuis les commits Git non encore mergés sur `main`. Appelé par `deploy.sh` avant chaque déploiement.

```bash
python3 scripts/generate_changelog.py
```

---

### `generate_readmes.py`
Génère ou met à jour les fichiers `README.md` de chaque service via un LLM (Gemini). Analyse le code source et produit une documentation structurée.

```bash
python3 scripts/generate_readmes.py
```

---

### `generate_pipeline_docs.py`
Génère la documentation technique des pipelines de données (Pub/Sub, Drive, Batch) sous forme de diagrammes Mermaid et de fichiers Markdown.

```bash
python3 scripts/generate_pipeline_docs.py
```

---

### `generate_specs.py`
Génère les fichiers `spec.md` de chaque service (contrat d'interface API) à partir des routes FastAPI.

```bash
python3 scripts/generate_specs.py
```

---

## 🔬 Outils de développement

## ⚙️ Fichiers de support

| Fichier | Rôle |
|---|---|
| `requirements.txt` | Dépendances Python des scripts (`httpx`, `pyyaml`, `pytest`…) |
| `logger_config.py` | Configuration du logger partagé entre les scripts Python |
| `.antigravity_env` | Surcharges locales de variables d'environnement (non versionné) |

---

## 📌 Fichiers internes

| Fichier | Statut |
|---|---|
| `agent_prompt_tests.py` | Tests de prompts agents (>150k) — utilisé par `/analyse-prompt` |
| `_insert_ui_format_tests.py` | Script interne de génération de tests UI |
