# Prompts API Specification

## Présentation
Le microservice **Prompts API** est la tour de contrôle de l'ingénierie de commandes pour les modèles d'Intelligence Artificielle de la plateforme Zenika.
Il centralise, versionne et distribue les instructions (system prompts) utilisées par les différents agents et services (notamment l'Agent API et le CV API) pour encadrer le comportement de Google Gemini.

## Description Fonctionnelle Détaillée
L'API Prompts répond au besoin vital de gouvernance de l'IA. Plutôt que d'avoir des directives ("prompts") codées en dur ("hardcodées") et fragmentées dans le code source de chaque microservice, cette API offre un référentiel dynamique et centralisé.
D'un point de vue fonctionnel, elle permet aux administrateurs (Prompt Engineers) de :
- Créer, éditer et activer des comportements d'IA à la volée, sans nécessiter le redéploiement complet des microservices applicatifs.
- Ajuster les formats de sortie et les instructions de parsing pour l'ingestion de CV (RAG), garantissant ainsi une flexibilité face aux changements de l'API de Google.
- Assurer une très haute performance de récupération par la distribution vers un cache Redis, évitant de surcharger la base de données relationnelle à chaque inférence de l'Agent.

---

## 🏛️ Architecture et Modèles
- Base de données PostgreSQL dédiée pour la persistance à long terme des prompts (versions, descriptions, variables attendues).
- Interface de mise en cache Redis pour une livraison ultra-rapide aux applicatifs consommateurs (O(1) access time).
- Outils d'évaluation intégrés (Promptfoo pour générer automatiquement de la donnée synthétique de test).

## 🛠️ Endpoints Principaux
> **Sécurité :** L'accès à la modification des prompts nécessite une authentification forte par JWT, propagée par la passerelle de sécurité.

- `GET /prompts/` : Liste l'ensemble des prompts hébergés (avec leur statut d'activation).
- `GET /prompts/{name}` : Récupère la définition complète d'un prompt ciblé afin qu'un microservice (ex: `cv_api`) puisse le fournir au LLM.
- `POST /prompts/` : Crée une nouvelle instruction d'IA pour un nouveau use-case.
- `PUT /prompts/{name}` : Modifie contextuellement et dynamiquement le contenu d'un prompt, forçant ainsi l'invalidation du cache Redis (synchronisation).
- `GET /spec` : Retourne le présent manifeste.

## 🔒 Sécurité Zero-Trust & JWT
L'intégralité des routes (hors santé et documentation OpenAPI) exigent dorénavant un JWT d'authentification vérifié. Le token doit être passé dans l'entête HTTP (`Authorization: Bearer <token>`). Tous les composants internes et externes propagent l'identité du requérant.

## 📡 Schema OpenAPI Auto-Généré

- **GET** `/metrics` : Metrics
- **GET** `/health` : Health Check
- **GET** `/version` : Get Version
- **GET** `/mcp/{path}` : Proxy Mcp
- **POST** `/mcp/{path}` : Proxy Mcp
- **DELETE** `/mcp/{path}` : Proxy Mcp
- **PUT** `/mcp/{path}` : Proxy Mcp
- **GET** `/spec` : Get Spec
- **GET** `/user/me` : Get My Prompt
- **PUT** `/user/me` : Update My Prompt
- **GET** `/` : List Prompts
- **POST** `/` : Create Prompt
- **GET** `/{key}` : Read Prompt
- **PUT** `/{key}` : Update Prompt
- **POST** `/{key}/analyze` : Analyze Prompt
- **POST** `/errors/report` : Report Error For Prompt
