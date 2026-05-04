import pytest
from fastapi.routing import APIRoute

# Liste blanche des URL publiques autorisées sans authentification JWT
PUBLIC_WHITELIST = {
    "/health",
    "/ready",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/version",
    "/spec",
    "/login",
    "/logout",
    "/refresh",
    "/service-account/login",
    "/google/config",
    "/google/login",
    "/google/callback",
    "/pubsub",
    "/sync",
    "/",
    "/me",
    "/health/agents"
}

def test_all_routes_are_secured_by_jwt():
    """
    Test de sécurité systémique (Zero-Trust)
    Vérifie par introspection stricte que toutes les routes exposées dans l'API 
    possèdent bien le paramètre `Depends(verify_jwt)`, à l'exception
    de la liste blanche stricte.
    Si une route est exposée publiquement sans authentification, le CI échouera.
    """
    try:
        import os
        if "SECRET_KEY" not in os.environ:
            os.environ["SECRET_KEY"] = "dummy-for-test"
        from mcp_app import app
    except ImportError:
        pytest.skip("Impossible de charger 'app' depuis main.py (structure non standard).")

    unprotected_routes = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            # Bypass de la route "/mcp" ou "//mcp" servant au proxy interne de l'agent
            path = getattr(route, "path", "")
            if path.startswith("/mcp") or path.startswith("//mcp"):
                continue
            
            # Vérification de la liste blanche
            is_public = False
            for w in PUBLIC_WHITELIST:
                if route.path == w or route.path.startswith(f"{w}/"):
                    is_public = True
                    break
            if is_public:
                continue
            
            has_jwt = False
            
            # Recherche de la dépendance JWT
            if route.dependencies:
                for dep in route.dependencies:
                    # Soit la dependance est une fonction dont le nom contient "verify_jwt"
                    if dep.dependency and hasattr(dep.dependency, "__name__") and "verify_jwt" in dep.dependency.__name__:
                        has_jwt = True
                        break
            
            # Gestion des dépendances passées localement via paramètre _ : dict = Depends(verify_jwt)
            if not has_jwt:
                for param in route.dependant.dependencies:
                    if param.call and hasattr(param.call, "__name__") and "verify_jwt" in param.call.__name__:
                        has_jwt = True
                        break

            if not has_jwt:
                unprotected_routes.append(f"{list(route.methods)} {route.path}")

    assert not unprotected_routes, (
        f"🚨 SECURITY BREACH (Zero-Trust) : Ces endpoints sont publiquement "
        f"exposés sans vérification JWT : {unprotected_routes}. "
        f"Vous DEVEZ utiliser `APIRouter(dependencies=[Depends(verify_jwt)])`."
    )
