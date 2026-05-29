import json
import logging
from datetime import datetime, timezone

from mcp.types import TextContent

logger = logging.getLogger(__name__)


async def handle_log_sre_triage(arguments: dict, client, table_ref: str) -> list[TextContent]:
    """Insère un rapport de triage SRE dans BigQuery.

    Les champs services_* sont encodés en JSON string pour compatibilité
    avec insert_rows_json (BigQuery ARRAY<STRING> non supporté nativement).
    """
    try:
        triggered_at = arguments.get("triggered_at") or datetime.now(timezone.utc).isoformat()
        env = arguments.get("env", "dev")
        severity = arguments.get("severity", "OK")
        hours_window = int(arguments.get("hours_window", 1))

        report_excerpt = arguments.get("report_excerpt", "") or ""
        if len(report_excerpt) > 1000:
            report_excerpt = report_excerpt[:1000]

        row = {
            "triggered_at": triggered_at,
            "env": env,
            "severity": severity,
            "hours_window": hours_window,
            "services_critical": json.dumps(arguments.get("services_critical") or []),
            "services_warning": json.dumps(arguments.get("services_warning") or []),
            "services_ok": json.dumps(arguments.get("services_ok") or []),
            "total_5xx": arguments.get("total_5xx", 0),
            "dq_errors_count": arguments.get("dq_errors_count", 0),
            "dq_errors_detail": arguments.get("dq_errors_detail", ""),
            "tokens_in": arguments.get("tokens_in", 0),
            "tokens_out": arguments.get("tokens_out", 0),
            "cost_usd": arguments.get("cost_usd", 0.0),
            "report_excerpt": report_excerpt,
            "playbook_used": arguments.get("playbook_used", False),
            "followup_scheduled": arguments.get("followup_scheduled", False),
        }

        errors = client.insert_rows_json(table_ref, [row])
        if errors:
            logger.error("[sre_triage] BigQuery insert errors: %s", errors)
            return [TextContent(type="text", text=json.dumps({"success": False, "error": str(errors)}))]

        logger.info("[sre_triage] Report logged — env=%s severity=%s triggered_at=%s", env, severity, triggered_at)
        return [TextContent(type="text", text=json.dumps({"success": True, "table": table_ref}))]

    except Exception as e:
        logger.exception("[sre_triage] Unexpected error while logging SRE triage report")
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_get_sre_trends(arguments: dict, client, table_ref: str) -> list[TextContent]:
    """Interroge l'historique BigQuery des triages SRE pour détecter les tendances.

    Retourne pour chaque env :
    - Résumé des N derniers triages
    - Tendance dq_errors_count (stable / hausse / baisse / hausse_critique)
    - Tendance erreurs 5xx
    - Interprétation textuelle lisible par le LLM

    Utilisé par l'agent SRE en Phase 0 pour enrichir son analyse avec le contexte
    historique : 'competencies-api avait 0 DQ error il y a 2h, maintenant 30 — régression.'
    """
    try:
        from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter  # noqa: PLC0415

        env = arguments.get("env", "dev")
        lookback_triages = int(arguments.get("lookback_triages", 5))

        query = f"""
            WITH recent AS (
                SELECT
                    triggered_at, severity, total_5xx, dq_errors_count,
                    services_critical, services_warning, report_excerpt,
                    ROW_NUMBER() OVER (ORDER BY triggered_at DESC) AS rn
                FROM `{table_ref}`
                WHERE env = @env
                LIMIT {lookback_triages}
            ),
            stats AS (
                SELECT
                    COUNT(*) AS total_triages,
                    COUNTIF(severity = 'CRITICAL') AS critical_count,
                    COUNTIF(severity = 'WARNING') AS warning_count,
                    COUNTIF(severity = 'OK') AS ok_count,
                    AVG(dq_errors_count) AS avg_dq_errors,
                    AVG(total_5xx) AS avg_5xx,
                    MAX(dq_errors_count) AS max_dq_errors,
                    MAX(total_5xx) AS max_5xx
                FROM recent
            ),
            latest AS (
                SELECT dq_errors_count, total_5xx, severity, triggered_at
                FROM recent WHERE rn = 1
            ),
            previous AS (
                SELECT AVG(dq_errors_count) AS avg_dq, AVG(total_5xx) AS avg_5xx
                FROM recent WHERE rn > 1
            )
            SELECT
                s.*,
                l.dq_errors_count AS latest_dq_errors,
                l.total_5xx AS latest_5xx,
                l.severity AS latest_severity,
                CAST(l.triggered_at AS STRING) AS latest_triggered_at,
                p.avg_dq AS prev_avg_dq,
                p.avg_5xx AS prev_avg_5xx,
                CASE
                    WHEN p.avg_dq IS NULL OR p.avg_dq = 0 THEN 'new'
                    WHEN l.dq_errors_count > p.avg_dq * 2 THEN 'hausse_critique'
                    WHEN l.dq_errors_count > p.avg_dq * 1.3 THEN 'hausse'
                    WHEN l.dq_errors_count < p.avg_dq * 0.7 THEN 'baisse'
                    ELSE 'stable'
                END AS dq_trend,
                CASE
                    WHEN p.avg_5xx IS NULL OR p.avg_5xx = 0 THEN 'new'
                    WHEN l.total_5xx > p.avg_5xx * 2 THEN 'hausse_critique'
                    WHEN l.total_5xx > p.avg_5xx * 1.3 THEN 'hausse'
                    WHEN l.total_5xx < p.avg_5xx * 0.7 THEN 'baisse'
                    ELSE 'stable'
                END AS error_trend
            FROM stats s, latest l, previous p
        """

        config = QueryJobConfig(
            query_parameters=[ScalarQueryParameter("env", "STRING", env)],
        )

        rows = list(client.query(query, job_config=config))

        if not rows:
            result = {
                "env": env,
                "status": "no_history",
                "message": (
                    f"Aucun historique disponible pour env={env} "
                    "(premiers triages en cours d'accumulation)."
                ),
                "lookback_triages": lookback_triages,
            }
        else:
            row = dict(rows[0])
            result = {
                "env": env,
                "lookback_triages": lookback_triages,
                "total_triages_analysed": row.get("total_triages", 0),
                "latest_severity": row.get("latest_severity", "UNKNOWN"),
                "latest_triggered_at": row.get("latest_triggered_at", ""),
                "severity_distribution": {
                    "critical": row.get("critical_count", 0),
                    "warning": row.get("warning_count", 0),
                    "ok": row.get("ok_count", 0),
                },
                "dq_errors": {
                    "latest": row.get("latest_dq_errors", 0),
                    "average": round(float(row.get("avg_dq_errors") or 0), 1),
                    "max": row.get("max_dq_errors", 0),
                    "trend": row.get("dq_trend", "unknown"),
                    "prev_average": round(float(row.get("prev_avg_dq") or 0), 1),
                },
                "errors_5xx": {
                    "latest": row.get("latest_5xx", 0),
                    "average": round(float(row.get("avg_5xx") or 0), 1),
                    "max": row.get("max_5xx", 0),
                    "trend": row.get("error_trend", "unknown"),
                    "prev_average": round(float(row.get("prev_avg_5xx") or 0), 1),
                },
                "interpretation": _build_trend_interpretation(row),
            }

        return [TextContent(type="text", text=json.dumps(result, default=str))]

    except Exception as e:
        logger.exception("[sre_trends] Erreur lors de la récupération des tendances SRE")
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


