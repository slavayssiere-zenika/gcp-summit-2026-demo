---
description: Analyse complète de la résilience, sécurité et fiabilité (SRE) de l'architecture, avec priorisation des axes d'amélioration.
---

# Workflow : Analyse Résilience, Sécurité et Fiabilité (/analyse-resilience-security-fiability)

// turbo-all

Ce workflow définit une marche à suivre stricte pour auditer l'ensemble du projet sous les prismes de la résilience (capacité à survivre aux pannes), de la sécurité (Zero-Trust, permissions) et de la fiabilité (stabilité, monitoring). À l'issue de cet audit, l'agent proposera un rapport listant les axes d'amélioration triés par priorité (P0, P1, P2...).

## Étape 0 : Découverte et Cartographie
Avant tout audit, lire les fichiers de configuration globaux et les `README.md` principaux pour comprendre la topologie actuelle. L'agent doit identifier les services critiques et les points d'intégration réseau.

## 1. Audit de la Résilience (Resilience)
Évaluer la capacité des microservices à gérer les pannes en cascade et les instabilités réseau :
- **Stratégies de Retry et Circuit Breaker** : Vérifier que les appels inter-services (via `httpx` ou MCP) utilisent des mécanismes de retry robustes (ex: `tenacity`) et des timeouts explicites.
- **Failfast et Zéro Erreur Silencieuse** : S'assurer qu'aucune exception n'est avalée silencieusement (`except Exception: pass`). Toute erreur doit être logguée, monitorée, et gérée via un fallback ou remontée explicitement.
- **Auto-Correction et Fallback** : Identifier les points de défaillance uniques. Vérifier si un fallback direct en base de données (SQLAlchemy) est implémenté en cas d'indisponibilité d'une API, conformément aux standards de la plateforme.
- **Idempotence des Opérations** : Vérifier que les endpoints de mutation (POST, PUT) ou les tâches asynchrones sont protégés contre les doublons et les requêtes répétées.

## 2. Audit de la Sécurité (Security)
Évaluer la protection des données et le contrôle d'accès :
- **Zero-Trust et Authentification** : Vérifier la présence systématique de `Depends(verify_jwt)` sur tous les routeurs (FastAPI) et la stricte validation des claims (ex: `sub`).
- **Contrôle d'Accès par Rôle (RBAC)** : Valider que les actions sensibles et destructives imposent des rôles spécifiques (`admin`, `service_account`) au niveau du backend, et que les clients MCP propagent correctement le JWT (`auth_header_var`).
- **Protection des Secrets (Leak Mitigation)** : S'assurer de l'utilisation de `os.environ.pop()` pour les secrets critiques après l'initialisation de l'application, afin d'éviter l'exposition via des attaques de Prompt Injection ou d'introspection.
- **Protection de l'Infrastructure** : Vérifier les configurations Terraform (Cloud Armor, Egress VPC / Zero-Trust networking) et s'assurer que les images Docker s'exécutent en mode non-root (`USER appuser`).

## 3. Audit de la Fiabilité (Fiability / Reliability)
Évaluer la stabilité du code, les performances et l'observabilité de la plateforme :
- **Pagination Stricte et Limites** : Aucun endpoint listant des entités ou interrogeant des APIs externes (Drive, BigQuery) ne doit utiliser de hard limit silencieuse. La pagination (`skip`/`limit` + `total` ou page tokens) est obligatoire.
- **Contrats d'Interface et Pydantic** : S'assurer que toutes les réponses inter-services sont validées formellement via `Model.model_validate()` avec gestion des `ValidationError`. L'utilisation de parsing JSON tolérant (`.get()`) est formellement interdite pour les contrats.
- **Observabilité et FinOps** : Confirmer l'intégration de `Instrumentator` (FastAPI), des traces Sentry/Cloud Trace, et du suivi strict FinOps (`log_ai_consumption`) sur tous les appels LLM.
- **Qualité de Code et Tests** : Examiner la couverture des tests (unitaire, intégration, schémas de contrat), l'absence de fuites asynchrones dans les tests, et le strict respect des conventions PEP 8 (notamment la limite de 120 caractères).

## 4. Génération du Rapport et Priorisation
Générer un artefact Markdown (ex: `audit_sre_report.md`) contenant le bilan exhaustif de l'analyse, structuré comme suit :
- **Synthèse de la posture globale** : Résumé exécutif sur l'état de l'architecture.
- **Axes d'améliorations classés par criticité** :
  - **[P0] Critique** : Failles de sécurité ouvertes (ex: endpoint non protégé), contrats API rompus (erreurs silencieuses bloquantes), absence de validation Pydantic, crashs réseau non gérés.
  - **[P1] Majeur** : Absence de pagination, requêtes non-idempotentes, manque de retry sur les services tiers, absence de test sur des composants vitaux, hard limits.
  - **[P2] Mineur** : Dette technique, optimisation PEP8, amélioration des logs et traces, consolidation de la CI/CD.
  - **[P3] Recommandation** : Évolutions architecturales à long terme (ex: migration d'outils, refactoring).
