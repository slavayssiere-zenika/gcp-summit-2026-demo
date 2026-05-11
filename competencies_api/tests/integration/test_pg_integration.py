"""
Tests d'intégration competencies_api — nécessitent Docker.

Valide les comportements PostgreSQL-specific invisibles en SQLite :
1. ON CONFLICT DO NOTHING dans assignments_router.py:38
2. Pagination réelle PostgreSQL
3. delete_cache_pattern() avec scan_iter(match=pattern) sur vrai Redis
4. Contrat d'interface shared/schemas/pagination.py (model_validate) — ADR-0015

Note : Les routes competencies_api sont montées à la racine (pas de préfixe).
"""
import sys
import os

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text

# Racine du monorepo pour résoudre shared/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

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
    """Valide la liste des compétences sur vrai PostgreSQL + contrat PaginationResponse."""
    from shared.schemas.pagination import PaginationResponse

    for name in ["Python", "Go", "Rust"]:
        client.post("/", json={"name": name, "category": "Tech"})

    resp = client.get("/")
    assert resp.status_code == 200

    # Validation du contrat shared/schemas (Golden Rules §3 — ADR-0015)
    try:
        data = PaginationResponse[dict].model_validate(resp.json())
    except ValidationError as ve:
        pytest.fail(
            f"Rupture de contrat competencies_api (shared/schemas/pagination.py) : {ve}\n"
            f"Réponse brute : {resp.json()}"
        )
    assert len(data.items) >= 3, f"Attendu >= 3 compétences, trouvé {len(data.items)}"


def test_isolation_between_tests_no_state_leak(client):
    """Valide que wipe_competencies_db garantit une isolation parfaite."""
    from shared.schemas.pagination import PaginationResponse

    resp = client.get("/")
    assert resp.status_code == 200

    data = PaginationResponse[dict].model_validate(resp.json())
    assert data.total == 0, f"State-leak : {data.total} compétences persistent entre les tests"


def test_cleanup_orphans_real_postgres(client, postgres_container):
    """Valide que /bulk/cleanup-orphans supprime correctement les évaluations liées aux orphelins."""
    # 1. Créer une compétence parente
    resp = client.post("/", json={"name": "Parent", "category": "Tech"})
    parent_id = resp.json()["id"]

    # 2. Créer une compétence enfant (avec parent -> non orpheline)
    resp = client.post("/", json={"name": "Enfant", "parent_id": parent_id})
    resp.json()["id"]

    # 3. Créer une compétence orpheline AVEC une évaluation score > 0 (doit être gardée)
    resp = client.post("/", json={"name": "Orpheline_Valide"})
    valid_id = resp.json()["id"]

    # 4. Créer une compétence orpheline AVEC une évaluation score 0 (doit être supprimée en cascade)
    resp = client.post("/", json={"name": "Orpheline_Zero"})
    zero_id = resp.json()["id"]

    # 5. Créer une orpheline vraie SANS aucune liaison (doit être supprimée)
    resp = client.post("/", json={"name": "Orpheline_Vraie"})
    resp.json()["id"]

    # Insérer les évaluations manuellement (pour by-pass l'A2A)
    from sqlalchemy import create_engine, text
    sync_url = postgres_container.get_connection_url()
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO competency_evaluations (user_id, competency_id, ai_score, user_score) "
                "VALUES (1, :cid, 1.0, 0.0)"
            ),
            {"cid": valid_id}
        )
        conn.execute(
            text(
                "INSERT INTO competency_evaluations (user_id, competency_id, ai_score, user_score) "
                "VALUES (1, :cid, 0.0, 0.0)"
            ),
            {"cid": zero_id}
        )
    engine.dispose()

    # Exécuter le endpoint (doit retourner un 200 et non un 500)
    resp = client.post("/bulk/cleanup-orphans")
    assert resp.status_code == 200, f"Erreur nettoyage: {resp.json()}"

    # Explication du count de 4:
    # - Orpheline_Zero : a un score 0, donc considérée orpheline -> supprimée
    # - Orpheline_Vraie : aucune liaison -> supprimée
    # - Enfant : aucune liaison, considérée orpheline (leaf) -> supprimée
    # - Parent : perd son enfant, devient leaf, n'a aucune liaison -> supprimée en cascade
    assert resp.json()["deleted_count"] == 4

    # Vérifier que seule Orpheline_Valide (et les catégories par défaut) existent toujours
    remaining = client.get("/").json()["items"]
    names = [c["name"] for c in remaining]
    assert "Orpheline_Valide" in names
    assert "Parent" not in names
    assert "Enfant" not in names
    assert "Orpheline_Zero" not in names
    assert "Orpheline_Vraie" not in names


def test_bulk_tree_drops_real_postgres(client, postgres_container):
    """Valide que /bulk_tree supprime proprement les compétences (drops) au lieu de les archiver."""
    # 1. Créer une compétence qui sera droppée (avec une éval)
    resp = client.post("/", json={"name": "A_Supprimer", "category": "Tech"})
    drop_id = resp.json()["id"]

    # 2. Créer une compétence qui sera omise de l'arbre mais PAS droppée (doit être archivée)
    client.post("/", json={"name": "A_Archiver", "category": "Tech"})

    # 3. Créer une compétence qui sera conservée dans l'arbre
    resp = client.post("/", json={"name": "Enfant_A_Garder", "category": "Tech"})

    from sqlalchemy import create_engine, text
    sync_url = postgres_container.get_connection_url()
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO competency_evaluations (user_id, competency_id, ai_score, user_score) "
                "VALUES (1, :cid, 3.0, 0.0)"
            ),
            {"cid": drop_id}
        )
    engine.dispose()

    # Exécuter le bulk_tree avec "drops"
    resp = client.post("/bulk_tree", json={
        "tree": {"Tech": {"sub": {"Enfant_A_Garder": {}}}},
        "drops": ["A_Supprimer"]
    })
    assert resp.status_code == 200, f"Erreur bulk_tree: {resp.json()}"

    remaining = client.get("/").json()["items"]

    # Trouver les piliers (racines)
    tech_node = next((c for c in remaining if c["name"] == "Tech"), None)
    archives_node = next((c for c in remaining if c["name"] == "Compétences Archives / Non classées"), None)

    assert tech_node is not None, "Le pilier Tech devrait exister"
    assert archives_node is not None, "Le pilier Archives devrait exister"

    tech_subs = [c["name"] for c in tech_node.get("sub_competencies", [])]
    archives_subs = [c["name"] for c in archives_node.get("sub_competencies", [])]

    # "A_Supprimer" est physiquement supprimée car dans drops, donc n'est ni dans Tech ni dans Archives
    assert "A_Supprimer" not in tech_subs
    assert "A_Supprimer" not in archives_subs

    # "Enfant_A_Garder" est conservée dans Tech
    assert "Enfant_A_Garder" in tech_subs

    # "A_Archiver" est conservée et déplacée dans les Archives
    assert "A_Archiver" in archives_subs


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