def _build_trend_interpretation(row: dict) -> str:
    """Génère un texte d'interprétation lisible par le LLM depuis les métriques de tendance."""
    parts = []

    dq_trend = row.get("dq_trend", "unknown")
    err_trend = row.get("error_trend", "unknown")
    latest_dq = int(row.get("latest_dq_errors") or 0)
    prev_dq = round(float(row.get("prev_avg_dq") or 0), 1)
    latest_5xx = int(row.get("latest_5xx") or 0)
    prev_5xx = round(float(row.get("prev_avg_5xx") or 0), 1)
    total = int(row.get("total_triages") or 1)
    critical_count = int(row.get("critical_count") or 0)
    critical_pct = critical_count * 100 // max(total, 1)

    if dq_trend == "hausse_critique":
        ratio = latest_dq / max(prev_dq, 1)
        parts.append(
            f"🔴 RÉGRESSION DATA QUALITY : dq_errors {prev_dq} → {latest_dq} "
            f"(×{ratio:.1f} vs historique)."
        )
    elif dq_trend == "hausse":
        parts.append(f"⚠️ Hausse Data Quality : {prev_dq} → {latest_dq} dq_errors.")
    elif dq_trend == "baisse":
        parts.append(f"✅ Amélioration Data Quality : {prev_dq} → {latest_dq} dq_errors.")
    elif dq_trend == "stable":
        parts.append(f"✅ Data Quality stable : {latest_dq} dq_errors (moy. {prev_dq}).")
    else:
        parts.append("ℹ️ Premier triage — pas encore d'historique de comparaison.")

    if err_trend == "hausse_critique":
        parts.append(f"🔴 RÉGRESSION 5xx : {prev_5xx} → {latest_5xx}.")
    elif err_trend == "hausse":
        parts.append(f"⚠️ Hausse 5xx : {prev_5xx} → {latest_5xx}.")
    elif err_trend == "baisse":
        parts.append(f"✅ Amélioration 5xx : {prev_5xx} → {latest_5xx}.")

    if critical_pct >= 50:
        parts.append(
            f"🔴 Plateforme instable : {critical_pct}% des {total} derniers triages CRITICAL."
        )

    return " | ".join(parts) if parts else "Données insuffisantes pour une tendance."
