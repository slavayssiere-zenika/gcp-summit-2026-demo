import base64
import json
import logging
import os
import time
from typing import Optional

import httpx
from fastapi import BackgroundTasks, HTTPException, Request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import jwt as jose_jwt
from jose.exceptions import JWTError
from opentelemetry.propagate import inject
from sqlalchemy.future import select

import database
import src.services.config as _svc_config
from src.auth import SECRET_KEY as _AUTH_SECRET_KEY
from src.cvs.models import CVProfile
from src.services.cv_import_service import process_cv_core

logger = logging.getLogger(__name__)

USERS_API_URL = os.getenv("USERS_API_URL", "http://users_api:8001")


class PubsubService:
    @staticmethod
    async def _run_cv_delete_bg(
        bg_url: str,
        bg_google_file_id: str,
        bg_jwt: str,
        bg_drive_api_url: str,
        bg_headers: dict
    ):
        """Pipeline d'archivage CV et désactivation utilisateur."""
        async with database.SessionLocal() as bg_db:
            try:
                # 1. Archiver le CV
                stmt = select(CVProfile).filter(
                    CVProfile.source_url.like(
                        f"%{bg_google_file_id}%"))
                cvs = (await bg_db.execute(stmt)).scalars().all()
                user_id = None
                if cvs:
                    for cv in cvs:
                        cv.is_archived = True
                        user_id = cv.user_id
                    await bg_db.commit()
                    logger.info(
                        f"[PubSub/BG] CV(s) archivé(s) pour le fichier {bg_google_file_id} (user_id={user_id})")
                else:
                    logger.warning(
                        f"[PubSub/BG] Aucun CV trouvé pour le fichier {bg_google_file_id} à archiver.")

                # 2. Désactiver l'utilisateur (si non admin)
                if user_id:
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as http_client:
                            u_res = await http_client.get(f"{USERS_API_URL.rstrip('/')}/{user_id}", headers=bg_headers)
                            if u_res.status_code == 200:
                                user_data = u_res.json()
                                if user_data.get("role") != "admin":
                                    user_data["is_active"] = False
                                    update_res = await http_client.put(
                                        f"{USERS_API_URL.rstrip('/')}/{user_id}", json=user_data, headers=bg_headers
                                    )
                                    if update_res.is_success:
                                        logger.info(
                                            f"[PubSub/BG] Utilisateur {user_id} désactivé car non admin.")
                                    else:
                                        logger.error(
                                            f"[PubSub/BG] Échec désactivation user {user_id}: {
                                                update_res.text}"
                                        )
                                else:
                                    logger.info(
                                        f"[PubSub/BG] Utilisateur {user_id} est admin, on ne le désactive pas.")
                    except Exception as e:
                        logger.error(
                            f"[PubSub/BG] Erreur vérif/désactivation user {user_id}: {e}")

                # 3. Notifier drive_api (DELETED_OK)
                try:
                    async with httpx.AsyncClient(timeout=10.0) as patch_client:
                        res = await patch_client.patch(
                            f"{
                                bg_drive_api_url.rstrip('/')}/files/{bg_google_file_id}",
                            json={
                                "status": "DELETED_OK",
                                "error_message": None},
                            headers=bg_headers
                        )
                        if res.is_error:
                            logger.error(
                                f"[PubSub/BG] Échec PATCH DELETED_OK: HTTP {res.status_code}")
                        else:
                            logger.info(
                                f"[PubSub/BG] Notifié drive_api DELETED_OK pour {bg_google_file_id}")
                except Exception as e:
                    logger.warning(
                        f"[PubSub/BG] Impossible de notifier drive_api (DELETED_OK): {e}")

            except Exception as e:
                logger.error(
                    f"[PubSub/BG] Erreur inattendue dans _run_cv_delete_bg pour {bg_google_file_id}: {e}",
                    exc_info=True
                )

    @staticmethod
    async def _run_cv_pipeline_bg(
        bg_google_file_id: str,
        bg_url: str,
        bg_google_access_token: Optional[str],
        bg_source_tag: Optional[str],
        bg_folder_name: Optional[str],
        bg_headers: dict,
        bg_jwt: str,
        bg_token_payload: dict,
        bg_drive_api_url: str,
        bg_file_type: str = "google_doc",
    ):
        """Pipeline complet exécuté en arrière-plan après ACK Pub/Sub."""
        pipeline_start_time = time.monotonic()  # Chrono pour KPI processing_duration_ms
        async with database.SessionLocal() as bg_db:
            try:
                local_bg_tasks = BackgroundTasks()
                result = await process_cv_core(
                    url=bg_url,
                    google_access_token=bg_google_access_token,
                    source_tag=bg_source_tag,
                    folder_name=bg_folder_name,
                    headers=bg_headers,
                    token_payload=bg_token_payload,
                    db=bg_db,
                    auth_token=bg_jwt,
                    file_type=bg_file_type,
                    background_tasks=local_bg_tasks, genai_client=_svc_config.client
                )

                # IMPORTANT: Starlette's BackgroundTasks are not automatically executed
                # when not returned in an HTTP response. We must execute them
                # manually.
                await local_bg_tasks()
                # Notification succès → drive_api (avec durée de traitement
                # pour KPIs)
                pipeline_duration_ms = int(
                    (time.monotonic() - pipeline_start_time) * 1000)
                try:
                    async with httpx.AsyncClient(timeout=10.0) as patch_client:
                        res = await patch_client.patch(
                            f"{
                                bg_drive_api_url.rstrip('/')}/files/{bg_google_file_id}",
                            json={
                                "status": "IMPORTED_CV",
                                "user_id": result.user_id,
                                "error_message": None,
                                "processing_duration_ms": pipeline_duration_ms,
                            },
                            headers=bg_headers
                        )
                        if res.is_error:
                            logger.error(
                                f"[PubSub/BG] Échec PATCH IMPORTED_CV: HTTP {res.status_code}")
                        else:
                            logger.info(
                                f"[PubSub/BG] Import réussi {bg_google_file_id} → user_id={
                                    result.user_id} duration={pipeline_duration_ms}ms")
                except Exception as e:
                    logger.warning(
                        f"[PubSub/BG] Impossible de notifier drive_api (IMPORTED_CV): {e}")

            except HTTPException as he:
                error_detail = he.detail
                status = "IGNORED_NOT_CV" if ("Not a CV" in str(
                    error_detail) or "LLM Parsing failed" in str(error_detail)) else "ERROR"
                logger.error(
                    f"[PubSub/BG] Échec pipeline {bg_google_file_id}: {error_detail} → statut={status}")
                try:
                    async with httpx.AsyncClient(timeout=10.0) as patch_client:
                        await patch_client.patch(
                            f"{
                                bg_drive_api_url.rstrip('/')}/files/{bg_google_file_id}",
                            json={
                                "status": status,
                                "error_message": str(error_detail)},
                            headers=bg_headers
                        )
                except Exception as e:
                    logger.warning(
                        f"[PubSub/BG] Impossible de notifier drive_api ({status}): {e}")

            except Exception as ex:
                logger.error(
                    f"[PubSub/BG] Erreur inattendue pour {bg_google_file_id}: {ex}",
                    exc_info=True)
                try:
                    async with httpx.AsyncClient(timeout=10.0) as patch_client:
                        await patch_client.patch(
                            f"{
                                bg_drive_api_url.rstrip('/')}/files/{bg_google_file_id}",
                            json={"status": "ERROR",
                                  "error_message": f"Erreur inattendue: {ex}"},
                            headers=bg_headers
                        )
                except Exception:
                    raise

    @staticmethod
    async def handle_pubsub_cv_import(
            request: Request, background_tasks: BackgroundTasks):
        """
        Worker Pub/Sub push subscriber pour l'ingestion des CVs.

        Workflow :
        1. Validation OIDC du token Google (RS256) — vérifie que l'émetteur est bien le SA pubsub_invoker.
        2. Décodage base64 du payload Pub/Sub.
        3. ACK IMMÉDIAT (202) → Pub/Sub augmente sa concurrence (slow-start algorithm).
        4. Traitement ASYNCHRONE du pipeline LLM en BackgroundTask.
        5. Notification PATCH drive_api : IMPORTED_CV (succès) ou ERROR (échec).

        ARCHITECTURE : Le retour 202 immédiat est essentiel pour le parallélisme.
        Pub/Sub mesure le temps de réponse de l'endpoint pour calibrer sa concurrence.
        Une réponse en 2 min forçait une concurrence de 1-2 messages. Avec < 1s → 10+ parallèles.

        Sécurité : si le token OIDC est absent ou invalide → 401 (Pub/Sub va retenter).
        Idempotence : si le CV existe déjà (même email), mise à jour au lieu de création.
        """

        # ── 1. Validation OIDC ───────────────────────────────────────────────
        invoker_sa_email = os.getenv("PUBSUB_INVOKER_SA_EMAIL", "")
        auth_header_val = request.headers.get("Authorization", "")

        if not auth_header_val.startswith("Bearer "):
            logger.warning("[PubSub] Requête sans token OIDC — rejetée.")
            raise HTTPException(status_code=401, detail="Missing OIDC token")

        oidc_token = auth_header_val.replace("Bearer ", "")

        # En dev local (pas de SA configuré), on tolère un bypass contrôlé
        if invoker_sa_email and invoker_sa_email != "sa-pubsub-invoker-dev@your-project.iam.gserviceaccount.com":
            try:
                # ⚠️ Ne PAS utiliser request.url.path : le LB GCP réécrit le path
                # (ex: /cv-api/pubsub/import-cv → /pubsub/import-cv) donc il ne
                # correspond plus à l'audience dans le token OIDC.
                # On lit l'audience depuis une env var injectée par Terraform,
                # qui est identique à push_config.oidc_token.audience dans
                # pubsub.tf.
                pubsub_audience = os.getenv("PUBSUB_CV_IMPORT_AUDIENCE", "")
                if not pubsub_audience:
                    # Fallback: reconstruction depuis Host + path original (dev
                    # local sans LB)
                    pubsub_audience = f"https://{
                        request.headers.get(
                            'host', '')}{
                        request.url.path}"
                decoded = google_id_token.verify_oauth2_token(
                    oidc_token,
                    google_requests.Request(),
                    audience=pubsub_audience
                )
                token_email = decoded.get("email", "")
                if token_email != invoker_sa_email:
                    logger.warning(
                        f"[PubSub] SA non autorisé: {token_email} (attendu: {invoker_sa_email})")
                    raise HTTPException(
                        status_code=401, detail="Unauthorized Pub/Sub invoker")
                logger.info(
                    f"[PubSub] OIDC validé pour {token_email} (audience: {pubsub_audience})")
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"[PubSub] Échec validation OIDC: {e}")
                raise HTTPException(
                    status_code=401,
                    detail=f"Invalid OIDC token: {e}")

        # ── 2. Décodage du payload Pub/Sub ───────────────────────────────────
        try:
            body = await request.json()
            message = body.get("message", {})
            raw_data = base64.b64decode(
                message.get("data", "")).decode("utf-8")
            payload = json.loads(raw_data)
        except Exception as e:
            logger.error(f"[PubSub] Payload invalide: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid Pub/Sub payload: {e}")

        google_file_id = payload.get("google_file_id", "")
        url = payload.get("url", "")
        source_tag = payload.get("source_tag", "")
        folder_name = payload.get("folder_name", "")
        google_access_token = payload.get("google_access_token")
        file_type = payload.get("file_type",
                                "google_doc")  # "google_doc" | "docx"
        # Production: OIDC ID Token Google (RS256, 1h)
        oidc_token = payload.get("oidc_token", "")
        # Local dev: MOCK_M2M_JWT fallback
        jwt = payload.get("jwt", "")
        action = payload.get("action", "upsert")

        if not url or not google_file_id:
            logger.error(
                "[PubSub] Payload incomplet (url ou google_file_id manquant)")
            raise HTTPException(status_code=400, detail="Payload incomplet")

        # ── Fix #4 : Échange du token OIDC Google → JWT applicatif frais ─────
        # En production, drive_api embarque un OIDC ID Token (validité 1h) dans le message Pub/Sub
        # à la place du JWT applicatif HS256 qui expirait pendant le backoff Pub/Sub (30s→600s).
        # Le worker échange le token OIDC ici, au moment réel du traitement,
        # pour un JWT frais.
        if oidc_token:
            try:
                async with httpx.AsyncClient(timeout=10.0) as oidc_client:
                    oidc_res = await oidc_client.post(
                        f"{USERS_API_URL.rstrip('/')}/service-account/login",
                        json={"id_token": oidc_token},
                    )
                    if oidc_res.status_code == 200:
                        jwt = oidc_res.json().get("access_token", "")
                        logger.info(
                            "[PubSub] OIDC token échangé → JWT applicatif frais obtenu.")
                    else:
                        logger.error(
                            f"[PubSub] Échange OIDC échoué (HTTP {
                                oidc_res.status_code}) — retry Pub/Sub.")
                        raise HTTPException(
                            status_code=500,
                            detail=f"OIDC exchange failed: HTTP {
                                oidc_res.status_code}")
            except HTTPException:
                raise
            except Exception as e_oidc:
                logger.error(
                    f"[PubSub] Impossible d'échanger l'OIDC token: {e_oidc}")
                raise HTTPException(
                    status_code=500,
                    detail=f"OIDC exchange error: {e_oidc}")

            # ── Upgrade vers un service-token longue durée (90 min) ──────────
            # Le JWT issu de service-account/login n'a que 15 min (ACCESS_TOKEN_EXPIRE_MINUTES).
            # Le traitement Gemini + compétences + missions peut dépasser ce délai → 403 sur items_api.
            # On échange vers /internal/service-token qui délivre un token de
            # 90 min.
            if jwt:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as svc_client:
                        svc_res = await svc_client.post(
                            f"{USERS_API_URL.rstrip('/')}/internal/service-token",
                            headers={"Authorization": f"Bearer {jwt}"},
                        )
                        if svc_res.status_code == 200:
                            jwt = svc_res.json().get("access_token", jwt)
                            logger.info(
                                "[PubSub] Service-token longue durée obtenu (90 min).")
                        else:
                            logger.warning(
                                f"[PubSub] Upgrade service-token échoué (HTTP {
                                    svc_res.status_code}) — JWT court conservé (15 min).")
                except Exception as e_svc:
                    logger.warning(
                        f"[PubSub] Impossible d'obtenir le service-token longue durée: {e_svc} — JWT court conservé.")

        if not jwt:
            logger.error(
                "[PubSub] Aucun token d'authentification dans le payload (ni oidc_token, ni jwt).")
            raise HTTPException(
                status_code=500,
                detail="Configuration error: aucun token dans le message Pub/Sub")

        headers = {"Authorization": f"Bearer {jwt}"}
        inject(headers)
        logger.info(f"[PubSub] Traitement de {google_file_id} ({url})")

        drive_api_url = os.getenv("DRIVE_API_URL", "http://drive_api:8006")
        try:
            async with httpx.AsyncClient(timeout=10.0) as patch_client:
                res = await patch_client.patch(
                    f"{drive_api_url.rstrip('/')}/files/{google_file_id}",
                    json={"status": "PROCESSING"},
                    headers=headers
                )
                if res.is_error:
                    logger.error(
                        f"[PubSub] Échec PATCH PROCESSING vers drive_api: HTTP {res.status_code} - {res.text}")
        except Exception as e:
            logger.warning(
                f"[PubSub] Impossible de notifier drive_api (PROCESSING): {e}")

        # ── 4. Décoder le JWT applicatif pour obtenir token_payload compatible ────
        # Le JWT a été obtenu via échange OIDC (prod) ou MOCK_M2M_JWT (local).
        # Il est nécessaire pour que process_cv_core puisse appeler les services internes
        # (users_api, competencies_api, missions_api) avec une identité valide.
        # _AUTH_SECRET_KEY est la constante chargée au démarrage par src.auth
        # (avant purge env)
        if not _AUTH_SECRET_KEY:
            logger.error(
                "[PubSub] SECRET_KEY absente — impossible de valider le JWT interne.")
            raise HTTPException(
                status_code=500,
                detail="Configuration error: SECRET_KEY manquante")
        try:
            token_payload = jose_jwt.decode(
                jwt, _AUTH_SECRET_KEY, algorithms=["HS256"])
        except JWTError as e:
            logger.error(
                f"[PubSub] JWT interne invalide (corrompu ou expiré): {e}")
            raise HTTPException(
                status_code=500,
                detail=f"JWT interne invalide: {e}")

        # Lancement du pipeline en arrière-plan
        try:
            if action == "delete":
                background_tasks.add_task(
                    PubsubService._run_cv_delete_bg,
                    url, google_file_id, jwt, drive_api_url, headers
                )
            else:
                background_tasks.add_task(
                    PubsubService._run_cv_pipeline_bg,
                    google_file_id, url, google_access_token, source_tag, folder_name,
                    headers, jwt, token_payload, drive_api_url,
                    file_type,
                )
        except Exception as e:
            logger.error(
                f"[PubSub] Erreur au lancement de la tâche de fond: {e}")
            try:
                async with httpx.AsyncClient(timeout=10.0) as patch_client:
                    await patch_client.patch(
                        f"{drive_api_url.rstrip('/')}/files/{google_file_id}",
                        json={
                            "status": "ERROR",
                            "error_message": f"Erreur de setup pipeline: {e}"},
                        headers=headers
                    )
            except Exception:
                pass

        return {"status": "accepted"}
