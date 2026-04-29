from fastapi import APIRouter

from .auth_router import auth_router
from .system_router import router as system_router
from .crud_router import router as crud_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(system_router)
router.include_router(crud_router)
