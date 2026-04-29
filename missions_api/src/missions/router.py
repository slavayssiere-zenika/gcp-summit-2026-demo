from fastapi import APIRouter, Depends
from src.auth import verify_jwt

from .analysis_router import router as analysis_router
from .crud_router import router as crud_router
from .user_router import router as user_router

router = APIRouter(prefix="", tags=["Missions"], dependencies=[Depends(verify_jwt)])
public_router = APIRouter(prefix="", tags=["Public"])

# Ordre d'enregistrement critique : statique avant dynamique
router.include_router(analysis_router)
router.include_router(crud_router)
router.include_router(user_router)

__all__ = ["router", "public_router"]
