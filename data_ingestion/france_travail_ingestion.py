import os
import sys
import time
import requests
from typing import List, Dict, Any
from datetime import datetime, timezone
from requests.exceptions import RequestException
from google.cloud import bigquery

# ==============================================================================
# CONFIGURATION
# Les secrets doivent être sourcés via `source secrets.sh` avant l'exécution.
# ==============================================================================
CLIENT_ID = os.environ.get("FRANCE_TRAVAIL_ID")
CLIENT_SECRET = os.environ.get("FRANCE_TRAVAIL_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print("Erreur : FRANCE_TRAVAIL_ID et FRANCE_TRAVAIL_SECRET doivent être définis en variables d'environnement.", file=sys.stderr)
    print("Assurez-vous de faire un `source secrets.sh` au préalable.", file=sys.stderr)
    sys.exit(1)

# GCP / BigQuery
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "slavayssiere-sandbox-462015") # Adapt if needed
DATASET_ID = "analytics_data"
TABLE_ID = "job_offers"

# Zenika Categories to search
ZENIKA_CATEGORIES = [
    "Développeur", "Data Engineer", "Data Scientist", "DevOps", 
    "Cloud Architect", "Consultant IT", "Tech Lead", "Scrum Master", 
    "Agile Coach", "Développeur Fullstack", "Développeur Frontend", 
    "Développeur Backend"
]

# API Endpoints
AUTH_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire"
JOB_SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
ROME_URL_TEMPLATE = "https://api.francetravail.io/partenaire/rome-metiers/v1/metiers/{}"
AGENCY_URL_TEMPLATE = "https://api.francetravail.io/partenaire/referentielagences/v1/agences/{}"

# Scopes (Standard France Travail Partenaire scopes)
SCOPES = "api_offresdemploiv2 o2dsoffre api_rome-metiersv1 api_referentielagencesv1"

# ==============================================================================
# API CLIENT
# ==============================================================================

class FranceTravailClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expiry = 0
        
        # Rate Limiting State (Timestamps of last calls)
        self.last_calls = {
            'job': 0.0,     # Offres d'emploi v2 (10/s)
            'agency': 0.0,  # Référentiel des agences v1 (1/s)
            'rome': 0.0,    # ROME 4.0 (Toutes APIs) (1/s)
            'market': 0.0,  # Marché du travail v1 (10/s)
            'access': 0.0   # Accès à l'emploi des demandeurs d'emploi v1 (10/s)
        }

    def _get_token(self) -> str:
        """Récupère ou rafraîchit le token OAuth2."""
        if time.time() < self.token_expiry and self.access_token:
            return self.access_token

        print("Demande d'un nouveau jeton d'accès France Travail...")
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": SCOPES
        }
        response = requests.post(AUTH_URL, data=data)
        response.raise_for_status()
        
        token_data = response.json()
        self.access_token = token_data["access_token"]
        # Réduit l'expiration de 60s pour la sécurité
        self.token_expiry = time.time() + token_data.get("expires_in", 1199) - 60 
        return self.access_token

    def _wait_rate_limit(self, call_type: str):
        """Gère les pauses pour respecter strictement les Rate Limits."""
        now = time.time()
        
        # Configuration des délais minimums entre deux appels
        delays = {
            'job': 0.1,     # Offres d'emploi v2 (10/s)
            'market': 0.1,  # Marché du travail v1 (10/s)
            'access': 0.1,  # Accès à l'emploi des demandeurs (10/s)
            'agency': 1.0,  # Référentiel des agences v1 (1/s)
            'rome': 1.0     # ROME 4.0 - toutes sous-APIs (1/s)
        }
        
        delay = delays.get(call_type, 1.0) # Défaut sécuritaire: 1 appel/sec
        last_call_time = self.last_calls.get(call_type, 0.0)
        
        elapsed = now - last_call_time
        if elapsed < delay:
            time.sleep(delay - elapsed)
            
        self.last_calls[call_type] = time.time()

    def _make_request(self, method: str, url: str, call_type: str, params: dict = None) -> dict:
        """Exécute une requête avec relance sur 429."""
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/json"
        }
        
        retries = 3
        for attempt in range(retries):
            self._wait_rate_limit(call_type)
            try:
                if method.upper() == "GET":
                    response = requests.get(url, headers=headers, params=params)
                else: # GET by default here for simplicity
                    response = requests.get(url, headers=headers, params=params)
                    
                if response.status_code == 429:
                    print(f"[{call_type}] Code 429: Limit atteinte. Pause de 1 seconde.")
                    time.sleep(1.0) # Pause d'une seconde de pénalité en cas de 429
                    continue
                    
                response.raise_for_status()
                # Status code 204 ou empty
                if not response.content:
                    return {}
                    
                return response.json()
            except RequestException as e:
                # 400, 404: no data found or bad request
                # 401, 403: gateway authorization sync issues, fallback gracefully
                if response is not None and response.status_code in [400, 401, 403, 404]:
                    print(f"  [Avertissement] Accès refusé ou donnée introuvable ({response.status_code}) pour {url}. Utilisation du fallback.")
                    return {}
                print(f"Erreur API ({url}) : {e}")
                if attempt == retries - 1:
                    raise
                time.sleep(2)
        return {}

    def search_jobs(self, keyword: str, limit: int = 10) -> List[dict]:
        print(f"Recherche offres emploi pour : {keyword}")
        params = {
            "motsCles": keyword,
            "range": f"0-{limit-1}"
        }
        response_data = self._make_request("GET", JOB_SEARCH_URL, 'job', params=params)
        return response_data.get("resultats", [])

    def get_rome_skills(self, rome_code: str) -> List[str]:
        if not rome_code:
            return []
        print(f"  > Récupération compétences ROME : {rome_code}")
        url = ROME_URL_TEMPLATE.format(rome_code)
        response_data = self._make_request("GET", url, 'rome')
        
        skills = []
        # Extraction défensive (ROME V4.0)
        # Typiquement structure: "savoirsFaire" : [{"libelle": "..."}] etc.
        for sa in response_data.get("savoirsAgi", []):
            if "libelle" in sa:
                skills.append(sa["libelle"])
        for sf in response_data.get("savoirsFaire", []):
            if "libelle" in sf:
                skills.append(sf["libelle"])
        
        return list(set(skills))

    def get_agency_details(self, agency_id: str) -> str:
        if not agency_id or agency_id == "INCONNUE":
            return ""
        print(f"  > Récupération infos agence : {agency_id}")
        url = AGENCY_URL_TEMPLATE.format(agency_id)
        response_data = self._make_request("GET", url, 'agency')
        
        return response_data.get("nom", f"Agence {agency_id}")

