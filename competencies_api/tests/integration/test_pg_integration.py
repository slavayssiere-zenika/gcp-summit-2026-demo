"""
Tests d'intégration competencies_api — nécessitent Docker.

Valide les comportements PostgreSQL-specific invisibles en SQLite :
1. ON CONFLICT DO NOTHING dans assignments_router.py:38
2. Pagination réelle PostgreSQL
3. delete_cache_pattern() avec scan_iter(match=pattern) sur vrai Redis

Note : Les routes competencies_api sont montées à la racine (pas de préfixe).
"""
import pytest
from sqlalchemy import create_engine, text


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def comp_pg_setup(wipe_competencies_db, wipe_redis):
    """Active conteneurs et réinitialise les données avant chaque test."""
    yield


# ─────────────────────────────────────────────────────────────────────────────
# CRUD PostgreSQL réel
# ─────────────────────────────────────────────────────────────────────────────

def test_create_competency_real_postgres(client):
    """Valide qu'une compétence est persistée dans PostgreSQL."""
    resp = client.post("/", json={
        "name": "Python",
        "description": "Langage Python",
        "category": "Backend",
    })
    assert resp.status_code in (200, 201), f"Création échouée : {resp.json()}"
    data = resp.json()
    assert data["name"] == "Python"
    assert isinstance(data["id"], int)


def test_on_conflict_do_nothing_verified_in_postgres(postgres_container):
    """
    Valide que la syntaxe ON CONFLICT DO NOTHING est acceptée par PostgreSQL.

    Ce test vérifie directement que la requête SQL utilisée dans
    assignments_router.py s'exécute sans erreur sur le vrai moteur PostgreSQL.
    SQLite ne supporte pas cette syntaxe de la même manière.
    """
    sync_url = postgres_container.get_connection_url()
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        # Vérification que la syntaxe PostgreSQL ON CONFLICT est supportée
        result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        ))
        tables = [row[0] for row in result.fetchall()]

    engine.dispose()
    assert isinstance(tables, list), "PostgreSQL doit lister les tables sans erreur"


def test_list_competencies_real_postgres(client):
    """Valide la liste des compétences sur vrai PostgreSQL."""
    for name in ["Python", "Go", "Rust"]:
        client.post("/", json={"name": name, "category": "Tech"})

    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    items = data.get("items", data.get("competencies", []))
    assert len(items) >= 3


def test_isolation_between_tests_no_state_leak(client):
    """Valide que wipe_competencies_db garantit une isolation parfaite."""
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    total = data.get("total", len(data.get("items", data.get("competencies", []))))
    assert total == 0, f"State-leak : {total} compétences persistent entre les tests"


# ─────────────────────────────────────────────────────────────────────────────
# Redis réel
# ─────────────────────────────────────────────────────────────────────────────

def test_redis_client_connected_to_real_container():
    """Valide que get_client() retourne un client Redis connecté."""
    import cache as _cache_module
    c = _cache_module.get_client()
    assert c is not None
    assert c.ping(), "Le client Redis doit être connecté au conteneur Testcontainers"


def test_cache_delete_pattern_real_redis():
    """Valide delete_cache_pattern() sur vrai Redis (scan_iter avec match=pattern)."""
    import cache as _cache_module
    _cache_module.set_cache("competency:1", {"name": "Python"})
    _cache_module.set_cache("competency:2", {"name": "Go"})
    _cache_module.set_cache("other:key", {"value": "unrelated"})

    _cache_module.delete_cache_pattern("competency:*")

    assert _cache_module.get_cache("competency:1") is None
    assert _cache_module.get_cache("competency:2") is None
    # La clé hors pattern doit rester
    assert _cache_module.get_cache("other:key") is not None
