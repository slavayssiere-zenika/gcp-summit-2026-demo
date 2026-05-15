import os

import pytest

from shared.tests.zero_trust import assert_zero_trust

# Liste blanche des URL publiques autorisées sans authentification JWT
PUBLIC_WHITELIST = {
    "/",
    "/docs",
    "/google/callback",
    "/google/config",
    "/google/login",
    "/health",
    "/health/agents",
    "/login",
    "/logout",
    "/me",
    "/metrics",
    "/openapi.json",
    "/pubsub",
    "/ready",
    "/redoc",
    "/refresh",
    "/service-account/login",
    "/spec",
    "/sync",
    "/version",
}


def test_all_routes_are_secured_by_jwt():
    """
    Test de sécurité systémique (Zero-Trust)
    Vérifie par introspection stricte que toutes les routes exposées dans l'API
    possèdent bien le paramètre `Depends(verify_jwt)`, à l'exception
    de la liste blanche stricte.
    """
    try:
        if "SECRET_KEY" not in os.environ:
            os.environ["SECRET_KEY"] = "dummy-for-test-" + "x" * 16
        from main import app
    except ImportError:
        pytest.skip("Impossible de charger 'app' depuis main.py.")

    assert_zero_trust(app, PUBLIC_WHITELIST)
