"""
hitl_router.py — Phase 3 HITL (Human-In-The-Loop) router.

Endpoints exposés :
  POST /hitl/create  — crée une demande d'approbation en Redis (wrapper HTTP de hitl_create_entry)
  POST /hitl/respond — enregistre la décision du manager (approved/rejected)
  GET  /hitl/pending — liste les demandes en attente

Stockage Redis DB 12 (co-localisé avec les sessions Missions) :
  hitl:{hitl_id}:pending  → TTL 30 min  → ciphertext AES-256-GCM (base64)
  hitl:{hitl_id}:response → TTL 24h     → ciphertext AES-256-GCM (base64)

Sécurité (IMP-3) :
  - Les payloads sont chiffrés avec AES-256-GCM avant stockage en Redis.
  - La clé de chiffrement est dérivée de SECRET_KEY via SHA-256 (32B).
  - Le nonce (12B aléatoire) est préfixé au ciphertext : base64(nonce || ciphertext).
  - L'authentification GCM garantit l'intégrité (tamper-proof).

L'agent lit hitl:{hitl_id}:response pour débloquer le flow suspendu.
"""
import base64
import hashlib
import json
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from shared.auth.jwt import verify_jwt_request as verify_jwt
import redis.asyncio as _redis

logger = logging.getLogger(__name__)

# ── Configuration Redis HITL ──────────────────────────────────────────────────
_HITL_PENDING_TTL = int(os.getenv("HITL_PENDING_TTL_SECONDS", "1800"))   # 30 min
_HITL_RESPONSE_TTL = int(os.getenv("HITL_RESPONSE_TTL_SECONDS", "86400"))  # 24h
_HITL_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/12")


# ── Chiffrement AES-256-GCM (IMP-3) ──────────────────────────────────────────

def _derive_hitl_key() -> bytes:
    """Dérive une clé AES-256 (32B) depuis SECRET_KEY via SHA-256.

    La clé est recalculée à chaque appel depuis l'env pour garantir que
    les données chiffrées restent cohérentes avec le SECRET_KEY courant.
    """
    secret = os.getenv("SECRET_KEY", "").encode("utf-8")
    return hashlib.sha256(secret).digest()  # 32B → AES-256


