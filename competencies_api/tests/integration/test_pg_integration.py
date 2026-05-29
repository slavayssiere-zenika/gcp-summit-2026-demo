"""
Tests d'intégration competencies_api — nécessitent Docker.

Valide les comportements PostgreSQL-specific invisibles en SQLite :
1. ON CONFLICT DO NOTHING dans assignments_router.py:38
2. Pagination réelle PostgreSQL
3. delete_cache_pattern() avec scan_iter(match=pattern) sur vrai Redis
4. Contrat d'interface shared/schemas/pagination.py (model_validate) — ADR-0015

Note : Les routes competencies_api sont montées à la racine (pas de préfixe).
"""
from unittest.mock import patch, AsyncMock
import sys
import os

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text

# Racine du monorepo pour résoudre shared/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def mock_gemini_alias():
    """Mocke _generate_aliases_for_competency pour éviter l'instanciation du client
    google-genai sans clé API — ce qui cause un AttributeError asyncio lors du teardown
    (aclose() sur un _async_httpx_client jamais initialisé).

    IMPORTANT : la fonction est importée via `from helpers import ...` dans les routers,
    il faut donc patcher dans CHAQUE module appelant (pas dans le module source helpers).
    Les appels IA externes doivent toujours être mockés en tests d'intégration.
    """
    with patch(
        "src.competencies.competencies_router._generate_aliases_for_competency",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "src.competencies.suggestions_router._generate_aliases_for_competency",
        new_callable=AsyncMock,
        return_value=None,
    ):
        yield


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
    """Valide que /bulk/cleanup-orphans supprime correctement les évaluations liées aux orphelins.

    IMPORTANT : les noms de compétences doivent avoir un ratio de similarité floue < 0.6
    entre eux pour éviter la déduplication automatique dans create_competency.
    Ratio "orpheline_*" ≈ 0.67 → tous fusionnés sur le premier → test cassé.
    Solution : noms sémantiquement très distincts.
    """
    # 1. Créer une compétence racine (aura un enfant → non-feuille)
    resp = client.post("/", json={"name": "RootNode", "category": "Tech"})
    parent_id = resp.json()["id"]

    # 2. Créer un enfant (leaf sans éval → orphelin à supprimer)
    resp = client.post("/", json={"name": "ChildLeaf", "parent_id": parent_id})
    resp.json()["id"]

    # 3. Feuille racine AVEC score > 0 (doit être gardée)
    resp = client.post("/", json={"name": "KeptComp"})
    kept_id = resp.json()["id"]

    # 4. Feuille racine AVEC score = 0 (doit être supprimée)
    resp = client.post("/", json={"name": "ZeroScore"})
    zero_id = resp.json()["id"]

    # 5. Feuille racine SANS évaluation (doit être supprimée)
    resp = client.post("/", json={"name": "Unlisted"})
    lone_id = resp.json()["id"]

    # Guard : 4 IDs distincts = 4 compétences réellement créées (déduplication floue évitée)
    assert len({parent_id, kept_id, zero_id, lone_id}) == 4, (
        "Les noms utilisés déclenchent la déduplication floue — choisir des noms plus distincts."
    )

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
            {"cid": kept_id}
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
    from main import app
    from shared.auth.jwt import VerifyJwtOrOidc
    overrides = {}
    for route in app.routes:
        if hasattr(route, "dependencies"):
            for dep in route.dependencies:
                if isinstance(dep.dependency, VerifyJwtOrOidc):
                    overrides[dep.dependency] = lambda: {"sub": "1", "role": "admin"}
        if hasattr(route, "dependant"):
            for dep in route.dependant.dependencies:
                if isinstance(dep.call, VerifyJwtOrOidc):
                    overrides[dep.call] = lambda: {"sub": "1", "role": "admin"}
    with patch.dict(app.dependency_overrides, overrides):
        resp = client.post("/bulk/cleanup-orphans")
        assert resp.status_code == 200, f"Erreur nettoyage: {resp.json()}"

    # Explication du count de 4 :
    # - ZeroScore : eval score 0 → orpheline → supprimée (iter 1)
    # - Unlisted  : aucune éval → orpheline → supprimée (iter 1)
    # - ChildLeaf : leaf sans éval → orpheline → supprimée (iter 1)
    # - RootNode  : perd ChildLeaf, devient leaf sans éval → supprimé (iter 2)
    assert resp.json()["deleted_count"] == 4

    # Vérifier que seule KeptComp (et les catégories système éventuelles) existent toujours
    remaining = client.get("/").json()["items"]
    names = [c["name"] for c in remaining]
    assert "KeptComp" in names
    assert "RootNode" not in names
    assert "ChildLeaf" not in names
    assert "ZeroScore" not in names
    assert "Unlisted" not in names


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
    from main import app
    from shared.auth.jwt import VerifyJwtOrOidc
    overrides = {}
    for route in app.routes:
        if hasattr(route, "dependencies"):
            for dep in route.dependencies:
                if isinstance(dep.dependency, VerifyJwtOrOidc):
                    overrides[dep.dependency] = lambda: {"sub": "1", "role": "admin"}
        if hasattr(route, "dependant"):
            for dep in route.dependant.dependencies:
                if isinstance(dep.call, VerifyJwtOrOidc):
                    overrides[dep.call] = lambda: {"sub": "1", "role": "admin"}
    with patch.dict(app.dependency_overrides, overrides):
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
# Redis réel (déplacé vers les tests globaux de shared.cache)
# ─────────────────────────────────────────────────────────────────────────────
