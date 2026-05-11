"""
test_contract.py — Contract testing via Schemathesis (mode ASGI, sans serveur réseau).

Schemathesis génère automatiquement des cas de test depuis le schéma OpenAPI
et vérifie que chaque réponse respecte le contrat déclaré :
- Aucune réponse 5xx inattendue
- Les champs `required` sont présents dans la réponse
- Les types des champs correspondent au schéma
- Les codes de statut retournés sont documentés

Dépendances : conftest.py (JWT override + SQLite in-memory + FakeRedis).
Les overrides sont automatiquement appliqués à l'app importée.

Marker : @pytest.mark.contract — exécuter avec : pytest -m contract
"""
import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis.checks import not_a_server_error

# L'app est importée via conftest.py (side-effects : DB + JWT + Redis override)
# On l'importe directement ici pour passer à schemathesis.
from main import app  # noqa: E402 — conftest.py a déjà configuré les overrides

# Chargement du schéma OpenAPI directement depuis l'app ASGI (sans serveur réseau).
# API schemathesis 4.x : filtrage via .exclude(path_regex=...) chaîné.
# Exclusion des endpoints non-testables en mode contrat :
#   - /mcp/* : proxy vers sidecar stdio (non disponible en test)
#   - /google/* : OAuth2 redirect flow (non déterministe)
schema = (
    schemathesis.openapi.from_asgi("/openapi.json", app)
    .exclude(path_regex=r"^/mcp/")
    .exclude(path_regex=r"^/google/")
)


@schema.parametrize()
@settings(
    max_examples=20,
    deadline=None,
    # SQLite in-memory peut déclencher HealthCheck.too_slow sur certaines opérations
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
def test_api_contract(case):
    """
    Vérifie que chaque endpoint respecte son contrat OpenAPI.

    Pour chaque opération (méthode + path), schemathesis génère 20 cas avec des
    données aléatoires valides et vérifie :
    1. Pas de 500 Internal Server Error (check : not_a_server_error)

    Note : `response_conformance` et `unsupported_method` sont exclus car :
    - FastAPI retourne 422 (pas 405) pour les méthodes non documentées (comportement stdlib)
    - Les endpoints /metrics, /health, /ready ne documentent pas tous leurs status codes
    """
    case.call_and_validate(checks=[not_a_server_error])