def _encrypt_hitl(data: dict) -> str:
    """Chiffre un dict Python en AES-256-GCM et retourne base64(nonce || ciphertext).

    Le nonce (12B aléatoire) est généré par secrets.token_bytes pour garantir
    l'unicité. Le tag d'authentification GCM (16B) est appendé par AESGCM.

    Args:
        data: Dict Python sérialisable en JSON.

    Returns:
        Chaîne base64 URL-safe : base64(12B_nonce || ciphertext_+_16B_tag)
    """
    key = _derive_hitl_key()
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)           # 96 bits — recommandation NIST pour GCM
    plaintext = json.dumps(data).encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)  # AAD=None
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def _decrypt_hitl(blob: str) -> dict:
    """Déchiffre un blob AES-256-GCM et retourne le dict Python original.

    Args:
        blob: Chaîne base64 retounée par _encrypt_hitl.

    Returns:
        Dict Python reconstitué.

    Raises:
        ValueError: Si le blob est invalide ou si la clé ne correspond pas (tamper).
    """
    key = _derive_hitl_key()
    aesgcm = AESGCM(key)
    raw = base64.urlsafe_b64decode(blob.encode("ascii"))
    nonce, ciphertext = raw[:12], raw[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return json.loads(plaintext.decode("utf-8"))


def _get_hitl_redis():
    """Lazy singleton Redis client for HITL (same DB as Missions sessions)."""
    return _redis.from_url(_HITL_REDIS_URL, decode_responses=True)


# ── Modèles Pydantic ──────────────────────────────────────────────────────────

class HitlRespondRequest(BaseModel):
    hitl_id: str
    decision: str  # "approved" | "rejected"
    comment: str = ""


class HitlCreateRequest(BaseModel):
    """Payload interne — appelé par run_agent_query quand requires_human_approval=True."""
    mission_title: str
    reason: str
    candidates: list[dict] = []
    urgency_level: str = "medium"
    session_id: str = ""


# ── Router protégé ────────────────────────────────────────────────────────────
hitl_router = APIRouter(dependencies=[Depends(verify_jwt)])


def _verify_manager(payload: dict = Depends(verify_jwt)) -> dict:
    """Dépendance RBAC — restreint l'accès aux rôles manager et admin.

    Appelée uniquement sur POST /hitl/respond pour garantir que seul
    un responsable RH peut approuver ou rejeter une demande HITL.

    Raises:
        HTTPException 403: Si le role JWT n'est pas manager/admin/staffing_manager.
    """
    role = payload.get("role", "")
    if role not in ("manager", "admin", "staffing_manager"):
        raise HTTPException(
            status_code=403,
            detail="Accès refusé — rôle 'manager' ou 'admin' requis pour approuver un HITL.",
        )
    return payload


# ── Fonction pure partagée ────────────────────────────────────────────────────

async def hitl_create_entry(
    mission_title: str,
    reason: str,
    candidates: list | None = None,
    urgency_level: str = "medium",
    session_id: str = "",
) -> dict:
    """Crée une demande HITL en Redis et retourne {hitl_id, expires_at, success}.

    Fonction pure appelable directement depuis agent.py sans aller-retour HTTP.
    Utilisée aussi par l'endpoint /hitl/create comme wrapper.

    Args:
        mission_title: Titre de la mission nécessitant validation.
        reason: Explication du besoin de validation humaine.
        candidates: Liste de candidats recommandés (dicts).
        urgency_level: "low" | "medium" | "high".
        session_id: ID de session A2A pour retrouver la conversation.

    Returns:
        {"hitl_id": str, "expires_at": str (ISO8601), "success": True}

    Raises:
        Exception: propagée si Redis est indisponible.
    """
    hitl_id = str(uuid.uuid4())
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=_HITL_PENDING_TTL)
    ).isoformat()

    payload_data = {
        "hitl_id": hitl_id,
        "mission_title": mission_title,
        "reason": reason,
        "candidates": candidates or [],
        "urgency_level": urgency_level,
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at,
    }

    r = _get_hitl_redis()
    await r.setex(f"hitl:{hitl_id}:pending", _HITL_PENDING_TTL, _encrypt_hitl(payload_data))
    await r.close()
    logger.info("[HITL] Demande créée hitl_id=%s mission='%s'", hitl_id, mission_title)
    return {"hitl_id": hitl_id, "expires_at": expires_at, "success": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@hitl_router.post("/hitl/respond")
async def hitl_respond(
    request: HitlRespondRequest,
    payload: dict = Depends(_verify_manager),  # RBAC: manager/admin uniquement
):
    """Enregistre la décision humaine (approved/rejected) en Redis.

    Réservé aux rôles manager et admin (vérifié par _verify_manager).
    L'agent Missions (run_agent_query) peut surveiller la clé hitl:{hitl_id}:response
    pour débloquer le flow suspendu — pattern long-polling ou webhook.
    """
    if request.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision doit être 'approved' ou 'rejected'")

    try:
        r = _get_hitl_redis()
        pending_key = f"hitl:{request.hitl_id}:pending"
        pending_raw = await r.get(pending_key)
        if pending_raw is None:
            await r.close()
            raise HTTPException(
                status_code=404,
                detail=f"Demande HITL '{request.hitl_id}' introuvable ou expirée.",
            )

        # Déchiffrement AES-256-GCM (IMP-3)
        try:
            _decrypt_hitl(pending_raw)  # Vérification d'intégrité + existence
        except Exception:
            await r.close()
            logger.warning("[HITL] Pending hitl_id=%s : blob invalide ou clé incorrecte", request.hitl_id)
            raise HTTPException(
                status_code=404,
                detail=f"Demande HITL '{request.hitl_id}' introuvable ou expirée.",
            )

        response_payload = {
            "hitl_id": request.hitl_id,
            "decision": request.decision,
            "comment": request.comment,
            "decided_at": datetime.now(timezone.utc).isoformat(),
        }
        await r.setex(
            f"hitl:{request.hitl_id}:response",
            _HITL_RESPONSE_TTL,
            _encrypt_hitl(response_payload),
        )
        await r.delete(pending_key)
        await r.close()

        logger.info(
            "[HITL] Decision '%s' enregistrée pour hitl_id=%s",
            request.decision, request.hitl_id,
        )
        return {
            "success": True,
            "message": f"Décision '{request.decision}' enregistrée avec succès.",
            "hitl_id": request.hitl_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[HITL] Erreur hitl_respond: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur Redis HITL: {type(e).__name__}")


@hitl_router.get("/hitl/pending")
async def hitl_pending():
    """Liste les demandes HITL en attente pour l'utilisateur courant."""
    try:
        r = _get_hitl_redis()
        keys = await r.keys("hitl:*:pending")
        pending = []
        for key in keys:
            raw = await r.get(key)
            if raw:
                try:
                    data = _decrypt_hitl(raw)
                    pending.append(data)
                except Exception as dec_err:
                    logger.warning("[HITL] Clé %s — déchiffrement échoué : %s", key, dec_err)
        await r.close()
        return {"pending": pending, "count": len(pending)}
    except Exception as e:
        logger.error("[HITL] Erreur hitl_pending: %s", e, exc_info=True)
        return {"pending": [], "count": 0, "error": str(e)}


@hitl_router.post("/hitl/create")
async def hitl_create(request: HitlCreateRequest):
    """Crée une demande HITL en Redis — wrapper HTTP autour de hitl_create_entry().

    Retourne le hitl_id et expires_at pour inclusion dans la réponse A2A
    → le frontend affiche le composant HitlApproval.vue.
    Pour un appel interne depuis agent.py, utiliser directement hitl_create_entry().
    """
    try:
        return await hitl_create_entry(
            mission_title=request.mission_title,
            reason=request.reason,
            candidates=request.candidates,
            urgency_level=request.urgency_level,
            session_id=request.session_id,
        )
    except Exception as e:
        logger.error("[HITL] Erreur hitl_create: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur Redis HITL create: {type(e).__name__}")
