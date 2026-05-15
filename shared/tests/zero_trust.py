"""
zero_trust.py — Utilitaire de test Zero-Trust partagé.

Usage dans chaque service :

    from shared.tests.zero_trust import assert_zero_trust

    PUBLIC_WHITELIST = {"/health", "/ready", "/metrics", ...}

    def test_all_routes_are_secured_by_jwt():
        from main import app
        assert_zero_trust(app, PUBLIC_WHITELIST)
"""
from fastapi.routing import APIRoute


def assert_zero_trust(app, public_whitelist: set) -> None:
    """Vérifie par introspection FastAPI que toutes les routes (hors whitelist)
    possèdent bien le paramètre `Depends(verify_jwt)`.

    Args:
        app: Instance FastAPI à inspecter.
        public_whitelist: Ensemble de paths URL autorisés sans JWT.

    Raises:
        AssertionError: Si au moins un endpoint est exposé sans JWT.
    """
    unprotected_routes = []

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue

        path = getattr(route, "path", "")

        # Bypass des routes MCP proxy (sidecar interne) — correspondance exacte ou sous-chemin
        if path == "/mcp" or path.startswith("/mcp/") or path.startswith("//mcp/"):
            continue

        # Vérification de la liste blanche
        is_public = any(
            route.path == w or route.path.startswith(f"{w}/")
            for w in public_whitelist
        )
        if is_public:
            continue

        has_jwt = False

        # Recherche via les dépendances du routeur
        if route.dependencies:
            for dep in route.dependencies:
                if (
                    dep.dependency
                    and hasattr(dep.dependency, "__name__")
                    and "verify_jwt" in dep.dependency.__name__
                ):
                    has_jwt = True
                    break

        # Recherche via les dépendances inline (paramètre `_ = Depends(verify_jwt)`)
        if not has_jwt:
            for param in route.dependant.dependencies:
                if (
                    param.call
                    and hasattr(param.call, "__name__")
                    and "verify_jwt" in param.call.__name__
                ):
                    has_jwt = True
                    break

        if not has_jwt:
            unprotected_routes.append(f"{list(route.methods)} {route.path}")

    assert not unprotected_routes, (
        f"\U0001f6a8 SECURITY BREACH (Zero-Trust) : Ces endpoints sont publiquement "
        f"expos\u00e9s sans v\u00e9rification JWT : {unprotected_routes}. "
        f"Vous DEVEZ utiliser `APIRouter(dependencies=[Depends(verify_jwt)])`."
    )