# ==============================================================================
# BIGQUERY INGESTION
# ==============================================================================

def ingest_to_bigquery(rows_to_insert: List[dict]):
    if not rows_to_insert:
        print("Aucune donnée à insérer dans BigQuery.")
        return

    print(f"Ingestion de {len(rows_to_insert)} lignes dans BigQuery ({PROJECT_ID}.{DATASET_ID}.{TABLE_ID})...")
    client = bigquery.Client(project=PROJECT_ID)
    table_ref = client.dataset(DATASET_ID).table(TABLE_ID)

    # Insert
    errors = client.insert_rows_json(table_ref, rows_to_insert)
    if not errors:
        print("✅ Ingestion BigQuery réussie.")
    else:
        print(f"❌ Erreurs lors de l'insertion : {errors}")

# ==============================================================================
# MAIN BATCH
# ==============================================================================

def run_etl():
    client = FranceTravailClient(CLIENT_ID, CLIENT_SECRET)
    
    # Structure cible (Flatten Schema pour LLM MCP)
    extracted_data = []

    for category in ZENIKA_CATEGORIES:
        jobs = client.search_jobs(category, limit=100) # Augmentation à 100 pour maximiser les données
        for job in jobs:
            offer_id = job.get("id")
            job_title = job.get("intitule")
            rome_code = job.get("romeCode")
            description = job.get("description", "")
            
            # Extraction des informations de contact/agence
            agency = job.get("entreprise", {})
            # Parfois stocké dans contact > agence
            if job.get("contact") and "courriel" in job.get("contact"):
                 agency_id = job.get("agence", {}).get("code") or "INCONNUE"
            else:
                 agency_id = None
                 
            # Note: Si un offer_id n'existe pas, on passe.
            if not offer_id:
                continue

            # API ROME
            skills = []
            if rome_code:
                skills = client.get_rome_skills(rome_code)

            # Si aucune compétence retournée (rate limit ou absence), fallback sur ROME brut de l'offre
            if not skills and job.get("competences"):
                skills = [c.get("libelle", "") for c in job.get("competences", [])]
            
            # API Agences
            agency_name = ""
            if agency_id:
                agency_name = client.get_agency_details(agency_id)

            # Record
            record = {
                "offer_id": str(offer_id),
                "job_title": job_title,
                "zenika_category": category,
                "rome_code": rome_code,
                "skills": [s for s in skills if s], # Filtrer vides
                "creation_date": datetime.now(timezone.utc).isoformat(),
                "description": description[:1000] if description else "", # Limiter à 1000 pour BQ
                "agency_id": str(agency_id) if agency_id else None,
                "agency_name": agency_name if agency_name else None,
            }
            extracted_data.append(record)
            print(f"  [+] Offre '{job_title[:30]}...' traitée ({len(extracted_data)} en attente d'ingestion)")

    # Ingestion BigQuery finale
    ingest_to_bigquery(extracted_data)

if __name__ == "__main__":
    run_etl()
