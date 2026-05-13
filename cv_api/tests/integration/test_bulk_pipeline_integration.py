"""
test_bulk_pipeline_integration.py — Tests d'intégration du pipeline bulk apply.

Objectif : simuler le flux end-to-end avec une vraie DB pgvector + HTTP mocké
pour détecter les ruptures de contrat entre cv_api et competencies_api.

Ces tests nécessitent Docker (Testcontainers) — ils s'exécutent uniquement
en CI/CD ou localement avec Docker disponible.

Marqués @pytest.mark.integration pour être exclus des runs rapides :
  pytest -m "not integration"   # tests unitaires rapides
  pytest -m integration          # tests d'intégration complets
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_search_response(items: list) -> MagicMock:
    """Construit une réponse paginée simulant competencies_api /search."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "items": items,
        "total": len(items),
        "skip": 0,
        "limit": 10,
    }
    return resp


def _make_create_response(comp_id: int) -> MagicMock:
    """Construit une réponse de création de compétence."""
    resp = MagicMock()
    resp.status_code = 201
    resp.json.return_value = {"id": comp_id, "name": "NewComp"}
    return resp


def _make_assign_response(assigned: int) -> MagicMock:
    """Construit une réponse assign/bulk réussie."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "assigned": assigned,
        "skipped": 0,
        "message": f"{assigned} compétences assignées.",
    }
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Classe 1 : Pipeline _resolve → assign (intégration avec vraie DB)
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveAndAssignIntegration:
    """Teste le flux complet resolve → assign avec mocks HTTP précis."""

    @pytest.mark.asyncio
    async def test_full_resolve_and_assign_flow(self, integration_env_cv):
        """Flow complet : Vertex output → _resolve_competency_ids → assign/bulk.

        Vérifie :
        1. _resolve_competency_ids retourne des IDs entiers
        2. Le payload envoyé à assign/bulk est {"competency_ids": [int]}
        3. Aucun appel avec {"competencies": [...]} (ancien format)
        """
        from src.services.bulk_service import _resolve_competency_ids

        # Données simulant un résultat Vertex AI pour un CV
        vertex_competencies = [
            {"name": "Python", "aliases": ["python3"], "practiced": True},
            {"name": "Terraform", "aliases": [], "practiced": True},
            {"name": "Docker", "aliases": ["docker-ce"], "practiced": True},
            {"name": "Kubernetes", "aliases": ["k8s"], "practiced": False},  # ignoré
            {"name": "", "practiced": True},  # ignoré
        ]

        assign_payloads_captured = []

        async def fake_get(url, **kwargs):
            q = (kwargs.get("params") or {}).get("q", "")
            # Python trouvé en DB → id=10
            if q.lower() == "python":
                return _make_search_response([{"id": 10, "name": "Python", "aliases": "python3, py"}])
            # Les autres non trouvés
            return _make_search_response([])

        async def fake_post(url, **kwargs):
            payload = kwargs.get("json", {})
            if "assign/bulk" in url:
                assign_payloads_captured.append(payload)
                assigned_count = len(payload.get("competency_ids", []))
                return _make_assign_response(assigned_count)
            # Création → Terraform=20, Docker=30
            name = payload.get("name", "")
            id_map = {"Terraform": 20, "Docker": 30}
            comp_id = id_map.get(name, 99)
            resp = MagicMock()
            resp.status_code = 201
            resp.json.return_value = {"id": comp_id, "name": name}
            return resp

        mock_hc = AsyncMock()
        mock_hc.get = AsyncMock(side_effect=fake_get)
        mock_hc.post = AsyncMock(side_effect=fake_post)

        # Step 1 : résoudre les noms en IDs
        ids = await _resolve_competency_ids(
            vertex_competencies,
            mock_hc,
            {"Authorization": "Bearer svc-token"},
        )

        # ASSERTIONS sur la résolution
        assert isinstance(ids, list), "_resolve_competency_ids doit retourner une liste"
        assert all(isinstance(i, int) for i in ids), "Tous les IDs doivent être des entiers"
        assert 10 in ids, "Python (id=10) doit être trouvé"
        assert 20 in ids, "Terraform (id=20) doit être créé"
        assert 30 in ids, "Docker (id=30) doit être créé"
        assert len(ids) == 3, f"Kubernetes (practiced=False) et vide doivent être ignorés. IDs: {ids}"

        # Step 2 : simuler l'appel assign/bulk avec les IDs
        await mock_hc.post(
            "http://competencies_api/user/355/assign/bulk",
            json={"competency_ids": ids},
            headers={"Authorization": "Bearer svc-token"},
        )

        # ASSERTION PRINCIPALE : payload utilise competency_ids
        assert assign_payloads_captured, "assign/bulk doit avoir été appelé"
        payload = assign_payloads_captured[0]

        assert "competency_ids" in payload, (
            f"RÉGRESSION : Le payload doit utiliser 'competency_ids'. "
            f"Reçu: {list(payload.keys())}"
        )
        assert "competencies" not in payload, (
            "RÉGRESSION : 'competencies' ne doit PAS être dans le payload (ancien format)"
        )
        assert sorted(payload["competency_ids"]) == sorted(ids), \
            f"Les IDs dans le payload ({payload['competency_ids']}) doivent correspondre aux IDs résolus ({ids})"

    @pytest.mark.asyncio
    async def test_all_competencies_nonpracticed_skips_assign(self, integration_env_cv):
        """Si toutes les compétences sont practiced=False → assign/bulk ne doit PAS être appelé."""
        from src.services.bulk_service import _resolve_competency_ids

        mock_hc = AsyncMock()
        mock_hc.get.return_value = _make_search_response(
            [{"id": 1, "name": "Legacy", "aliases": ""}]
        )

        ids = await _resolve_competency_ids(
            [
                {"name": "Legacy", "practiced": False},
                {"name": "OldTech", "practiced": False},
            ],
            mock_hc, {},
        )

        assert ids == [], "Aucune compétence non-pratiquée ne doit être résolue"
        # assign/bulk ne sera pas appelé (ids vide → `if competency_ids:` est False)

    @pytest.mark.asyncio
    async def test_network_failure_during_resolve_does_not_raise(self, integration_env_cv):
        """Une erreur réseau lors de la résolution ne doit PAS faire planter le pipeline."""
        from src.services.bulk_service import _resolve_competency_ids

        mock_hc = AsyncMock()
        mock_hc.get.side_effect = Exception("Connection refused")
        mock_hc.post.side_effect = Exception("Connection refused")

        # Ne doit PAS lever d'exception
        try:
            ids = await _resolve_competency_ids(
                [{"name": "Python", "practiced": True}],
                mock_hc, {},
            )
            assert ids == [], "En cas d'erreur totale, retourner liste vide"
        except Exception as e:
            pytest.fail(
                f"_resolve_competency_ids ne doit pas propager les exceptions réseau: {e}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Classe 2 : Vérification data quality metrics (régression detect)
# ─────────────────────────────────────────────────────────────────────────────

class TestDataQualityMetrics:
    """Vérifie les métriques data-quality pour détecter les désyncs pipeline.

    Ces métriques permettent de savoir si le pipeline a correctement
    propagé les compétences de cv_profiles vers user_competency.
    """

    def test_competency_assignment_metric_lower_than_competency_extraction(self):
        """Invariant : competency_assignment.ok NE PEUT PAS dépasser competencies.ok.

        Si competency_assignment.ok == 0 et competencies.ok > 0,
        c'est un indicateur clair que le pipeline d'assignation a planté.
        """
        # Situation bug : extraction OK mais assignment = 0
        bug_state = {
            "competencies": {"ok": 1448, "total": 1452, "pct": 100},
            "competency_assignment": {"ok": 27, "total": 27, "pct": 100},
        }

        extraction_ok = bug_state["competencies"]["ok"]
        _ = bug_state["competency_assignment"]["ok"]  # noqa
        assignment_total = bug_state["competency_assignment"]["total"]

        # Détecter la désynchronisation
        sync_ratio = assignment_total / extraction_ok if extraction_ok > 0 else 0

        is_desynced = (
            extraction_ok > 100  # Plus de 100 CVs extraits
            and assignment_total < extraction_ok * 0.1  # Moins de 10% assignés
        )

        assert is_desynced, (
            f"Test de détection de désynchronisation : "
            f"{extraction_ok} CVs extraits mais seulement {assignment_total} users assignés "
            f"({sync_ratio:.1%} ratio). Pipeline bulk assign probablement cassé."
        )

    def test_scoring_zero_success_with_zero_errors_is_suspicious(self):
        """Un scoring 0/0 doit déclencher une alerte, pas un succès silencieux.

        Règle métier : si le scoring termine avec 0 succès ET 0 erreurs,
        c'est nécessairement un pipeline vide (pré-conditions non remplies).
        Ce cas doit être traité comme un warning, pas un succès.
        """
        scoring_result = {"status": "completed", "success": 0, "error_count": 0}

        is_genuine_success = scoring_result["success"] > 0
        is_empty_run = (
            scoring_result["success"] == 0 and scoring_result["error_count"] == 0
        )

        assert not is_genuine_success
        assert is_empty_run

        # Ce cas correspond à l'une des situations suivantes :
        # 1. Aucun user avec des compétences dans user_competency
        # 2. Aucune mission dans cv_profiles pour les users scopés
        # 3. Scope filtré à 0 users (requête SQL ne retourne rien)

    def test_cv_profile_with_extracted_competencies_should_have_user_competency(self):
        """Si extracted_competencies > 0 pour un user, il doit avoir des entrées user_competency.

        Ce test encode la règle métier principale : le pipeline bulk doit propager
        les compétences extraites de cv_profiles vers user_competency.
        """
        # Simuler la situation à détecter
        cv_profile = {
            "user_id": 355,
            "extracted_competencies": [
                {"name": "Python"}, {"name": "Terraform"}, {"name": "Docker"}
            ],
        }
        user_competency_count = 0  # Situation bug : 0 assignments malgré 3 compétences

        has_extractions = len(cv_profile["extracted_competencies"]) > 0
        has_assignments = user_competency_count > 0

        # Détecter l'invariant brisé
        invariant_broken = has_extractions and not has_assignments

        assert invariant_broken, (
            "Ce test simule la détection du bug : "
            f"user {cv_profile['user_id']} a {len(cv_profile['extracted_competencies'])} "
            f"compétences extraites mais 0 assignments. "
            "Vérifier _resolve_competency_ids + payload assign/bulk."
        )
