#!/usr/bin/env python3
"""admin.py — Console d'administration Zenika Platform.

Usage:
  python3 scripts/admin.py status                  # Vue d'ensemble de tous les services
  python3 scripts/admin.py quality                 # Rapport data quality complet
  python3 scripts/admin.py cv <action>             # Pipeline CV (bulk/taxonomy/reindex)
  python3 scripts/admin.py scoring <action>        # Pipeline Scoring IA Vertex
  python3 scripts/admin.py drive <action>          # Drive / ingestion / DLQ
  python3 scripts/admin.py help                    # Aide complète

Actions CV:
  status          Statut du pipeline bulk reanalyse
  start           Lance la ré-analyse Vertex AI Batch (tous CVs)
  start --ids 1,2 Lance la ré-analyse pour des CVs spécifiques
  cancel          Annule le pipeline en cours (soft cancel, GCS préservé)
  reset           Reset complet de l'état Redis
  retry-apply     Rejoue la phase apply depuis les résultats GCS
  reindex         Ré-indexe les embeddings globaux
  reindex-chunks  Ré-indexe les chunks de missions RAG
  reindex-chunks --force  Force la re-création complète des chunks
  fix-low-quality Identifie les CVs sous le seuil d'extraction et les réimporte
  fix-low-quality --threshold 60   Seuil personnalisé (défaut: 75)
  fix-low-quality --yes            Sans confirmation interactive
  fix-low-quality --skip-scoring   Ne pas déclencher le scoring delta (étape 8)
  fix-low-quality --max-attempts N Limite de réessais avant exclusion (défaut: 3)
  fix-low-quality --reset-excluded Réintègre les CVs exclus par le circuit-breaker
  taxonomy-status Statut du pipeline taxonomie
  taxonomy-start  Lance le batch taxonomie (map→reduce→sweep)
  taxonomy-step <step>    Lance une étape manuelle (map/reduce/sweep/deduplicate)
  taxonomy-check  Avance la machine à états du batch taxonomie
  taxonomy-cancel Annule le batch en cours
  taxonomy-recover Récupère un batch bloqué en erreur
  taxonomy-reset  Reset forcé de l'état Redis du batch
  taxonomy-list   Liste l'historique des jobs batch GCP
  remediate       Remédiation des erreurs silencieuses legacy

Actions Scoring:
  status          Statut du pipeline scoring IA
  start           Lance le scoring delta (compétences sans score)
  start --full    Lance le scoring complet (re-score tout)
  start --force   Force le scoring de tous les consultants
  cancel          Annule et reset l'état du scoring
  resume          Reprend le scoring après scale-to-zero
  debug           Config debug Vertex Batch (diagnostique)

Actions Drive:
  status          Statut Drive (total, pending, erreurs)
  ingestion       KPIs d'ingestion et folder stats
  history         Historique des dernières ingestions
  retry           Retry des fichiers en erreur
  retry --force   Force le reset immédiat de tous les zombies
  purge-errors    Purge toutes les erreurs en IGNORED
  quality-gate    Quality gate batch (re-queue les CVs incomplets)
  dlq-status      Statut de la Dead Letter Queue Pub/Sub
  dlq-replay      Rejoue tous les messages de la DLQ
  sync            Déclenche une synchronisation Drive manuelle

Options:
  --env prd|uat|dev   Environnement cible (défaut: prd)
  --no-cache          Forcer un nouveau login JWT
"""

import argparse

import sys

from admin_helpers import (
    BOLD, GREEN, GREY, RED, RESET, YELLOW,
    api_delete, api_get, api_post, banner, err, get_jwt, grade_color,
    info, ok, print_bulk_status, print_data_quality, print_drive_status,
    print_kv, section, status_icon, warn, progress_bar,
)


# ── CMD: status global ────────────────────────────────────────────────────────

