"""
sre_triage.py — SRE Triage automatique déclenché par Cloud Scheduler ou manuellement.

Ce module expose la logique de construction de la requête de triage SRE et la
structure de retour.  Il délègue l'exécution réelle à ``run_agent_query`` de
l'Agent Ops afin que le LLM puisse utiliser ses tools natifs (Cloud Logging,
Cloud Trace, monitoring_mcp) pour produire un diagnostic actionnable.

Endpoint : POST /tasks/sre-triage
Sécurité  : OIDC (Cloud Scheduler) — validé via ``verify_oidc_token``.

Structure de la requête Cloud Scheduler (body JSON) :
  {
    "services": ["cv_api", "agent_router_api"],   // optionnel — tous si absent
    "hours":    2,                                  // fenêtre temporelle (défaut: 1h)
    "threshold_5xx": 5                              // nb minimum erreurs 5xx (défaut: 5)
  }
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Marqueurs de sévérité utilisés dans les rapports générés par l'agent
_CRITICAL_MARKER = "🔴"   # service critique — seuil 5xx dépassé
_WARNING_MARKER = "⚠️"    # service dégradé ou alerte FinOps
_OK_MARKER = "✅"          # tout va bien

# Clé du playbook SRE dans prompts_api — chargé par l'agent en Phase 0
_PLAYBOOK_KEY = "prompts_api.sre_triage.playbook"

# Emoji d'en-tête Google Chat par sévérité
_CHAT_EMOJI = {
    "CRITICAL": "🔴",
    "WARNING": "⚠️",
    "OK": "✅",
}

# Tronçon max du rapport dans Google Chat (limite de 4096 chars par section)
_CHAT_REPORT_MAX_CHARS = 3800


# ---------------------------------------------------------------------------
# Schemas Pydantic — request / response
# ---------------------------------------------------------------------------

class SreTriageRequest(BaseModel):
    """Payload optionnel envoyé par Cloud Scheduler ou par un appel manuel."""

    services: Optional[list[str]] = Field(
        default=None,
        description=(
            "Liste des services à inspecter. "
            "Si absent, tous les services de la plateforme sont analysés."
        ),
    )
    hours: int = Field(
        default=1,
        ge=1,
        le=24,
        description="Fenêtre temporelle d'analyse en heures (1 à 24).",
    )
    threshold_5xx: int = Field(
        default=5,
        ge=0,
        description="Nombre minimum d'erreurs 5xx pour déclencher une alerte dans le rapport.",
    )


class SreTriageReport(BaseModel):
    """Rapport de triage SRE produit par l'Agent Ops."""

    triggered_at: str = Field(description="Timestamp ISO-8601 UTC du déclenchement.")
    services_inspected: Optional[list[str]] = Field(
        default=None,
        description="Services analysés (None = tous).",
    )
    hours: int = Field(description="Fenêtre temporelle utilisée.")
    threshold_5xx: int = Field(description="Seuil d'erreurs 5xx utilisé.")
    response: str = Field(description="Rapport en Markdown produit par l'Agent Ops.")
    steps: list = Field(default_factory=list, description="Étapes de raisonnement de l'agent.")
    thoughts: str = Field(default="", description="Pensées de l'agent (Thinking mode).")
    usage: dict = Field(default_factory=dict, description="Tokens consommés et coût estimé.")
    source: str = Field(default="ops_agent", description="Source de la réponse.")
    severity: str = Field(
        default="OK",
        description="Sévérité calculée du rapport : OK | WARNING | CRITICAL.",
    )


# ---------------------------------------------------------------------------
# Severity classifier
# ---------------------------------------------------------------------------

def classify_report(response_text: str) -> str:
    """Détermine la sévérité du rapport à partir des marqueurs visuels.

    Returns:
        "CRITICAL" si le rapport contient au moins un marqueur 🔴.
        "WARNING"  si le rapport contient des ⚠️ sans 🔴.
        "OK"       si uniquement des ✅ ou aucun marqueur connu.
    """
    if _CRITICAL_MARKER in response_text:
        return "CRITICAL"
    if _WARNING_MARKER in response_text:
        return "WARNING"
    return "OK"


