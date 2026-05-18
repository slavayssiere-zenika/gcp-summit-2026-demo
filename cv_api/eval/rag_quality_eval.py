"""
test_rag_quality.py — Framework d'évaluation de la qualité RAG (R3).

Objectif :
    Mesurer la capacité du moteur de recherche vectorielle à retrouver
    les bons candidats dans les top-K résultats, et détecter toute
    régression de qualité (changement de modèle d'embedding, de prompt,
    ou de seuil de distance).

Métriques calculées :
    - Recall@K  : proportion de candidats attendus retrouvés dans les K premiers
    - MRR       : Mean Reciprocal Rank (position moyenne du premier hit)
    - Precision@K : précision parmi les K premiers résultats

Usage :
    # Depuis la racine du monorepo :
    RAG_EVAL_BASE_URL=https://api.dev.zenika.slavayssiere.fr/api/cv \\
    RAG_EVAL_TOKEN=$(python3 scripts/mcp_cli.py _get_token) \\
    pytest cv_api/eval/test_rag_quality.py -v --tb=short

    # En mode dry-run (sans expected_user_ids configurés) :
    RAG_EVAL_DRY_RUN=true \\
    pytest cv_api/eval/test_rag_quality.py -v --tb=short

    # Filtrer par tag :
    pytest cv_api/eval/test_rag_quality.py -v -k "cloud or devops"

Intégration CI/CD :
    Appelé optionnellement depuis scripts/deploy.sh après le déploiement de cv_api.
    Voir scripts/run_rag_eval.sh pour le wrapper d'intégration.
"""

import json
import os
from pathlib import Path
from typing import Optional

import httpx
import pytest

# ── Configuration ──────────────────────────────────────────────────────────────
_GOLDEN_PATH = Path(__file__).parent / "golden_queries.json"

# URL de base de l'API cv_api (sans trailing slash)
# Exemples :
#   Dev Cloud Run : https://api.dev.zenika.slavayssiere.fr/api/cv
#   Local         : http://localhost:8004
BASE_URL = os.getenv("RAG_EVAL_BASE_URL", "http://localhost:8004")

# JWT Bearer token pour authentification
API_TOKEN = os.getenv("RAG_EVAL_TOKEN", "")

# Top-K pour le calcul de Recall@K et Precision@K
TOP_K = int(os.getenv("RAG_EVAL_TOP_K", "5"))

# Seuil de Recall@K minimum global (overridé par cas si min_recall_at_k défini)
DEFAULT_RECALL_THRESHOLD = float(os.getenv("RAG_EVAL_RECALL_THRESHOLD", "0.5"))

# Mode dry-run : execute les requêtes mais ne bloque pas sur les métriques
# (utile avant d'avoir alimenté expected_user_ids)
DRY_RUN = os.getenv("RAG_EVAL_DRY_RUN", "false").lower() == "true"

