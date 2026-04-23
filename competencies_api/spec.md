# Competencies API Specification

## Présentation
Le cœur d'Intelligence de Carrière (IC) de l'Agent de Consultation Zenika.
L'API **Competencies** gère une nomenclature arborescente (Structure N-Aires 3 Niveaux : Domaines > Sujets > Technologies) représentant toutes les aptitudes manipulables au sein de l'organisation.

---

## 🏛️ Architecture et Modèles Récursifs
Contrairement aux bases plates traditionnelles, le modèle métier repose sur des concepts d'auto-parentage assurant une structuration en répertoire (Dossiers/Sous-dossiers).

## Description Fonctionnelle Détaillée
Fonctionnellement, l'API Competencies est la cartographie des savoir-faire de Zenika. Elle permet de structurer la capacité de l'entreprise à répondre à des appels d'offres ou à recruter stratégiquement.
Le service permet de construire dynamiquement un arbre de compétences (ex: Cloud > Google Cloud > Kubernetes) sans duplicat via ses règles de gestion strictes (idempotence).
Il offre aux managers la possibilité de :
- Mettre à jour les référentiels technologiques face à un marché mouvant.
- Évaluer factuellement les compétences des collaborateurs (croisement entre `Competencies` et `Users`).
- Interroger (souvent via l'Agent IA) le catalogue d'expertise interne pour construire des équipes projet sur-mesure ou identifier des manques capacitaires à combler par la formation (GPEC - Gestion Prévisionnelle des Emplois et des Compétences).

### 1. La Compétence (Table : `competencies`)
- `id` : Integer (PK)
- `name` : String (Indexé)
- `description` : String
- `parent_id` : Integer (FOREIGN KEY vers `id`)
- `sub_competencies` : Array[] (Chargement paresseux via SQLAlchemy `selectin`). Les enfants directs de cette racine.

### 2. Attribution d'Aptitudes (Table pivot : `user_competencies`)
Un profil ne peut prétendre à posséder "Python" s'il n'est pas lié via cette table.
- `user_id` : Intérieur de `Users API`
- `competency_id` : Intérieur de cette architecture

---

## 🛠️ Endpoints Principaux
> **Security Guard :** Pare-feu centralisé (Propagation du Header API Bearer HTTP) vérifiant l'exigibilité des mutations auprès de `Users API`.

### Graph et Arborescence
L'API ne retourne pas une liste plate écrasant la structure.
- `GET /competencies/` : Retourne UNIQUEMENT les **Racines Fondatrices** de l'Arbre (`parent_id == None`). Les sous-niveaux s'y abritent nativement. Supporte la pagination `?limit=1000`.
- `GET /competencies/{id}` : Extrait une branche précise et ses descendants.
- `POST /competencies/` : **[Idempotent Upsert]** Forge un nœud. Si un parent ou nœud portant exactement le même `name` existe déjà, l'API intercepte la demande et retourne silencieusement l'objet existant. Protège les Index SQL contre les conflits asynchrones RAG. Exige un `parent_id` optionnel pour nidation.

### Accréditations Collaborateurs (Silo User-Binding)
- `POST /competencies/user/{u_id}/assign/{c_id}` : Décerne une qualification confirmée à un user métier (vérifie que `u_id` existe côté Users).
- `DELETE /competencies/user/{u_id}/remove/{c_id}` : Rétracte la validation d'acquis.

---

## 🤖 Modèle Conversationnel LMM (MCP Tiers)
L'Agent peut manipuler la vue "Skills" sans effort grâce aux tools injectables :
- `create_competency` : Avec transmission possible du `parent_id` (Nesting autonome).
- `assign_competency_to_user`
- `delete_competency`
- `list_competencies`

## 🔒 Sécurité Zero-Trust & JWT
L'intégralité des routes (hors santé et documentation OpenAPI) exigent dorénavant un JWT d'authentification vérifié. Le token doit être passé dans l'entête HTTP (`Authorization: Bearer <token>`). Tous les composants internes et externes propagent l'identité du requérant.

## 📡 Schema OpenAPI Auto-Généré

- **GET** `/metrics` : Metrics
- **GET** `/health` : Health
- **GET** `/version` : Get Version
- **GET** `/spec` : Get Spec
- **GET** `/` : List Competencies
- **POST** `/` : Create Competency
- **GET** `/search` : Search Competencies
- **POST** `/suggestions` : Create Competency Suggestion
- **GET** `/suggestions` : List Competency Suggestions
- **PATCH** `/suggestions/{suggestion_id}/review` : Review Competency Suggestion
- **GET** `/{competency_id}` : Get Competency
- **PUT** `/{competency_id}` : Update Competency
- **DELETE** `/{competency_id}` : Delete Competency
- **GET** `/{competency_id}/users` : List Competency Users
- **POST** `/bulk_tree` : Bulk Import Tree
- **POST** `/stats/counts` : Get Competency Stats
- **POST** `/user/{user_id}/assign/{competency_id}` : Assign Competency To User
- **DELETE** `/user/{user_id}/remove/{competency_id}` : Remove Competency From User
- **GET** `/user/{user_id}` : List User Competencies
- **POST** `/internal/users/merge` : Merge Users
- **DELETE** `/user/{user_id}/clear` : Clear User Competencies
- **GET** `/evaluations/user/{user_id}` : List User Evaluations
- **GET** `/evaluations/user/{user_id}/competency/{competency_id}` : Get User Competency Evaluation
- **POST** `/evaluations/user/{user_id}/competency/{competency_id}/user-score` : Set User Competency Score
- **POST** `/evaluations/user/{user_id}/competency/{competency_id}/ai-score` : Trigger Ai Score Single
- **POST** `/evaluations/user/{user_id}/ai-score-all` : Trigger Ai Score All
- **GET** `/analytics/agency-coverage` : Get Agency Competency Coverage
- **GET** `/analytics/skill-gaps` : Get Skill Gaps
- **GET** `/analytics/similar-consultants/{user_id}` : Get Similar Consultants
- **GET** `/mcp/{path}` : Proxy Mcp
- **PUT** `/mcp/{path}` : Proxy Mcp
- **POST** `/mcp/{path}` : Proxy Mcp
- **DELETE** `/mcp/{path}` : Proxy Mcp