# ---------------------------------------------------------------------------
# Cloud Logging — rapport complet (sans troncature)
# ---------------------------------------------------------------------------

def _emit_structured_log(report: SreTriageReport) -> None:
    """Émet un log structuré Cloud Logging avec la sévérité du rapport.

    Le champ ``message`` contient un marker filtré par Cloud Monitoring :
      - [SRE-TRIAGE-CRITICAL] → déclenche l'alerte Cloud Monitoring
      - [SRE-TRIAGE-WARNING]  → visible dans les logs, pas d'alerte
      - [SRE-TRIAGE-OK]       → log INFO discret

    Le champ ``sre_report_full`` contient le rapport Markdown intégral
    (sans limite de caractères) pour consultation dans Cloud Logging Explorer.
    """
    extra = {
        "sre_triggered_at": report.triggered_at,
        "sre_hours": report.hours,
        "sre_threshold_5xx": report.threshold_5xx,
        "sre_services": report.services_inspected or "ALL",
        "sre_severity": report.severity,
        "sre_tokens_in": report.usage.get("total_input_tokens", 0),
        "sre_tokens_out": report.usage.get("total_output_tokens", 0),
        "sre_cost_usd": report.usage.get("estimated_cost_usd", 0.0),
        # Rapport Markdown complet — consultable dans Cloud Logging Explorer
        "sre_report_full": report.response,
    }

    if report.severity == "CRITICAL":
        logger.critical(
            "[SRE-TRIAGE-CRITICAL] Incident(s) critique(s) détecté(s) sur la plateforme — "
            "intervention requise. Consulter sre_report_full pour le rapport complet.",
            extra=extra,
        )
    elif report.severity == "WARNING":
        logger.warning(
            "[SRE-TRIAGE-WARNING] Alerte(s) dégradée(s) détectée(s) — "
            "surveillance recommandée. Consulter sre_report_full.",
            extra=extra,
        )
    else:
        logger.info(
            "[SRE-TRIAGE-OK] Triage SRE terminé — aucun incident critique. Plateforme nominale.",
            extra=extra,
        )


# ---------------------------------------------------------------------------
# Google Chat — Helper et notification riche avec rapport complet
# ---------------------------------------------------------------------------

def _get_webhook_url() -> str:
    """Récupère l'URL du webhook Google Chat de manière sécurisée.

    1. Regarde d'abord si GOOGLE_CHAT_WEBHOOK_URL est directement dans l'environnement.
    2. Sinon, cherche GOOGLE_CHAT_WEBHOOK_SECRET_NAME et tente de lire la version 'latest'
       depuis GCP Secret Manager en attrapant les erreurs pour éviter tout crash.
    """
    # 1. Option directe (dev local)
    webhook_url = os.environ.get("GOOGLE_CHAT_WEBHOOK_URL", "").strip()
    if webhook_url:
        return webhook_url

    # 2. Récupération via Secret Manager (GCP)
    secret_name = os.environ.get("GOOGLE_CHAT_WEBHOOK_SECRET_NAME", "").strip()
    project_id = os.environ.get("GCP_PROJECT_ID", "").strip()
    if not secret_name or not project_id:
        return ""

    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        val = response.payload.data.decode("UTF-8").strip()

        # Validation basique pour voir s'il y a un placeholder ou si c'est vide
        if not val or "PLACEHOLDER" in val:
            logger.warning(
                "[SRE Chat] Le secret %s contient une valeur par défaut ou vide. "
                "Notification ignorée.",
                secret_name,
            )
            return ""

        return val
    except Exception as exc:
        # En cas de problème de droits, secret inexistant, version manquante, etc.
        logger.error(
            "[SRE Chat] Impossible d'accéder au secret %s via Secret Manager "
            "(non-bloquant) : %s",
            secret_name,
            exc,
        )
        return ""