# Timeout HTTP pour les appels /search
TIMEOUT_S = float(os.getenv("RAG_EVAL_TIMEOUT", "30.0"))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_golden_cases() -> list[dict]:
    """Charge et valide les cas golden depuis le fichier JSON."""
    with open(_GOLDEN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cases", [])


def _search(query: str, limit: int = TOP_K, agency: Optional[str] = None) -> list[dict]:
    """Appelle GET /search et retourne la liste des résultats."""
    headers = {}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"

    params = {"query": query, "limit": limit}
    if agency:
        params["agency"] = agency

    response = httpx.get(
        f"{BASE_URL.rstrip('/')}/search",
        params=params,
        headers=headers,
        timeout=TIMEOUT_S,
        follow_redirects=True,
    )
    if response.status_code == 404:
        # Aucun résultat — moteur opérationnel mais corpus vide pour cette query
        return []
    response.raise_for_status()
    data = response.json()
    return data.get("items", data) if isinstance(data, dict) else data


def _recall_at_k(retrieved_ids: list[int], expected_ids: list[int]) -> float:
    """Recall@K = |retrieved ∩ expected| / |expected|"""
    if not expected_ids:
        return 1.0  # Pas d'expected défini → cas non calibré, pas de pénalité
    retrieved_set = set(retrieved_ids)
    hits = sum(1 for uid in expected_ids if uid in retrieved_set)
    return hits / len(expected_ids)


def _mrr(retrieved_ids: list[int], expected_ids: list[int]) -> float:
    """Mean Reciprocal Rank = 1 / position du premier hit (0 si aucun hit)."""
    expected_set = set(expected_ids)
    for rank, uid in enumerate(retrieved_ids, start=1):
        if uid in expected_set:
            return 1.0 / rank
    return 0.0


def _precision_at_k(retrieved_ids: list[int], expected_ids: list[int]) -> float:
    """Precision@K = |retrieved ∩ expected| / K"""
    if not retrieved_ids:
        return 0.0
    expected_set = set(expected_ids)
    hits = sum(1 for uid in retrieved_ids if uid in expected_set)
    return hits / len(retrieved_ids)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def golden_cases() -> list[dict]:
    cases = _load_golden_cases()
    assert cases, f"Aucun cas golden trouvé dans {_GOLDEN_PATH}"
    return cases


@pytest.fixture(scope="session")
def api_reachable() -> bool:
    """Vérifie que l'API est accessible avant d'exécuter les tests."""
    try:
        r = httpx.get(f"{BASE_URL.rstrip('/')}/health", timeout=5.0)
        return r.status_code in (200, 204)
    except Exception:
        return False


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("case", _load_golden_cases(), ids=lambda c: c["id"])
def test_rag_recall_at_k(case: dict, api_reachable: bool):
    """
    Pour chaque cas golden, vérifie que Recall@K >= seuil configuré.

    Stratégie :
    - Si expected_user_ids est vide → cas non calibré, le test passe toujours
      et affiche les résultats pour calibrage manuel.
    - Si expected_user_ids est rempli → le test échoue si Recall@K < min_recall_at_k.
    """
    if not api_reachable:
        pytest.skip(f"API non accessible sur {BASE_URL} — vérifiez RAG_EVAL_BASE_URL")

    query = case["query"]
    expected_ids = case.get("expected_user_ids", [])
    min_recall = case.get("min_recall_at_k", DEFAULT_RECALL_THRESHOLD)
    tags = case.get("tags", [])
    case_id = case["id"]

    # Exécution de la recherche
    results = _search(query, limit=TOP_K)
    retrieved_ids = [r["user_id"] for r in results]
    retrieved_scores = [(r["user_id"], round(r.get("similarity_score", 0), 4)) for r in results]

    # Calcul des métriques
    recall = _recall_at_k(retrieved_ids, expected_ids)
    mrr = _mrr(retrieved_ids, expected_ids)
    precision = _precision_at_k(retrieved_ids, expected_ids)

    # Affichage toujours visible (utile pour calibrage et rapport)
    print(f"\n{'='*60}")
    print(f"[{case_id}] {query}")
    print(f"  Tags      : {', '.join(tags)}")
    print(f"  Top-{TOP_K} IDs : {retrieved_ids}")
    print(f"  Scores    : {retrieved_scores}")
    print(f"  Expected  : {expected_ids}")
    print(f"  Source URLs: {[r.get('source_url') for r in results[:3]]}")
    print(f"  Recall@{TOP_K}  : {recall:.3f}  (seuil: {min_recall})")
    print(f"  MRR       : {mrr:.3f}")
    print(f"  Precision@{TOP_K}: {precision:.3f}")

    # Cas non calibré → skip silencieux (ne bloque pas le CI)
    if not expected_ids:
        pytest.skip(
            f"[{case_id}] Cas non calibré (expected_user_ids vide). "
            f"Résultats affichés pour calibrage manuel. "
            f"Top-{TOP_K}: {retrieved_ids}"
        )

    # Dry-run → on n'assert pas, juste on log
    if DRY_RUN:
        print(f"  [DRY-RUN] Recall={recall:.3f} — assertion ignorée")
        return

    # Assertion principale
    assert recall >= min_recall, (
        f"[{case_id}] Recall@{TOP_K}={recall:.3f} < seuil={min_recall}. "
        f"Candidats attendus={expected_ids}, retrouvés={retrieved_ids}. "
        f"→ Vérifiez GEMINI_EMBEDDING_MODEL ou VECTOR_DISTANCE_THRESHOLD."
    )


@pytest.mark.parametrize("case", _load_golden_cases(), ids=lambda c: c["id"])
def test_rag_results_have_source_url(case: dict, api_reachable: bool):
    """
    R5 — Vérifie que chaque résultat contient un champ source_url non nul.
    Garantit que la traçabilité documentaire est opérationnelle.
    """
    if not api_reachable:
        pytest.skip(f"API non accessible sur {BASE_URL}")

    results = _search(case["query"], limit=3)

    if not results:
        pytest.skip(f"[{case['id']}] Aucun résultat — corpus probablement vide")

    for r in results:
        assert "source_url" in r, (
            f"[{case['id']}] Champ source_url manquant dans le résultat pour user_id={r.get('user_id')}. "
            "Vérifiez que R5 est bien déployé (search_service.py)."
        )
        # source_url peut être None si le profil n'a pas de URL Drive
        # On vérifie juste la présence du champ, pas sa valeur


@pytest.mark.parametrize("case", _load_golden_cases(), ids=lambda c: c["id"])
def test_rag_results_have_embedding_model(case: dict, api_reachable: bool):
    """
    R1 — Vérifie que chaque résultat expose embedding_model.
    Garantit que le versionning du modèle est opérationnel.
    """
    if not api_reachable:
        pytest.skip(f"API non accessible sur {BASE_URL}")

    results = _search(case["query"], limit=3)

    if not results:
        pytest.skip(f"[{case['id']}] Aucun résultat — corpus probablement vide")

    for r in results:
        assert "embedding_model" in r, (
            f"[{case['id']}] Champ embedding_model manquant pour user_id={r.get('user_id')}. "
            "Vérifiez que R1 est bien déployé."
        )


def test_rag_threshold_header_present(api_reachable: bool):
    """
    R6 — Vérifie que les headers X-Threshold-Filtered-Count et X-Distance-Threshold
    sont présents dans la réponse HTTP /search.
    """
    if not api_reachable:
        pytest.skip(f"API non accessible sur {BASE_URL}")

    headers_auth = {}
    if API_TOKEN:
        headers_auth["Authorization"] = f"Bearer {API_TOKEN}"

    response = httpx.get(
        f"{BASE_URL.rstrip('/')}/search",
        params={"query": "développeur expert cloud GCP", "limit": 5},
        headers=headers_auth,
        timeout=TIMEOUT_S,
        follow_redirects=True,
    )

    if response.status_code == 404:
        pytest.skip("Aucun résultat — corpus probablement vide")

    response.raise_for_status()

    assert "X-Threshold-Filtered-Count" in response.headers, (
        "Header X-Threshold-Filtered-Count manquant dans la réponse /search. "
        "Vérifiez que R6 est bien déployé (search_service.py)."
    )
    assert "X-Distance-Threshold" in response.headers, (
        "Header X-Distance-Threshold manquant dans la réponse /search. "
        "Vérifiez que R6 est bien déployé (search_service.py)."
    )
    threshold_value = float(response.headers["X-Distance-Threshold"])
    assert 0.0 < threshold_value < 1.0, (
        f"X-Distance-Threshold={threshold_value} hors de la plage attendue (0, 1). "
        "Vérifiez VECTOR_DISTANCE_THRESHOLD."
    )
    print(f"\n[R6] Distance threshold actif : {threshold_value}")
    print(f"[R6] Candidats filtrés : {response.headers.get('X-Threshold-Filtered-Count', 'N/A')}")
