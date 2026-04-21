# Users API Specification

## Présentation
Le microservice **Users API** est le pilier d'authentification et d'habilitation de la plateforme Zenika. 
Conçu sous **FastAPI** avec un support **PostgreSQL/Redis**, il gère l'identité, le contrôle d'accès (RBAC) et l'émission des jetons JWT sécurisant tous les appels inter-services.

---

## 🏛️ Architecture et Entités
### 1. Utilisateurs (User)
Les profils de la console Agent Zenika.
- `id` : Integer (Clé Primaire)
- `email` : String (Unique)
- `full_name` : String
- `hashed_password` : String (Bcrypt protégé)
- `allowed_category_ids` : List[Int] (Contrôle d'accès inter-services)
- `is_active` : Boolean (Permet la désactivation)

### 2. Cache & Performance
Toutes les lectures (Get User, Get All) s'appuient sur un middleware **Redis** avec une persistance par TTL (Tee-to-Live) court, invalidé lors des modifications (PUT, POST) par une logique de pattern regex.

---

## 🔐 Endpoints Principaux
> **Note de Sécurité :** À l'exception de `/login` et `/docs`, l'ensemble des requêtes nécessitent la transmission du header `Authorization: Bearer <token_jwt>`.

### Authentification
- `POST /users/login` : Vérifie les *credentials* (OAuth2PasswordBearer Form ou JSON Body) et génère le token d'identité.
- `GET /users/me` : Décrypte le Token fourni et renvoie le profil actif si valide.

### Opérations CRUD
- `GET /users/` : Pagination des profils.
- `GET /users/{id}` : Récupération fine d'un collègue/profil spécifique.
- `POST /users/` : Enregistrement d'un nouvel utilisateur (avec encodage Bcrypt du mot de passe transparent).
- `PUT /users/{id}` : Édition dynamique d'un profil métier existant.
- `DELETE /users/{id}` : Clôture/Effacement strict d'un profil de l'organisation.

---

## 🤖 Orchestration MCP
Ce microservice fait tourner un serveur secondaire (`mcp_server.py`) qui permet à Gemini (L'Agent Zenika) de piloter ces données :
- `search_users` : Moteur de recherche NLP.
- `toggle_user_status` : Désactivation/Réactivation de comptes en un clic.
- `get_user_stats` : Analyse de population d'accès.

## Description Fonctionnelle Détaillée
L'API Users est le registre central des collaborateurs de Zenika. D'un point de vue fonctionnel, ce service est responsable du cycle de vie des identités de l'entreprise :
- **Onboarding / Offboarding** : Création des collaborateurs, définition de leurs mots de passe, et désactivation de comptes de manière sécurisée et tracée.
- **Sécurité & Accréditation** : Fourniture du rempart d'authentification (JWT) garantissant que seuls les employés légitimes peuvent interroger l'Agent IA, modifier le référentiel de compétences ou lire l'inventaire matériel. Il porte la logique de RBAC (Role-Based Access Control) via les catégories de droits.
- **Transversalité** : Les autres microservices dépendent continuellement de l'API Users pour enrichir leurs propres données (par exemple, afficher le nom et prénom d’un propriétaire de matériel dans l'`items_api` au lieu d'un simple identifiant numérique).


## 🔒 Sécurité Zero-Trust & JWT
L'intégralité des routes (hors santé et documentation OpenAPI) exigent dorénavant un JWT d'authentification vérifié. Le token doit être passé dans l'entête HTTP (`Authorization: Bearer <token>`). Tous les composants internes et externes propagent l'identité du requérant.

## 📡 Schema OpenAPI Auto-Généré

- **GET** `/metrics` : Metrics
- **GET** `/health` : Router Health
- **GET** `/version` : Get Version
- **POST** `/login` : Login
- **POST** `/refresh` : Refresh Token Route
- **POST** `/logout` : Logout
- **POST** `/service-account/login` : Service Account Login
- **GET** `/google/config` : Get Google Config
- **GET** `/google/login` : Google Login
- **GET** `/google/callback` : Google Callback
- **POST** `/internal/service-token` : Create Service Token
- **POST** `/suspend/{email}` : Suspend User
- **GET** `/spec` : Get Spec
- **GET** `/stats` : Get User Stats
- **GET** `/` : List Users
- **POST** `/` : Create User
- **GET** `/search` : Search Users
- **POST** `/bulk` : Get Users Bulk
- **GET** `/me` : Get Me
- **GET** `/duplicates` : Get Duplicates
- **POST** `/merge` : Merge Users
- **GET** `/{user_id}` : Get User
- **PUT** `/{user_id}` : Update User
- **DELETE** `/{user_id}` : Delete User
- **PUT** `/mcp/{path}` : Proxy Mcp
- **POST** `/mcp/{path}` : Proxy Mcp
- **GET** `/mcp/{path}` : Proxy Mcp
- **DELETE** `/mcp/{path}` : Proxy Mcp
