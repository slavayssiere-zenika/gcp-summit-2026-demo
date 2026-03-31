# Competencies API Specification

## Présentation
Le cœur d'Intelligence de Carrière (IC) de l'Agent de Consultation Zenika.
L'API **Competencies** gère une nomenclature arborescente (Structure N-Aires 3 Niveaux : Domaines > Sujets > Technologies) représentant toutes les aptitudes manipulables au sein de l'organisation.

---

## 🏛️ Architecture et Modèles Récursifs
Contrairement aux bases plates traditionnelles, le modèle métier repose sur des concepts d'auto-parentage assurant une structuration en répertoire (Dossiers/Sous-dossiers).

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
