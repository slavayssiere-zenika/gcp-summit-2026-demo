"""taxonomy_batch_service.py — Orchestrateur asynchrone pour le recalcul batch de la taxonomie."""
import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timezone

import httpx
from google.cloud import storage as gcs_storage
from google.genai import types

import src.services.config as _svc_config
from src.cvs.routers._shared import BATCH_GCS_BUCKET
from src.cvs.task_state import tree_task_manager
from src.services.finops import log_finops
from src.services.taxonomy_service import fetch_prompt as _fetch_prompt
from src.services.taxonomy_service import get_existing_competencies as _get_existing_competencies
from src.gemini_retry import generate_content_with_retry

logger = logging.getLogger(__name__)


class TaxonomyBatchService:
    @staticmethod
    async def generate_autonomous_service_token() -> str:
        """
        Génère un service_token de 90 minutes de manière autonome en utilisant
        l'identité propre du microservice cv_api (OIDC ID Token → JWT court → JWT 90min).
        Cela garantit que les jobs batch peuvent se poursuivre même s'ils sont réveillés
        par Cloud Scheduler (qui n'a pas de claim 'role') ou si le token du caller expire.
        """
        try:
            import google.auth.transport.requests as google_requests
            from google.oauth2 import id_token as sa_id_token

            is_local = os.getenv("USE_IAM_AUTH", "false").lower() != "true"
            users_api_url = os.getenv("USERS_API_URL", "http://users_api:8000")

            short_jwt = ""
            if is_local:
                short_jwt = os.getenv("MOCK_M2M_JWT", "")
            else:
                try:
                    req = google_requests.Request()
                    oidc_token = sa_id_token.fetch_id_token(req, users_api_url)
                    async with httpx.AsyncClient(timeout=10.0) as hc:
                        res = await hc.post(
                            f"{users_api_url.rstrip('/')}/service-account/login",
                            json={"id_token": oidc_token}
                        )
                        if res.status_code == 200:
                            short_jwt = res.json().get("access_token", "")
                except Exception as e:
                    logger.warning(
                        f"[batch-auth] Impossible de générer le JWT court OIDC: {e}")

            if short_jwt:
                async with httpx.AsyncClient(timeout=10.0) as hc:
                    res2 = await hc.post(
                        f"{users_api_url.rstrip('/')}/internal/service-token",
                        headers={"Authorization": f"Bearer {short_jwt}"}
                    )
                    if res2.status_code == 200:
                        return res2.json().get("access_token", "")
        except Exception as e:
            logger.error(
                f"[batch-auth] Erreur fatale génération token autonome: {e}")
        return ""

    @staticmethod
    async def start_batch(auth_header: str) -> dict:
        latest_status = await tree_task_manager.get_latest_status()
        if latest_status and latest_status.get(
                "status") == "running" and latest_status.get("batch_job_id"):
            job_id_check = latest_status.get("batch_job_id")
            try:
                live_job = await asyncio.to_thread(_svc_config.vertex_batch_client.batches.get, name=job_id_check)
                live_state = live_job.state.name if hasattr(
                    live_job.state, "name") else str(live_job.state)
                if live_state in ("JOB_STATE_RUNNING",
                                  "JOB_STATE_PENDING", "JOB_STATE_QUEUED"):
                    return {
                        "success": False, "message": f"Batch déjà en cours ({live_state}). Attendez la fin ou annulez."}
                logger.info(
                    f"[batch-start] Job {job_id_check} déjà terminé ({live_state}) mais Redis bloqué — déblocage automatique.")
            except Exception as e_check:
                logger.warning(
                    f"[batch-start] Impossible de vérifier l'état Vertex AI : {e_check} — blocage conservateur.")
                return {
                    "success": False, "message": "Batch en cours (impossible de vérifier Vertex AI). Utilisez 'Réinitialiser' si bloqué."}

        await tree_task_manager.initialize_task()
        await tree_task_manager.update_progress(batch_step="map", new_log="Démarrage du processus Batch (Map)...")

        auth_token = auth_header.replace(
            "Bearer ", "") if auth_header and "Bearer " in auth_header else auth_header
        start_service_token = auth_token
        fresh_start = await TaxonomyBatchService.generate_autonomous_service_token()
        if fresh_start:
            start_service_token = fresh_start
            logger.info(
                "[batch-start] Service token autonome (90 min) stocké en Redis.")
        else:
            logger.warning(
                "[batch-start] Échec génération token autonome — fallback sur le JWT court.")
        await tree_task_manager.update_progress(service_token=start_service_token)

        await tree_task_manager.update_progress(new_log="Nettoyage des compétences orphelines en cours...")
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
                headers = {"Authorization": f"Bearer {start_service_token}"}
                from opentelemetry.propagate import inject
                inject(headers)
                res = await client.post(f"{_svc_config.COMPETENCIES_API_URL.rstrip('/')}/bulk/cleanup-orphans", headers=headers)
                res.raise_for_status()
                data = res.json()
                deleted_count = data.get("deleted_count", 0)
                await tree_task_manager.update_progress(new_log=f"Nettoyage terminé : {deleted_count} compétence(s) orpheline(s) supprimée(s).")
        except Exception as e:
            logger.warning(
                f"[batch-start] Échec du nettoyage des orphelines: {e}")
            error_msg = f"Échec du nettoyage des orphelines: {str(e)}"
            await tree_task_manager.update_progress(status="error", error=error_msg)
            return {"success": False, "error": error_msg}

        existing_names = await _get_existing_competencies(f"Bearer {start_service_token}")
        logger.info(
            f"[batch-start] {len(existing_names)} compétences récupérées pour le Map.")
        if not existing_names:
            error_msg = "Aucune compétence trouvée dans competencies_api. Vérifiez que l'API est démarrée et que des compétences existent en base avant de lancer le batch."
            await tree_task_manager.update_progress(status="error", error=error_msg)
            return {"success": False, "error": error_msg}

        try:
            instruction_map = await _fetch_prompt("cv_api.generate_taxonomy_tree_map", f"Bearer {start_service_token}")
        except RuntimeError as e:
            await tree_task_manager.update_progress(status="error", error=str(e))
            return {"success": False, "error": str(e)}

        chunk_size = 500
        existing_names_chunks = [existing_names[i:i + chunk_size]
                                 for i in range(0, len(existing_names), chunk_size)]

        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".jsonl") as f:
            for i, chunk in enumerate(existing_names_chunks):
                skills_str = ", ".join(chunk)
                map_instruction = instruction_map.replace(
                    "{{EXISTING_COMPETENCIES}}", skills_str)
                req = {
                    "id": f"chunk-{i}",
                    "request": {
                        "contents": [{"role": "user", "parts": [{"text": map_instruction}]}],
                        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
                    }
                }
                f.write(json.dumps(req) + "\n")
            temp_path = f.name

        try:
            if not _svc_config.vertex_batch_client:
                raise ValueError(
                    "Vertex AI _svc_config.client non initialisé (GCP_PROJECT_ID ou VERTEX_LOCATION manquant).")
            if not BATCH_GCS_BUCKET:
                raise ValueError("BATCH_GCS_BUCKET non configuré.")

            gcs_client = gcs_storage.Client()
            timestamp = int(datetime.now(timezone.utc).timestamp())
            blob_name = f"taxonomy/input/map-{timestamp}.jsonl"
            bucket = gcs_client.bucket(BATCH_GCS_BUCKET)
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(
                temp_path, content_type="application/jsonl")
            src_uri = f"gs://{BATCH_GCS_BUCKET}/{blob_name}"
            dest_uri = f"gs://{BATCH_GCS_BUCKET}/taxonomy/output/map-{timestamp}/"

            batch_job = await asyncio.to_thread(
                _svc_config.vertex_batch_client.batches.create,
                model=os.environ["GEMINI_PRO_MODEL"],
                src=src_uri,
                config={"display_name": "taxonomy-map-batch", "dest": dest_uri}
            )
            await tree_task_manager.update_progress(batch_job_id=batch_job.name, batch_step="map", new_log=f"Job Batch Map créé (ID: {batch_job.name}). En attente de Vertex AI...")
            os.unlink(temp_path)
            return {"success": True, "batch_job_id": batch_job.name}
        except Exception as e:
            logger.error(f"Erreur création batch Map: {e}")
            await tree_task_manager.update_progress(status="error", error=str(e))
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return {"success": False, "error": str(e)}

    @staticmethod
    async def check_batch(auth_header: str, user_caller: str) -> dict:
        auth_token = auth_header.replace(
            "Bearer ", "") if auth_header and "Bearer " in auth_header else auth_header

        latest_status = await tree_task_manager.get_latest_status()
        if not latest_status or latest_status.get("status") not in (
                "running", "batch_running") or not latest_status.get("batch_job_id"):
            return {"success": True, "message": "Aucun batch en cours"}

        batch_job_id = latest_status.get("batch_job_id")
        batch_step = latest_status.get("batch_step")

        if not batch_job_id.startswith("projects/"):
            batch_job_id = f"projects/{
                _svc_config.GCP_PROJECT_ID}/locations/europe-west1/batchPredictionJobs/{batch_job_id}"

        if batch_step in ("deduplicating", "sweeping"):
            logger.info(
                f"[batch-check] Phase intermédiaire '{batch_step}' en cours — pas de polling Vertex AI.")
            return {
                "success": True,
                "state": batch_step.upper(),
                "message": f"Traitement {batch_step} en cours (tâche de fond LLM)...",
            }

        persisted_svc_token = latest_status.get("service_token") or auth_token
        if not latest_status.get("service_token"):
            logger.warning(
                "[batch-check] service_token absent du state Redis — tentative de ré-acquisition via identité autonome.")
            try:
                fresh = await TaxonomyBatchService.generate_autonomous_service_token()
                if fresh:
                    persisted_svc_token = fresh
                    await tree_task_manager.update_progress(service_token=fresh)
            except Exception as e_compat:
                logger.warning(
                    f"[batch-check] Ré-acquisition autonome échouée: {e_compat}")

        try:
            batch_job = await asyncio.to_thread(_svc_config.vertex_batch_client.batches.get, name=batch_job_id)
            if batch_job.state.name != "JOB_STATE_SUCCEEDED":
                if batch_job.state.name == "JOB_STATE_FAILED":
                    try:
                        await asyncio.to_thread(_svc_config.vertex_batch_client.batches.delete, name=batch_job_id)
                    except Exception as e:
                        logger.error(
                            f"Impossible de supprimer le batch échoué: {e}")

                    error_msg = f"Le job Batch a échoué côté GCP (Status: {
                        batch_job.state.name})"
                    await tree_task_manager.update_progress(status="error", error=error_msg)
                    return {"success": False, "error": error_msg}

                if batch_job.state.name == "JOB_STATE_PENDING":
                    timeout_hours = float(os.environ.get(
                        "BATCH_PENDING_TIMEOUT_HOURS", "3"))
                    create_time = getattr(batch_job, "create_time", None)
                    if create_time:
                        elapsed_hours = (
                            datetime.now(
                                timezone.utc) - create_time).total_seconds() / 3600
                        if elapsed_hours >= timeout_hours:
                            logger.warning(
                                f"[batch-check] Batch {batch_job_id} bloqué en PENDING depuis {
                                    elapsed_hours:.1f}h (seuil={timeout_hours}h) — cancel + restart automatique.")
                            try:
                                await asyncio.to_thread(_svc_config.vertex_batch_client.batches.cancel, name=batch_job_id)
                            except Exception as e_cancel:
                                logger.warning(
                                    f"[batch-check] Impossible d'annuler le batch: {e_cancel}")
                            await tree_task_manager.update_progress(
                                status="error",
                                error=f"Batch {batch_job_id} annulé automatiquement après {
                                    elapsed_hours:.1f}h en PENDING. Un nouveau batch sera déclenché."
                            )
                            return {
                                "success": True,
                                "action": "auto_restart",
                                "message": f"Batch annulé après {elapsed_hours:.1f}h — prochain trigger relancera le pipeline.",
                            }

                progress_data = {}
                cs = getattr(batch_job, "completion_stats", None)
                if cs:
                    successful = int(
                        getattr(
                            cs,
                            "success_count",
                            None) or getattr(
                            cs,
                            "successful_count",
                            0) or 0)
                    failed = int(
                        getattr(
                            cs,
                            "failed_count",
                            None) or getattr(
                            cs,
                            "error_count",
                            0) or 0)
                    incomplete = int(getattr(cs, "incomplete_count", 0) or 0)
                    total = int(
                        getattr(
                            cs,
                            "total_count",
                            None) or 0) or (
                        successful +
                        failed +
                        incomplete)
                    progress_data = {
                        "completed": successful,
                        "total": total,
                        "failed": failed,
                        "percent": int((successful / total) * 100) if total > 0 else 0
                    }

                elapsed_info = ""
                if getattr(batch_job, "create_time", None):
                    elapsed_s = (
                        datetime.now(
                            timezone.utc) -
                        batch_job.create_time).total_seconds()
                    elapsed_info = f"{int(elapsed_s //
                                          3600)}h{int((elapsed_s %
                                                       3600) //
                                                      60)}m"

                return {
                    "success": True,
                    "state": batch_job.state.name,
                    "step": batch_step,
                    "progress": progress_data,
                    "elapsed": elapsed_info
                }

            dest_obj = batch_job.dest
            if not dest_obj or not dest_obj.gcs_uri:
                raise ValueError(
                    "batch_job.dest.gcs_uri est vide — le résultat n'est pas encore disponible.")

            dest_uri = dest_obj.gcs_uri
            gcs_dest = dest_uri.replace(f"gs://{BATCH_GCS_BUCKET}/", "")
            gcs_client = gcs_storage.Client()
            output_bucket = gcs_client.bucket(BATCH_GCS_BUCKET)
            blobs = list(output_bucket.list_blobs(prefix=gcs_dest))
            output_blob = next(
                (b for b in blobs if b.name.endswith(".jsonl")), None)
            if not output_blob:
                raise ValueError(
                    f"Aucun fichier .jsonl trouvé dans {dest_uri}")
            file_content = output_blob.download_as_text()

            total_prompt_tokens = 0
            total_candidates_tokens = 0
            parsed_results = []

            for line in file_content.splitlines():
                resp = json.loads(line)
                if "response" in resp and "usageMetadata" in resp["response"]:
                    total_prompt_tokens += resp["response"]["usageMetadata"].get(
                        "promptTokenCount", 0)
                    total_candidates_tokens += resp["response"]["usageMetadata"].get(
                        "candidatesTokenCount", 0)

                if "response" in resp and "candidates" in resp["response"] and len(
                        resp["response"]["candidates"]) > 0:
                    parts = resp["response"]["candidates"][0].get(
                        "content", {}).get("parts", [])
                    if parts:
                        parsed_results.append(parts[0].get("text", ""))

            usage = {"prompt_token_count": total_prompt_tokens,
                     "candidates_token_count": total_candidates_tokens}

            if batch_step == "map":
                await log_finops(user_caller, "recalculate_tree_batch_map", os.environ["GEMINI_MODEL"], usage, auth_token=auth_token)

                map_result = {}
                for i, text in enumerate(parsed_results):
                    try:
                        cleaned = text.strip()
                        if cleaned.startswith("```json"):
                            cleaned = cleaned[7:]
                        if cleaned.startswith("```"):
                            cleaned = cleaned[3:]
                        if cleaned.endswith("```"):
                            cleaned = cleaned[:-3]
                        cleaned = cleaned.strip()

                        raw_map, _ = json.JSONDecoder().raw_decode(cleaned)
                        if isinstance(raw_map, dict) and "items" in raw_map:
                            raw_map = raw_map["items"]
                        parsed_chunk = {}
                        if isinstance(raw_map, list):
                            for item in raw_map:
                                if isinstance(item, dict):
                                    parsed_chunk.update(item)
                        elif isinstance(raw_map, dict):
                            parsed_chunk.update(raw_map)

                        for pillar, skills in parsed_chunk.items():
                            if not isinstance(skills, list):
                                continue
                            if pillar not in map_result:
                                map_result[pillar] = []
                            map_result[pillar].extend(skills)
                    except Exception as e:
                        logger.error(
                            f"Erreur de parsing sur le chunk {i} du Map (ignoré): {e}")
                        continue

                if not map_result:
                    return {
                        "success": False, "error": "Aucun chunk JSONL n'a pu être parsé correctement."}

                await tree_task_manager.update_progress(map_result=map_result, batch_step="deduplicating", new_log="Map Batch terminé. Exécution de Deduplicate...")

                fresh = await TaxonomyBatchService.generate_autonomous_service_token()
                dedup_service_token = fresh if fresh else persisted_svc_token
                if fresh:
                    await tree_task_manager.update_progress(service_token=fresh)

                async def run_dedup(svc_token: str = dedup_service_token):
                    _svc_auth_header = f"Bearer {svc_token}"
                    try:
                        instruction_dedup = await _fetch_prompt("cv_api.generate_taxonomy_tree_deduplicate", _svc_auth_header)
                        map_json_str = json.dumps(
                            map_result, ensure_ascii=False)
                        dedup_instruction = instruction_dedup.replace(
                            "{{MAP_RESULT}}", map_json_str)

                        response_dedup = await generate_content_with_retry(
                            _svc_config.client,
                            model=os.environ["GEMINI_PRO_MODEL"],
                            contents=[dedup_instruction],
                            config=types.GenerateContentConfig(
                                temperature=0.1,
                                response_mime_type="application/json",
                                max_output_tokens=65536,
                            )
                        )
                        await log_finops(user_caller, "recalculate_tree_batch_dedup", os.environ["GEMINI_PRO_MODEL"], response_dedup.usage_metadata, auth_token=svc_token)

                        finish_reason = None
                        if response_dedup.candidates:
                            finish_reason = str(
                                getattr(
                                    response_dedup.candidates[0],
                                    "finish_reason",
                                    "")).upper()
                        if finish_reason and "MAX_TOKEN" in finish_reason:
                            raise ValueError(
                                f"La réponse Deduplicate a été tronquée par le LLM (finish_reason={finish_reason}). "
                                "Augmentez max_output_tokens ou réduisez le prompt."
                            )

                        cleaned = response_dedup.text.strip()
                        if cleaned.startswith("```json"):
                            cleaned = cleaned[7:]
                        if cleaned.startswith("```"):
                            cleaned = cleaned[3:]
                        if cleaned.endswith("```"):
                            cleaned = cleaned[:-3]
                        cleaned = cleaned.strip()
                        try:
                            raw_dedup, _ = json.JSONDecoder().raw_decode(cleaned)
                        except json.JSONDecodeError as json_err:
                            raise ValueError(
                                f"Erreur Deduplicate: {json_err} — "
                                f"Réponse LLM (premiers 500 chars): {cleaned[:500]!r}"
                            )

                        pillars_list = []
                        if isinstance(raw_dedup, list):
                            pillars_list = raw_dedup
                        elif isinstance(raw_dedup, dict):
                            if "pillars" in raw_dedup:
                                pillars_list = raw_dedup["pillars"]
                            else:
                                pillars_list = list(raw_dedup.keys())

                        completed_pillars = []
                        for p in pillars_list:
                            if isinstance(p, dict) and "name" in p:
                                completed_pillars.append(p)
                            elif isinstance(p, str):
                                completed_pillars.append(
                                    {"name": p, "description": ""})

                        if not completed_pillars:
                            raise ValueError(
                                f"Le LLM a retourné un résultat vide ou non reconnu pour la déduplication : {
                                    str(raw_dedup)[
                                        :200]}")

                        await tree_task_manager.update_progress(completed_pillars=completed_pillars, new_log="Deduplicate terminé. Lancement du Batch Reduce...")

                        instruction_reduce = await _fetch_prompt("cv_api.generate_taxonomy_tree_reduce", _svc_auth_header)

                        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".jsonl") as f:
                            for i, p in enumerate(completed_pillars):
                                p_name = p.get("name", "")
                                reduce_prompt = instruction_reduce.replace(
                                    "{{CURRENT_PILLAR}}", p_name).replace(
                                    "{{MAP_RESULT}}", map_json_str)
                                req = {
                                    "id": f"pillar-{i}",
                                    "request": {
                                        "contents": [{"role": "user", "parts": [{"text": reduce_prompt}]}],
                                        "generationConfig": {
                                            "temperature": 0.1,
                                            "responseMimeType": "application/json",
                                            "maxOutputTokens": 65536
                                        }
                                    }
                                }
                                f.write(json.dumps(req) + "\n")
                            temp_path = f.name

                        gcs_client_reduce = gcs_storage.Client()
                        ts_reduce = int(datetime.now(timezone.utc).timestamp())
                        blob_reduce_name = f"taxonomy/input/reduce-{ts_reduce}.jsonl"
                        reduce_bucket = gcs_client_reduce.bucket(
                            BATCH_GCS_BUCKET)
                        blob_reduce = reduce_bucket.blob(blob_reduce_name)
                        blob_reduce.upload_from_filename(
                            temp_path, content_type="application/jsonl")
                        src_reduce_uri = f"gs://{BATCH_GCS_BUCKET}/{blob_reduce_name}"
                        dest_reduce_uri = f"gs://{BATCH_GCS_BUCKET}/taxonomy/output/reduce-{ts_reduce}/"

                        reduce_batch_job = await asyncio.to_thread(
                            _svc_config.vertex_batch_client.batches.create,
                            model=os.environ["GEMINI_PRO_MODEL"],
                            src=src_reduce_uri,
                            config={
                                "display_name": "taxonomy-reduce-batch",
                                "dest": dest_reduce_uri}
                        )
                        await tree_task_manager.update_progress(batch_job_id=reduce_batch_job.name, batch_step="reduce", new_log=f"Job Batch Reduce créé (ID: {reduce_batch_job.name}). En attente Vertex AI...")
                        os.unlink(temp_path)
                    except Exception as e:
                        logger.error(f"Erreur background dedup: {e}")
                        await tree_task_manager.update_progress(status="error", error=f"Erreur Deduplicate: {str(e)}")

                asyncio.create_task(run_dedup())
                return {"success": True, "state": "PROCESSING_DEDUP"}

            elif batch_step == "reduce":
                await log_finops(user_caller, "recalculate_tree_batch_reduce", os.environ["GEMINI_PRO_MODEL"], usage, auth_token=auth_token)

                res_tree = {}
                for i, text in enumerate(parsed_results):
                    try:
                        cleaned = text.strip()
                        if cleaned.startswith("```json"):
                            cleaned = cleaned[7:]
                        if cleaned.startswith("```"):
                            cleaned = cleaned[3:]
                        if cleaned.endswith("```"):
                            cleaned = cleaned[:-3]
                        cleaned = cleaned.strip()

                        import json_repair

                        raw_res = json_repair.loads(cleaned)
                        if isinstance(raw_res, dict):
                            res_tree.update(raw_res)
                    except Exception as e:
                        snippet = cleaned[-100:] if len(
                            cleaned) > 100 else cleaned
                        error_msg = f"Erreur JSON Reduce: {e}. Extrait: {snippet}"
                        logger.error(error_msg)
                        await tree_task_manager.update_progress(status="error", error=error_msg)
                        return {"success": False, "error": error_msg}
                if not res_tree:
                    return {
                        "success": False, "error": "Aucun chunk JSONL du Reduce n'a pu être parsé."}

                expected_pillars = latest_status.get("completed_pillars", [])
                expected_names = {p.get("name")
                                  for p in expected_pillars if p.get("name")}
                actual_names = set(res_tree.keys())

                import re

                def normalize(n): return re.sub(
                    r'[^a-z0-9]', '', (n or '').lower().replace('&', 'et'))

                expected_norm = {normalize(n): n for n in expected_names}
                actual_norm = {normalize(n): n for n in actual_names}
                missing_norm = set(expected_norm.keys()) - \
                    set(actual_norm.keys())

                if missing_norm:
                    missing_original = [expected_norm[k] for k in missing_norm]
                    error_msg = f"Reduce incomplet : les piliers suivants manquent dans la réponse Vertex AI: {
                        ', '.join(missing_original)}. Trouvés : {
                        ', '.join(actual_names)}"
                    await tree_task_manager.update_progress(status="error", error=error_msg)
                    return {"success": False, "error": error_msg}

                await tree_task_manager.update_progress(res_tree=res_tree, batch_step="sweeping", new_log="Reduce Batch terminé. Exécution de Sweep...")

                if "{{CURRENT_PILLAR}}" in res_tree or "{{PILLAR_NAME}}" in res_tree:
                    error_msg = (
                        "res_tree corrompu : la clef '{{CURRENT_PILLAR}}' est présente, "
                        "le prompt Reduce n'a pas substitué le placeholder. "
                        "Relancez un nouveau batch depuis zéro (Recover ne suffit pas)."
                    )
                    await tree_task_manager.update_progress(status="error", error=error_msg)
                    return {"success": False, "error": error_msg}

                fresh = await TaxonomyBatchService.generate_autonomous_service_token()
                sweep_service_token = fresh if fresh else persisted_svc_token
                if fresh:
                    await tree_task_manager.update_progress(service_token=fresh)

                try:
                    instruction_sweep = await _fetch_prompt("cv_api.generate_taxonomy_tree_sweep", f"Bearer {sweep_service_token}")
                    existing_names = await _get_existing_competencies(f"Bearer {sweep_service_token}")

                    def get_all_used_names(node, used=None):
                        if used is None:
                            used = set()
                        if isinstance(node, dict):
                            if "name" in node:
                                used.add(node["name"])
                            if "merge_from" in node and isinstance(
                                    node["merge_from"], list):
                                for m in node["merge_from"]:
                                    used.add(m)
                            for k, v in node.items():
                                if isinstance(k, str) and k not in (
                                        "sub", "sub_competencies", "description", "aliases", "name", "merge_from"):
                                    used.add(k)
                                if k not in ("description", "aliases"):
                                    get_all_used_names(v, used)
                        elif isinstance(node, list):
                            for item in node:
                                get_all_used_names(item, used)
                        elif isinstance(node, str):
                            used.add(node)
                        return used

                    used_names = get_all_used_names(res_tree)
                    missing = list(set(existing_names) - used_names)

                    if not missing:
                        await tree_task_manager.update_progress(sweep_result=[], missing_competencies=[], new_log="Aucune compétence manquante détectée. Application de l'arbre en DB...")

                        competencies_api_url = os.getenv(
                            "COMPETENCIES_API_URL", "http://competencies_api:8000")
                        apply_headers = {
                            "Authorization": f"Bearer {sweep_service_token}"}
                        from opentelemetry.propagate import inject
                        inject(apply_headers)
                        async with httpx.AsyncClient() as http_client:
                            res = await http_client.post(
                                f"{competencies_api_url}/bulk_tree",
                                json={
                                    "tree": res_tree,
                                    "sweep_assignments": [],
                                    "merges": []},
                                headers=apply_headers,
                                timeout=180.0
                            )
                            if res.status_code == 200:
                                await tree_task_manager.update_progress(status="completed", new_log="Taxonomie appliquée avec succès !")
                                return {"success": True, "state": "COMPLETED"}
                            else:
                                await tree_task_manager.update_progress(status="error", error=f"Erreur d'application: {res.text}")
                                return {
                                    "success": False, "error": f"Erreur d'application: {res.text}"}
                    else:
                        with tempfile.NamedTemporaryFile("w", delete=False) as f:
                            chunk_size = 150
                            for i in range(0, len(missing), chunk_size):
                                missing_chunk = missing[i:i + chunk_size]
                                sweep_instruction = instruction_sweep.replace(
                                    "{{MISSING_COMPETENCIES}}", ", ".join(missing_chunk)).replace(
                                    "{{RES_TREE}}", json.dumps(
                                        res_tree, ensure_ascii=False))
                                req = {
                                    "request": {
                                        "contents": [{"role": "user", "parts": [{"text": sweep_instruction}]}],
                                        "generationConfig": {
                                            "temperature": 0.1,
                                            "responseMimeType": "application/json",
                                            "maxOutputTokens": 8192,
                                            "responseSchema": {
                                                "type": "OBJECT",
                                                "properties": {
                                                    "merges": {
                                                        "type": "ARRAY",
                                                        "items": {
                                                            "type": "OBJECT",
                                                            "properties": {
                                                                "canonical": {"type": "STRING"},
                                                                "merge_from": {"type": "ARRAY", "items": {"type": "STRING"}}
                                                            },
                                                            "required": ["canonical", "merge_from"]
                                                        }
                                                    },
                                                    "assignments": {
                                                        "type": "ARRAY",
                                                        "items": {
                                                            "type": "OBJECT",
                                                            "properties": {
                                                                "competency": {"type": "STRING"},
                                                                "pillar": {"type": "STRING"}
                                                            },
                                                            "required": ["competency", "pillar"]
                                                        }
                                                    }
                                                },
                                                "required": ["merges", "assignments"]
                                            }
                                        }
                                    }
                                }
                                f.write(json.dumps(req) + "\n")
                            temp_path = f.name

                        gcs_client_sweep = gcs_storage.Client()
                        ts_sweep = int(datetime.now(timezone.utc).timestamp())
                        blob_sweep_name = f"taxonomy/input/sweep-{ts_sweep}.jsonl"
                        sweep_bucket = gcs_client_sweep.bucket(
                            BATCH_GCS_BUCKET)
                        blob_sweep = sweep_bucket.blob(blob_sweep_name)
                        blob_sweep.upload_from_filename(
                            temp_path, content_type="application/jsonl")
                        src_sweep_uri = f"gs://{BATCH_GCS_BUCKET}/{blob_sweep_name}"
                        dest_sweep_uri = f"gs://{BATCH_GCS_BUCKET}/taxonomy/output/sweep-{ts_sweep}/"

                        sweep_batch_job = await asyncio.to_thread(
                            _svc_config.vertex_batch_client.batches.create,
                            model=os.environ["GEMINI_PRO_MODEL"],
                            src=src_sweep_uri,
                            config={
                                "display_name": "taxonomy-sweep-batch",
                                "dest": dest_sweep_uri}
                        )
                        await tree_task_manager.update_progress(batch_job_id=sweep_batch_job.name, batch_step="sweep", missing_competencies=missing, new_log=f"Job Batch Sweep créé (ID: {sweep_batch_job.name}). En attente Vertex AI...")
                        os.unlink(temp_path)

                        return {"success": True, "state": "PROCESSING_SWEEP"}

                except Exception as e:
                    logger.error(f"Erreur de création Sweep Batch: {e}")
                    await tree_task_manager.update_progress(status="error", error=f"Erreur Sweep: {str(e)}")
                    return {"success": False, "error": str(e)}

            elif batch_step == "sweep":
                await log_finops(user_caller, "recalculate_tree_batch_sweep", os.environ["GEMINI_PRO_MODEL"], usage, auth_token=auth_token)

                try:
                    sweep_assignments = []
                    merges = []
                    for i, text in enumerate(parsed_results):
                        try:
                            cleaned = text.strip()
                            if cleaned.startswith("```json"):
                                cleaned = cleaned[7:]
                            if cleaned.startswith("```"):
                                cleaned = cleaned[3:]
                            if cleaned.endswith("```"):
                                cleaned = cleaned[:-3]
                            cleaned = cleaned.strip()

                            import json_repair
                            raw_res = json_repair.loads(cleaned)
                            if isinstance(raw_res, dict):
                                if "assignments" in raw_res:
                                    sweep_assignments.extend(
                                        raw_res["assignments"])
                                if "merges" in raw_res:
                                    merges.extend(raw_res["merges"])
                        except Exception as e:
                            logger.error(
                                f"Erreur de parsing sur le chunk {i} du Sweep (ignoré): {e}")

                    res_tree = latest_status.get("res_tree", {})
                    if not res_tree:
                        raise ValueError(
                            "L'arbre (res_tree) est manquant dans l'état de la tâche. Impossible d'appliquer la taxonomie.")

                    await tree_task_manager.update_progress(sweep_result=sweep_assignments, new_log=f"Sweep Batch terminé ({len(sweep_assignments)} assignations, {len(merges)} merges). Application en base de données...")

                    competencies_api_url = os.getenv(
                        "COMPETENCIES_API_URL", "http://competencies_api:8000")
                    apply_headers = {"Authorization": f"Bearer {auth_token}"}
                    from opentelemetry.propagate import inject
                    inject(apply_headers)

                    async with httpx.AsyncClient() as http_client:
                        res = await http_client.post(
                            f"{competencies_api_url}/bulk_tree",
                            json={
                                "tree": res_tree,
                                "sweep_assignments": sweep_assignments,
                                "merges": merges},
                            headers=apply_headers,
                            timeout=180.0
                        )
                        if res.status_code == 200:
                            await tree_task_manager.update_progress(status="completed", new_log="Taxonomie appliquée avec succès !")
                            return {"success": True, "state": "COMPLETED"}
                        else:
                            error_msg = f"Erreur d'application en base: {
                                res.text}"
                            logger.error(error_msg)
                            await tree_task_manager.update_progress(status="error", error=error_msg)
                            return {"success": False, "error": error_msg}

                except Exception as e:
                    logger.error(f"Erreur d'application du Sweep: {e}")
                    await tree_task_manager.update_progress(status="error", error=f"Erreur d'application: {str(e)}")
                    return {"success": False, "error": str(e)}

        except Exception as e:
            logger.error(
                f"Erreur inattendue dans le check batch: {e}",
                exc_info=True)
            await tree_task_manager.update_progress(status="error", error=str(e))
            return {"success": False, "error": str(e)}
