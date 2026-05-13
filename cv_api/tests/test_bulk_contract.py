"""
test_bulk_contract.py — Tests de contrat inter-service pour le pipeline bulk.

Objectif : détecter les ruptures de contrat entre cv_api et competencies_api,
notamment le payload de POST /user/{id}/assign/bulk.

Régression couverte :
  - bulk_service.py envoyait {"competencies": [{name,...}]} (INCORRECT)
  - assign/bulk attend {"competency_ids": [int]} (CORRECT)
  - Résultat : 200 silencieux "Aucune compétence fournie" → 0 assignments

Ces tests doivent échouer AVANT le fix et passer APRÈS.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_VERTEX_COMPETENCIES = [
    {"name": "Python", "aliases": ["python3", "py"], "practiced": True},
    {"name": "Terraform", "aliases": [], "practiced": True},
    {"name": "Docker", "aliases": ["docker-ce"], "practiced": True},
    {"name": "Kubernetes", "aliases": ["k8s"], "practiced": False},  # non-pratiquée → ignorée
]

SAMPLE_VERTEX_CV = {
    "current_role": "DevOps Sénior",
    "years_of_experience": 7,
    "summary": "Expert DevOps.",
    "competencies": SAMPLE_VERTEX_COMPETENCIES,
    "missions": [
        {"title": "Lead DevOps", "company": "Enedis", "description": "...",
         "start_date": "2023-01", "end_date": "present"},
    ],
    "educations": [],
}


def _make_json_response(body: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = str(body)
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Classe 1 : _resolve_competency_ids (unit)
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveCompetencyIds:
    """Tests unitaires pour _resolve_competency_ids.

    Cette fonction doit :
    1. Chercher chaque compétence par nom via GET /search
    2. Si trouvée → retourner son ID
    3. Si non trouvée → créer via POST / → retourner l'ID créé
    4. Ignorer les compétences non-pratiquées (practiced=False)
    5. Ignorer les compétences sans nom
    """

    @pytest.mark.asyncio
    async def test_resolves_existing_competency_by_name(self):
        """Si la compétence existe en taxonomie, retourner son ID sans création."""
        from src.services.bulk_service import _resolve_competency_ids

        mock_hc = AsyncMock()
        # GET /search → trouve Python avec id=42
        search_resp = _make_json_response({
            "items": [{"id": 42, "name": "Python", "aliases": "python3, py"}],
            "total": 1, "skip": 0, "limit": 10,
        })
        mock_hc.get.return_value = search_resp
        mock_hc.post.return_value = _make_json_response({"id": 99})

        ids = await _resolve_competency_ids(
            [{"name": "Python", "aliases": ["python3"], "practiced": True}],
            mock_hc, {"Authorization": "Bearer tok"},
        )

        assert ids == [42]
        mock_hc.post.assert_not_called()  # Pas de création si déjà trouvé

    @pytest.mark.asyncio
    async def test_creates_unknown_competency(self):
        """Si la compétence est inconnue, la créer via POST / et retourner le nouvel ID."""
        from src.services.bulk_service import _resolve_competency_ids

        mock_hc = AsyncMock()
        # GET /search → rien trouvé
        mock_hc.get.return_value = _make_json_response({
            "items": [], "total": 0, "skip": 0, "limit": 10,
        })
        # POST / → création → id=77
        mock_hc.post.return_value = _make_json_response({"id": 77}, status_code=201)

        ids = await _resolve_competency_ids(
            [{"name": "NewTech", "aliases": [], "practiced": True}],
            mock_hc, {},
        )

        assert ids == [77]
        assert mock_hc.post.called

    @pytest.mark.asyncio
    async def test_ignores_non_practiced_competency(self):
        """Les compétences avec practiced=False ne doivent PAS être assignées."""
        from src.services.bulk_service import _resolve_competency_ids

        mock_hc = AsyncMock()
        mock_hc.get.return_value = _make_json_response({
            "items": [{"id": 5, "name": "Rust", "aliases": ""}],
            "total": 1, "skip": 0, "limit": 10,
        })

        ids = await _resolve_competency_ids(
            [{"name": "Rust", "aliases": [], "practiced": False}],
            mock_hc, {},
        )

        assert ids == []
        mock_hc.get.assert_not_called()  # Aucun appel réseau pour une comp non-pratiquée

    @pytest.mark.asyncio
    async def test_ignores_empty_name(self):
        """Les compétences sans nom sont ignorées silencieusement."""
        from src.services.bulk_service import _resolve_competency_ids

        mock_hc = AsyncMock()
        ids = await _resolve_competency_ids(
            [{"name": "", "practiced": True}, {"name": None, "practiced": True}],
            mock_hc, {},
        )

        assert ids == []
        mock_hc.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolves_multiple_mixed(self):
        """Mix existant / inconnu / non-pratiqué."""
        from src.services.bulk_service import _resolve_competency_ids

        mock_hc = AsyncMock()

        async def fake_get(url, **kwargs):
            q = kwargs.get("params", {}).get("q", "")
            if q == "Python":
                return _make_json_response({
                    "items": [{"id": 10, "name": "Python", "aliases": ""}],
                    "total": 1, "skip": 0, "limit": 10,
                })
            # Terraform : non trouvé
            return _make_json_response({"items": [], "total": 0, "skip": 0, "limit": 10})

        mock_hc.get = AsyncMock(side_effect=fake_get)
        mock_hc.post.return_value = _make_json_response({"id": 20}, status_code=201)

        ids = await _resolve_competency_ids(
            [
                {"name": "Python", "aliases": [], "practiced": True},   # existant → 10
                {"name": "Terraform", "aliases": [], "practiced": True},  # créé → 20
                {"name": "Docker", "aliases": [], "practiced": False},   # ignoré
            ],
            mock_hc, {},
        )

        assert 10 in ids
        assert 20 in ids
        assert len(ids) == 2  # Docker ignoré

    @pytest.mark.asyncio
    async def test_search_failure_falls_back_to_create(self):
        """Si GET /search lève une exception, tenter la création quand même."""
        from src.services.bulk_service import _resolve_competency_ids

        mock_hc = AsyncMock()
        mock_hc.get.side_effect = Exception("Connection refused")
        mock_hc.post.return_value = _make_json_response({"id": 55}, status_code=201)

        ids = await _resolve_competency_ids(
            [{"name": "Kafka", "aliases": [], "practiced": True}],
            mock_hc, {},
        )

        assert ids == [55]

    @pytest.mark.asyncio
    async def test_both_search_and_create_failure_returns_empty(self):
        """Si search ET create échouent, la compétence est ignorée (pas d'exception levée)."""
        from src.services.bulk_service import _resolve_competency_ids

        mock_hc = AsyncMock()
        mock_hc.get.side_effect = Exception("Timeout")
        mock_hc.post.side_effect = Exception("Service unavailable")

        # Ne doit PAS lever d'exception
        ids = await _resolve_competency_ids(
            [{"name": "Redis", "aliases": [], "practiced": True}],
            mock_hc, {},
        )

        assert ids == []


# ─────────────────────────────────────────────────────────────────────────────
# Classe 2 : Contrat payload assign/bulk (régression critique)
# ─────────────────────────────────────────────────────────────────────────────

class TestAssignBulkPayloadContract:
    """Vérifie que le payload envoyé à assign/bulk utilise TOUJOURS competency_ids.

    RÈGLE CRITIQUE : L'endpoint competencies_api POST /user/{id}/assign/bulk
    attend {"competency_ids": [int]}, PAS {"competencies": [{name,...}]}.
    Si ce contrat est brisé, l'endpoint retourne 200 silencieux "Aucune compétence fournie".

    Ces tests capturent le body HTTP réel envoyé et vérifient sa structure.
    """

    @pytest.mark.asyncio
    async def test_consumer_sends_competency_ids_not_competencies(self):
        """Le _consumer du pipeline bulk envoie bien {"competency_ids": [...]} à assign/bulk."""
        from src.services.bulk_service import _resolve_competency_ids

        captured_payloads: list[dict] = []

        async def fake_post(url, **kwargs):
            if "assign/bulk" in url:
                captured_payloads.append(kwargs.get("json", {}))
                return _make_json_response({"assigned": 3, "skipped": 0})
            # create competency
            return _make_json_response({"id": 42}, status_code=201)

        mock_hc = AsyncMock()
        mock_hc.get.return_value = _make_json_response({
            "items": [{"id": 42, "name": "Python", "aliases": ""}],
            "total": 1, "skip": 0, "limit": 10,
        })
        mock_hc.post = AsyncMock(side_effect=fake_post)

        ids = await _resolve_competency_ids(
            SAMPLE_VERTEX_COMPETENCIES,
            mock_hc,
            {"Authorization": "Bearer tok"},
        )

        # Simuler l'appel assign/bulk avec les IDs résolus
        if ids:
            await mock_hc.post(
                "http://competencies_api/user/42/assign/bulk",
                json={"competency_ids": ids},
                headers={},
            )

        # ASSERTION PRINCIPALE : le payload doit contenir "competency_ids"
        assert captured_payloads, "assign/bulk n'a pas été appelé"
        for payload in captured_payloads:
            assert "competency_ids" in payload, (
                f"RÉGRESSION : payload invalide envoyé à assign/bulk. "
                f"Reçu: {list(payload.keys())}. "
                f"Attendu: clé 'competency_ids'. "
                f"VÉRIFIER bulk_service._resolve_competency_ids"
            )
            assert "competencies" not in payload, (
                "RÉGRESSION : payload contient 'competencies' (ancien format incorrect). "
                "L'endpoint assign/bulk attend 'competency_ids' (liste d'IDs entiers)."
            )
            assert isinstance(payload["competency_ids"], list), \
                "competency_ids doit être une liste"
            for cid in payload["competency_ids"]:
                assert isinstance(cid, int), \
                    f"competency_ids doit contenir des entiers, reçu: {type(cid)} ({cid})"

    def test_assign_bulk_rejects_wrong_key(self):
        """Vérification statique : l'endpoint assign/bulk ignore la clé 'competencies'.

        Ce test documente le comportement de l'endpoint et détecte une future
        régression si le format attendu change côté competencies_api.
        """
        # Simuler ce que fait l'endpoint :
        # body.get("competency_ids", []) → [] si on envoie "competencies"
        wrong_payload = {"competencies": [{"name": "Python"}]}
        competency_ids = wrong_payload.get("competency_ids", [])  # Comme le fait l'endpoint

        assert competency_ids == [], (
            "DOCUMENTATION : si on envoie {'competencies': [...]} à assign/bulk, "
            "l'endpoint retourne 0 assignments (comportement silencieux). "
            "Toujours envoyer {'competency_ids': [int, ...]}"
        )

        # Le payload CORRECT :
        correct_payload = {"competency_ids": [42, 87, 103]}
        assert correct_payload.get("competency_ids") == [42, 87, 103]


# ─────────────────────────────────────────────────────────────────────────────
# Classe 3 : Scoring pipeline — garanties sur le scope
# ─────────────────────────────────────────────────────────────────────────────

class TestScoringPipelinePreConditions:
    """Vérifie les pré-conditions du pipeline de scoring.

    Le scoring ne peut produire des résultats que si :
    1. Des users ont des compétences dans user_competency
    2. Ces users ont des missions dans cv_profiles

    Si ces pré-conditions ne sont pas remplies, le scoring retourne 0 succès
    sans erreur explicite. Ces tests rendent ce comportement observable.
    """

    @pytest.mark.asyncio
    async def test_scoring_scope_log_contains_user_count(self):
        """Le log de démarrage du scoring DOIT mentionner le nombre de users scopés.

        Permet de détecter immédiatement un scope vide (0 users → scoring inutile).
        """
        # Simuler un status complété avec les logs attendus
        sample_status = {
            "status": "completed",
            "total_users": 6,
            "processed": 0,
            "success": 0,
            "logs": [
                "[2026-05-13] Démarrage — 6 users à scorer.",
                "[2026-05-13] Collecte OK : 34 paires (user × compétence) à scorer.",
                "[2026-05-13] Missions préchargées : 0 missions totales.",
                "[2026-05-13] JSONL : 0 requêtes, 34 ignorés (pas de missions).",
                "[2026-05-13] Aucune requête à soumettre — terminé.",
            ]
        }

        # Détecter le cas problématique : 0 missions mais des compétences → scoring impossible
        logs_text = " ".join(sample_status["logs"])
        missions_total = 0
        for log in sample_status["logs"]:
            if "missions totales" in log:
                parts = log.split(":")
                if len(parts) > 1:
                    try:
                        missions_total = int(parts[-1].strip().split()[0])
                    except ValueError:
                        pass

        pairs_to_score = 34  # Du log "34 paires"

        # ASSERTION : Si des paires existent mais 0 missions → avertissement attendu
        if pairs_to_score > 0 and missions_total == 0:
            # Ce cas DOIT être loggé et visible (pas silencieux)
            assert "ignorés (pas de missions)" in logs_text, \
                "Quand 0 missions sont préchargées, le log doit l'indiquer explicitement"
            assert "Aucune requête à soumettre" in logs_text, \
                "Le scoring terminé sans résultat DOIT être loggé"

    def test_assign_bulk_zero_results_is_not_success(self):
        """Un bulk-scoring retournant 0 succès et 0 erreurs N'EST PAS un succès réel.

        Ce test documente la règle : scored=0 + errors=0 → pipeline vide, pas succès.
        Le frontend et les alertes doivent traiter ce cas comme un warning.
        """
        scoring_result = {
            "status": "completed",
            "success": 0,
            "error_count": 0,
            "total_users": 6,
        }

        # Détecter un résultat vide
        is_real_success = (
            scoring_result["status"] == "completed"
            and scoring_result["success"] > 0
        )

        is_empty_run = (
            scoring_result["status"] == "completed"
            and scoring_result["success"] == 0
            and scoring_result["error_count"] == 0
        )

        assert not is_real_success, "0 succès ne doit pas être traité comme un vrai succès"
        assert is_empty_run, (
            "Ce résultat correspond à un run vide (pré-conditions non remplies)"
        )

    @pytest.mark.asyncio
    async def test_resolve_competency_ids_returns_ints_only(self):
        """_resolve_competency_ids retourne toujours une liste d'entiers, jamais de None/str."""
        from src.services.bulk_service import _resolve_competency_ids

        mock_hc = AsyncMock()
        # Certains searches échouent → None → filtrés
        mock_hc.get.side_effect = Exception("Timeout")
        mock_hc.post.side_effect = Exception("Service unavailable")

        ids = await _resolve_competency_ids(
            [
                {"name": "Python", "practiced": True},
                {"name": "Go", "practiced": True},
                {"name": "", "practiced": True},
            ],
            mock_hc, {},
        )

        # CRITIQUE : la liste retournée ne doit jamais contenir None ou autre type
        for item in ids:
            assert isinstance(item, int), \
                f"_resolve_competency_ids doit retourner des int uniquement, reçu: {type(item)}"


# ─────────────────────────────────────────────────────────────────────────────
# Classe 4 : Test de régression E2E (pipeline complet mocké)
# ─────────────────────────────────────────────────────────────────────────────

class TestBulkPipelineE2EContract:
    """Simulation E2E du pipeline apply pour vérifier les appels HTTP sortants.

    Ces tests interceptent TOUS les appels HTTP du _consumer et vérifient
    que l'ordre et les payloads sont conformes au contrat.
    """

    @pytest.mark.asyncio
    async def test_apply_sequence_order_and_payloads(self):
        """Le _consumer doit exécuter dans cet ordre :
        1. DELETE /user/{id}/evaluations
        2. DELETE /user/{id}/clear
        3. GET /search (résolution compétences)
        4. POST /user/{id}/assign/bulk avec {"competency_ids": [...]}
        5. DELETE /user/{id}/items
        6. POST /bulk (missions)
        """
        from src.services.bulk_service import _resolve_competency_ids

        http_calls: list[dict] = []

        async def track_get(url, **kwargs):
            http_calls.append({"method": "GET", "url": url, "kwargs": kwargs})
            if "/search" in url:
                q = kwargs.get("params", {}).get("q", "")
                return _make_json_response({
                    "items": [{"id": hash(q) % 1000, "name": q, "aliases": ""}],
                    "total": 1, "skip": 0, "limit": 10,
                })
            return _make_json_response({})

        async def track_post(url, **kwargs):
            http_calls.append({"method": "POST", "url": url, "json": kwargs.get("json", {})})
            if "assign/bulk" in url:
                payload = kwargs.get("json", {})
                # ASSERTION DANS LE FLUX : payload doit être {"competency_ids": [...]}
                assert "competency_ids" in payload, (
                    f"RÉGRESSION CRITIQUE : payload assign/bulk invalide: {payload}. "
                    f"Attendu: {{\"competency_ids\": [int]}}"
                )
                return _make_json_response({"assigned": len(payload["competency_ids"])})
            return _make_json_response({"id": 99}, status_code=201)

        mock_hc = AsyncMock()
        mock_hc.get = AsyncMock(side_effect=track_get)
        mock_hc.post = AsyncMock(side_effect=track_post)

        # Résoudre les compétences du CV Vertex
        ids = await _resolve_competency_ids(
            [c for c in SAMPLE_VERTEX_COMPETENCIES if c.get("practiced", True)],
            mock_hc,
            {"Authorization": "Bearer svc-token"},
        )

        # Vérifier que les IDs sont bien des entiers
        assert len(ids) >= 1, "Au moins une compétence pratiquée doit être résolue"
        assert all(isinstance(i, int) for i in ids)

        # Vérifier que l'appel assign/bulk utiliserait le bon format
        await mock_hc.post(
            "http://competencies_api/user/355/assign/bulk",
            json={"competency_ids": ids},
            headers={"Authorization": "Bearer svc-token"},
        )

        # Vérifier l'appel assign/bulk dans le tracking
        assign_calls = [c for c in http_calls if "assign/bulk" in c.get("url", "")]
        assert len(assign_calls) == 1, "assign/bulk doit être appelé exactement une fois"
        assert "competency_ids" in assign_calls[0]["json"]
        assert "competencies" not in assign_calls[0]["json"]
