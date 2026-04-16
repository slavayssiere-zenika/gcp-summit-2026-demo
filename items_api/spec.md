# Items API Specification

## Présentation
Le microservice **Items API** est l'interface de gestion granulaire du dictionnaire de données rattaché aux utilisateurs de la Console Agent Zenika.
Il permet de référencer des objets métier (ordinateurs, cours, serveurs, documents) et de les trier efficacement grâce à un système multiclausal de classifications imbriquées de type N:M (Many-to-Many).

---

## 🏛️ Architecture et Modèles

## Description Fonctionnelle Détaillée
L'API Items couvre le besoin organisationnel de suivi des actifs (Asset Management). Dans une entreprise moderne, les collaborateurs interagissent avec une multitude de ressources transverses : matériel IT (laptops, téléphones), accès logiciels, licences, ou encore supports de formation.
Ce service permet la catégorisation fine de tout objet physique ou virtuel, et orchestre son assignation à des collaborateurs.
Par ses capacités de croisement de catégories et son intégration avec le MCP (Agent), il permet de répondre instantanément à des problématiques logistiques et RH complexes, comme: "Lister tout le matériel Apple détenu par les développeurs basés à Paris" ou "Retrouver l'historique des attributions de serveurs de test".

### 1. Table : Items
Les objets manipulables.
- `id` : Integer (PK)
- `name` : String (Indexé)
- `description` : String
- `owner_id` : Integer (Clé associée dynamiquement à `Users API`)
- `categories` : Relation Many-To-Many vers la table Catégorie.

### 2. Table : Categories
Les méta-tags permettant l'indexation.
- `id` : Integer (PK)
- `name` : String (Indexé)
- `description` : String
- `items` : Relation Many-to-Many chargée de manière 'selectin' paresseuse.

### 3. Relation Table : `item_category`
Le pivot Many-to-Many connectant les items à autant de catégories qu'ils le nécessitent.

---

## 🛠️ Endpoints Principaux
> **Security Guard :** L'API attend le `Authorization: Bearer <token>` depuis le Header et propage ce dernier vers `users_api` pour authentifier les `owner_id`. L'endpoint valide également si le token du requesteur contient les autorisations nécessaires (filtrage RBAC Category ID).

### Gestion de l'Inventaire (Items)
- `GET /items/` : Récupère la liste de tous les objets globaux (Paginable).
- `GET /items/{id}` : Récupère le détail (propriétaire, stats) d'un objet. En injectant le Header, le backend enrichit les informations propriétaires (nom, prénom) via call HTTP invisible vers Users API.
- `POST /items/` : Crée un item (nécessite l'existence d'au moins une des `category_ids` soumise).
- `PUT /items/{id}` : Modification d'entité.
- `DELETE /items/{id}` : Destructeur de la base.

### Indexation (Categories)
- `GET /items/categories` : Renvoie toute la nomenclature.
- `POST /items/categories` : Crée de nouvelles branches de classement.

---

## 🌟 Orchestration Agent (MCP)
Le service jumeau `mcp_server.py` permet à l'Agent Gemini de lire ce métier via l'interface suivante :
- `search_items` : Filtre et retrouve du matériel à grande échelle.
- `items_by_category` : Aggrégeur logique de tris de catégories.
- Et les outils de manipulations CRUD de base (`delete`, `create`, `list_categories`).

## 🔒 Sécurité Zero-Trust & JWT
L'intégralité des routes (hors santé et documentation OpenAPI) exigent dorénavant un JWT d'authentification vérifié. Le token doit être passé dans l'entête HTTP (`Authorization: Bearer <token>`). Tous les composants internes et externes propagent l'identité du requérant.

## 📡 Schema OpenAPI Auto-Généré

- **GET** `/metrics` : Metrics
- **GET** `/health` : Health
- **GET** `/version` : Get Version
- **POST** `/pubsub/user-events` : Handle User Pubsub Events
- **GET** `/spec` : Get Spec
- **GET** `/categories` : List Categories
- **POST** `/categories` : Create Category
- **GET** `/stats` : Get Item Stats
- **GET** `/` : List Items
- **POST** `/` : Create Item
- **GET** `/{item_id}` : Get Item
- **PUT** `/{item_id}` : Update Item
- **DELETE** `/{item_id}` : Delete Item
- **GET** `/search/query` : Search Items
- **GET** `/user/{user_id}` : List User Items
- **POST** `/internal/users/merge` : Merge Users
- **DELETE** `/mcp/{path}` : Proxy Mcp
- **GET** `/mcp/{path}` : Proxy Mcp
- **POST** `/mcp/{path}` : Proxy Mcp
- **PUT** `/mcp/{path}` : Proxy Mcp
