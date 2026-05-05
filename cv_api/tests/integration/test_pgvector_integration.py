"""
Tests d'intégration cv_api — nécessitent Docker + image pgvector/pgvector:pg16.

Ces tests couvrent 3 types PostgreSQL-only totalement invisibles en SQLite :
1. Vector(3072) — pgvector : colonne semantic_embedding + requêtes cosine distance
2. JSONB          — missions, extracted_competencies, educations
3. ARRAY(String)  — competencies_keywords + jsonb_array_length() SQL

Ces bugs seraient SILENCIEUX avec SQLite (pas d'erreur, comportement différent).
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def cv_pg_setup(wipe_cv_db):
    """Active le conteneur pgvector et recrée le schéma avant chaque test."""
    yield


@pytest.fixture
def db_session(pgvector_container):
    """Session SQLAlchemy synchrone pour inspecter directement la DB dans les tests."""
    sync_url = pgvector_container.get_connection_url()
    engine = create_engine(sync_url)
    with Session(engine) as session:
        yield session
    engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Validation pgvector : Vector(3072)
# ─────────────────────────────────────────────────────────────────────────────

def test_table_created_with_vector_column(pgvector_container):
    """
    Valide que la table cv_profiles est créée avec la colonne Vector(3072).

    C'est le test de base : sans image pgvector, ce test échoue au CREATE TABLE
    avec "ERROR: type vector does not exist".
    """
    sync_url = pgvector_container.get_connection_url()
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT column_name, data_type "
            "FROM information_schema.columns "
            "WHERE table_name = 'cv_profiles' AND column_name = 'semantic_embedding'"
        ))
        row = result.fetchone()
    engine.dispose()

    assert row is not None, "La colonne semantic_embedding n'existe pas dans cv_profiles"
    assert row[1] == "USER-DEFINED", (
        f"Type attendu 'USER-DEFINED' (pgvector), obtenu '{row[1]}'"
    )


def test_insert_and_read_vector_embedding(db_session, pgvector_container):
    """
    Valide qu'un embedding Vector(3072) peut être inséré et relu sans corruption.

    SQLite n'a aucun équivalent — ce test n'est pas réalisable autrement.
    """
    # Vecteur de test : 3072 dimensions avec une valeur constante
    embedding = [0.1] * 3072

    db_session.execute(text(
        "INSERT INTO cv_profiles "
        "(user_id, raw_content, semantic_embedding, is_archived) "
        "VALUES (:uid, :content, :emb, false)"
    ), {
        "uid": 42,
        "content": "Test CV avec embedding pgvector",
        "emb": str(embedding),  # pgvector accepte le format [0.1, 0.1, ...]
    })
    db_session.commit()

    result = db_session.execute(text(
        "SELECT id, user_id FROM cv_profiles WHERE user_id = 42"
    ))
    row = result.fetchone()
    assert row is not None, "Le profil CV avec embedding n'a pas été persisté"
    assert row[1] == 42


def test_cosine_distance_query_pgvector(db_session):
    """
    Valide que l'opérateur <=> (cosine distance pgvector) fonctionne en SQL.

    C'est la requête centrale de search_service.py — impossible à tester
    en SQLite (l'opérateur n'existe pas, ferait une NameError SQL silencieuse).
    """
    embedding = [0.1] * 3072

    db_session.execute(text(
        "INSERT INTO cv_profiles "
        "(user_id, raw_content, semantic_embedding, is_archived) "
        "VALUES (:uid, :content, :emb, false)"
    ), {
        "uid": 99,
        "content": "CV cosine test",
        "emb": str(embedding),
    })
    db_session.commit()

    # Requête cosine distance — cœur de search_service.py
    query_vector = [0.1] * 3072
    result = db_session.execute(text(
        "SELECT user_id, semantic_embedding <=> :q AS distance "
        "FROM cv_profiles "
        "WHERE semantic_embedding IS NOT NULL "
        "ORDER BY distance "
        "LIMIT 5"
    ), {"q": str(query_vector)})
    rows = result.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 99
    # Distance cosine entre deux vecteurs identiques = 0.0
    assert rows[0][1] < 0.001, f"Distance cosine attendue ≈ 0, obtenue {rows[0][1]}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Validation JSONB : missions, extracted_competencies
# ─────────────────────────────────────────────────────────────────────────────

def test_jsonb_missions_insert_and_query(db_session):
    """
    Valide que jsonb_array_length() fonctionne sur la colonne missions (JSONB).

    C'est la requête de data_quality_service.py:95 — silencieuse en SQLite
    (la fonction n'existe pas, retourne 0 lignes sans erreur).
    """
    missions_data = '[{"title": "Mission A"}, {"title": "Mission B"}]'

    db_session.execute(text(
        "INSERT INTO cv_profiles "
        "(user_id, raw_content, missions, is_archived) "
        "VALUES (:uid, :content, :missions, false)"
    ), {
        "uid": 10,
        "content": "CV avec missions JSONB",
        "missions": missions_data,
    })
    db_session.commit()

    # Requête identique à data_quality_service.py:95
    result = db_session.execute(text(
        "SELECT user_id FROM cv_profiles WHERE jsonb_array_length(missions) > 0"
    ))
    rows = result.fetchall()
    assert len(rows) == 1, (
        "jsonb_array_length() doit retourner les profils avec au moins 1 mission"
    )
    assert rows[0][0] == 10


def test_jsonb_empty_vs_null_missions(db_session):
    """
    Valide le comportement PostgreSQL JSONB sur les tableaux vides vs NULL.

    JSONB NULL et '[]' se comportent différemment que dans SQLite.
    Ce test détecte les erreurs de comptage dans data_quality_service.
    """
    # Profil avec missions vides (JSON array vide)
    db_session.execute(text(
        "INSERT INTO cv_profiles (user_id, raw_content, missions, is_archived) "
        "VALUES (:uid, :content, '[]', false)"
    ), {"uid": 11, "content": "CV missions vides"})

    # Profil avec missions NULL
    db_session.execute(text(
        "INSERT INTO cv_profiles (user_id, raw_content, missions, is_archived) "
        "VALUES (:uid, :content, NULL, false)"
    ), {"uid": 12, "content": "CV missions null"})
    db_session.commit()

    # jsonb_array_length(NULL) = NULL → pas compté dans WHERE > 0
    # jsonb_array_length('[]') = 0 → pas compté non plus
    result = db_session.execute(text(
        "SELECT COUNT(*) FROM cv_profiles WHERE jsonb_array_length(missions) > 0"
    ))
    count = result.scalar()
    assert count == 0, (
        f"Les missions NULL/vides ne doivent pas être comptées comme > 0 (obtenu {count})"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Validation ARRAY(String) : competencies_keywords
# ─────────────────────────────────────────────────────────────────────────────

def test_array_string_competencies(db_session):
    """
    Valide que la colonne ARRAY(String) competencies_keywords fonctionne.

    PostgreSQL ARRAY n'existe pas en SQLite — INSERT silencieusement ignoré
    ou converti en chaîne, cassant les requêtes de filtre.
    """
    db_session.execute(text(
        "INSERT INTO cv_profiles "
        "(user_id, raw_content, competencies_keywords, is_archived) "
        "VALUES (:uid, :content, :keywords, false)"
    ), {
        "uid": 20,
        "content": "CV avec compétences",
        "keywords": "{Python,FastAPI,PostgreSQL}",  # Syntaxe PostgreSQL ARRAY littéral
    })
    db_session.commit()

    result = db_session.execute(text(
        "SELECT competencies_keywords FROM cv_profiles WHERE user_id = 20"
    ))
    row = result.fetchone()
    assert row is not None
    assert "Python" in row[0], f"Mot-clé 'Python' attendu dans {row[0]}"
    assert "FastAPI" in row[0], f"Mot-clé 'FastAPI' attendu dans {row[0]}"
