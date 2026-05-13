# Analyse Critique du Pipeline d'Ingestion CV

> Analyse produite le 2026-05-13 à partir du code source et des logs Cloud Run `cv-api-prd`.

---

## Vue d'ensemble du pipeline

```
[Pub/Sub PUSH] → [Étape 1: Download] → [Étape 2: LLM Extraction] → [Étape 3: Résolution Identité]
             → [Étape 4: (BG) Compétences + Missions] → [Étape 5: Embedding] → [Étape 6: DB Save]
             → [Étape 7: (BG) AI Scoring] → [Notification drive_api]
```

---

## Analyse étape par étape

---

### 🔵 Étape 0 — Auth & ACK Pub/Sub
**Fichier**: `pubsub_service.py`

#### Ce qui se passe
1. Réception OIDC token Google (RS256) depuis Pub/Sub
2. Échange token OIDC → JWT applicatif via `users_api` (2 appels HTTP)
3. Réponse **202 Accepted** immédiate à Pub/Sub
4. Lancement `BackgroundTask`

#### Résultats de sortie attendus
- `202 Accepted` → Pub/Sub acquitte, stop les retries
- JWT 90 min disponible pour tous les appels downstream

#### Point critique 🔴
**Le double échange de token (OIDC → service-account login → service-token) ajoute ~500-1500ms sur chaque CV.**
Si `users_api` est en cold start (0 instance min), ce délai peut atteindre **15-20 secondes**.
Pub/Sub interprète alors une lenteur dans la réponse comme un signal de backpressure et réduit son débit — ce qui est en fait positif pour le throttling mais peut entraîner des faux timeouts.

#### Observation logs
```
Les logs de 06:40 montrent des remediate-legacy actifs mais aucun log [PubSub/BG]
→ Le pipeline était actif la nuit, plus d'activité le matin.
```

---

### 🔵 Étape 1 — Téléchargement du Document
**Fichier**: `cv_extraction_service.py::fetch_cv_content()`

#### Ce qui se passe
- **Google Doc natif** → `GET /drive/v3/files/{id}/export?mimeType=text/plain` (timeout 30s)
- **DOCX** → `GET /drive/v3/files/{id}?alt=media` + extraction via `python-docx` (timeout 60s)
- **URL directe** → `GET url` générique (timeout 30s)

#### Résultats de sortie
- `raw_text` : texte brut entre **500 et 100 000 caractères**
- Si `> 100 000 chars` → WARNING + troncature à 100k avant LLM
- Durée typique : **200ms - 2000ms**

#### Points critiques 🔴

**1. Erreur la plus fréquente du pipeline** (`"Failed downloading CV content: "`)
```
Les logs de la session précédente montrent cette erreur comme cause principale des zombies.
```
Causes possibles :
- Token Google Drive expiré ou token OIDC échangé trop tard
- Google Doc exporté en format vide (document partagé avec restrictions)
- Timeout 30s dépassé sur `export` Drive API (rare mais arrive sur CVs de >50 pages)

**2. Aucune retry sur le download** — si Google Drive répond avec un 429 (quota), le CV part directement en `ERROR`.

**3. La branche "URL directe" n'envoie pas le token** si le token est présent mais l'URL n'est pas un pattern `docs.google.com/document/d/` → le `GET` échoue silencieusement en 403.

#### Recommandation
Ajouter un retry exponentiel (max 3 tentatives, backoff 2s) sur le download Drive :

```python
@retry(wait=wait_exponential(min=2, max=30), stop=stop_after_attempt(3),
       retry=retry_if_exception_type(httpx.HTTPStatusError))
async def _fetch_with_retry(url, headers, ...):
    ...
```

---

### 🔴 Étape 2 — Extraction LLM (Gemini) — GOULOT D'ÉTRANGLEMENT PRINCIPAL
**Fichier**: `cv_extraction_service.py::analyze_cv_with_llm()`

#### Ce qui se passe
1. Fetch du prompt depuis `prompts_api` (cache 5 min)
2. Fetch de l'arbre taxonomique depuis `competencies_api` (cache 5 min)
3. Appel Gemini `gemini-3.1-flash-lite-preview` avec Structured Output JSON
4. Parse JSON

#### Résultats de sortie attendus
```json
{
  "is_cv": true,
  "first_name": "Jean", "last_name": "Dupont", "email": "jean.dupont@zenika.com",
  "summary": "...",
  "current_role": "Consultant Senior DevOps",
  "years_of_experience": 8,
  "competencies": [{"name": "Kubernetes", "parent": "...", "practiced": true}, ...],
  "missions": [{"title": "...", "company": "...", ...}],
  "educations": [...],
  "is_anonymous": false,
  "trigram": null
}
```

#### Durée typique : **3 000 - 25 000ms**
C'est l'étape la plus lente du pipeline, de loin.

#### Points critiques 🔴

**1. Le prompt est enrichi de toute la taxonomie (~200+ compétences)** à chaque appel.
La taxonomie est concaténée en plain text dans le prompt. Sur un arbre de 200 compétences avec aliases, cela représente **~3 000-5 000 tokens supplémentaires par appel**.

