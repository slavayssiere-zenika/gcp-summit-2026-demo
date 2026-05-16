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


# ── Données de référence ──────────────────────────────────────────────────────

FIRST_NAMES = [
    "Alice", "Bob", "Charlie", "David", "Emma", "Frank",
    "Grace", "Henry", "Isabel", "Jack", "Karl", "Laura",
]
LAST_NAMES = [
    "Martin", "Bernard", "Thomas", "Petit", "Robert", "Richard",
    "Durand", "Dubois", "Moreau", "Laurent", "Simon", "Michel",
]

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


# ── Classe 1 : Navigation utilisateur classique ───────────────────────────────

class ZenikaPerfUser(HttpUser):
    """
    Simule un utilisateur standard naviguant sur la plateforme.
    Charge : lecture des listes (users, items, compétences, missions).
    """
    weight = 3  # 75 % du trafic total
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

    def _login(self):
        res = self.client.post(
            f"{self.users_api}/login",
            json={"email": "admin@zenika.com", "password": "admin"},
        )
        if res.status_code == 200:
            self.token = res.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None
            self.headers = {}
            print(f"[ZenikaPerfUser] Auth failed: HTTP {res.status_code}")

    # --- Users API ---
    @task(3)
    def list_users(self):
        skip = random.randint(0, 100)
        self.client.get(
            f"{self.users_api}/?skip={skip}&limit=50",
            headers=self.headers,
            name="[Users] GET /users/",
        )

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
        self.client.get(
            f"{self.items_api}/?skip={skip}&limit=50",
            headers=self.headers,
            name="[Items] GET /items/",
        )

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
        user_id = random.randint(1, 400)
        self.client.get(
            f"{self.cv_api}/user/{user_id}/missions",
            headers=self.headers,
            name="[CV] GET /user/{id}/missions",
        )

    @task(1)
    def get_cv_user_details(self):
        user_id = random.randint(1, 400)
        self.client.get(
            f"{self.cv_api}/user/{user_id}",
            headers=self.headers,
            name="[CV] GET /user/{id}",
        )

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

    # --- Prompts API ---
    @task(1)
    def get_prompt(self):
        self.client.get(
            f"{self.prompts_api}/agent_router_api.system_instruction",
            headers=self.headers,
            name="[Prompts] GET /prompt/{key}",
        )


# ── Classe 2 : Pipeline d'ingestion CV (sans IA) ─────────────────────────────

class CVIngestionPipelineUser(HttpUser):
    """
    Simule le pipeline complet d'ingestion de CV SANS appel IA.

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
    weight = 1  # 25 % du trafic total
    wait_time = between(0.5, 1.5)

    # Compteur de CVs simulés partagé entre instances (approximatif)
    _cv_count: int = 0
    CV_TARGET: int = 3000  # Objectif : 3000 CVs ingérés

    def on_start(self):
        self.users_api = os.getenv("USERS_API_URL", "http://users_api:8000")
        self.competencies_api = os.getenv("COMPETENCIES_API_URL", "http://competencies_api:8003")
        self.cv_api = os.getenv("CV_API_URL", "http://cv_api:8004")
        self.missions_api = os.getenv("MISSIONS_API_URL", "http://missions_api:8009")

        self._login()
        self._comp_ids: list[int] = []
        self._user_ids_created: list[int] = []

    def _login(self):
        res = self.client.post(
            f"{self.users_api}/login",
            json={"email": "admin@zenika.com", "password": "admin"},
        )
        if res.status_code == 200:
            self.token = res.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None
            self.headers = {}
            print(f"[CVIngestion] Auth failed: HTTP {res.status_code}")

    def _fetch_competency_ids(self) -> list[int]:
        """Récupère les IDs de compétences disponibles (paginé, mis en cache par instance)."""
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
            return res.json()
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
        Étape 3 : Crée 50 missions textuelles pour ce candidat.
        Simule l'extraction de missions depuis le CV (sans IA : payload texte brut).
        Chaque mission est envoyée individuellement pour stresser l'endpoint de création.
        """
        for i in range(50):
            skills = random.sample(MISSION_SKILLS, k=random.randint(2, 5))
            duration_months = random.randint(3, 36)
            payload = {
                "title": f"{random.choice(MISSION_TITLES)} #{i + 1}",
                "client": random.choice(CLIENTS),
                "description": (
                    f"Mission de {duration_months} mois. "
                    f"Technologies utilisées : {', '.join(skills)}. "
                    f"Consultant : user_{user_id}. Référence perf-test."
                ),
                "skills": skills,
                "duration_months": duration_months,
                "user_id": user_id,
            }
            self.client.post(
                f"{self.missions_api}/missions",
                json=payload,
                headers=self.headers,
                name="[Ingestion] POST /missions (create mission)",
            )

    def _read_profile(self, user_id: int) -> None:
        """
        Étape 4 : Lecture de validation du profil ingéré.
        Simule le chargement post-ingestion pour vérifier la cohérence des données.
        """
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

        # Étape 3 : Création de 50 missions
        self._create_missions(user_id)

        # Étape 4 : Validation lecture du profil
        self._read_profile(user_id)

        # Étape 5 : Analytics (1 fois sur 10 pour ne pas surcharger)
        if cv_num % 10 == 0:
            self._read_analytics()
            print(f"  📊 [{cv_num}/{self.CV_TARGET}] CVs ingérés simulés")
