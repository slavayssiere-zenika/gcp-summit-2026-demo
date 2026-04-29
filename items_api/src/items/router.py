from fastapi import APIRouter

# Import the modular routers
from .admin_router import router as admin_router
from .admin_router import public_router as admin_public_router
from .crud_router import router as crud_router

# The main router that orchestrates everything
router = APIRouter()
public_router = APIRouter()

# 1. Statique/Admin (DOIT être avant les wildcards)
router.include_router(admin_router)
public_router.include_router(admin_public_router)

# 2. CRUD/Wildcards (DOIT être en dernier pour ne pas masquer les routes statiques)
router.include_router(crud_router)