async def _send_chat_notification(report: SreTriageReport) -> None:
    """Envoie le rapport SRE complet dans l'espace Google Chat SRE.

    Ne fait rien si GOOGLE_CHAT_WEBHOOK_URL est absent (local dev / env sans webhook).
    N'envoie rien pour les rapports OK (éviter le spam).

    Le message est un texte Markdown structuré avec le rapport intégral tronqué
    à _CHAT_REPORT_MAX_CHARS si nécessaire (limite Google Chat : 4096 chars/section).
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        logger.debug("[SRE Chat] Webhook Google Chat absent ou inaccessible — notification ignorée.")
        return

    if report.severity == "OK":
        logger.debug("[SRE Chat] Rapport OK — pas de notification Google Chat (anti-spam).")
        return

    emoji = _CHAT_EMOJI.get(report.severity, "ℹ️")
    env = os.environ.get("K_SERVICE", "local").split("-")[-1]  # ex: "prd" ou "dev"

    # Tronquer le rapport si trop long pour Google Chat
    report_body = report.response
    truncated = False
    if len(report_body) > _CHAT_REPORT_MAX_CHARS:
        report_body = report_body[:_CHAT_REPORT_MAX_CHARS]
        truncated = True

    # Construction du message Google Chat (format texte Markdown)
    services_label = (
        ", ".join(report.services_inspected) if report.services_inspected else "tous les services"
    )
    tokens_in = report.usage.get("total_input_tokens", 0)
    tokens_out = report.usage.get("total_output_tokens", 0)
    cost = report.usage.get("estimated_cost_usd", 0.0)

    header = (
        f"{emoji} *TRIAGE SRE {report.severity}* — `{env}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 Fenêtre : -{report.hours}h  |  🎯 Seuil 5xx : {report.threshold_5xx}"
        f"  |  🔎 Scope : {services_label}\n"
        f"⏰ Déclenché le : {report.triggered_at[:19].replace('T', ' ')} UTC\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    footer = (
        f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 Tokens : {tokens_in} in / {tokens_out} out  |  💰 Coût estimé : ${cost:.4f}\n"
        f"🔗 Rapport complet : Cloud Logging Explorer — filtre `[SRE-TRIAGE-{report.severity}]`\n"
        f"💬 Triage manuel approfondi : `/sre-report`\n"
        f"⏭️ Prochaine vérification automatique dans ~2h"
    )

    if truncated:
        truncation_notice = (
            f"\n\n_⚠️ Rapport tronqué à {_CHAT_REPORT_MAX_CHARS} caractères"
            " — voir Cloud Logging pour le rapport complet._"
        )
        footer = truncation_notice + footer

    message_text = header + report_body + footer

    payload = {"text": message_text}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            if response.status_code == 200:
                logger.info(
                    "[SRE Chat] Notification Google Chat envoyée avec succès (severity=%s).",
                    report.severity,
                )
            else:
                logger.warning(
                    "[SRE Chat] Webhook a retourné HTTP %d : %s",
                    response.status_code,
                    response.text[:200],
                )
    except Exception as exc:
        # Non-bloquant : une erreur webhook ne doit jamais faire échouer le triage
        logger.warning("[SRE Chat] Erreur envoi webhook Google Chat : %s", exc)


# ---------------------------------------------------------------------------
# Fréquence adaptative — follow-up 30min si CRITICAL
# ---------------------------------------------------------------------------

async def _schedule_followup_check(report: SreTriageReport) -> None:
    """Crée un job Cloud Scheduler one-shot pour relancer le triage dans 30 minutes.

    Déclenchée uniquement quand severity==CRITICAL pour vérifier si l'incident
    est résolu avant le prochain triage planifié à 2h.

    Le job est nommé `sre-triage-followup-<workspace>` et est écrasé s'il existe
    déjà (idempotent — plusieurs CRITICAL consécutifs ne créent qu'un seul follow-up).

    Ne fait rien en local (K_SERVICE absent) ou si les variables GCP sont manquantes.
    """
    project_id = os.environ.get("GCP_PROJECT_ID", "").strip()
    region = os.environ.get("CLOUD_RUN_REGION", "europe-west1").strip()
    service_uri = os.environ.get("CLOUD_RUN_SERVICE_URI", "").strip()
    sa_email = os.environ.get("CLOUD_RUN_SA_EMAIL", "").strip()

    # Variables disponibles uniquement dans Cloud Run (pas en local)
    if not project_id or not service_uri:
        logger.debug("[SRE Followup] Variables GCP absentes — planification ignorée (local dev).")
        return

    try:
        from google.cloud import scheduler_v1  # noqa: PLC0415

        client = scheduler_v1.CloudSchedulerClient()
        parent = f"projects/{project_id}/locations/{region}"
        workspace = os.environ.get("K_SERVICE", "dev").split("-")[-1]
        job_name = f"{parent}/jobs/sre-triage-followup-{workspace}"

        followup_time = datetime.now(timezone.utc) + timedelta(minutes=30)
        cron_schedule = f"{followup_time.minute} {followup_time.hour} * * *"

        body_json = '{"hours": 1, "threshold_5xx": 0}'

        oidc = scheduler_v1.OidcToken(
            service_account_email=sa_email,
            audience=service_uri,
        ) if sa_email else None

        job = scheduler_v1.Job(
            name=job_name,
            description=(
                f"[AUTO] Follow-up SRE 30min — déclenché après CRITICAL détecté le "
                f"{report.triggered_at[:19]} UTC"
            ),
            schedule=cron_schedule,
            time_zone="UTC",
            attempt_deadline="600s",
            http_target=scheduler_v1.HttpTarget(
                uri=f"{service_uri}/tasks/sre-triage",
                http_method=scheduler_v1.HttpMethod.POST,
                body=body_json.encode(),
                headers={"Content-Type": "application/json"},
                oidc_token=oidc,
            ),
        )

        # Upsert : met à jour si le job existe, crée sinon
        try:
            client.get_job(name=job_name)
            client.update_job(job=job)
            logger.info(
                "[SRE Followup] Job Cloud Scheduler mis à jour — suivi dans 30min (%s UTC).",
                followup_time.strftime("%H:%M"),
            )
        except Exception:
            client.create_job(parent=parent, job=job)
            logger.info(
                "[SRE Followup] Job Cloud Scheduler créé — suivi dans 30min (%s UTC).",
                followup_time.strftime("%H:%M"),
            )

    except Exception as exc:
        # Non-bloquant : un échec de planification ne doit pas faire échouer le triage
        logger.warning("[SRE Followup] Erreur planification follow-up Cloud Scheduler : %s", exc)


# ---------------------------------------------------------------------------
# Parsing structuré du rapport Markdown → métriques BigQuery
# ---------------------------------------------------------------------------

def _parse_report_metrics(report: "SreTriageReport") -> dict:
    """Extrait les métriques structurées du rapport Markdown pour stockage BigQuery.

    Analyse le rapport en langage naturel produit par le LLM et en extrait
    les dimensions quantitatives : services par statut, comptages erreurs,
    présence du playbook, etc.

    Robuste par conception : toute erreur de parsing retourne un dict vide
    plutôt que de lever une exception (le triage ne doit jamais échouer
    pour une erreur de parsing de rapport).
    """
    import json as _json
    import re as _re

    text = report.response or ""

    services_critical: list = []
    services_warning: list = []
    services_ok: list = []
    total_5xx = 0
    dq_errors_count = 0

    try:
        # Extraction des services depuis le tableau Markdown
        # Pattern : | service-name | ✅/⚠️/🔴 | ...
        for line in text.splitlines():
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) < 2:
                continue
            svc = cells[0]
            status_cell = cells[1] if len(cells) > 1 else ""
            # Filtrer les lignes d'en-tête
            if svc.lower() in ("service", "---", ""):
                continue
            if _CRITICAL_MARKER in status_cell:
                services_critical.append(svc)
            elif _WARNING_MARKER in status_cell:
                services_warning.append(svc)
            elif _OK_MARKER in status_cell:
                services_ok.append(svc)

            # Comptage 5xx depuis la 3ème colonne si numérique
            if len(cells) > 2:
                m = _re.search(r"\d+", cells[2])
                if m:
                    try:
                        total_5xx += int(m.group())
                    except ValueError:
                        pass

        # Comptage ValidationError dans la section Data Quality
        dq_section_match = _re.search(
            r"Alertes Data Quality(.*?)(?=##|\Z)", text, _re.DOTALL
        )
        if dq_section_match:
            dq_text = dq_section_match.group(1)
            occurrences = _re.findall(r"Occurrence\s*:\s*(\d+)", dq_text)
            dq_errors_count = sum(int(o) for o in occurrences)

    except Exception as parse_exc:
        logger.debug("[SRE Metrics] Erreur parsing rapport : %s", parse_exc)

    playbook_used = "[Playbook indisponible]" not in text and "SRE-" in text
    followup_scheduled = report.severity == "CRITICAL"

    # Extrait du résumé exécutif (1ères lignes après "## Résumé Exécutif")
    excerpt = ""
    try:
        m = _re.search(r"## Résumé Exécutif\s*\n(.*?)(?=\n##|\Z)", text, _re.DOTALL)
        if m:
            excerpt = m.group(1).strip()[:1000]
    except Exception:
        pass

    return {
        "triggered_at": report.triggered_at,
        "env": "prd" if "prd" in (report.source or "") else "dev",
        "severity": report.severity,
        "hours_window": report.hours,
        "services_critical": _json.dumps(services_critical),
        "services_warning": _json.dumps(services_warning),
        "services_ok": _json.dumps(services_ok),
        "total_5xx": total_5xx,
        "dq_errors_count": dq_errors_count,
        "dq_errors_detail": "",  # enrichi si besoin
        "tokens_in": report.usage.get("total_input_tokens", 0),
        "tokens_out": report.usage.get("total_output_tokens", 0),
        "cost_usd": report.usage.get("estimated_cost_usd", 0.0),
        "report_excerpt": excerpt,
        "playbook_used": playbook_used,
        "followup_scheduled": followup_scheduled,
    }


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------

def build_sre_triage_query(request: SreTriageRequest) -> str:
    """Construit la requête en langage naturel structurée pour l'Agent Ops.

    La requête est suffisamment détaillée pour que l'agent utilise proactivement
    ses tools (Cloud Logging, Cloud Trace, monitoring_mcp) sans ambiguïté.
    La Phase 0 demande explicitement à l'agent de charger le playbook SRE.
    """
    services_clause = (
        f"sur les services suivants : {', '.join(request.services)}"
        if request.services
        else "sur tous les services de la plateforme (cv_api, agent_router_api, "
             "agent_hr_api, agent_ops_api, agent_missions_api, users_api, "
             "items_api, competencies_api, missions_api, drive_api, prompts_api)"
    )

    return (
        f"## 🚨 Triage SRE Automatique — Fenêtre -{request.hours}h\n\n"
        f"Effectue un diagnostic complet {services_clause}.\n\n"
        f"### Phase 0 — Chargement du Playbook (OBLIGATOIRE EN PREMIER)\n"
        f"Appelle `get_prompt(key=\"{_PLAYBOOK_KEY}\")` et mémorise les patterns "
        f"d'erreurs connus. Pour chaque anomalie détectée, cross-référencer avec "
        f"le playbook et citer le code applicable (ex: SRE-DB-001) dans le rapport.\n\n"
        f"### Phase 1 — Diagnostic Système\n"
        f"1. **Erreurs 5xx** : Recherche toutes les erreurs HTTP 5xx survenues dans les "
        f"{request.hours} dernière(s) heure(s). Signale celles qui dépassent le seuil de "
        f"{request.threshold_5xx} occurrences.\n"
        f"2. **Latences anormales** : Identifie les requêtes dont la latence P99 dépasse "
        f"le double de la médiane. Récupère les trace IDs des spans les plus lents.\n"
        f"3. **Corrélation logs/traces** : Pour chaque anomalie détectée, utilise "
        f"`search_cloud_logs_by_trace` pour corréler avec les logs d'application.\n"
        f"4. **FinOps** : Signale toute consommation de tokens anormale (>2x la moyenne) "
        f"dans la même fenêtre temporelle.\n\n"
        f"### Phase 2 — Rapport Markdown\n"
        f"Produis un rapport structuré avec :\n"
        f"   - ✅ Services sains (aucune anomalie)\n"
        f"   - ⚠️ Services dégradés (seuil proche ou FinOps à surveiller)\n"
        f"   - 🔴 Services critiques (seuil dépassé — action requise)\n"
        f"   - Pour chaque service dégradé/critique : cause probable + "
        f"**Playbook appliqué : [SRE-XXX-NNN]** + action recommandée\n\n"
        f"Commence immédiatement par le Phase 0 sans attendre de confirmation."
    )


# ---------------------------------------------------------------------------
# Triage runner
# ---------------------------------------------------------------------------

async def run_sre_triage(
    request: SreTriageRequest,
    auth_token: str,
    user_id: str = "scheduler@system",
) -> SreTriageReport:
    """Exécute le triage SRE en déléguant à l'Agent Ops.

    Séquence :
      1. Construction de la requête (query builder)
      2. Exécution via run_agent_query (LLM + tools MCP)
      3. Classification de sévérité (OK / WARNING / CRITICAL)
      4. Émission du log structuré Cloud Logging (rapport complet)
      5. Notification Google Chat si WARNING ou CRITICAL

    Args:
        request:    Paramètres du triage (services, fenêtre, seuil).
        auth_token: Token JWT Bearer pour propager aux MCP servers.
        user_id:    Identifiant de la source du déclenchement.

    Returns:
        SreTriageReport validé par Pydantic.
    """
    # Import local pour éviter une dépendance circulaire au module-level.
    # agent.run_agent_query importe agent_commons qui importe ce module lors des tests.
    from agent import run_agent_query  # noqa: PLC0415

    triggered_at = datetime.now(timezone.utc).isoformat()
    query = build_sre_triage_query(request)

    logger.info(
        "[SRE Triage] Déclenchement — services=%s, hours=%d, threshold_5xx=%d",
        request.services or "ALL",
        request.hours,
        request.threshold_5xx,
    )

    result = await run_agent_query(
        query, session_id=None, auth_token=auth_token, user_id=user_id,
        prompt_key="agent_ops_api.sre_triage.system_instruction",
    )

    report = SreTriageReport(
        triggered_at=triggered_at,
        services_inspected=request.services,
        hours=request.hours,
        threshold_5xx=request.threshold_5xx,
        response=result.get("response", ""),
        steps=result.get("steps", []),
        thoughts=result.get("thoughts", ""),
        usage=result.get("usage", {}),
        source=result.get("source", "ops_agent"),
        severity=classify_report(result.get("response", "")),
    )

    # 1. Log structuré Cloud Logging — rapport COMPLET (sans troncature)
    _emit_structured_log(report)

    # 2. Notification Google Chat — rapport complet dans l'espace SRE
    await _send_chat_notification(report)

    # 3. Fréquence adaptative — follow-up 30min si CRITICAL
    if report.severity == "CRITICAL":
        await _schedule_followup_check(report)

    # 4. Historique BigQuery — métriques structurées via analytics_mcp
    await _push_triage_to_analytics(report, auth_token)

    return report


async def _push_triage_to_analytics(report: SreTriageReport, auth_token: str) -> None:
    """Envoie les métriques du triage dans BigQuery via analytics_mcp.

    Non-bloquant : toute erreur est loggée en WARNING sans interrompre le triage.
    Permet le suivi historique, la détection de tendances et le dashboard Data Quality.
    """
    analytics_url = os.environ.get("ANALYTICS_MCP_URL", "")
    if not analytics_url:
        logger.debug("[SRE Analytics] ANALYTICS_MCP_URL absent — push BigQuery ignoré (local dev).")
        return

    try:
        metrics = _parse_report_metrics(report)
        payload = {
            "tool": "log_sre_triage",
            "arguments": metrics,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{analytics_url}/mcp/call",
                json=payload,
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            if resp.status_code == 200:
                logger.info(
                    "[SRE Analytics] Triage enregistré dans BigQuery (severity=%s, dq_errors=%d).",
                    report.severity,
                    metrics.get("dq_errors_count", 0),
                )
            else:
                logger.warning(
                    "[SRE Analytics] analytics_mcp a retourné HTTP %d : %s",
                    resp.status_code,
                    resp.text[:200],
                )
    except Exception as exc:
        logger.warning("[SRE Analytics] Erreur push BigQuery analytics_mcp : %s", exc)
