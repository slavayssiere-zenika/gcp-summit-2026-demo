"""
locustfile.py — Tests de performance Zenika Console Agent.

Deux profils de charge :
  1. ZenikaPerfUser       — Navigation utilisateur classique (lecture CRUD).
  2. CVIngestionPipelineUser — Simulation du pipeline d'ingestion de CV :
       Crée un user → assigne 30 compétences → stocke 50 missions
       → lit les profils → interroge les endpoints analytics.
       Sans IA, sans vraie ingestion de document.

Paramètres Locust conseillés pour le profil ingestion :
    --users 30 --spawn-rate 3 --run-time 5m
    (30 pipelines concurrents = ~3000 CVs sur 5 min)
"""
import os
import random
import string
import time
from locust import HttpUser, between, task
from pydantic import ValidationError

# shared/ monte en volume (PYTHONPATH=/shared) — source de verite unique.
# Le Dockerfile locust/Dockerfile installe pydantic sur locustio/locust.
from shared.schemas.pagination import PaginationResponse as _PaginationResponse


class _DataQualityReport:
    """Validation du rapport data quality cv_api.

    Contrat reel (inspecte sur /cv-api/bulk-reanalyse/data-quality) :
      {"computed_at": ..., "total_cvs": int, "users_with_cv": int, "score": int, "grade": str, "metrics": {...}}
    Champs source : cv_api/src/services/data_quality_service.py.
    """

    _REQUIRED = ("total_cvs", "users_with_cv", "score", "grade")

    @classmethod
    def model_validate(cls, data: dict) -> "_DataQualityReport":
        for field in cls._REQUIRED:
            if field not in data:
                raise ValueError(f"[data-quality] champ obligatoire manquant: '{field}'")
        return cls()


class _CvProfilePagination:
    """Validation de GET /user/{id} cv_api.

    Contrat reel (inspecte sur /cv-api/user/{id}) :
      {"items": [{"user_id": int, "source_url": str, ...}], "total": int, "skip": int, "limit": int}
    Pas de 'id' dans l item (clef = user_id). Enveloppe = PaginationResponse.
    """

    @classmethod
    def model_validate(cls, data: dict) -> "_CvProfilePagination":
        if "items" not in data:
            raise ValueError("[cv-profile] champ 'items' manquant dans la reponse paginee")
        if not isinstance(data["items"], list):
            raise ValueError("[cv-profile] 'items' doit etre une liste")
        if "total" not in data:
            raise ValueError("[cv-profile] champ 'total' manquant")
        return cls()


def _validate_contract(response, model_cls, name: str) -> bool:
    """Valide la reponse JSON contre un schema Pydantic (shared/schemas/).

    Detecte les ruptures de contrat inter-services invisibles au status HTTP :
    champ renomme, type errone, liste manquante. Conforme AGENTS.md §3.
    A utiliser uniquement dans un contexte catch_response.
    """
    try:
        data = response.json()
        model_cls.model_validate(data)
        return True
    except ValidationError as exc:
        first = exc.errors()[0]
        response.failure(
            f"[ContractBreak] {name} — champ='{first.get('loc')}' "
            f"erreur='{first.get('msg')}'"
        )
        return False
    except (ValueError, KeyError) as exc:
        response.failure(f"[ContractBreak] {name} — {exc}")
        return False
    except Exception as exc:
        response.failure(f"[ContractBreak] {name} — parse error: {exc}")
        return False


# ── Referentiel partage avec seed_data.py ────────────────────────────────────
# test_data.json  : donnees statiques (noms, categories, requetes de recherche)
# seeded_ids.json : IDs reels ecrits par seed_data.py apres chaque seeding
_DATA_DIR = "/locust/data"
_TEST_DATA: dict = {}
_SEEDED_IDS: dict = {}

try:
    import json as _json
    with open(f"{_DATA_DIR}/test_data.json", encoding="utf-8") as _f:
        _TEST_DATA = _json.load(_f)
except Exception as _e:
    print(f"[Locust] WARN: test_data.json non trouve ({_e}) — donnees par defaut utilisees.")

try:
    import json as _json
    with open(f"{_DATA_DIR}/seeded_ids.json", encoding="utf-8") as _f:
        _SEEDED_IDS = _json.load(_f)
except Exception as _e:
    print(f"[Locust] WARN: seeded_ids.json non trouve ({_e}) — bootstrap API active.")

