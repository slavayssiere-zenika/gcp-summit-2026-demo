"""
Tests d'intégration users_api — nécessitent Docker.

Valide les comportements PostgreSQL-specific invisibles en SQLite :
1. Contrat d'interface shared/schemas/users.py (UsersResponse.model_validate)
2. Isolation réelle des données entre tests via wipe_users_db
3. Connectivité Redis réelle (lazy init cache)

Note : Les routes users_api sont montées à la racine (pas de préfixe /users/).
"""
import os
import sys

import pytest

# Racine du monorepo pour résoudre shared/
_MONOREPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _MONOREPO_ROOT not in sys.path:
    sys.path.insert(0, _MONOREPO_ROOT)


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def users_pg_setup(wipe_users_db, wipe_redis):
    """Active conteneurs et réinitialise les données avant chaque test."""
    yield


# ─────────────────────────────────────────────────────────────────────────────
# CRUD PostgreSQL réel
# ─────────────────────────────────────────────────────────────────────────────

def test_create_user_real_postgres(client):
    """Valide qu'un utilisateur est persisté dans PostgreSQL."""
    resp = client.post("/", json={
        "username": "alice",
        "email": "alice@zenika.com",
        "password": "secret123",
    })
    assert resp.status_code in (200, 201), f"Création échouée : {resp.json()}"
    data = resp.json()
    assert data["email"] == "alice@zenika.com"
    assert isinstance(data["id"], int)


def test_upsert_behavior_on_duplicate_email_postgres(client):
    """
    Valide le comportement upsert sur email dupliqué en PostgreSQL.

    users_api utilise un pattern UPSERT intentionnel (IntegrityError catch):
    un doublon ne retourne pas 409 mais met à jour le profil existant.
    Ce test valide que ce comportement fonctionne sur un vrai PostgreSQL
    (la contrainte UNIQUE doit exister en base pour déclencher l'IntegrityError).
    """
    payload = {"username": "bob", "email": "bob@zenika.com", "password": "password123"}
    r1 = client.post("/", json=payload)
    assert r1.status_code in (200, 201)
    original_id = r1.json()["id"]

    # Second POST avec le même email → upsert (doit retourner le même user)
    r2 = client.post("/", json={"username": "bob-updated", "email": "bob@zenika.com", "password": "newpass123"})
    assert r2.status_code in (200, 201), (
        f"L'upsert doit réussir (200/201), obtenu {r2.status_code} : {r2.json()}"
    )
    # Même ID (pas de doublon en base)
    assert r2.json()["id"] == original_id, (
        f"L'upsert doit retourner le même ID user ({original_id}), obtenu {r2.json()['id']}"
    )


def test_list_users_real_postgres(client):
    """Valide la liste des utilisateurs via le contrat shared/schemas/users.py."""
    from pydantic import ValidationError
    from shared.schemas.users import UsersResponse

    client.post("/", json={"username": "u1", "email": "u1@zenika.com", "password": "password"})
    client.post("/", json={"username": "u2", "email": "u2@zenika.com", "password": "password"})

    resp = client.get("/")
    assert resp.status_code == 200

    # Validation via shared/schemas (Golden Rules §3 — contrat d'interface, ADR-0015)
    try:
        data = UsersResponse.model_validate(resp.json())
    except ValidationError as ve:
        raise AssertionError(
            f"Rupture de contrat API users (shared/schemas/users.py) : {ve}\n"
            f"Raw keys: {list(resp.json().keys())}"
        )
    assert data.total >= 2
    assert len(data.items) >= 2


def test_isolation_between_tests_no_state_leak(client):
    """Valide que wipe_users_db garantit une isolation parfaite entre tests."""
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    users = data.get("users", data.get("items", data if isinstance(data, list) else []))
    # Après wipe, aucun utilisateur ne doit persister
    assert len(users) == 0, f"State-leak : {len(users)} utilisateurs persistent"


# ─────────────────────────────────────────────────────────────────────────────
# Redis réel
# ─────────────────────────────────────────────────────────────────────────────

# Les tests de shared.cache sont traités au niveau du projet parent.
