# Pipeline d'Ingestion des CVs — Architecture End-to-End

Ce document décrit en détail le cycle de vie complet d'un CV au sein de l'écosystème **Zenika Console Agent**, depuis sa découverte sur Google Drive jusqu'à son analyse sémantique et l'évaluation de ses compétences par l'IA.

---

## 1. Découverte et Synchronisation Drive (`drive_api`)

Le point d'entrée du pipeline est le microservice `drive_api`, responsable de l'écoute et du suivi des documents sur les espaces de stockage (Google Drive).

- **Scan & Webhooks** : `drive_api` synchronise les dossiers configurés (par tag/agence). Lorsqu'un nouveau fichier (Doc, Docx, PDF) est détecté ou modifié, il est inscrit dans la base de données relationnelle locale (`drive_sync_state`).
- **Statut Initial** : Le fichier est inséré avec le statut `PENDING`.
- **Zombies Sweeper** : Avant chaque batch, un processus de nettoyage remet en `PENDING` les fichiers coincés en `PROCESSING` ou `QUEUED` depuis plus de 15 minutes (suite à un crash d'instance ou une perte de message Pub/Sub).

## 2. Ordonnancement et File d'Attente Pub/Sub (`drive_api` → Pub/Sub)

Afin d'absorber la charge des imports massifs et de permettre la concurrence, le système utilise **Google Cloud Pub/Sub**.

- **Ingestion Batch** : Périodiquement, `IngestionService.ingest_batch()` récupère un lot de fichiers `PENDING` (limité par `MAX_DRIVE_CV_IMPORT`).
- **Publication** : Pour chaque fichier, le service :
  1. Construit un payload contenant le `google_file_id`, l'URL du fichier, le tag de l'agence, et un jeton `oidc_token` d'authentification inter-services.
  2. Pousse le message sur le topic `PUBSUB_CV_IMPORT_TOPIC`.
  3. Met à jour le statut du fichier en `QUEUED` dans sa propre base.

## 3. Réception Asynchrone PUSH (`cv_api`)

Le microservice `cv_api` est configuré en mode **Push Subscriber**. L'infrastructure (via le load balancer) achemine les messages Pub/Sub vers la route dédiée `/pubsub/import-cv`.

- **Sécurité Zéro-Trust** : L'endpoint vérifie d'abord la validité du token OIDC (signature RS256 de Google) pour s'assurer que la requête provient bien de Pub/Sub (`sa-pubsub-invoker`).
- **Échange de Token (Auth A2A)** : Le token OIDC a une validité très courte et est spécifique à Google. `cv_api` échange ce token via `users_api` (`/service-account/login` puis `/internal/service-token`) pour obtenir un JWT applicatif de longue durée (90 minutes) capable de traverser tous les microservices internes.
- **Acquittement Rapide (ACK)** : Pour maximiser la concurrence dynamique (Slow-Start Algorithm de Pub/Sub), `cv_api` notifie immédiatement `drive_api` pour passer le fichier en statut `PROCESSING`, déclenche une `BackgroundTask` (traitement en mémoire asynchrone), et répond `202 Accepted` à Pub/Sub. Le message est ainsi retiré de la file d'attente.

## 4. Analyse et Extraction IA (`cv_api`)

C'est le cœur du réacteur (`process_cv_core` dans `cv_import_service.py`), où l'IA entre en jeu.

### A. Téléchargement du document
Le contenu brut du document Google Drive (HTML ou texte) est téléchargé en utilisant les credentials d'accès.

### B. Extraction Structurée (LLM Gemini Vertex AI)
Le texte brut est envoyé au modèle Gemini avec un prompt strict imposant une sortie en JSON (Structured Output). Le LLM extrait :
- Les informations personnelles (Prénom, Nom, Email).
- Un résumé de profil.
- L'historique des missions (Client, Contexte, Durée, Environnement technique).
- Les compétences clés.

> **Gestion d'erreur** : Si le LLM échoue à parser ou déclare que le fichier n'est pas un CV, le statut est mis à jour en `IGNORED_NOT_CV` ou `ERROR`, qui remontent au frontend.

### C. Résolution d'Identité (`users_api`)
- Le système cherche si l'email extrait correspond à un utilisateur existant.
- S'il n'existe pas, un nouvel utilisateur est créé via `users_api`. En cas de conflit d'email anonymisé, une logique de désambiguïsation est appliquée.

### D. Stockage Profil, Missions et Compétences (RAG)
- Le modèle de données relationnel `CVProfile` est upserté.
- Les compétences et les missions sont parsées et assignées au profil de l'utilisateur.

## 5. Vectorisation Sémantique (`cv_api` / pgvector)

Afin d'alimenter les fonctionnalités RAG (Recherche Sémantique des consultants), le CV subit une vectorisation.

- **Distillation** : Les missions, le résumé et les compétences sont concaténés dans une "super-string" optimisée.
- **Embedding** : Ce texte est converti en vecteur mathématique via le modèle d'embedding Gemini (`task_type="RETRIEVAL_DOCUMENT"`).
- **Indexation** : Le vecteur est stocké dans la base PostgreSQL AlloyDB via l'extension `pgvector`, rendant le profil instantanément éligible à la recherche de profils via `agent_hr_api`.

## 6. Scoring et Alignement Taxonomique (`competencies_api` / Batch IA)

Le profil brut possède désormais des compétences sous forme de texte ("Java", "Kubernetes", "VueJS"). Ces mots-clés doivent être alignés avec le standard de l'entreprise (Taxonomie).

- **Taxonomy Batch Service** : Un job d'arrière-plan asynchrone (ou une phase de batching Vertex) interroge le LLM pour assigner les mots-clés trouvés dans le CV aux "Piliers" ou nœuds de l'arbre taxonomique officiel.
- **Scoring des Niveaux** : Selon les missions et les années d'expérience détectées pour une compétence, l'IA attribue automatiquement un score (1, 2, 3) qui valide le niveau d'expertise du consultant. Ce score met à jour `competencies_api`.

## 7. Finalisation

Une fois le pipeline achevé avec succès :
- `cv_api` exécute un appel HTTP PATCH vers `drive_api`.
- Le statut du document passe de `PROCESSING` à `IMPORTED_CV`.
- Des statistiques FinOps (tokens IA consommés) et de durée (`processing_duration_ms`) sont collectées et poussées vers BigQuery via `analytics_mcp`.

---

### 🚨 Architecture de Résilience (Fail-Fast & Timeout)
- **Timeouts BDD** : Si le pool SQLAlchemy sature lors des pics d'ingestion (ex: timeout de connexion), le process `BackgroundTasks` échoue et est capté.
- **Zombies** : Comme mentionné, si une instance est arrêtée pendant l'étape 4, le fichier reste en `PROCESSING`. Au bout de 15 min, `drive_api` s'en aperçoit, le reset en `PENDING` et le remet dans la boucle Pub/Sub (At-Least-Once Delivery).
- **Dead Letter Queue (DLQ)** : Si `cv_api` retourne une erreur `HTTP 5xx` à Pub/Sub de manière répétée (avant l'acquittement `202`), le message est relancé avec un délai exponentiel jusqu'à 5 fois, puis isolé dans une DLQ pour analyse SRE sans bloquer la file d'attente principale.