def cmd_status(args, token: str, base: str) -> None:
    banner("🔍 Vue d'ensemble — Zenika Platform")

    section("Pipeline CV (bulk-reanalyse)")
    data = api_get(base, "/api/cv/bulk-reanalyse/status", token)
    if data:
        s = data.get("status", "idle")
        print(f"  {status_icon(s)} {BOLD}{s}{RESET}")
        for k in ["total_cvs", "processed", "applied", "errors"]:
            if k in data:
                print_kv(k, data[k])
    else:
        warn("Non disponible")

    section("Pipeline Scoring IA")
    data = api_get(base, "/api/competencies/bulk-scoring-all/status", token)
    if data:
        s = data.get("status", "idle")
        print(f"  {status_icon(s)} {BOLD}{s}{RESET}")
        for k in ["total_users", "triggered", "success_count", "error_count"]:
            if k in data:
                print_kv(k, data[k])
    else:
        warn("Non disponible")

    section("Pipeline Taxonomie")
    data = api_get(base, "/api/cv/recalculate_tree/status", token)
    if data:
        s = data.get("status", "idle")
        step = data.get("batch_step", "")
        print(f"  {status_icon(s)} {BOLD}{s}{RESET}" + (f" [{step}]" if step else ""))
    else:
        warn("Non disponible")

    section("Drive / Ingestion")
    data = api_get(base, "/api/drive/status", token)
    if data:
        total = data.get("total_files_scanned", 0)
        imp = data.get("imported", 0)
        errs = data.get("errors", 0)
        pct = round(imp / total * 100, 1) if total else 0
        print(f"  {progress_bar(int(pct))}  ({imp}/{total})")
        if errs:
            print(f"  {RED}⚠️  {errs} erreurs{RESET}")
    else:
        warn("Non disponible")

    section("DLQ (Dead Letter Queue)")
    dlq = api_get(base, "/api/drive/dlq/status", token)
    if dlq:
        count = dlq.get("message_count", 0)
        icon = "🔴" if count > 0 else "✅"
        print(f"  {icon} {count} message(s) en attente")
    else:
        warn("Non disponible")

    section("Data Quality")
    dq = api_get(base, "/api/cv/bulk-reanalyse/data-quality", token)
    if dq:
        score = dq.get("score", 0)
        grade = dq.get("grade", "?")
        print(f"  Score : {BOLD}{score}/100{RESET}  {grade_color(grade)}  {progress_bar(score)}")
    else:
        warn("Non disponible")


# ── CMD: data quality ─────────────────────────────────────────────────────────

def cmd_quality(args, token: str, base: str) -> None:
    banner("📊 Rapport Data Quality")

    section("CV Pipeline — Data Quality")
    data = api_get(base, "/api/cv/bulk-reanalyse/data-quality", token)
    print_data_quality(data)

    section("Couverture Compétences")
    cov = api_get(base, "/api/competencies/stats/coverage", token)
    if cov:
        uwc = cov.get("users_with_competencies", 0)
        total = cov.get("total_users", uwc) or uwc
        pct = round(uwc / total * 100, 1) if total else 0
        print(f"\n  {progress_bar(int(pct))}  ({uwc}/{total} consultants)")
        print_kv("Avec compétences", uwc)
        print_kv("Total consultants", total)

    section("Scoring IA")
    stats = api_get(base, "/api/competencies/evaluations/scoring-stats", token)
    if stats:
        pct = stats.get("coverage_pct", 0)
        print(f"\n  {progress_bar(int(pct))}")
        print_kv("Users scorés ≥10", stats.get("users_with_min_scored", "?"))
        print_kv("Users total", stats.get("total_users_with_competencies", "?"))
        print_kv("Score moyen/user", stats.get("avg_scored_per_user", "?"))
        st = stats.get("status", "?")
        print_kv("Status", f"{status_icon(st)} {st}")

    section("Drive Ingestion")
    kpis = api_get(base, "/api/drive/ingestion/stats", token)
    if kpis:
        for k, v in kpis.items():
            if isinstance(v, (int, float, str)):
                print_kv(k, v)


