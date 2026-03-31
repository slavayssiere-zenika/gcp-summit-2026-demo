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
