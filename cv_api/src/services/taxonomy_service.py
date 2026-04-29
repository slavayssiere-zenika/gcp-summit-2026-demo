"""
taxonomy_service.py — Orchestration LLM de l'arbre des compétences (recalculate_tree).

Ce module contient :
- fetch_prompt()               — Récupération de prompt depuis prompts_api avec fallback
- get_existing_competencies()  — Listing paginé depuis competencies_api
- run_taxonomy_step()          — Orchestration LLM Map/Dedup/Reduce/Sweep/Apply

Consommé par router.py pour les endpoints :
    POST /recalculate_tree/step
    POST /recalculate_tree
    GET  /recalculate_tree/status
"""

import asyncio
import json
import logging
import os
from typing import Any, Optional

import httpx
from opentelemetry.propagate import inject

import database
from src.cvs.models import CVProfile
from src.cvs.task_state import task_state_manager, tree_task_manager
from src.services.config import COMPETENCIES_API_URL, PROMPTS_API_URL
from src.services.finops import log_finops
from src.gemini_retry import generate_content_with_retry

logger = logging.getLogger(__name__)


async def fetch_prompt(prompt_name: str, fallback_file: str, auth_header: str) -> Optional[str]:
    """Récupère un prompt depuis prompts_api avec fallback fichier local.

    Args:
        prompt_name: Nom du prompt dans prompts_api (ex: "cv_api.generate_taxonomy_tree_map").
        fallback_file: Chemin vers le fichier texte de fallback local.
        auth_header: Header Authorization pour l'appel HTTP.

    Returns:
        Contenu du prompt, ou None si indisponible (prompts_api ET fichier local absents).
    """
    try:
        async with httpx.AsyncClient() as http_client:
            headers_downstream = {"Authorization": auth_header}
            res_prompt = await http_client.get(
                f"{PROMPTS_API_URL.rstrip('/')}/{prompt_name}",
                headers=headers_downstream,
                timeout=5.0,
            )
            res_prompt.raise_for_status()
            return res_prompt.json()["value"]
    except Exception as e:
        logger.warning(f"Prompt {prompt_name} indisponible (erreur: {e}). Fallback local.")
        if os.path.exists(fallback_file):
            with open(fallback_file, "r", encoding="utf-8") as f:
                return f.read()
        return None


async def get_existing_competencies(auth_header: str) -> list[str]:
    """Liste toutes les compétences depuis competencies_api (avec pagination).

    Enrichit la liste avec les compétences détectées dans les CVs en base
    pour alimenter le LLM avec le corpus complet.

    Args:
        auth_header: Header Authorization pour l'appel HTTP.

    Returns:
        Liste de noms de compétences (strings). Vide si l'API est indisponible.
    """
    from sqlalchemy.future import select as sa_select

    try:
        async with httpx.AsyncClient(timeout=45.0) as http_client:
            headers = {"Authorization": auth_header}
            inject(headers)
            all_comps = []
            skip = 0
            limit = 100

            while True:
                comp_res = await http_client.get(
                    f"{COMPETENCIES_API_URL.rstrip('/')}/",
                    params={"skip": skip, "limit": limit},
                    headers=headers,
                    timeout=10.0,
                )
                comp_res.raise_for_status()
                comp_data = comp_res.json()

                items = comp_data.get("items", []) if isinstance(comp_data, dict) else comp_data
                all_comps.extend(items)

                if isinstance(comp_data, dict) and "total" in comp_data:
                    if len(all_comps) >= comp_data["total"]:
                        break
                elif len(items) < limit:
                    break
                skip += limit

            def get_all_names(nodes: list) -> list[str]:
                names = []
                for n in nodes:
                    names.append(n["name"])
                    if "sub_competencies" in n and n["sub_competencies"]:
                        names.extend(get_all_names(n["sub_competencies"]))
                return names

            existing_names = get_all_names(all_comps)

            # Enrichissement avec les compétences détectées dans les CVs
            try:
                async for db_session in database.get_db():
                    profiles = (
                        await db_session.execute(sa_select(CVProfile))
                    ).scalars().all()
                    for p in profiles:
                        if p.competencies_keywords:
                            for k in p.competencies_keywords:
                                if k and isinstance(k, str):
                                    k = k.strip()
                                    if k and k not in existing_names:
                                        existing_names.append(k)
                    break
            except Exception as ex_cv:
                logger.warning(f"Impossible de récupérer les compétences des CV: {ex_cv}")

            return existing_names

    except Exception as e:
        logger.warning(f"Failed to fetch existing competencies: {e}", exc_info=True)
        return []