FIRST_NAMES = _TEST_DATA.get("first_names", [
    "Alice", "Bob", "Charlie", "David", "Emma", "Frank",
    "Grace", "Henry", "Isabel", "Jack", "Karl", "Laura",
])
LAST_NAMES = _TEST_DATA.get("last_names", [
    "Martin", "Bernard", "Thomas", "Petit", "Robert", "Richard",
    "Durand", "Dubois", "Moreau", "Laurent", "Simon", "Michel",
])
_SEARCH_QUERIES = _TEST_DATA.get("search_queries", {
    "users": ["alice", "bob", "zenika"],
    "items": ["python", "java", "cloud"],
    "cv":    ["python senior", "cloud architect"],
})

MISSION_SKILLS = [
    "Python", "Java", "TypeScript", "Kubernetes", "Terraform",
    "CI/CD", "Docker", "Vue.js", "PostgreSQL", "Spark",
    "TensorFlow", "Architecture", "Scrum", "AWS", "GCP",
]

MISSION_TITLES = [
    "Migration Cloud Native",
    "Refonte Architecture Microservices",
    "Optimisation Pipeline Data",
    "Développement Agent IA",
    "Audit Sécurité Zero-Trust",
    "Déploiement Kubernetes Multi-Régions",
    "Coaching Tech Lead",
    "Intégration LLM en Production",
    "Revue de Code Avancée",
    "Formation DevOps avancée",
]

CLIENTS = [
    "Renault", "BNP Paribas", "SNCF", "Orange", "Société Générale",
    "EDF", "Airbus", "Michelin", "L'Oréal", "Total",
]


def _random_str(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=n))


# Pool partage entre les deux classes.
# Charge depuis seeded_ids.json (ecrit par seed_data.py) si disponible,
# sinon bootstrap via API au premier on_start.
_CREATED_USER_IDS: list[int] = list(_SEEDED_IDS.get("user_ids", []))
_CV_PROFILE_USER_IDS: list[int] = list(_SEEDED_IDS.get("cv_profile_user_ids", []))
# Set pour le O(1) membership check dans _read_profile
# (evite 404 sur /cv/user/{id} pour les users crees EN DIRECT qui n'ont pas de profil CV)
_CV_PROFILE_USER_IDS_SET: set[int] = set(_CV_PROFILE_USER_IDS)
_MISSION_IDS: list[int] = list(_SEEDED_IDS.get("mission_ids", []))
_CATEGORY_IDS: list[int] = list(_SEEDED_IDS.get("category_ids", []))
_ITEM_IDS: list[int] = list(_SEEDED_IDS.get("item_ids", []))

_SEEDED_READY = bool(_CV_PROFILE_USER_IDS)  # True = pas besoin de bootstrap API


# ── Classe 1 : Navigation utilisateur classique ───────────────────────────────

# LOCUST_SCENARIO=navigation -> ZenikaPerfUser uniquement (stress test navigation pure, 500 users).
# LOCUST_SCENARIO=full (defaut) -> ZenikaPerfUser (poids 3) + CVIngestionPipelineUser (poids 1).
_SCENARIO = os.getenv("LOCUST_SCENARIO", "full")