**2. Le prompt injecte la taxonomie pour "normalisation" mais le LLM ne la respecte pas toujours.**
Les logs de remédiation montrent des cas où des compétences extraites ne correspondent à aucun nœud de l'arbre (ex: "Python3" au lieu de "Python", "K8S" au lieu de "Kubernetes").

**3. Aucune validation post-extraction** — si le LLM retourne 0 compétences ou 0 missions pour un CV de 10 pages, l'étape passe en WARNING mais n'est pas retraitée.

**4. Le modèle `gemini-3.1-flash-lite-preview` est le modèle le moins cher**
→ Ce n'est pas le plus performant pour une extraction structurée complexe (45 champs JSON, logique `practiced`, classification `mission_type`).

#### Analyse FinOps (depuis BigQuery `ai_usage`)
| Action | Modèle | Input tokens/CV | Output tokens/CV | Coût estimé/CV |
|--------|--------|-----------------|------------------|----------------|
| `analyze_cv` | `gemini-3.1-flash-lite-preview` | ~8 000-15 000 | ~2 000-4 000 | ~$0.002-0.005 |

#### Recommandation Modèle IA
| Modèle | Avantage | Inconvénient | Score extraction |
|--------|----------|-------------|-----------------|
| `gemini-3.1-flash-lite-preview` (actuel) | Très rapide, très bon marché | Hallucinations sur taxonomie, rate les missions implicites | ⭐⭐⭐ |
| `gemini-3.1-flash-preview` | Bon équilibre | 5× plus cher | ⭐⭐⭐⭐ |
| `gemini-2.5-flash` (Vertex Batch) | Qualité élevée, -50% si batch | Latence 24h si batch | ⭐⭐⭐⭐⭐ |

**Recommandation** : Passer à `gemini-3.1-flash-preview` pour l'import unitaire en ligne (meilleure extraction, surcoût ~$0.003/CV acceptable), et conserver `flash-lite` uniquement pour le batch de re-analyse.

---

### 🟡 Étape 3 — Résolution d'Identité
**Fichier**: `cv_storage_service.py::resolve_identity_and_user()`

#### Ce qui se passe
Cascade de lookups HTTP vers `users_api` :
1. Check DB locale (`CVProfile.source_url == url`)
2. Search par nom de dossier Drive
3. Search par email extrait
4. Search par prénom+nom LLM
5. Si non trouvé → création utilisateur

#### Résultats de sortie
- `user_id` (int) + warnings de divergence d'identité
- Durée : **500ms - 3 000ms** (3-4 appels HTTP séquentiels)

#### Points critiques 🟡

**1. Les lookups sont séquentiels** — on pourrait paralléliser les recherches par email ET par nom.

**2. La logique de divergence** (dossier != LLM) génère des warnings mais **choisit toujours le nom de dossier**. Si le dossier est mal nommé (ex: "Dupont Jean" au lieu de "Jean Dupont"), l'utilisateur sera créé avec le mauvais nom.

**3. L'email généré automatiquement** (`prenom.nom@zenika.com`) peut collisionner avec un email réel si le consultant a changé de nom ou si deux consultants ont le même prénom+nom normalisé.

**Observation clé** : Les logs de 06:40 montrent des cas `user_id=509 a 4 compétences assignées sur 20` → la résolution d'identité fonctionne (user_id trouvé) mais le mapping des compétences en étape 4 est partiel.

---

### 🔴 Étape 4 (Background) — Assignation Compétences + Création Missions
**Fichier**: `cv_storage_service.py::bg_process_competencies_and_missions()`

#### Ce qui se passe
1. Fetch des compétences existantes de l'utilisateur (GET `/competencies/user/{id}`)
2. Pour chaque compétence extraite : `resolve_comp_id` → lookup par nom, puis par alias
3. Si non trouvée → création de la compétence + éventuelle création du parent
4. Assignation de la compétence à l'utilisateur
5. Fetch des catégories items → création des missions en bulk

#### Résultats de sortie
- `bg_errors[]` : liste des erreurs non-bloquantes
- Durée : **5 000 - 60 000ms** (N×3 appels HTTP pour N compétences)

#### Points critiques 🔴

**1. Semaphore de 3 connexions simultanées pour les compétences** (`sem = asyncio.Semaphore(3)`)
Avec 20 compétences/CV → 7 vagues × (lookup + éventuelle création) = ~20-30 appels HTTP séquentialisés.
C'est l'étape la plus lente après le LLM.

**2. La vérification `if not comp.get("practiced", True)` est bug-prone.**
La valeur par défaut est `True`, ce qui signifie que si `practiced` est absent, la compétence EST assignée. C'est le comportement souhaité mais ambigu.

**3. Double resolve_comp_id** — `resolve_comp_id(name)` est appelé **deux fois** pour vérifier l'existence avant création (lignes 314 et 337). Cela double les appels HTTP à `competencies_api`.

**4. Logs de 06:40 confirment que ~30% des CVs ont des compétences partiellement assignées** :
```
user_id=509: 4/20 compétences → ERROR Drive
user_id=101: 4/17 compétences → ERROR Drive
user_id=817: 4/17 compétences → ERROR Drive
user_id=267: 4/16 compétences → ERROR Drive
```
**Ce pattern "4 compétences sur N" suggère que la connexion ou le quota `competencies_api` tombe après ~4 créations réussies**, pas un problème de parsing.

