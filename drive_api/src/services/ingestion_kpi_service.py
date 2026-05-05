import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, update, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import DriveFolder, DriveSyncState, DriveSyncStatus
from src.redis_client import get_redis
from src.routers.files_router import _compute_kpi_metric, _reset_errors_to_pending

logger = logging.getLogger(__name__)

class IngestionKpiService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_ingestion_stats(self) -> dict:
        total = (await self.db.execute(select(func.count()).select_from(DriveSyncState))).scalar() or 0
        imported = (await self.db.execute(
            select(func.count()).select_from(DriveSyncState).where(DriveSyncState.status == DriveSyncStatus.IMPORTED_CV)
        )).scalar() or 0
        errors = (await self.db.execute(
            select(func.count()).select_from(DriveSyncState).where(DriveSyncState.status == DriveSyncStatus.ERROR)
        )).scalar() or 0
        pending = (await self.db.execute(
            select(func.count()).select_from(DriveSyncState).where(DriveSyncState.status == DriveSyncStatus.PENDING)
        )).scalar() or 0
        queued = (await self.db.execute(
            select(func.count()).select_from(DriveSyncState).where(DriveSyncState.status == DriveSyncStatus.QUEUED)
        )).scalar() or 0
        processing = (await self.db.execute(
            select(func.count()).select_from(DriveSyncState).where(DriveSyncState.status == DriveSyncStatus.PROCESSING)
        )).scalar() or 0
        ignored = (await self.db.execute(
            select(func.count()).select_from(DriveSyncState).where(DriveSyncState.status == DriveSyncStatus.IGNORED_NOT_CV)
        )).scalar() or 0

        kpi_import_rate = _compute_kpi_metric(imported, total, 90.0, 75.0)
        kpi_error_rate = _compute_kpi_metric(imported, imported + errors, 95.0, 85.0)

        named = (await self.db.execute(
            select(func.count()).select_from(DriveSyncState).where(
                and_(
                    DriveSyncState.status == DriveSyncStatus.IMPORTED_CV,
                    DriveSyncState.parent_folder_name.isnot(None),
                    DriveSyncState.parent_folder_name != ""
                )
            )
        )).scalar() or 0
        kpi_naming = _compute_kpi_metric(named, imported, 95.0, 80.0)

        linked = (await self.db.execute(
            select(func.count()).select_from(DriveSyncState).where(
                and_(
                    DriveSyncState.status == DriveSyncStatus.IMPORTED_CV,
                    DriveSyncState.user_id.isnot(None)
                )
            )
        )).scalar() or 0
        kpi_user_link = _compute_kpi_metric(linked, imported, 95.0, 80.0)

        avg_ms_result = (await self.db.execute(
            select(func.avg(DriveSyncState.processing_duration_ms)).where(
                and_(
                    DriveSyncState.status == DriveSyncStatus.IMPORTED_CV,
                    DriveSyncState.processing_duration_ms.isnot(None)
                )
            )
        )).scalar()
        avg_ms = round(float(avg_ms_result), 0) if avg_ms_result else None
        duration_status = "ok"
        if avg_ms is not None:
            if avg_ms > 60000:
                duration_status = "critical"
            elif avg_ms > 30000:
                duration_status = "warning"
        kpi_duration = {
            "value": round(avg_ms / 1000, 1) if avg_ms else 0.0,
            "pct": min(100, round((avg_ms or 0) / 60000 * 100, 1)),
            "ok": int(avg_ms / 1000) if avg_ms else 0,
            "total": 60,
            "status": duration_status,
            "unit": "s"
        }

        last_imported_at = (await self.db.execute(
            select(func.max(DriveSyncState.imported_at)).where(DriveSyncState.imported_at.isnot(None))
        )).scalar()
        last_processed = (await self.db.execute(
            select(func.max(DriveSyncState.last_processed_at))
        )).scalar()
        freshness_hours = None
        freshness_status = "ok"
        reference_time = last_imported_at or last_processed
        if reference_time:
            diff_hours = (datetime.now(timezone.utc) - reference_time).total_seconds() / 3600
            freshness_hours = round(diff_hours, 1)
            if diff_hours > 48:
                freshness_status = "critical"
            elif diff_hours > 24:
                freshness_status = "warning"

        scores = [
            kpi_import_rate["pct"] * 0.25,
            kpi_user_link["pct"] * 0.30,
            kpi_naming["pct"] * 0.15,
            kpi_error_rate["pct"] * 0.15,
            (100 if freshness_status == "ok" else 50 if freshness_status == "warning" else 0) * 0.15,
        ]
        score = round(sum(scores), 1)
        grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"

        issues = []
        if kpi_import_rate["status"] != "ok":
            issues.append(f"Taux d'import {kpi_import_rate['status']} : {kpi_import_rate['pct']}%")
        if kpi_user_link["status"] != "ok":
            issues.append(f"Liaison consultant {kpi_user_link['status']} : {kpi_user_link['pct']}%")
        if kpi_naming["status"] != "ok":
            issues.append(f"Nommage non résolu : {kpi_naming['pct']}%")
        if freshness_status != "ok":
            issues.append(f"Pipeline inactif depuis {freshness_hours}h")
        if errors > 0 and total > 0 and (errors / total) > 0.1:
            issues.append(f"{errors} fichiers en erreur ({round(errors/total*100, 1)}%) — lancez un Quality Gate Batch")

        recommendation = (
            "\u2705 Pipeline en bonne santé." if not issues
            else "\u26a0\ufe0f Lancez un Quality Gate Batch pour corriger les données incomplètes."
        )

        redis = get_redis()
        is_rebuilding_tree = bool(redis.get("drive:sync:rebuild_running"))

        return {
            "total_files": total, "imported": imported, "errors": errors,
            "pending": pending, "queued": queued, "processing": processing, "ignored": ignored,
            "freshness_hours": freshness_hours,
            "is_rebuilding_tree": is_rebuilding_tree,
            "metrics": {
                "Taux d'import réussi": kpi_import_rate,
                "Taux sans erreur": kpi_error_rate,
                "Nommage résolu": kpi_naming,
                "Liaison consultant": kpi_user_link,
                "Durée de traitement": kpi_duration,
            },
            "score": score, "grade": grade,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "issues": issues, "recommendation": recommendation,
        }

    async def get_folder_kpis(self) -> list[dict]:
        folders = (await self.db.execute(select(DriveFolder))).scalars().all()
        result = []

        for folder in folders:
            fid = folder.id
            fid_filter = DriveSyncState.folder_id == fid

            total = (await self.db.execute(
                select(func.count()).select_from(DriveSyncState).where(fid_filter)
            )).scalar() or 0
            imported = (await self.db.execute(
                select(func.count()).select_from(DriveSyncState).where(
                    fid_filter, DriveSyncState.status == DriveSyncStatus.IMPORTED_CV)
            )).scalar() or 0
            errors = (await self.db.execute(
                select(func.count()).select_from(DriveSyncState).where(
                    fid_filter, DriveSyncState.status == DriveSyncStatus.ERROR)
            )).scalar() or 0
            pending = (await self.db.execute(
                select(func.count()).select_from(DriveSyncState).where(
                    fid_filter, DriveSyncState.status == DriveSyncStatus.PENDING)
            )).scalar() or 0
            queued = (await self.db.execute(
                select(func.count()).select_from(DriveSyncState).where(
                    fid_filter, DriveSyncState.status == DriveSyncStatus.QUEUED)
            )).scalar() or 0
            processing = (await self.db.execute(
                select(func.count()).select_from(DriveSyncState).where(
                    fid_filter, DriveSyncState.status == DriveSyncStatus.PROCESSING)
            )).scalar() or 0
            ignored = (await self.db.execute(
                select(func.count()).select_from(DriveSyncState).where(
                    fid_filter, DriveSyncState.status == DriveSyncStatus.IGNORED_NOT_CV)
            )).scalar() or 0

            linked = (await self.db.execute(
                select(func.count()).select_from(DriveSyncState).where(
                    fid_filter,
                    DriveSyncState.status == DriveSyncStatus.IMPORTED_CV,
                    DriveSyncState.user_id.isnot(None))
            )).scalar() or 0

            avg_ms_row = (await self.db.execute(
                select(func.avg(DriveSyncState.processing_duration_ms)).where(
                    fid_filter, DriveSyncState.processing_duration_ms.isnot(None))
            )).scalar()

            last_import_row = (await self.db.execute(
                select(func.max(DriveSyncState.imported_at)).where(
                    fid_filter, DriveSyncState.imported_at.isnot(None))
            )).scalar()

            import_rate = round((imported / total * 100), 1) if total > 0 else 0.0
            error_rate = round((errors / total * 100), 1) if total > 0 else 0.0
            user_link_rate = round((linked / imported * 100), 1) if imported > 0 else 0.0

            if error_rate > 15 or (imported > 0 and user_link_rate < 80):
                folder_status = "critical"
            elif error_rate > 5 or (imported > 0 and user_link_rate < 90) or import_rate < 90:
                folder_status = "warning"
            else:
                folder_status = "ok"

            result.append({
                "folder_id": fid, "folder_name": folder.folder_name, "tag": folder.tag,
                "total": total, "imported": imported, "errors": errors,
                "pending": pending, "queued": queued, "processing": processing, "ignored": ignored,
                "import_rate_pct": import_rate, "error_rate_pct": error_rate,
                "user_link_rate_pct": user_link_rate,
                "avg_processing_ms": round(float(avg_ms_row), 0) if avg_ms_row else None,
                "last_import_at": last_import_row.isoformat() if last_import_row else None,
                "status": folder_status,
            })

        priority = {"critical": 0, "warning": 1, "ok": 2}
        result.sort(key=lambda x: (priority.get(x["status"], 3), -x["error_rate_pct"]))
        return result

    async def get_ingestion_history(self, limit: int = 50) -> list[dict]:
        limit = min(limit, 200)
        stmt = (
            select(DriveSyncState)
            .where(DriveSyncState.status == DriveSyncStatus.IMPORTED_CV)
            .order_by(DriveSyncState.imported_at.desc().nullslast(), DriveSyncState.last_processed_at.desc())
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            {
                "google_file_id": r.google_file_id, "file_name": r.file_name,
                "parent_folder_name": r.parent_folder_name, "user_id": r.user_id,
                "queued_at": r.queued_at.isoformat() if r.queued_at else None,
                "imported_at": r.imported_at.isoformat() if r.imported_at else None,
                "processing_duration_ms": r.processing_duration_ms,
            }
            for r in rows
        ]

    async def batch_retry(self, force: bool = False) -> dict:
        result = await _reset_errors_to_pending(self.db, force=force)
        return result

    async def quality_gate_batch(self) -> dict:
        now = datetime.now(timezone.utc)
        reason_breakdown: dict[str, int] = {}
        all_fixed_ids: list[str] = []

        stmt_no_user = (
            update(DriveSyncState)
            .where(and_(DriveSyncState.status == DriveSyncStatus.IMPORTED_CV, DriveSyncState.user_id.is_(None)))
            .values(status=DriveSyncStatus.PENDING, error_message="Quality Gate: user_id manquant", last_processed_at=now)
            .returning(DriveSyncState.google_file_id)
        )
        ids_no_user = [r[0] for r in (await self.db.execute(stmt_no_user)).fetchall()]
        reason_breakdown["user_id_manquant"] = len(ids_no_user)
        all_fixed_ids.extend(ids_no_user)

        stmt_no_name = (
            update(DriveSyncState)
            .where(and_(
                DriveSyncState.status == DriveSyncStatus.IMPORTED_CV,
                or_(DriveSyncState.parent_folder_name.is_(None), DriveSyncState.parent_folder_name == ""),
                DriveSyncState.google_file_id.notin_(ids_no_user)
            ))
            .values(status=DriveSyncStatus.PENDING, error_message="Quality Gate: nommage manquant", last_processed_at=now)
            .returning(DriveSyncState.google_file_id)
        )
        ids_no_name = [r[0] for r in (await self.db.execute(stmt_no_name)).fetchall()]
        reason_breakdown["nommage_manquant"] = len(ids_no_name)
        all_fixed_ids.extend(ids_no_name)

        error_threshold = now - timedelta(minutes=30)
        stmt_errors = (
            update(DriveSyncState)
            .where(and_(DriveSyncState.status == DriveSyncStatus.ERROR, DriveSyncState.last_processed_at < error_threshold))
            .values(status=DriveSyncStatus.PENDING, error_message="Quality Gate: erreur persistante", last_processed_at=now)
            .returning(DriveSyncState.google_file_id)
        )
        ids_errors = [r[0] for r in (await self.db.execute(stmt_errors)).fetchall()]
        reason_breakdown["erreur_persistante"] = len(ids_errors)
        all_fixed_ids.extend(ids_errors)

        await self.db.commit()

        if all_fixed_ids:
            try:
                redis = get_redis()
                pipe = redis.pipeline()
                for fid in all_fixed_ids:
                    pipe.delete(f"drive:file:known:{fid}")
                pipe.execute()
            except Exception as e_redis:
                logger.warning(f"[QualityGate] Redis cache invalidation partielle : {e_redis}")

        total_queued = sum(reason_breakdown.values())
        logger.info(f"[QualityGate] {total_queued} fichiers remis en PENDING — {reason_breakdown}")
        
        return {
            "total_queued": total_queued,
            "reason_breakdown": reason_breakdown
        }