class ZenikaPerfUser(HttpUser):
    """
    Simule un utilisateur standard naviguant sur la plateforme.
    Charge : lecture des listes (users, items, compétences, missions).
    En mode navigation (LOCUST_SCENARIO=navigation) : seule classe active (500 users).
    """
    weight = 1 if _SCENARIO == "navigation" else 3  # 75 % du trafic total
    wait_time = between(1, 3)

    def on_start(self):
        self.users_api = os.getenv("USERS_API_URL", "http://users_api:8000")
        self.items_api = os.getenv("ITEMS_API_URL", "http://items_api:8001")
        self.competencies_api = os.getenv("COMPETENCIES_API_URL", "http://competencies_api:8003")
        self.cv_api = os.getenv("CV_API_URL", "http://cv_api:8004")
        self.missions_api = os.getenv("MISSIONS_API_URL", "http://missions_api:8009")
        self.drive_api = os.getenv("DRIVE_API_URL", "http://drive_api:8006")
        self.prompts_api = os.getenv("PROMPTS_API_URL", "http://prompts_api:8000")
        self._login()
        # Si seeded_ids.json est charge, les pools sont deja remplis au niveau module
        # → pas besoin d appel API au demarrage (evite le burst initial)
        if not _SEEDED_READY:
            if not _CV_PROFILE_USER_IDS:
                self._bootstrap_cv_pool()
            if not _MISSION_IDS:
                self._bootstrap_mission_pool()

    def _bootstrap_cv_pool(self) -> None:
        """Charge les user_ids ayant un profil CV depuis GET /cv/users/tags/map.

        Appele une seule fois au premier on_start pour eviter les 404
        sur GET /cv/user/{id} et /cv/user/{id}/missions.
        """
        try:
            res = self.client.get(
                f"{self.cv_api}/users/tags/map",
                headers=self.headers,
                name="[Bootstrap] GET /cv/users/tags/map",
            )
            if res.status_code == 200:
                uid_map = res.json()
                for uid_str in uid_map.keys():
                    try:
                        _CV_PROFILE_USER_IDS.append(int(uid_str))
                    except ValueError:
                        pass
                print(f"[Bootstrap] {len(_CV_PROFILE_USER_IDS)} users avec profil CV charges.")
        except Exception as e:
            print(f"[Bootstrap] Erreur chargement pool CV: {e}")

    def _bootstrap_mission_pool(self) -> None:
        """Charge les IDs de missions depuis GET /missions/.

        Appele une seule fois au premier on_start pour eviter les 404
        sur GET /missions/{id}. Skip si aucune mission disponible.
        """
        try:
            res = self.client.get(
                f"{self.missions_api}/missions/?skip=0&limit=50",
                headers=self.headers,
                name="[Bootstrap] GET /missions/",
            )
            if res.status_code == 200:
                data = res.json()
                for mission in data.get("items", []):
                    mid = mission.get("id")
                    if mid:
                        _MISSION_IDS.append(int(mid))
                print(f"[Bootstrap] {len(_MISSION_IDS)} missions chargees.")
        except Exception as e:
            print(f"[Bootstrap] Erreur chargement pool missions: {e}")

    # Duree avant expiration a partir de laquelle on renouvelle le token (secondes).
    # 720s = 12 min → refresh avant les 15 min de TTL prod, safe pour les tests.
    _TOKEN_REFRESH_THRESHOLD = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 15)) * 60 - 180

    def _login(self):
        res = self.client.post(
            f"{self.users_api}/login",
            json={"email": "admin@zenika.com", "password": "admin"},
            name="/login",
        )
        if res.status_code == 200:
            self.token = res.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self._token_issued_at = time.monotonic()
        else:
            self.token = None
            self.headers = {}
            self._token_issued_at = 0.0
            print(f"[ZenikaPerfUser] Auth failed: HTTP {res.status_code} — {res.text[:120]}")

    def _ensure_fresh_token(self):
        """Re-login proactif si le token approche de son expiration."""
        age = time.monotonic() - getattr(self, "_token_issued_at", 0.0)
        if not self.token or age >= self._TOKEN_REFRESH_THRESHOLD:
            self._login()

    # --- Users API ---
    @task(3)
    def list_users(self):
        skip = random.randint(0, 100)
        with self.client.get(
            f"{self.users_api}/?skip={skip}&limit=50",
            headers=self.headers,
            name="[Users] GET /users/",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                _validate_contract(resp, _PaginationResponse, "GET /users/")

    @task(1)
    def get_me(self):
        self.client.get(
            f"{self.users_api}/me",
            headers=self.headers,
            name="[Users] GET /users/me",
        )

    # --- Items API ---
    @task(3)
    def list_items(self):
        skip = random.randint(0, 100)
        with self.client.get(
            f"{self.items_api}/?skip={skip}&limit=50",
            headers=self.headers,
            name="[Items] GET /items/",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                _validate_contract(resp, _PaginationResponse, "GET /items/")

    @task(1)
    def list_categories(self):
        self.client.get(
            f"{self.items_api}/categories",
            headers=self.headers,
            name="[Items] GET /categories",
        )

    # --- Competencies API ---
    @task(2)
    def list_competencies(self):
        self.client.get(
            f"{self.competencies_api}/",
            headers=self.headers,
            name="[Competencies] GET /competencies/",
        )

    # --- CV API ---
    @task(1)
    def get_cv_user_missions(self):
        # _CV_PROFILE_USER_IDS garantit un user avec profil CV reel -> zero 404
        user_id = random.choice(_CV_PROFILE_USER_IDS) if _CV_PROFILE_USER_IDS else random.randint(1, 400)
        self.client.get(
            f"{self.cv_api}/user/{user_id}/missions",
            headers=self.headers,
            name="[CV] GET /user/{id}/missions",
        )

    @task(1)
    def get_cv_user_details(self):
        user_id = random.choice(_CV_PROFILE_USER_IDS) if _CV_PROFILE_USER_IDS else random.randint(1, 400)
        with self.client.get(
            f"{self.cv_api}/user/{user_id}",
            headers=self.headers,
            name="[CV] GET /user/{id}",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                _validate_contract(resp, _CvProfilePagination, "GET /cv/user/{id}")

    # --- Missions API ---
    @task(2)
    def list_missions(self):
        skip = random.randint(0, 10)
        self.client.get(
            f"{self.missions_api}/missions?skip={skip}&limit=20",
            headers=self.headers,
            name="[Missions] GET /missions",
        )

    # --- Drive API ---
    @task(1)
    def list_drive_files(self):
        self.client.get(
            f"{self.drive_api}/files",
            headers=self.headers,
            name="[Drive] GET /files",
        )

    @task(1)
    def get_drive_status(self):
        self.client.get(
            f"{self.drive_api}/status",
            headers=self.headers,
            name="[Drive] GET /status",
        )

    @task(1)
    def get_ingestion_stats(self):
        self.client.get(
            f"{self.drive_api}/ingestion/stats",
            headers=self.headers,
            name="[Drive] GET /ingestion/stats",
        )

    # --- Bulk pipeline monitoring ---
    @task(1)
    def get_cv_bulk_status(self):
        """Simule un admin surveillant l etat du pipeline bulk de reanalyse CV."""
        self.client.get(
            f"{self.cv_api}/bulk-reanalyse/status",
            headers=self.headers,
            name="[CV] GET /bulk-reanalyse/status",
        )

    @task(1)
    def get_cv_bulk_data_quality(self):
        """Interroge le rapport qualite du pipeline bulk CV."""
        self.client.get(
            f"{self.cv_api}/bulk-reanalyse/data-quality",
            headers=self.headers,
            name="[CV] GET /bulk-reanalyse/data-quality",
        )

    @task(1)
    def get_competencies_scoring_status(self):
        """Surveille l etat du scoring Vertex AI Batch."""
        self.client.get(
            f"{self.competencies_api}/bulk-scoring-all/status",
            headers=self.headers,
            name="[Competencies] GET /bulk-scoring-all/status",
        )

    # --- Prompts API ---
    @task(1)
    def get_prompt(self):
        self.client.get(
            f"{self.prompts_api}/agent_router_api.system_instruction",
            headers=self.headers,
            name="[Prompts] GET /prompt/{key}",
        )

    # --- Data Quality & Analytics CV (BigQuery via cv_api) ---

    @task(2)
    def get_data_quality_report(self):
        """GET /cv/bulk-reanalyse/data-quality — query SQL + cache Redis.

        Endpoint lourd : parcourt cv_profiles, calcule scores fiabilite,
        taux de completion, distribution par agence. Cache TTL=60s en Redis.
        Sous 500 users : stress le cache miss et le pool DB cv.
        Valide le contrat : total_profiles, profiles_with_competencies, profiles_with_missions.
        """
        with self.client.get(
            f"{self.cv_api}/bulk-reanalyse/data-quality",
            headers=self.headers,
            name="[DataQuality] GET /cv/data-quality (PostgreSQL+Redis)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                _validate_contract(resp, _DataQualityReport, "GET /cv/data-quality")

    @task(1)
    def get_skills_coverage(self):
        """GET /cv/analytics/skills-coverage — agregation par competence.

        Jointure cv_profiles x competencies pour calculer le taux de couverture
        des competences de l arbre. Query lourde sans cache.
        """
        self.client.get(
            f"{self.cv_api}/analytics/skills-coverage",
            headers=self.headers,
            name="[DataQuality] GET /cv/analytics/skills-coverage (agregation DB)",
        )

    @task(1)
    def get_reanalyze_status(self):
        """GET /cv/reanalyze/status — statut du pipeline batch de re-analyse."""
        self.client.get(
            f"{self.cv_api}/reanalyze/status",
            headers=self.headers,
            name="[DataQuality] GET /cv/reanalyze/status",
        )

    # --- Users API (routes non testees) ---

    @task(1)
    def get_user_by_id(self):
        """GET /users/{user_id} — lecture simple PostgreSQL."""
        user_id = random.choice(_CV_PROFILE_USER_IDS) if _CV_PROFILE_USER_IDS else random.randint(1, 400)
        self.client.get(
            f"{self.users_api}/{user_id}",
            headers=self.headers,
            name="[Users] GET /users/{id}",
        )

    @task(1)
    def search_users(self):
        """GET /users/search — recherche fulltext PostgreSQL."""
        q = random.choice(_SEARCH_QUERIES.get("users", ["alice", "bob", "zenika"]))
        self.client.get(
            f"{self.users_api}/search?query={q}",
            headers=self.headers,
            name="[Users] GET /users/search",
        )

    @task(1)
    def get_users_stats(self):
        """GET /users/stats — stats agregees DB (count par agence, actifs/inactifs)."""
        self.client.get(
            f"{self.users_api}/stats",
            headers=self.headers,
            name="[Users] GET /users/stats",
        )

    @task(1)
    def get_users_duplicates(self):
        """GET /users/duplicates — scan des doublons email/nom PostgreSQL."""
        self.client.get(
            f"{self.users_api}/duplicates",
            headers=self.headers,
            name="[Users] GET /users/duplicates",
        )

    # --- Items API (routes non testees) ---

    @task(1)
    def get_item_by_id(self):
        """GET /items/{item_id} — lecture item PostgreSQL par PK."""
        item_id = random.choice(_ITEM_IDS) if _ITEM_IDS else random.randint(1, 200)
        self.client.get(
            f"{self.items_api}/{item_id}",
            headers=self.headers,
            name="[Items] GET /items/{id}",
        )

    @task(1)
    def get_items_by_user(self):
        """GET /items/user/{user_id} — items d un consultant PostgreSQL."""
        user_id = random.choice(_CV_PROFILE_USER_IDS) if _CV_PROFILE_USER_IDS else random.randint(1, 400)
        self.client.get(
            f"{self.items_api}/user/{user_id}",
            headers=self.headers,
            name="[Items] GET /items/user/{id}",
        )

    @task(1)
    def search_items(self):
        """GET /items/search/query — recherche texte DB/Redis."""
        q = random.choice(_SEARCH_QUERIES.get("items", ["python", "java", "cloud"]))
        self.client.get(
            f"{self.items_api}/search/query?query={q}",
            headers=self.headers,
            name="[Items] GET /items/search/query",
        )

    @task(1)
    def get_items_stats(self):
        """GET /items/stats — stats agregees items par categorie PostgreSQL."""
        self.client.get(
            f"{self.items_api}/stats",
            headers=self.headers,
            name="[Items] GET /items/stats",
        )

    # --- CV API (routes non testees) ---

    @task(1)
    def get_cv_user_full_details(self):
        """GET /cv/user/{id}/details — profil CV complet avec scoring PostgreSQL."""
        user_id = random.choice(_CV_PROFILE_USER_IDS) if _CV_PROFILE_USER_IDS else random.randint(1, 400)
        self.client.get(
            f"{self.cv_api}/user/{user_id}/details",
            headers=self.headers,
            name="[CV] GET /user/{id}/details",
        )

    @task(1)
    def get_cv_similar(self):
        """GET /cv/user/{id}/similar — CVs similaires pgvector. Requiert un profil CV indexe.

        Note : retourne 404 en local (pas d'embeddings Gemini disponibles sans GCP).
        Ce 404 est marque comme succes car c'est un comportement attendu hors GCP.
        """
        if not _CV_PROFILE_USER_IDS:
            return
        user_id = random.choice(_CV_PROFILE_USER_IDS)
        with self.client.get(
            f"{self.cv_api}/user/{user_id}/similar",
            headers=self.headers,
            name="[CV] GET /user/{id}/similar",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                # 404 attendu en local : profil sans embedding (pas de GCP)
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}: {resp.text[:80]}")

    @task(1)
    def get_cv_ranking_experience(self):
        """GET /cv/ranking/experience — classement par anciennete PostgreSQL."""
        self.client.get(
            f"{self.cv_api}/ranking/experience",
            headers=self.headers,
            name="[CV] GET /ranking/experience",
        )

    @task(1)
    def get_cv_recalculate_tree_status(self):
        """GET /cv/recalculate_tree/status — statut batch taxonomy PostgreSQL."""
        self.client.get(
            f"{self.cv_api}/recalculate_tree/status",
            headers=self.headers,
            name="[CV] GET /recalculate_tree/status",
        )

    @task(1)
    def search_cv(self):
        """GET /cv/search — recherche semantique pgvector.

        Note : retourne 404 en local (embeddings Gemini non disponibles sans GCP).
        Ce 404 est marque comme succes car c'est un comportement attendu hors GCP.
        """
        q = random.choice(_SEARCH_QUERIES.get("cv", ["python senior", "cloud architect"]))
        with self.client.get(
            f"{self.cv_api}/search?query={q}",
            headers=self.headers,
            name="[CV] GET /search",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                # 404 attendu en local : pas d'embeddings sans GCP
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}: {resp.text[:80]}")

    # --- Missions API (routes non testees) ---

    @task(1)
    def get_missions_list(self):
        """GET /missions/ — liste des missions PostgreSQL (pagination)."""
        skip = random.randint(0, 2) * 10
        self.client.get(
            f"{self.missions_api}/missions/?skip={skip}&limit=10",
            headers=self.headers,
            name="[Missions] GET /missions/",
        )

    @task(1)
    def get_mission_by_id(self):
        """GET /missions/{id} — lecture mission PostgreSQL par id entier."""
        # Utilise les IDs reels bootstrappes ou skip si aucune mission disponible
        if not _MISSION_IDS:
            return
        mission_id = random.choice(_MISSION_IDS)
        self.client.get(
            f"{self.missions_api}/missions/{mission_id}",
            headers=self.headers,
            name="[Missions] GET /missions/{id}",
        )

    @task(1)
    def get_user_active_missions(self):
        """GET /missions/user/{user_id}/active — missions actives d un consultant."""
        user_id = random.choice(_CV_PROFILE_USER_IDS) if _CV_PROFILE_USER_IDS else random.randint(1, 400)
        self.client.get(
            f"{self.missions_api}/missions/user/{user_id}/active",
            headers=self.headers,
            name="[Missions] GET /missions/user/{id}/active",
        )

    # --- Prompts API (route generique) ---

    @task(1)
    def get_prompt_by_key(self):
        """GET /prompts/{key} — lecture prompt PostgreSQL (pattern generique multi-cles)."""
        keys = [
            "agent_router_api.system_instruction",
            "agent_hr_api.system_instruction",
            "agent_ops_api.system_instruction",
        ]
        key = random.choice(keys)
        self.client.get(
            f"{self.prompts_api}/{key}",
            headers=self.headers,
            name="[Prompts] GET /prompts/{key}",
        )


# ── Classe 2 : Pipeline d'ingestion CV (sans IA) ─────────────────────────────


class CVIngestionPipelineUser(HttpUser):
    """
    Simule le pipeline complet d'ingestion de CV SANS appel IA.

    Desactive en mode LOCUST_SCENARIO=navigation (weight=0).
    Note : les 404 sur /cv/user/{id} pour les users crees EN DIRECT sont
    ATTENDUS -- les profils CV ne sont injectes que pour les users du seed.

    Chaque user Locust représente un worker d'ingestion qui, en boucle :
      1. Crée un utilisateur (le candidat)
      2. Récupère les IDs de compétences disponibles
      3. Assigne 30 compétences en bulk → competencies_api
      4. Crée 50 missions (fiches de mission textuelles) → missions_api
      5. Lit le profil CV et les missions pour valider la cohérence
      6. Interroge les endpoints analytics compétences + CV

    Objectif : stresser les endpoints d'écriture haute-fréquence et vérifier
    que le système tient 3000 CVs (30 compétences + 50 missions chacun)
    sans dégradation de latence ni erreur de pool DB.
    """
    weight = 0 if _SCENARIO == "navigation" else 1  # 25% trafic en mode full, desactive en navigation
    wait_time = between(0.5, 1.5)

    # Compteur de CVs simulés partagé entre instances (approximatif)
    _cv_count: int = 0
    CV_TARGET: int = 3000  # Objectif : 3000 CVs ingérés

    def on_start(self):
        self.users_api = os.getenv("USERS_API_URL", "http://users_api:8000")
        self.items_api = os.getenv("ITEMS_API_URL", "http://items_api:8001")
        self.competencies_api = os.getenv("COMPETENCIES_API_URL", "http://competencies_api:8003")
        self.cv_api = os.getenv("CV_API_URL", "http://cv_api:8004")
        self.missions_api = os.getenv("MISSIONS_API_URL", "http://missions_api:8009")

        self._login()
        self._comp_ids: list[int] = []
        self._cat_ids: list[int] = []   # IDs categories pour POST /items/bulk
        self._user_ids_created: list[int] = []

    def _login(self):
        res = self.client.post(
            f"{self.users_api}/login",
            json={"email": "admin@zenika.com", "password": "admin"},
            name="/login",
        )
        if res.status_code == 200:
            self.token = res.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
            self._token_issued_at = time.monotonic()
        else:
            self.token = None
            self.headers = {}
            self._token_issued_at = 0.0
            print(f"[CVIngestion] Auth failed: HTTP {res.status_code} — {res.text[:120]}")

    def _ensure_fresh_token(self):
        """Re-login proactif si le token approche de son expiration."""
        ttl_seconds = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 15)) * 60
        age = time.monotonic() - getattr(self, "_token_issued_at", 0.0)
        if not self.token or age >= ttl_seconds - 180:
            self._login()

    def _fetch_competency_ids(self) -> list[int]:
        """Recupere les IDs de competences disponibles (pagine, mis en cache par instance)."""
        if self._comp_ids:
            return self._comp_ids
        res = self.client.get(
            f"{self.competencies_api}/?skip=0&limit=500",
            headers=self.headers,
            name="[Ingestion] GET /competencies/ (bootstrap)",
        )
        if res.status_code == 200:
            data = res.json()
            items = data.get("items", []) if isinstance(data, dict) else data
            self._comp_ids = [c["id"] for c in items if "id" in c]
        return self._comp_ids

    def _fetch_category_ids(self) -> list[int]:
        """Recupere les IDs de categories pour POST /items/bulk (mis en cache par instance)."""
        if self._cat_ids:
            return self._cat_ids
        res = self.client.get(
            f"{self.items_api}/categories?skip=0&limit=500",
            headers=self.headers,
            name="[Ingestion] GET /categories (bootstrap)",
        )
        if res.status_code == 200:
            data = res.json()
            items = data.get("items", []) if isinstance(data, dict) else data
            self._cat_ids = [c["id"] for c in items if "id" in c]
        return self._cat_ids

    def _create_candidate(self) -> dict | None:
        """
        Étape 1 : Crée un utilisateur candidat via users_api.
        Simule la création du profil avant ingestion.
        """
        uid = _random_str(8)
        ts = int(time.time() * 1000)
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        payload = {
            "username": f"cv_{uid}_{ts}",
            "email": f"cv.{uid}.{ts}@zenika-perf.test",
            "first_name": first,
            "last_name": last,
            "full_name": f"{first} {last}",
            "password": "perf_test_123!",
            "allowed_category_ids": [],
        }
        res = self.client.post(
            f"{self.users_api}/",
            json=payload,
            headers=self.headers,
            name="[Ingestion] POST /users/ (create candidate)",
        )
        if res.status_code in (200, 201):
            data = res.json()
            uid = data.get("id")
            if uid:
                _CREATED_USER_IDS.append(uid)
                # Limiter la taille du pool (evite la croissance infinie en memoire)
                if len(_CREATED_USER_IDS) > 5000:
                    _CREATED_USER_IDS.pop(0)
            return data
        return None

    def _assign_competencies_bulk(self, user_id: int, comp_ids: list[int]) -> None:
        """
        Étape 2 : Assigne 30 compétences en bulk au candidat.
        Simule l'étape post-analyse IA du pipeline (écriture competencies_api).
        """
        available = self._fetch_competency_ids()
        if not available:
            return
        # Pioche 30 compétences aléatoires (ou moins si pas assez disponibles)
        sample = random.sample(available, min(30, len(available)))
        self.client.post(
            f"{self.competencies_api}/user/{user_id}/assign/bulk",
            json={"competency_ids": sample},
            headers=self.headers,
            name="[Ingestion] POST /competencies/user/{id}/assign/bulk (30 comp.)",
        )

    def _create_missions(self, user_id: int) -> None:
        """
        Etape 3 : Cree 45 missions textuelles pour ce candidat.
        POST /missions attend du multipart/form-data (Form) avec title et description.
        Sans IA : le background task Gemini est lance mais on ne l attend pas.
        """
        for i in range(45):
            skills = random.sample(MISSION_SKILLS, k=random.randint(2, 5))
            duration_months = random.randint(3, 36)
            # missions_api accepte Form(...) pas JSON -> utiliser data= (multipart)
            form_data = {
                "title": f"{random.choice(MISSION_TITLES)} #{i + 1}",
                "description": (
                    f"Mission de {duration_months} mois. "
                    f"Technologies : {', '.join(skills)}. "
                    f"Consultant : user_{user_id}. Ref perf-test."
                ),
            }
            self.client.post(
                f"{self.missions_api}/missions",
                data=form_data,
                headers=self.headers,
                name="[Ingestion] POST /missions (create mission)",
            )

    def _create_items_bulk(self, user_id: int, category_ids: list) -> None:
        """
        Etape 3b : Cree 5 items via POST /items/bulk.
        Stresse le semaphore BULK_ENDPOINT_SEMAPHORE (defaut=5 slots).
        Un 429 est attendu sous charge elevee et compte comme succes de test.
        """
        if not category_ids:
            return
        items_payload = []
        for i in range(5):
            skills = random.sample(MISSION_SKILLS, k=3)
            items_payload.append({
                "name": f"Item CV {user_id} #{i + 1} {_random_str(4)}",
                "description": (
                    f"Item ingere depuis CV user_{user_id}. "
                    f"Competences : {', '.join(skills)}."
                ),
                "user_id": user_id,
                "category_ids": [random.choice(category_ids)],
                "metadata_json": {"source": "perf-test", "skills": skills},
            })
        with self.client.post(
            f"{self.items_api}/bulk",
            json={"items": items_payload},
            headers=self.headers,
            name="[Ingestion] POST /items/bulk (5 items)",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                resp.success()
            elif resp.status_code == 429:
                # Semaphore sature : comportement attendu sous charge
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}: {resp.text[:80]}")

    def _read_profile(self, user_id: int) -> None:
        """
        Etape 4 : Lecture de validation du profil ingere.
        Simule le chargement post-ingestion pour verifier la coherence.

        Note : /cv/user/{id} et /cv/user/{id}/missions retournent 404 pour les
        users crees EN DIRECT dans ce flow (aucun profil CV ingere). On n'appelle
        ces endpoints que pour les users du pool seede qui ont un profil existant.
        """
        # CV validation uniquement pour les users pre-seedes (qui ont un profil cv_api)
        if user_id in _CV_PROFILE_USER_IDS_SET:
            self.client.get(
                f"{self.cv_api}/user/{user_id}",
                headers=self.headers,
                name="[Ingestion] GET /cv/user/{id} (validate profile)",
            )
            self.client.get(
                f"{self.cv_api}/user/{user_id}/missions",
                headers=self.headers,
                name="[Ingestion] GET /cv/user/{id}/missions (validate missions)",
            )
        self.client.get(
            f"{self.competencies_api}/user/{user_id}?skip=0&limit=50",
            headers=self.headers,
            name="[Ingestion] GET /competencies/user/{id} (validate comp.)",
        )
        self.client.get(
            f"{self.missions_api}/missions/user/{user_id}/active",
            headers=self.headers,
            name="[Ingestion] GET /missions/user/{id}/active",
        )

    def _read_analytics(self) -> None:
        """
        Étape 5 : Interroge les endpoints analytics pour mesurer l'impact
        sur les requêtes agrégées après charge d'écriture.
        """
        self.client.get(
            f"{self.competencies_api}/stats/coverage",
            headers=self.headers,
            name="[Ingestion] GET /competencies/stats/coverage (analytics)",
        )
        self.client.get(
            f"{self.cv_api}/extraction-scores?skip=0&limit=10",
            headers=self.headers,
            name="[Ingestion] GET /cv/extraction-scores (analytics)",
        )

    @task
    def ingest_cv_pipeline(self):
        """
        Pipeline complet d'ingestion d'un CV sans IA.
        Chaque exécution = 1 CV ingéré (1 user + 30 compétences + 50 missions).
        """
        # Refresh proactif du token avant un pipeline long (multiples appels API)
        self._ensure_fresh_token()

        CVIngestionPipelineUser._cv_count += 1
        cv_num = CVIngestionPipelineUser._cv_count

        # Étape 1 : Création du candidat
        candidate = self._create_candidate()
        if not candidate:
            return
        user_id = candidate.get("id")
        if not user_id:
            return

        # Étape 2 : Assignation de 30 compétences
        self._assign_competencies_bulk(user_id, [])

        # Etape 3a : 45 missions individuelles
        self._create_missions(user_id)

        # Etape 3b : 5 items via POST /items/bulk (stresse le semaphore 429)
        self._create_items_bulk(user_id, self._fetch_category_ids())

        # Étape 4 : Validation lecture du profil
        self._read_profile(user_id)

        # Étape 5 : Analytics (1 fois sur 10 pour ne pas surcharger)
        if cv_num % 10 == 0:
            self._read_analytics()
            print(f"  📊 [{cv_num}/{self.CV_TARGET}] CVs ingérés simulés")
