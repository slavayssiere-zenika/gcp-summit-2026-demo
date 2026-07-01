import logging
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from shared.auth.jwt import verify_jwt_bearer as verify_jwt
from agent_commons.mcp_client import auth_header_var

logger = logging.getLogger(__name__)

bug_router = APIRouter(prefix="/sre", dependencies=[Depends(verify_jwt)])


class MessageSchema(BaseModel):
    role: str
    content: str


class ImprovementRequest(BaseModel):
    session_id: str = Field(description="L'ID de session de la discussion concernée.")
    user_comment: str = Field(description="Le commentaire/description fourni par l'utilisateur.")
    session_history: list[MessageSchema] = Field(
        default_factory=list,
        description="L'historique des messages échangés lors de la session."
    )


def _get_webhook_url() -> str:
    """Récupère l'URL du webhook Google Chat de manière sécurisée."""
    webhook_url = os.environ.get("GOOGLE_CHAT_WEBHOOK_URL", "").strip()
    if webhook_url:
        return webhook_url

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
        if not val or "PLACEHOLDER" in val:
            return ""
        return val
    except Exception as exc:
        logger.warning(
            "Impossible d'accéder au secret %s via Secret Manager (non-bloquant) : %s",
            secret_name,
            exc,
        )
        return ""


async def _send_chat_notification(
    user_email: str,
    session_id: str,
    user_comment: str,
    analysis_text: str
) -> None:
    """Envoie la demande d'amélioration et son analyse SRE sur Google Chat."""
    webhook_url = _get_webhook_url()
    if not webhook_url:
        logger.debug("[SRE Improvement] Webhook Google Chat absent ou inaccessible — notification ignorée.")
        return

    env = os.environ.get("K_SERVICE", "local").split("-")[-1]

    # Construction du message Google Chat
    header = (
        f"💡 *DEMANDE D'AMÉLIORATION UTILISATEUR* — `{env}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Utilisateur : `{user_email}`\n"
        f"🆔 Session ID : `{session_id}`\n"
        f"💬 Demande utilisateur : *\"{user_comment}\"*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    body = (
        "🤖 *Première analyse de l'Agent SRE :*\n"
        f"{analysis_text}\n"
    )

    footer = (
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💬 _Généré à la demande de l'utilisateur via la console_"
    )

    # Limite de taille pour éviter l'échec de publication (limite ~4096 chars pour Google Chat)
    total_len = len(header) + len(body) + len(footer)
    if total_len > 4000:
        available_space = 4000 - len(header) - len(footer)
        body = body[:available_space] + "\n\n_(analyse tronquée car trop longue)_"

    message_text = header + body + footer
    payload = {"text": message_text}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            if response.status_code == 200:
                logger.info("[SRE Improvement] Notification Google Chat envoyée avec succès.")
            else:
                logger.warning(
                    "[SRE Improvement] Webhook a retourné HTTP %d : %s",
                    response.status_code,
                    response.text[:200],
                )
    except Exception as exc:
        logger.warning("[SRE Improvement] Erreur envoi webhook Google Chat : %s", exc)


@bug_router.post("/improvement")
async def handle_improvement_request(
    request: Request,
    body: ImprovementRequest,
    payload: dict = Depends(verify_jwt)
):
    """Exécute l'analyse SRE sur la demande d'amélioration et la publie dans le Webhook."""
    # Import local pour éviter une dépendance circulaire
    from agent import run_agent_query

    user_email = payload.get("sub", "unknown@zenika.com")
    logger.info(
        "[SRE Improvement] Nouvelle demande d'amélioration reçue pour la session %s de la part de %s",
        body.session_id,
        user_email,
    )

    # Formater l'historique de conversation
    history_lines = []
    for msg in body.session_history:
        history_lines.append(f"- **{msg.role.upper()}**: {msg.content}")
    history_formatted = "\n".join(history_lines)

    # Construire la requête en langage naturel pour l'Agent Ops
    agent_query = (
        f"## 💡 Demande d'Amélioration & Diagnostic SRE\n\n"
        f"Un utilisateur ({user_email}) a demandé une amélioration ou signalé un dysfonctionnement sur la plateforme.\n"
        f"Voici son commentaire : \"{body.user_comment}\"\n\n"
        f"### Historique de la session associée :\n"
        f"{history_formatted}\n\n"
        f"### Objectifs de l'analyse :\n"
        f"1. Analyse le commentaire et l'historique de la session.\n"
        f"2. Utilise tes outils (Cloud Logging, Cloud Trace, AlloyDB) si l'historique ou le commentaire suggère "
        f"une erreur technique, une latence anormale ou un dysfonctionnement sur un service de la plateforme.\n"
        f"3. Rédige une synthèse technique (causes probables, impact, suggestions d'amélioration ou de correctifs).\n"
        f"4. Produis un diagnostic structuré au format Markdown, court et précis (max 2000 caractères)."
    )

    auth_header = request.headers.get("Authorization")
    auth_header_var.set(auth_header)

    try:
        # Lancer la requête auprès de l'agent Ops
        agent_result = await run_agent_query(
            query=agent_query,
            session_id=body.session_id,
            auth_token=auth_header,
            user_id=user_email,
            prompt_key="agent_ops_api.system_instruction",
        )

        analysis = agent_result.get("response", "L'agent n'a pas pu générer d'analyse.")

        # Envoyer la notification webhook en tâche de fond
        await _send_chat_notification(
            user_email=user_email,
            session_id=body.session_id,
            user_comment=body.user_comment,
            analysis_text=analysis,
        )

        return {
            "success": True,
            "message": "Demande d'amélioration analysée et transmise à l'équipe SRE.",
            "analysis": analysis,
        }
    except Exception as exc:
        logger.error("[SRE Improvement] Erreur critique lors de l'analyse de l'amélioration : %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne lors du traitement : {exc}"
        )