async def run_taxonomy_step(
    auth_header: str,
    user_caller: str,
    step: str,
    genai_client,
    target_pillar: Optional[str] = None,
) -> None:
    """Exécute une étape du pipeline de recalcul de l'arbre des compétences.

    Pipeline Map → Deduplicate → Reduce → Sweep → Apply.
    Chaque étape met à jour tree_task_manager (Redis) avec son statut.

    Args:
        auth_header: Header Authorization à propager aux APIs externes.
        user_caller: Identifiant de l'appelant (pour FinOps).
        step: Nom de l'étape : "map", "deduplicate", "reduce", "sweep", "apply".
        genai_client: Client GenAI initialisé.
        target_pillar: Pilier ciblé pour l'étape "reduce" (None = tous).
    """
    from google.genai import types

    try:
        if not genai_client:
            await tree_task_manager.update_progress(
                error="Gemini SDK non configuré.", status="error"
            )
            return

        latest_status = await tree_task_manager.get_latest_status()
        if not latest_status:
            latest_status = await tree_task_manager.initialize_task()

        map_result = latest_status.get("map_result")
        res_tree = latest_status.get("res_tree", {})
        completed_pillars = latest_status.get("completed_pillars", [])
        sweep_result = latest_status.get("sweep_result")

        auth_token = (
            auth_header.replace("Bearer ", "")
            if auth_header and "Bearer " in auth_header
            else auth_header
        )

        # ── Étape MAP ────────────────────────────────────────────────────────
        if step == "map":
            await tree_task_manager.update_progress(
                new_log="Étape 1a: Récupération des compétences existantes..."
            )
            existing_names = await get_existing_competencies(auth_header)

            await tree_task_manager.update_progress(
                new_log="Étape 1b: Catégorisation des compétences en grands piliers (Map)..."
            )
            instruction_map = await fetch_prompt(
                "cv_api.generate_taxonomy_tree_map",
                "cv_api.generate_taxonomy_tree_map.txt",
                auth_header,
            )
            if not instruction_map:
                await tree_task_manager.update_progress(
                    error="Prompt de map indisponible.", status="error"
                )
                return

            if not existing_names:
                existing_names = ["Aucune compétence existante"]

            chunk_size = 500
            existing_names_chunks = [
                existing_names[i: i + chunk_size]
                for i in range(0, len(existing_names), chunk_size)
            ]

            map_result = {}

            for i, chunk in enumerate(existing_names_chunks):
                if len(existing_names_chunks) > 1:
                    await tree_task_manager.update_progress(
                        new_log=(
                            f"Étape 1b: Catégorisation des compétences en grands piliers (Map) "
                            f"- Lot {i + 1}/{len(existing_names_chunks)}..."
                        )
                    )

                skills_str = ", ".join(chunk)
                map_instruction = instruction_map.replace("{{EXISTING_COMPETENCIES}}", skills_str)

                response_map = await generate_content_with_retry(
                    genai_client,
                    model=os.environ["GEMINI_MODEL"],
                    contents=[map_instruction],
                    config=types.GenerateContentConfig(
                        temperature=0.1, response_mime_type="application/json"
                    ),
                )

                await log_finops(
                    user_caller,
                    f"recalculate_tree_map_{i}",
                    os.environ["GEMINI_MODEL"],
                    response_map.usage_metadata,
                    auth_token=auth_token,
                )

                try:
                    raw_map = json.loads(response_map.text)
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
                    logger.warning(f"Erreur de parsing sur le lot {i + 1}: {e}")

            await tree_task_manager.update_progress(
                map_result=map_result,
                res_tree={},
                completed_pillars=[],
                sweep_result=None,
                status="waiting_for_user",
                new_log=f"Map terminé. {len(map_result.keys())} piliers générés. En attente de validation.",
            )

        # ── Étape DEDUPLICATE ────────────────────────────────────────────────
        elif step == "deduplicate":
            await tree_task_manager.update_progress(
                new_log="Étape 2: Déduplication des piliers..."
            )
            instruction_dedup = await fetch_prompt(
                "cv_api.generate_taxonomy_tree_deduplicate",
                "cv_api.generate_taxonomy_tree_deduplicate.txt",
                auth_header,
            )
            if not instruction_dedup:
                await tree_task_manager.update_progress(
                    error="Prompt de déduplication indisponible.", status="error"
                )
                return

            if not map_result:
                await tree_task_manager.update_progress(
                    error="Pas de map_result disponible pour la déduplication.", status="error"
                )
                return

            dedup_instruction = instruction_dedup.replace(
                "{{MAP_RESULT}}", json.dumps(map_result, ensure_ascii=False)
            )
            response_dedup = await generate_content_with_retry(
                genai_client,
                model=os.environ["GEMINI_MODEL"],
                contents=[dedup_instruction],
                config=types.GenerateContentConfig(
                    temperature=0.1, response_mime_type="application/json"
                ),
            )
            await log_finops(
                user_caller,
                "recalculate_tree_dedup",
                os.environ["GEMINI_MODEL"],
                response_dedup.usage_metadata,
                auth_token=auth_token,
            )

            raw_dedup = json.loads(response_dedup.text)
            if isinstance(raw_dedup, dict) and "items" in raw_dedup:
                raw_dedup = raw_dedup["items"]

            new_map_result = {}
            if isinstance(raw_dedup, list):
                for item in raw_dedup:
                    if isinstance(item, dict):
                        new_map_result.update(item)
            elif isinstance(raw_dedup, dict):
                new_map_result.update(raw_dedup)

            await tree_task_manager.update_progress(
                map_result=new_map_result,
                status="waiting_for_user",
                new_log="Déduplication terminée. En attente de validation.",
            )

        # ── Étape REDUCE ─────────────────────────────────────────────────────
        elif step == "reduce":
            if not map_result:
                await tree_task_manager.update_progress(
                    error="Pas de piliers disponibles. Exécutez l'étape map d'abord.",
                    status="error",
                )
                return

            instruction_reduce = await fetch_prompt(
                "cv_api.generate_taxonomy_tree_reduce",
                "cv_api.generate_taxonomy_tree_reduce.txt",
                auth_header,
            )

            pillars_to_process = [target_pillar] if target_pillar else map_result.keys()

            for pillar_name in pillars_to_process:
                if pillar_name not in map_result:
                    continue
                if pillar_name in completed_pillars and not target_pillar:
                    continue

                current_status = await tree_task_manager.get_latest_status()
                if current_status and current_status.get("status") in ["error", "cancelled"]:
                    logger.info("Processus Reduce interrompu par l'utilisateur.")
                    break

                pillar_skills = map_result[pillar_name]
                await tree_task_manager.update_progress(
                    new_log=f"Structuration du pilier : {pillar_name}..."
                )

                pillar_skills_str = ", ".join(pillar_skills)
                pillar_instruction = (
                    instruction_reduce
                    .replace("{{EXISTING_COMPETENCIES}}", pillar_skills_str)
                    .replace("{{CURRENT_PILLAR}}", pillar_name)
                )

                response_reduce = await generate_content_with_retry(
                    genai_client,
                    model=os.environ["GEMINI_PRO_MODEL"],
                    contents=[pillar_instruction],
                    config=types.GenerateContentConfig(
                        temperature=0.2, response_mime_type="application/json"
                    ),
                )
                await log_finops(
                    user_caller,
                    f"recalculate_tree_reduce_{pillar_name}",
                    os.environ["GEMINI_PRO_MODEL"],
                    response_reduce.usage_metadata,
                    auth_token=auth_token,
                )

                raw_reduce = json.loads(response_reduce.text)
                if isinstance(raw_reduce, dict) and "items" in raw_reduce:
                    raw_reduce = raw_reduce["items"]

                if isinstance(raw_reduce, list):
                    for item in raw_reduce:
                        if isinstance(item, dict):
                            res_tree.update(item)
                elif isinstance(raw_reduce, dict):
                    res_tree.update(raw_reduce)
                await tree_task_manager.update_progress(
                    res_tree=res_tree, completed_pillar=pillar_name
                )

            await tree_task_manager.update_progress(
                status="waiting_for_user",
                new_log="Étape Reduce terminée. En attente de validation.",
            )

        # ── Étape SWEEP ──────────────────────────────────────────────────────
        elif step == "sweep":
            await tree_task_manager.update_progress(
                new_log="Étape 4: Sweep (Rattrapage des compétences orphelines)..."
            )
            existing_names = await get_existing_competencies(auth_header)

            def get_all_used_names(node: Any, used: Optional[set] = None) -> set:
                if used is None:
                    used = set()
                if isinstance(node, dict):
                    if "name" in node:
                        used.add(node["name"])
                    if "merge_from" in node and isinstance(node["merge_from"], list):
                        for m in node["merge_from"]:
                            used.add(m)
                    for v in node.values():
                        if isinstance(v, (dict, list)):
                            get_all_used_names(v, used)
                elif isinstance(node, list):
                    for item in node:
                        get_all_used_names(item, used)
                return used

            used_names = get_all_used_names(res_tree)
            missing = list(set(existing_names) - used_names)

            await tree_task_manager.update_progress(missing_competencies=missing)

            if not missing:
                await tree_task_manager.update_progress(
                    sweep_result=[],
                    status="waiting_for_user",
                    new_log="Sweep terminé : Aucune compétence orpheline.",
                )
                return

            instruction_sweep = await fetch_prompt(
                "cv_api.generate_taxonomy_tree_sweep",
                "cv_api.generate_taxonomy_tree_sweep.txt",
                auth_header,
            )
            if not instruction_sweep:
                await tree_task_manager.update_progress(
                    error="Prompt de sweep indisponible.", status="error"
                )
                return

            sweep_instruction = (
                instruction_sweep
                .replace("{{MISSING_COMPETENCIES}}", ", ".join(missing))
                .replace("{{RES_TREE}}", json.dumps(res_tree, ensure_ascii=False))
            )

            response_sweep = await generate_content_with_retry(
                genai_client,
                model=os.environ["GEMINI_MODEL"],
                contents=[sweep_instruction],
                config=types.GenerateContentConfig(
                    temperature=0.1, response_mime_type="application/json"
                ),
            )
            await log_finops(
                user_caller,
                "recalculate_tree_sweep",
                os.environ["GEMINI_MODEL"],
                response_sweep.usage_metadata,
                auth_token=auth_token,
            )

            raw_sweep = json.loads(response_sweep.text)
            if isinstance(raw_sweep, dict) and "items" in raw_sweep:
                raw_sweep = raw_sweep["items"]

            sweep_res_list = []
            if isinstance(raw_sweep, list):
                sweep_res_list = raw_sweep
            elif isinstance(raw_sweep, dict):
                sweep_res_list = [raw_sweep]

            await tree_task_manager.update_progress(
                sweep_result=sweep_res_list,
                status="waiting_for_user",
                new_log=f"Sweep terminé. {len(sweep_res_list)} suggestions de rattrapage générées.",
            )

        # ── Étape APPLY ──────────────────────────────────────────────────────
        elif step == "apply":
            await tree_task_manager.update_progress(
                new_log="Assemblage et envoi de l'arbre final à competencies_api..."
            )

            def extract_merge_instructions(node: Any, merges: Optional[list] = None) -> list:
                if merges is None:
                    merges = []
                if isinstance(node, dict):
                    merge_from = node.get("merge_from", [])
                    name = node.get("name")
                    if name and merge_from:
                        merges.append({"canonical": name, "merge_from": merge_from})
                    for v in node.values():
                        if isinstance(v, (dict, list)):
                            extract_merge_instructions(v, merges)
                elif isinstance(node, list):
                    for item in node:
                        extract_merge_instructions(item, merges)
                return merges

            merge_instructions = extract_merge_instructions(res_tree)

            if sweep_result:
                for s in sweep_result:
                    name = s.get("name")
                    merge_from = s.get("merge_from", [])
                    if name and merge_from:
                        existing_merge = next(
                            (m for m in merge_instructions if m["canonical"] == name), None
                        )
                        if existing_merge:
                            existing_merge["merge_from"].extend(merge_from)
                        else:
                            merge_instructions.append({"canonical": name, "merge_from": merge_from})

            bulk_merge_result = []
            try:
                async with httpx.AsyncClient() as http_client:
                    bulk_headers = {"Authorization": auth_header}
                    inject(bulk_headers)
                    bulk_res = await http_client.post(
                        f"{COMPETENCIES_API_URL.rstrip('/')}/bulk_tree",
                        json={"tree": res_tree, "merges": merge_instructions},
                        headers=bulk_headers,
                        timeout=120.0,
                    )
                    if bulk_res.status_code == 200:
                        bulk_data = bulk_res.json()
                        bulk_merge_result = bulk_data.get("merges", [])
                        logger.info(
                            f"[recalculate_tree] bulk_tree appliqué avec succès. "
                            f"Fusions: {bulk_merge_result}"
                        )
                    else:
                        logger.warning(
                            f"[recalculate_tree] bulk_tree HTTP {bulk_res.status_code}: "
                            f"{bulk_res.text[:200]}"
                        )
            except Exception as e:
                logger.warning(
                    f"[recalculate_tree] Erreur lors de l'appel bulk_tree: {e}", exc_info=True
                )

            await tree_task_manager.update_progress(
                new_log=f"Terminé. {len(bulk_merge_result)} doublon(s) fusionné(s).",
                tree=res_tree,
                usage={"merges_applied": len(bulk_merge_result)},
                status="completed",
            )

    except Exception as e:
        await tree_task_manager.update_progress(error=f"Erreur: {str(e)}", status="error")
