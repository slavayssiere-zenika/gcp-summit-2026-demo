from fastapi import APIRouter

# Import the modular routers
from .admin_router import router as admin_router
from .admin_router import public_router as admin_public_router
from .routers.categories_router import router as categories_router
from .routers.search_router import router as search_router
from .crud_router import router as crud_router

# The main router that orchestrates everything
router = APIRouter()
public_router = APIRouter()

# RÈGLE FastAPI : routes statiques avant wildcards (KI fastapi-route-ordering)
# 1. Admin (DOIT être avant les wildcards)
router.include_router(admin_router)
public_router.include_router(admin_public_router)

# 2. Categories + Stats (routes statiques)
router.include_router(categories_router)

# 3. Search + By-user (routes statiques)
router.include_router(search_router)

# 4. CRUD/Wildcards (DOIT être en dernier pour ne pas masquer les routes statiques)
router.include_router(crud_router)
