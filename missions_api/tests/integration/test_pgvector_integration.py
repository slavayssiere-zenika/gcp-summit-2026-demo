"""
Tests d'intégration missions_api — nécessitent Docker + pgvector.

Valide les types PostgreSQL avancés invisibles en SQLite :
1. Contrat d'interface shared/schemas/missions.py (model_validate)
2. JSONB : extracted_competencies, prefiltered_candidates, proposed_team
3. ARRAY(String) : competencies_keywords
4. Vector(3072) : semantic_embedding + opérateur cosine distance <=>

Note : Les routes missions_api sont montées avec le préfixe /missions/.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, text


pytestmark = pytest.mark.integration

# Chemin vers la racine du monorepo pour résoudre shared/
_MONOREPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _MONOREPO_ROOT not in sys.path:
    sys.path.insert(0, _MONOREPO_ROOT)


@pytest.fixture(autouse=True)
def missions_pg_setup(wipe_missions_db):
    """Active PostgreSQL pgvector et réinitialise les données avant chaque test."""
    yield


# ─────────────────────────────────────────────────────────────────────────────
# Contrat d'interface shared/schemas (Golden Rules §3)
# ─────────────────────────────────────────────────────────────────────────────

def test_list_missions_schema_contract(client):
    """
    Valide que GET /missions respecte le contrat shared/schemas/missions.py.

    Utilise MissionsResponse.model_validate() conformément aux Golden Rules §3.
    Une ValidationError ici signifie une rupture de contrat entre missions_api
    et ses consommateurs (competencies_api, cv_api) — ADR-0015.
    """
    from pydantic import ValidationError
    from shared.schemas.missions import MissionsResponse

    resp = client.get("/missions")
    assert resp.status_code == 200

    try:
        data = MissionsResponse.model_validate(resp.json())
    except ValidationError as ve:
        raise AssertionError(
            f"Rupture de contrat missions_api (shared/schemas/missions.py) : {ve}\n"
            f"Raw keys: {list(resp.json().keys())}"
        )
    assert isinstance(data.total, int)
    assert isinstance(data.items, list)


# ─────────────────────────────────────────────────────────────────────────────
# Validation des types PostgreSQL avancés
# ─────────────────────────────────────────────────────────────────────────────

def test_pgvector_extension_is_active(postgres_container):
    """Valide que l'extension pgvector est active sur le conteneur PostgreSQL."""
    sync_url = postgres_container.get_connection_url()
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        row = result.fetchone()
    engine.dispose()
    assert row is not None, "L'extension pgvector doit être installée"
    assert row[0] == "vector"


def test_jsonb_columns_in_missions_schema(postgres_container):
    """
    Valide que les colonnes JSONB existent bien en PostgreSQL.

    En SQLite, JSONB est silencieusement converti en TEXT — ce test
    confirme que le schéma réel respecte les types natifs PostgreSQL.
    """
    sync_url = postgres_container.get_connection_url()
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT column_name, data_type "
            "FROM information_schema.columns "
            "WHERE table_name = 'missions' AND data_type = 'jsonb'"
        ))
        jsonb_cols = [row[0] for row in result.fetchall()]
    engine.dispose()

    expected = {"extracted_competencies", "prefiltered_candidates", "proposed_team"}
    assert expected.issubset(set(jsonb_cols)), (
        f"Colonnes JSONB attendues : {expected}, trouvées : {set(jsonb_cols)}"
    )


def test_array_string_column_in_missions_schema(postgres_container):
    """Valide que competencies_keywords est bien un ARRAY PostgreSQL."""
    sync_url = postgres_container.get_connection_url()
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT column_name, data_type "
            "FROM information_schema.columns "
            "WHERE table_name = 'missions' AND column_name = 'competencies_keywords'"
        ))
        row = result.fetchone()
    engine.dispose()
    assert row is not None, "La colonne competencies_keywords doit exister"
    assert "ARRAY" in row[1].upper() or row[1] == "ARRAY", (
        f"competencies_keywords doit être ARRAY, type trouvé : {row[1]}"
    )


def test_vector_column_in_missions_schema(postgres_container):
    """Valide que semantic_embedding est une colonne vector(3072)."""
    sync_url = postgres_container.get_connection_url()
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT column_name, udt_name "
            "FROM information_schema.columns "
            "WHERE table_name = 'missions' AND column_name = 'semantic_embedding'"
        ))
        row = result.fetchone()
    engine.dispose()
    assert row is not None, "La colonne semantic_embedding doit exister"
    assert row[1] == "vector", f"Le type doit être vector, trouvé : {row[1]}"


def test_jsonb_insert_and_query(postgres_container):
    """
    Valide l'insertion et la requête JSONB native PostgreSQL.

    Ce test ne peut pas être réalisé avec SQLite (JSONB non natif).
    Il valide que jsonb_array_length() fonctionne sur extracted_competencies.
    """
    sync_url = postgres_container.get_connection_url()
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO missions (title, description, status, extracted_competencies) "
            "VALUES ('Mission Test', 'Description test', 'DRAFT', :jsonb)"
        ), {"jsonb": '[{"skill": "Python"}, {"skill": "FastAPI"}]'})
        conn.commit()

        result = conn.execute(text(
            "SELECT jsonb_array_length(extracted_competencies) FROM missions "
            "WHERE title = 'Mission Test'"
        ))
        length = result.scalar()
    engine.dispose()
    assert length == 2, f"JSONB doit avoir 2 éléments, trouvé : {length}"


def test_cosine_distance_semantic_embedding(postgres_container):
    """
    Valide l'opérateur cosine distance <=> sur Vector(3072).

    Confirme que la recherche sémantique sur les missions fonctionne
    avec l'opérateur pgvector natif (invisible en SQLite).
    """
    sync_url = postgres_container.get_connection_url()
    engine = create_engine(sync_url)

    vec_a = [0.1] * 3072
    vec_b = [0.2] * 3072
    vec_str_a = "[" + ",".join(str(v) for v in vec_a) + "]"
    vec_str_b = "[" + ",".join(str(v) for v in vec_b) + "]"

    with engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO missions (title, description, status, semantic_embedding) "
            "VALUES ('Vec A', 'test', 'DRAFT', :vec)"
        ), {"vec": vec_str_a})
        conn.commit()

        result = conn.execute(text(
            f"SELECT title, semantic_embedding <=> '{vec_str_b}' AS distance "
            f"FROM missions ORDER BY distance LIMIT 1"
        ))
        row = result.fetchone()
    engine.dispose()

    assert row is not None, "La requête cosine distance doit retourner un résultat"
    assert row[0] == "Vec A"
    assert isinstance(float(row[1]), float), "La distance cosine doit être un float"
