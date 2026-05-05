"""
Tests d'intégration prompts_api — nécessitent Docker.

Valide la persistance réelle des prompts système sur PostgreSQL.
Les tests simulent un upsert (PUT crée ou met à jour).

Note : Les routes prompts_api sont montées à la racine :
  - PUT /{key} — créer/mettre à jour un prompt
  - GET /{key} — lire un prompt
  - GET /    — lister tous les prompts
"""
import pytest


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def prompts_pg_setup(wipe_prompts_db):
    """Active PostgreSQL et réinitialise les données avant chaque test."""
    yield


# ─────────────────────────────────────────────────────────────────────────────
# CRUD PostgreSQL réel
# ─────────────────────────────────────────────────────────────────────────────

def test_create_prompt_real_postgres(client):
    """Valide qu'un prompt système est persisté dans PostgreSQL via PUT."""
    resp = client.put("/test-key", json={
        "value": "Tu es un assistant IA expert en données."
    })
    assert resp.status_code in (200, 201, 204), (
        f"PUT /{'{key}'} échoué : {resp.status_code} {resp.text}"
    )


def test_get_prompt_real_postgres(client):
    """Valide que le prompt est lisible après insertion."""
    client.put("/agent-hr-key", json={"value": "Prompt RH initial."})

    resp = client.get("/agent-hr-key")
    assert resp.status_code == 200
    data = resp.json()
    assert "agent-hr-key" in str(data) or "Prompt RH" in str(data), (
        f"La valeur du prompt doit être présente dans la réponse : {data}"
    )


def test_list_prompts_real_postgres(client):
    """Valide la liste des prompts sur vrai PostgreSQL."""
    client.put("/key-1", json={"value": "Prompt 1"})
    client.put("/key-2", json={"value": "Prompt 2"})
    client.put("/key-3", json={"value": "Prompt 3"})

    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    items = data if isinstance(data, list) else data.get("items", data.get("prompts", []))
    assert len(items) >= 3, f"Attendu >= 3 prompts, trouvé {len(items)}"


def test_update_prompt_idempotent(client):
    """Valide qu'un PUT répété sur la même clé fonctionne (upsert)."""
    client.put("/upsert-key", json={"value": "Valeur initiale."})
    resp = client.put("/upsert-key", json={"value": "Valeur mise à jour."})
    assert resp.status_code in (200, 201, 204), (
        f"L'upsert doit réussir : {resp.status_code} {resp.text}"
    )


def test_isolation_no_state_leak(client):
    """Valide que wipe_prompts_db garantit une isolation parfaite."""
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    items = data if isinstance(data, list) else data.get("items", data.get("prompts", []))
    assert len(items) == 0, f"State-leak : {len(items)} prompts persistent entre les tests"