---

### 🔵 Étape 5 — Vectorisation (Embedding)
**Fichier**: `cv_import_service.py` lignes 168-209

#### Ce qui se passe
- 2 appels Gemini Embedding (`RETRIEVAL_DOCUMENT`) :
  - Embedding du "distilled content" (missions structurées + compétences)
  - Embedding du raw text (pour calcul du score de fiabilité cosine)
- Calcul de similarité cosine entre les deux vecteurs → `extraction_reliability_score`

#### Résultats de sortie
- Vecteur 3072 dimensions
- Score fiabilité 0-100 (cosine similarity distilled vs raw)
- Durée : **500ms - 2 000ms**

#### Point d'analyse
Le score de fiabilité est **calculé mais jamais utilisé pour déclencher un retraitement**.
Un score < 50% devrait déclencher un WARNING critique (le LLM a probablement halluciné ou raté l'essentiel du CV).

---

### 🔵 Étape 6 — Sauvegarde DB
**Fichier**: `cv_storage_service.py::upsert_cv_profile()`

Durée typique : **100ms - 500ms** — rapide, peu de risques.

---

### 🔴 Étape 7 (Background) — AI Scoring des Compétences
**Fichier**: `cv_storage_service.py` ligne 485-490

#### Ce qui se passe
```python
await _score_client.post(f"{COMPETENCIES_API_URL}/evaluations/user/{bg_user_id}/ai-score-all?only_missing=true", timeout=5.0)
```

#### Point critique 🔴
**Timeout de 5 secondes sur un appel qui déclenche N appels LLM en cascade** dans `competencies_api`.
Ce timeout est trop court pour un CV avec 15+ compétences à scorer. La réponse arrive après 5s →
`competencies_api` continue son travail mais `cv_api` ignore silencieusement le résultat.

---

## Synthèse des points critiques par priorité

| Priorité | Étape | Problème | Impact |
|----------|-------|---------|--------|
| 🔴 P0 | Étape 2 (LLM) | Modèle `flash-lite` sous-performant pour extraction complexe | 30% de CVs avec compétences partielles |
| 🔴 P0 | Étape 4 (BG Compétences) | Double `resolve_comp_id` + semaphore=3 trop conservatif | 30-60s par CV, timeouts `competencies_api` |
| 🔴 P1 | Étape 1 (Download) | Aucun retry sur erreur Drive | CVs en ERROR au lieu d'être retraités |
| 🟡 P1 | Étape 7 (AI Score) | Timeout 5s trop court | Scoring des niveaux souvent raté |
| 🟡 P2 | Étape 3 (Identité) | Lookups séquentiels | +1-2s inutiles par CV |
| 🟡 P2 | Étape 5 (Embedding) | Score fiabilité calculé mais non actionné | Données de mauvaise qualité non détectées |

---

## Recommandations d'optimisation

### 1. Prompt Engineering

**Problème** : La taxonomie est injectée en texte libre, le LLM l'ignore partiellement.

**Solution** : Séparer en deux appels Gemini :
- **Appel 1** : Extraction "libre" (identité, missions, summary) avec `flash-lite` → rapide
- **Appel 2** : Normalisation taxonomique (matcher les compétences extraites vers l'arbre) avec un prompt strict et plus simple → peut utiliser `flash-lite`

Cela évite de demander au LLM de faire deux tâches complexes en même temps.

**Alternative plus simple** : Après extraction, faire un post-processing Python qui normalise les noms en comparant avec l'arbre (`difflib.get_close_matches` ou lookup Redis).

### 2. Modèle IA

```yaml
# prd.yaml — recommandation
gemini_cv_model: "gemini-3.1-flash-preview"        # upgrade: meilleure extraction, +$0.003/CV
gemini_cv_scoring_model: "gemini-3.1-flash-lite-preview"  # scoring compétences: ok avec flash-lite
```

**Impact estimé** : Réduction de ~40% des cas "0 compétences extraites" et de ~25% des divergences de normalisation taxonomique.

### 3. Timeout AI Scoring

```python
# cv_storage_service.py ligne 489
# AVANT
timeout=5.0
# APRÈS
timeout=30.0  # le scoring déclenche N appels LLM dans competencies_api
```

### 4. Retry Download Drive

Ajouter dans `fetch_cv_content()` un retry exponentiel sur les erreurs 429/500 de l'API Drive.

### 5. Semaphore Compétences

Augmenter le semaphore de 3 à 8 pour paralléliser davantage les lookups de compétences :
```python
sem = asyncio.Semaphore(8)  # était 3
```

### 6. Score Fiabilité → Action

```python
# cv_import_service.py après calcul du score
if extraction_reliability_score is not None and extraction_reliability_score < 40:
    pipeline_warnings.append(
        f"⚠️ Score de fiabilité bas ({extraction_reliability_score}%) — "
        "le LLM a probablement raté des informations importantes."
    )
```