# ── CMD: cv ───────────────────────────────────────────────────────────────────

def cmd_cv(args, token: str, base: str) -> None:
    action = args.action

    if action == "status":
        banner("🔄 CV Pipeline — Statut")
        data = api_get(base, "/api/cv/bulk-reanalyse/status", token)
        print_bulk_status(data or {"status": "idle"})

    elif action == "start":
        banner("🚀 CV Pipeline — Démarrage Bulk Reanalyse")
        cv_ids = None
        if args.ids:
            try:
                cv_ids = [int(x.strip()) for x in args.ids.split(",")]
                info(f"Mode ciblé : {len(cv_ids)} CVs")
            except ValueError:
                err("--ids invalide : utilisez des entiers séparés par virgules (ex: 1,2,3)")
                sys.exit(1)
        body = {"cv_ids": cv_ids} if cv_ids else {}
        data = api_post(base, "/api/cv/bulk-reanalyse/start", token, body)
        if data:
            ok(data.get("message", "Pipeline démarré."))
            print_kv("total_cvs", data.get("total_cvs"))
            print_kv("status", data.get("status"))

    elif action == "cancel":
        banner("🚫 CV Pipeline — Annulation")
        warn("Les résultats GCS seront préservés (retry-apply reste possible).")
        data = api_post(base, "/api/cv/bulk-reanalyse/cancel", token)
        if data:
            ok(data.get("message", "Annulé."))
            if data.get("can_retry_apply"):
                info("retry-apply disponible — les résultats GCS sont intacts.")

    elif action == "reset":
        banner("⚠️  CV Pipeline — Reset complet Redis")
        warn("Cette action supprime l'état Redis et le dest_uri GCS.")
        data = api_post(base, "/api/cv/bulk-reanalyse/reset", token)
        if data:
            ok(data.get("message", "Reset effectué."))

    elif action == "retry-apply":
        banner("📥 CV Pipeline — Retry Apply (depuis GCS)")
        data = api_post(base, "/api/cv/bulk-reanalyse/retry-apply", token)
        if data:
            ok(data.get("message", "Retry apply démarré."))
            print_kv("dest_uri", data.get("dest_uri", "?"))

    elif action == "reindex":
        banner("🔢 CV — Ré-indexation Embeddings")
        params = {}
        if args.tag:
            params["tag"] = args.tag
        if args.user_id:
            params["user_id"] = args.user_id
        data = api_post(base, "/api/cv/reindex-embeddings", token, params=params)
        if data:
            ok(data.get("message", "Ré-indexation démarrée."))
            info("Suivre via logs Cloud Run [REINDEX]")

    elif action == "reindex-chunks":
        banner("🧩 CV — Ré-indexation Chunks (RAG R7)")
        params = {"force": str(getattr(args, "force", False)).lower()}
        if args.tag:
            params["tag"] = args.tag
        if args.user_id:
            params["user_id"] = args.user_id
        data = api_post(base, "/api/cv/bulk-reanalyse/reindex-mission-chunks", token, params=params)
        if data:
            ok(data.get("message", "Ré-indexation chunks démarrée."))
            info("Suivre via logs Cloud Run [CHUNK_REINDEX]")

    elif action == "taxonomy-status":
        banner("🌳 Taxonomie — Statut")
        data = api_get(base, "/api/cv/recalculate_tree/status", token)
        if data:
            s = data.get("status", "idle")
            print(f"\n  {status_icon(s)} {BOLD}{s}{RESET}")
            for k in ["batch_step", "batch_job_id", "error", "mode"]:
                if data.get(k):
                    print_kv(k, str(data[k])[:80])
            logs = data.get("logs", [])
            if logs:
                section("Derniers logs")
                for line in logs[-5:]:
                    print(f"  {GREY}• {line[:120]}{RESET}")

    elif action == "taxonomy-start":
        banner("🚀 Taxonomie — Démarrage Batch")
        data = api_post(base, "/api/cv/recalculate_tree/batch/start", token)
        if data:
            ok(str(data))

    elif action == "taxonomy-step":
        step = args.step
        if not step:
            err("--step requis (map/reduce/sweep/deduplicate)")
            sys.exit(1)
        banner(f"🔧 Taxonomie — Étape : {step}")
        body = {"step": step}
        if args.target_pillar:
            body["target_pillar"] = args.target_pillar
        data = api_post(base, "/api/cv/recalculate_tree/step", token, body)
        if data:
            ok(data.get("message", f"Étape {step} lancée."))

    elif action == "taxonomy-check":
        banner("🔍 Taxonomie — Check batch state machine")
        data = api_post(base, "/api/cv/recalculate_tree/batch/check", token)
        if data:
            ok(str(data))

    elif action == "taxonomy-cancel":
        banner("🚫 Taxonomie — Annulation batch")
        data = api_post(base, "/api/cv/recalculate_tree/batch/cancel", token)
        if data:
            ok(data.get("message", "Annulé."))

    elif action == "taxonomy-recover":
        banner("🔧 Taxonomie — Recover (déblocage)")
        data = api_post(base, "/api/cv/recalculate_tree/batch/recover", token)
        if data:
            if data.get("success"):
                ok(data.get("message", "Recover effectué."))
            else:
                warn(data.get("error", "Échec."))

    elif action == "taxonomy-reset":
        banner("⚠️  Taxonomie — Reset forcé Redis")
        data = api_post(base, "/api/cv/recalculate_tree/batch/reset", token)
        if data:
            ok(data.get("message", "Reset effectué."))

    elif action == "taxonomy-list":
        banner("📋 Taxonomie — Historique jobs Vertex")
        data = api_get(base, "/api/cv/recalculate_tree/batch/list", token)
        if data and data.get("batches"):
            batches = data["batches"]
            print(f"\n  {len(batches)} job(s) trouvé(s)\n")
            for b in batches[:10]:
                state = b.get("state", "?")
                icon = "✅" if "SUCCEEDED" in state else "❌" if "FAILED" in state else "🔄"
                name = b.get("display_name", b.get("name", "?"))[-40:]
                print(f"  {icon} {BOLD}{name}{RESET}  [{state}]")
                if b.get("create_time"):
                    print_kv("  créé", b["create_time"][:19])
                cs = b.get("completion_stats")
                if cs:
                    pct = cs.get("percent", 0)
                    print(f"     {progress_bar(pct, 20)}")

    elif action == "fix-low-quality":
        threshold = getattr(args, "threshold", 75)
        auto_yes = getattr(args, "yes", False)
        banner(f"🩺 CV — Correction qualité d'extraction (seuil < {threshold})")

        # ── 1. Blacklistés en base (drive_api) ───────────────────────────────
        bl = api_get(base, "/api/drive/files/blacklisted?limit=100", token)
        bl_items = (bl or {}).get("items", [])
        if bl_items:
            section(f"⛔  {len(bl_items)} fichier(s) blacklisté(s) — structurellement illisibles")
            print()
            print(f"  {'Score':>4}  {'Essais':>6}  {'Nom':<28}  Depuis")
            print(f"  {'─'*4}  {'─'*6}  {'─'*28}  {'─'*10}")
            for f in bl_items:
                attempts = f.get("extraction_attempt_count", "?")
                name = (f.get("parent_folder_name") or f.get("file_name") or "Inconnu")[:28]
                since = (f.get("extraction_blacklisted_at") or "?")[:10]
                print(f"  {RED}⛔{RESET}    {str(attempts):>5}  {name:<28}  {since}")
            print()
            warn("Ces fichiers ne seront plus re-importés depuis Drive jusqu'à mise à jour par le consultant.")
            print(f"  {GREY}  Déblacklister manuellement : python3 scripts/admin.py drive unblacklist --file-id {{id}}{RESET}")
            print()

        # ── 2. CVs avec score < seuil (cv_api) ───────────────────────────────
        low_cvs, skip, limit = [], 0, 100
        while True:
            page = api_get(
                base,
                f"/api/cv/extraction-scores?sort_desc=false&status=calculated&limit={limit}&skip={skip}",
                token,
            )
            if not page:
                err("Impossible de contacter /extraction-scores")
                break
            items = page.get("items", [])
            total_pages = page.get("total", 0)
            for cv in items:
                score = cv.get("extraction_reliability_score")
                if score is not None and score < threshold:
                    low_cvs.append(cv)
            if len(items) < limit or skip + limit >= total_pages:
                break
            skip += limit

        if not low_cvs:
            ok(f"Aucun CV sous le seuil {threshold} — qualité d'extraction satisfaisante.")
            return

        # ── 3. Affichage des CVs à ré-analyser ───────────────────────────────
        section(f"{len(low_cvs)} CV(s) à ré-analyser via Vertex AI Batch")
        print()
        print(f"  {'Score':>6}  {'Nom':<28}  {'Rôle':<25}  Agence")
        print(f"  {'─'*6}  {'─'*28}  {'─'*25}  {'─'*12}")
        cv_ids = []
        for cv in low_cvs:
            score = cv.get('extraction_reliability_score', '?')
            name = (cv.get('full_name') or 'Inconnu')[:28]
            role = (cv.get('current_role') or '?')[:25]
            tag = (cv.get('source_tag') or '?')[:12]
            cv_id = cv.get('id')
            if cv_id:
                cv_ids.append(cv_id)
            flag = f"{RED}⚠️ {RESET}" if isinstance(score, int) and score < 50 else "   "
            print(f"  {flag}{str(score):>4}  {name:<28}  {role:<25}  {tag}")

        print()
        info("Après ré-analyse : si le score reste < seuil, le fichier Drive sera blacklisté automatiquement.")
        warn(f"Ces {len(cv_ids)} CVs seront soumis à Vertex AI Batch (coût x0.5).")

        # ── 4. Confirmation ───────────────────────────────────────────────────
        if not auto_yes:
            try:
                answer = input(f"\n  Lancer la ré-analyse de {len(cv_ids)} CV(s) ? [o/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            if answer not in ("o", "oui", "y", "yes"):
                warn("Annulé. Relancez avec --yes pour ignorer cette confirmation.")
                return

        # ── 5. Lancement Vertex AI Batch ──────────────────────────────────────
        body = {"cv_ids": cv_ids}
        data = api_post(base, "/api/cv/bulk-reanalyse/start", token, body)
        if data:
            ok(data.get("message", f"{len(cv_ids)} CVs soumis au pipeline Vertex."))
            print_kv("total_cvs", data.get("total_cvs"))
            print_kv("cv_ids_filter", str(data.get("cv_ids_filter", cv_ids))[:80])
            print_kv("status", data.get("status"))
            info("Suivre via : python3 scripts/admin.py cv status")

        # ── 6. Scoring delta ──────────────────────────────────────────────────
        skip_scoring = getattr(args, "skip_scoring", False)
        if not skip_scoring:
            print()
            section("Scoring IA delta — compétences manquantes")
            info("Déclenchement du scoring delta pour les consultants sans score suffisant…")
            score_data = api_post(
                base,
                "/api/competencies/evaluations/bulk-scoring-all",
                token,
                params={"delta_only": "true", "force": "false"},
            )
            if score_data:
                ok(score_data.get("message", "Scoring delta démarré."))
                print_kv("triggered", score_data.get("triggered"))
                print_kv("total_users", score_data.get("total_users"))
                info("Suivre via : python3 scripts/admin.py scoring status")
            else:
                warn(
                    "Scoring delta non déclenché (pipeline peut-être déjà en cours). "
                    "Relancez manuellement : python3 scripts/admin.py scoring start"
                )

    elif action == "remediate":
        banner("🔧 Admin — Remédiation Legacy Errors")
        data = api_post(base, "/api/cv/admin/remediate-legacy", token)
        if data:
            fixed = data.get("fixed_count", 0)
            ok(f"{fixed} profil(s) corrigé(s).")


# ── CMD: scoring ──────────────────────────────────────────────────────────────

def cmd_scoring(args, token: str, base: str) -> None:
    action = args.action

    if action == "status":
        banner("🤖 Scoring IA — Statut")
        data = api_get(base, "/api/competencies/bulk-scoring-all/status", token)
        print_bulk_status(data or {"status": "idle"})

    elif action == "start":
        banner("🚀 Scoring IA — Démarrage")
        full = getattr(args, "full", False)
        force = getattr(args, "force", False)
        delta_only = not full
        mode = "force (tous)" if force else ("complet" if full else "delta (manquants)")
        info(f"Mode : {mode}")
        params = {"delta_only": str(delta_only).lower(), "force": str(force).lower()}
        data = api_post(base, "/api/competencies/evaluations/bulk-scoring-all", token, params=params)
        if data:
            ok(data.get("message", "Scoring démarré."))
            print_kv("triggered", data.get("triggered"))
            print_kv("total_users", data.get("total_users"))

    elif action == "cancel":
        banner("🚫 Scoring IA — Annulation")
        data = api_post(base, "/api/competencies/bulk-scoring-all/cancel", token)
        if data:
            ok(data.get("message", "Annulé et reset effectué."))

    elif action == "resume":
        banner("▶️  Scoring IA — Reprise manuelle")
        data = api_post(base, "/api/competencies/bulk-scoring-all/resume/manual", token)
        if data:
            action_taken = data.get("action", "?")
            ok(f"Action : {action_taken}")
            if data.get("batch_job_id"):
                print_kv("batch_job_id", data["batch_job_id"])

    elif action == "debug":
        banner("🔍 Scoring IA — Debug Config Vertex")
        data = api_get(base, "/api/competencies/bulk-scoring-all/debug-config", token)
        if data:
            for k, v in data.items():
                icon = "✅" if v and "⚠️" not in str(v) else "⚠️"
                print(f"  {icon} {k:<30}: {v}")


# ── CMD: drive ────────────────────────────────────────────────────────────────

def cmd_drive(args, token: str, base: str) -> None:
    action = args.action

    if action == "status":
        banner("📁 Drive — Statut")
        data = api_get(base, "/api/drive/status", token)
        print_drive_status(data or {})

    elif action == "ingestion":
        banner("📊 Drive — KPIs Ingestion")
        section("Stats globales")
        stats = api_get(base, "/api/drive/ingestion/stats", token)
        if stats:
            for k, v in stats.items():
                print_kv(k, v)
        section("Par agence (folder-kpis)")
        folder_kpis = api_get(base, "/api/drive/ingestion/folder-kpis", token)
        if folder_kpis:
            items = folder_kpis if isinstance(folder_kpis, list) else folder_kpis.get("items", [])
            for item in items[:15]:
                name = item.get("folder_name", item.get("name", "?"))[:30]
                imported = item.get("imported", 0)
                total = item.get("total", imported)
                errs = item.get("errors", 0)
                pct = round(imported / total * 100) if total else 0
                color = GREEN if pct >= 90 else YELLOW if pct >= 60 else RED
                print(f"  {color}{'█' * (pct // 10)}{'░' * (10 - pct // 10)}{RESET} "
                      f"{name:<30} {imported}/{total}"
                      + (f"  {RED}⚠️ {errs}{RESET}" if errs else ""))

    elif action == "history":
        banner("📋 Drive — Historique Ingestion")
        data = api_get(base, "/api/drive/ingestion/history", token)
        if data:
            items = data if isinstance(data, list) else data.get("items", [])
            for item in items[:20]:
                print(f"  • {item.get('file_name', '?')[:40]:<40}  "
                      f"{item.get('imported_at', '?')[:19]}")

    elif action == "retry":
        banner("🔄 Drive — Retry Erreurs")
        force = getattr(args, "force", False)
        if force:
            warn("Mode force : reset immédiat de tous les QUEUED/PROCESSING")
        params = {"force": str(force).lower()}
        data = api_post(base, "/api/drive/retry-errors", token, params=params)
        if data:
            ok(f"Erreurs remises en PENDING : {data.get('errors_reset', 0)}")
            ok(f"Zombies réinitialisés      : {data.get('zombies_reset', 0)}")
            info(f"Total reset                : {data.get('total_reset', 0)}")

    elif action == "purge-errors":
        banner("🗑️  Drive — Purge des erreurs")
        warn("Tous les fichiers en ERROR seront passés en IGNORED_NOT_CV.")
        data = api_delete(base, "/api/drive/errors", token)
        if data:
            ok(f"{data.get('cleared_count', 0)} erreur(s) purgée(s).")

    elif action == "quality-gate":
        banner("✅ Drive — Quality Gate Batch")
        data = api_post(base, "/api/drive/ingestion/quality-gate-batch", token)
        if data:
            queued = data.get("files_queued_for_retry", 0)
            ok(data.get("message", f"{queued} CVs republiés."))
            if data.get("reason_breakdown"):
                section("Répartition par raison")
                for reason, count in data["reason_breakdown"].items():
                    print_kv(reason, count)

    elif action == "dlq-status":
        banner("📬 Drive — Dead Letter Queue")
        data = api_get(base, "/api/drive/dlq/status", token)
        if data:
            count = data.get("message_count", 0)
            icon = "🔴" if count > 0 else "✅"
            print(f"\n  {icon} {BOLD}{count} message(s){RESET} dans la DLQ")
            print_kv("subscription", data.get("subscription", "?"))
            files = data.get("files", [])
            if files:
                section("Fichiers en DLQ")
                for f in files[:10]:
                    name = f.get("file_name", "?")
                    folder = f.get("parent_folder_name", "?")
                    status = f.get("status", "?")
                    print(f"  • {name[:35]:<35} [{folder}] — {status}")
            unknowns = data.get("unknown_payloads", 0)
            if unknowns:
                warn(f"{unknowns} payload(s) illisible(s) dans la DLQ.")

    elif action == "blacklisted":
        banner("⛔ Drive — Fichiers blacklistés (qualité extraction)")
        data = api_get(base, "/api/drive/files/blacklisted?limit=200", token)
        items = (data or {}).get("items", [])
        total = (data or {}).get("total", 0)
        if not items:
            ok("Aucun fichier blacklisté — tous les CVs sont extractibles.")
            return
        section(f"{total} fichier(s) blacklisté(s)")
        print()
        print(f"  {'Essais':>6}  {'Depuis':>10}  {'Nom':<28}  Google File ID")
        print(f"  {'─'*6}  {'─'*10}  {'─'*28}  {'─'*20}")
        for f in items:
            attempts = f.get("extraction_attempt_count", "?")
            name = (f.get("parent_folder_name") or f.get("file_name") or "Inconnu")[:28]
            since = (f.get("extraction_blacklisted_at") or "?")[:10]
            fid = f.get("google_file_id", "?")
            print(f"  {RED}{str(attempts):>6}{RESET}  {since:>10}  {name:<28}  {fid}")
        print()
        info("Pour déblacklister : python3 scripts/admin.py drive unblacklist --file-id <GOOGLE_FILE_ID>")

    elif action == "unblacklist":
        file_id = getattr(args, "file_id", None)
        if not file_id:
            err("--file-id requis. Exemple : python3 scripts/admin.py drive unblacklist --file-id 1AbC...")
            return
        banner(f"🔓 Drive — Déblacklist {file_id}")
        data = api_delete(base, f"/api/drive/files/{file_id}/blacklist", token)
        if data:
            ok(data.get("message", f"Fichier {file_id} déblaclisté."))
            info("Le fichier sera réingéré au prochain /sync.")

    elif action == "dlq-replay":
        banner("▶️  Drive — Replay DLQ")
        warn("Tous les messages DLQ seront remis en PENDING.")
        data = api_post(base, "/api/drive/dlq/replay", token)
        if data:
            ok(data.get("message", "Replay effectué."))
            print_kv("messages pullés", data.get("dlq_messages_pulled", 0))
            print_kv("fichiers PENDING", data.get("files_reset_to_pending", 0))
            if data.get("unknown_payloads"):
                warn(f"{data['unknown_payloads']} payload(s) illisible(s) ignoré(s).")

    elif action == "sync":
        banner("🔄 Drive — Synchronisation manuelle")
        data = api_post(base, "/api/drive/sync", token)
        if data:
            ok(f"Sync déclenchée : {data.get('status', '?')}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Console d'administration Zenika Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--env", default="prd", choices=["prd", "uat", "dev"])
    parser.add_argument("--no-cache", action="store_true")

    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="Vue d'ensemble de tous les services")

    # quality
    sub.add_parser("quality", help="Rapport data quality complet")

    # cv
    p_cv = sub.add_parser("cv", help="Actions pipeline CV")
    p_cv.add_argument("action", choices=[
        "status", "start", "cancel", "reset", "retry-apply",
        "reindex", "reindex-chunks", "fix-low-quality",
        "taxonomy-status", "taxonomy-start",
        "taxonomy-step", "taxonomy-check", "taxonomy-cancel", "taxonomy-recover",
        "taxonomy-reset", "taxonomy-list", "remediate",
    ])
    p_cv.add_argument("--ids", default=None, help="IDs CVs séparés par virgules")
    p_cv.add_argument("--tag", default=None, help="Filtre agence (source_tag)")
    p_cv.add_argument("--user-id", type=int, default=None)
    p_cv.add_argument("--force", action="store_true", help="Force re-création complète")
    p_cv.add_argument("--step", default=None, help="Étape taxonomy: map/reduce/sweep/deduplicate")
    p_cv.add_argument("--target-pillar", default=None)
    p_cv.add_argument("--resume", action="store_true")
    p_cv.add_argument(
        "--threshold", type=int, default=75,
        help="Seuil score extraction pour fix-low-quality (défaut: 75)"
    )
    p_cv.add_argument(
        "--yes", action="store_true",
        help="Confirme automatiquement sans prompt interactif"
    )
    p_cv.add_argument(
        "--skip-scoring", action="store_true",
        help="fix-low-quality : ne pas déclencher le scoring delta"
    )

    # scoring
    p_sc = sub.add_parser("scoring", help="Actions pipeline Scoring IA")
    p_sc.add_argument("action", choices=["status", "start", "cancel", "resume", "debug"])
    p_sc.add_argument("--full", action="store_true", help="Re-score toutes les compétences")
    p_sc.add_argument("--force", action="store_true", help="Force tous les consultants")

    # drive
    p_dr = sub.add_parser("drive", help="Actions Drive / Ingestion / DLQ")
    p_dr.add_argument("action", choices=[
        "status", "ingestion", "history", "retry",
        "purge-errors", "quality-gate", "dlq-status", "dlq-replay", "sync",
        "blacklisted", "unblacklist",
    ])
    p_dr.add_argument("--force", action="store_true")
    p_dr.add_argument("--file-id", dest="file_id", default=None,
                      help="unblacklist : Google File ID du fichier à déblacklister")

    # help
    sub.add_parser("help", help="Affiche l'aide complète")

    args = parser.parse_args()

    if args.command == "help":
        print(__doc__)
        return

    token, base_url = get_jwt(args.env, args.no_cache)

    if args.command == "status":
        cmd_status(args, token, base_url)
    elif args.command == "quality":
        cmd_quality(args, token, base_url)
    elif args.command == "cv":
        cmd_cv(args, token, base_url)
    elif args.command == "scoring":
        cmd_scoring(args, token, base_url)
    elif args.command == "drive":
        cmd_drive(args, token, base_url)

    print()


if __name__ == "__main__":
    main()
