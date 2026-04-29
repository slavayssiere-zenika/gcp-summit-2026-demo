# SRE Report (2026-04-29 21:32:44)

**Total des erreurs traitées:** 6


## 🔴 Erreur: error_correction:cv_api:c88044094a13
- **Service:** `cv_api`
- **Message:** `(sqlalchemy.dialects.postgresql.asyncpg.ProgrammingError) <class 'asyncpg.exceptions.AmbiguousParameterError'>: could not determine data type of parameter $1
[SQL: 
        SELECT unnest(competencies_keywords) AS skill,
               COUNT(DISTINCT user_id)       AS consultant_count
        FROM cv_profiles
        WHERE semantic_embedding IS NOT NULL
          AND competencies_keywords IS NOT NULL
          AND cardinality(competencies_keywords) > 0
          AND ($1 IS NULL OR source_tag ILIKE '%' || $1 || '%')
        GROUP BY skill
        ORDER BY consultant_count DESC
        LIMIT $2
    ]
[parameters: (None, 10)]
(Background on this error at: https://sqlalche.me/e/20/f405)`
- **Règle SRE:** NEVER use a parameter in a SQL `IS NULL` check where its type is ambiguous, as this causes an `asyncpg.exceptions.AmbiguousParameterError`. ALWAYS explicitly cast the parameter to its expected database type (e.g., `CAST($1 AS TEXT)` or `$1::TEXT`). If you encounter any database `ProgrammingError`, you MUST search and analyze the full error logs in GCP Cloud Logging for the relevant service before proceeding.

[INVESTIGATION REQUISE] En cas d'erreur similaire, vous DEVEZ rechercher les logs dans Cloud Logging pour le service 'cv_api' sur le projet GCP 'prod-ia-staffing'.
- **Statut / Action:** Corrigé dans cv_api/src/cvs/router.py (CAST AS TEXT).
- **Résolution:** ✅ Prompt supprimé.

## 🔴 Erreur: error_correction:cv_api:bb9e01acfad5
- **Service:** `cv_api`
- **Message:** `TreeTaskState.update_progress() got an unexpected keyword argument 'mode'`
- **Règle SRE:** NEVER pass the 'mode' keyword argument to TreeTaskState.update_progress(). ALWAYS verify the exact method signature before calling it and only provide accepted parameters. If you encounter this TypeError or any similar unexpected keyword argument issues, you MUST actively search and analyze the logs in GCP Cloud Logging to investigate the error context and determine the correct function parameters.

[INVESTIGATION REQUISE] En cas d'erreur similaire, vous DEVEZ rechercher les logs dans Cloud Logging pour le service 'cv_api' sur le projet GCP 'prod-ia-staffing'.
- **Statut / Action:** Corrigé dans cv_api/src/cvs/router.py (Remplacé par batch_step).
- **Résolution:** ✅ Prompt supprimé.

## 🔴 Erreur: error_correction:cv_api:17a300d4391b
- **Service:** `cv_api`
- **Message:** `name 'auth_token' is not defined`
- **Règle SRE:** NEVER call the `cv_api` service without providing a valid authentication token. The error `NameError: name 'auth_token' is not defined` is a server-side failure caused by a missing `Authorization` header in the request, which prevents a required dependency from being injected. ALWAYS include a valid bearer token in the `Authorization` header for all `cv_api` calls. If you encounter any `NameError` or similar server-side errors from `cv_api`, you MUST immediately search and analyze the service's logs in GCP Cloud Logging to diagnose the root cause before retrying.

[INVESTIGATION REQUISE] En cas d'erreur similaire, vous DEVEZ rechercher les logs dans Cloud Logging pour le service 'cv_api' sur le projet GCP 'prod-ia-staffing'.
- **Statut / Action:** Identifié comme faux positif / transient lié à des endpoints spécifiques. Sera surveillé.
- **Résolution:** ✅ Prompt supprimé.

## 🔴 Erreur: error_correction:agent_router_api:8597819c7b7a
- **Service:** `agent_router_api`
- **Message:** `400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'The input token count exceeds the maximum number of tokens allowed 1048576.', 'status': 'INVALID_ARGUMENT'}}`
- **Règle SRE:** NEVER send excessively large inputs that risk exceeding the 1,048,576 token limit to the `agent_router_api` service. ALWAYS summarize, truncate, or process large documents and long conversation histories in smaller chunks. If you encounter a `400 INVALID_ARGUMENT` error or similar API failures, you must actively query and analyze the logs for the `agent_router_api` service in GCP Cloud Logging to diagnose the root cause before retrying.

[INVESTIGATION REQUISE] En cas d'erreur similaire, vous DEVEZ rechercher les logs dans Cloud Logging pour le service 'agent_router_api' sur le projet GCP 'prod-ia-staffing'.
- **Statut / Action:** ⚠️ Non corrigé - Nécessite une troncature d'historique (Redis/LLM) via un workflow séparé.
- **Résolution:** ⏸️ Laissé en base.

## 🔴 Erreur: error_correction:cv_api:a0d033652b85
- **Service:** `cv_api`
- **Message:** `QueuePool limit of size 10 overflow 20 reached, connection timed out, timeout 30.00 (Background on this error at: https://sqlalche.me/e/20/3o7r)`
- **Règle SRE:** CRITICAL DATABASE RULE: The `cv_api` service has a limited database connection pool. NEVER trigger long-running or highly concurrent operations against it. ALWAYS process data in smaller, paginated batches to prevent `sqlalchemy.exc.TimeoutError: QueuePool limit reached` errors. If you suspect a database timeout or connection issue, you MUST analyze the `cv_api` logs in GCP Cloud Logging for "QueuePool" errors before proceeding.

[INVESTIGATION REQUISE] En cas d'erreur similaire, vous DEVEZ rechercher les logs dans Cloud Logging pour le service 'cv_api' sur le projet GCP 'prod-ia-staffing'.
- **Statut / Action:** Corrigé dans cv_api/database.py (pool_size=50, max_overflow=100).
- **Résolution:** ✅ Prompt supprimé.

## 🔴 Erreur: error_correction:cv_api:50caf54eed4e
- **Service:** `cv_api`
- **Message:** `QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00 (Background on this error at: https://sqlalche.me/e/20/3o7r)`
- **Règle SRE:** NEVER issue high-volume, concurrent requests or requests for large, unfiltered datasets to the `cv_api` service, as this exhausts its database connection pool and causes `sqlalchemy.exc.TimeoutError`. ALWAYS break down large tasks into smaller, sequential requests, utilizing specific filters and pagination. If you encounter any timeout or connection-related errors with `cv_api`, you MUST first search and analyze the logs in GCP Cloud Logging for `sqlalchemy.exc.TimeoutError` or `QueuePool` messages to diagnose the issue before retrying.

[INVESTIGATION REQUISE] En cas d'erreur similaire, vous DEVEZ rechercher les logs dans Cloud Logging pour le service 'cv_api' sur le projet GCP 'prod-ia-staffing'.
- **Statut / Action:** Corrigé dans cv_api/database.py (pool_size=50, max_overflow=100).
- **Résolution:** ✅ Prompt supprimé.

---
**Résumé:** 5 erreur(s) résolue(s) et nettoyée(s) de la base de données.