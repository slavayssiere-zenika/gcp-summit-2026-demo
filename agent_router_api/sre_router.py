import os
import httpx
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from shared.auth.jwt import verify_jwt_bearer as verify_jwt
from opentelemetry.propagate import inject

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sre", dependencies=[Depends(verify_jwt)])

@router.post("/improvement")
async def submit_improvement(request: Request, payload: dict = Depends(verify_jwt)):
    """Relaye la demande d'amélioration vers l'agent Ops."""
    data = await request.json()
    ops_url = os.getenv("AGENT_OPS_API_URL", "http://agent_ops_api:8080")
    
    # Propager l'en-tête d'authentification Bearer
    auth_header = request.headers.get("Authorization")
    headers = {"Authorization": auth_header} if auth_header else {}
    inject(headers)
    
    logger.info(
        "[Router SRE] Réception d'une demande d'amélioration pour la session %s. Relai vers %s.",
        data.get("session_id"),
        ops_url,
    )
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            res = await client.post(
                f"{ops_url.rstrip('/')}/sre/improvement",
                json=data,
                headers=headers,
            )
            if res.status_code != 200:
                logger.error(
                    "[Router SRE] Erreur agent Ops (%d) : %s",
                    res.status_code,
                    res.text[:300],
                )
                raise HTTPException(
                    status_code=res.status_code,
                    detail=f"Erreur de l'agent Ops : {res.text}"
                )
            return res.json()
        except httpx.RequestError as exc:
            logger.error("[Router SRE] Échec de communication avec l'agent Ops : %s", exc)
            raise HTTPException(
                status_code=502,
                detail=f"Erreur de communication avec l'agent Ops : {exc}"
            )
