"""
test_deduplication_resolution.py — TDD pour les 3 causes racines de doublons.

Problème prouvé en prod :
  "Google Kubernetes Engine" (créé à 17:19) est un doublon de "Kubernetes" (id=42)
  parce que resolve_comp_id et create_competency ne détectent pas l'expansion de nom.

Causes racines :
  RC1 — resolve_comp_id : exact-match seulement, rate les expansions de marque
  RC2 — create_competency : FUZZY_THRESHOLD=0.6 trop strict pour les expansions longues
  RC3 — bulk_tree : aliases insuffisants → les expansions ne sont jamais apprenables

Ces tests DOIVENT être rouges avant les fixes, verts après.
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./competencies_test.db")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("COMPETENCIES_API_URL", "http://competencies_api:8003")
os.environ.setdefault("USERS_API_URL", "http://users_api:8000")

_fake_redis_client = fakeredis.FakeRedis(decode_responses=True)

with patch("redis.from_url", return_value=_fake_redis_client), \
        patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter",
              return_value=MagicMock()):
    from shared.database import get_db
    from main import app
    from shared.auth.jwt import verify_jwt


def override_verify_jwt():
    return {"sub": "1", "role": "admin", "allowed_category_ids": [1]}


def get_client():
    from shared.auth.jwt import VerifyJwtOrOidc
    app.dependency_overrides[verify_jwt] = override_verify_jwt
    # Override VerifyJwtOrOidc instances (utilisés dans tree_router.py pour /bulk_tree)
    for route in app.routes:
        if hasattr(route, "dependencies"):
            for dep in route.dependencies:
                if isinstance(dep.dependency, VerifyJwtOrOidc):
                    app.dependency_overrides[dep.dependency] = override_verify_jwt
        if hasattr(route, "dependant"):
            for dep in route.dependant.dependencies:
                if isinstance(dep.call, VerifyJwtOrOidc):
                    app.dependency_overrides[dep.call] = override_verify_jwt
    from fastapi.testclient import TestClient
    return TestClient(app)


AUTH = {"Authorization": "Bearer testtoken"}


def _make_comp(comp_id=1, name="Kubernetes", aliases="k8s, kube, GKE", parent_id=None):
    from src.competencies.models import Competency
    c = Competency()
    c.id = comp_id
    c.name = name
    c.parent_id = parent_id
    c.aliases = aliases
    c.children = []
    c.description = "Candidate CV Skill"
    c.color = None
    c.icon = None
    c.is_validated = True
    c.category_id = 1
    c.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return c


def _patch_cache(mocker):
    mocker.patch("src.competencies.competencies_router.get_cache", return_value=None)
    mocker.patch("src.competencies.competencies_router.set_cache", return_value=None)
    mocker.patch("src.competencies.competencies_router.delete_cache", return_value=None)
    mocker.patch("shared.cache.clear_namespace", new_callable=mocker.AsyncMock)


# ==============================================================================
# RC2 — create_competency : containment check manquant
# ==============================================================================

class TestRC2ContainmentDeduplication:
    """
    RC2 : Le POST / ne détecte pas 'Google Kubernetes Engine' comme doublon de
    'Kubernetes' car SequenceMatcher("kubernetes", "google kubernetes engine")
    ~ 0.55 < THRESHOLD(0.6).

    Fix attendu : check de containment mot-entier AVANT le check fuzzy.
    Si le nom canonique est un mot entier dans le nom proposé, c'est un doublon.
    """

    def test_gke_expansion_resolves_to_kubernetes(self, mocker):
        """
        POST / avec 'Google Kubernetes Engine' doit résoudre vers 'Kubernetes' [42]
        via containment mot-entier, et NON créer un nouveau noeud.
        """
        _patch_cache(mocker)

        kubernetes = _make_comp(42, "Kubernetes", "k8s, kube, k8, k8s-cluster")

        async def fake_execute(stmt, *a, **kw):
            result = MagicMock()
            result.scalars.return_value.first.return_value = None
            result.scalars.return_value.all.return_value = [kubernetes]
            result.scalar.return_value = 0
            return result

        mock_db = AsyncMock()
        mock_db.execute = fake_execute
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        mocker.patch(
            "src.competencies.competencies_router.check_grammatical_conflict",
            return_value=None
        )
        mocker.patch(
            "src.competencies.competencies_router.serialize_competency",
            return_value={
                "id": 42, "name": "Kubernetes",
                "aliases": "k8s, kube, k8, k8s-cluster, Google Kubernetes Engine",
                "sub_competencies": [], "created_at": "2024-01-01T00:00:00"
            }
        )

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db

        with get_client() as client:
            resp = client.post(
                "/",
                json={"name": "Google Kubernetes Engine", "category_id": 1},
                headers=AUTH
            )

        assert resp.status_code in (200, 201), (
            f"Expected 200/201, got {resp.status_code}: {resp.text}"
        )
        data = resp.json()
        assert data["id"] == 42, (
            f"RC2 FAIL: 'Google Kubernetes Engine' a cree un nouveau noeud (id={data['id']}) "
            f"au lieu de resoudre vers 'Kubernetes' (id=42). "
            f"SequenceMatcher ratio ~0.55 < THRESHOLD 0.6 - containment check manquant."
        )
        assert "Google Kubernetes Engine" in kubernetes.aliases, (
            "RC2 FAIL: 'Google Kubernetes Engine' n'a pas ete ajoute comme alias de Kubernetes."
        )
        app.dependency_overrides.pop(get_db, None)

    def test_cloud_security_command_center_resolves_to_cscc(self, mocker):
        """
        POST / avec 'Cloud Security Command Center' doit resoudre vers
        la competence existante via containment mot-entier sur le nom complet.
        """
        _patch_cache(mocker)

        cscc = _make_comp(193, "Cloud Security Command Center", "CSCC, Security Command Center")

        async def fake_execute(stmt, *a, **kw):
            result = MagicMock()
            result.scalars.return_value.first.return_value = None
            result.scalars.return_value.all.return_value = [cscc]
            result.scalar.return_value = 0
            return result

        mock_db = AsyncMock()
        mock_db.execute = fake_execute
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        mocker.patch(
            "src.competencies.competencies_router.check_grammatical_conflict",
            return_value=None
        )
        mocker.patch(
            "src.competencies.competencies_router.serialize_competency",
            return_value={
                "id": 193, "name": "Cloud Security Command Center",
                "aliases": "CSCC, Security Command Center",
                "sub_competencies": [], "created_at": "2024-01-01T00:00:00"
            }
        )

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db

        with get_client() as client:
            resp = client.post(
                "/",
                json={"name": "Cloud Security Command Center", "category_id": 1},
                headers=AUTH
            )

        assert resp.status_code in (200, 201)
        assert resp.json()["id"] == 193, "RC2 FAIL: doublon CSCC non detecte."
        app.dependency_overrides.pop(get_db, None)

    def test_short_canonical_contained_in_long_proposed(self, mocker):
        """
        Cas generique : 'Docker' (canonique) doit etre detecte dans
        'Docker Swarm Orchestration Tool' via containment mot-entier.
        Ratio SequenceMatcher ~ 0.35 < 0.6 sans containment check.
        """
        _patch_cache(mocker)

        docker = _make_comp(37, "Docker", "dkr, dckr, Docker Engine")

        async def fake_execute(stmt, *a, **kw):
            result = MagicMock()
            result.scalars.return_value.first.return_value = None
            result.scalars.return_value.all.return_value = [docker]
            result.scalar.return_value = 0
            return result

        mock_db = AsyncMock()
        mock_db.execute = fake_execute
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        mocker.patch(
            "src.competencies.competencies_router.check_grammatical_conflict",
            return_value=None
        )
        mocker.patch(
            "src.competencies.competencies_router.serialize_competency",
            return_value={
                "id": 37, "name": "Docker",
                "aliases": "dkr, dckr, Docker Engine, Docker Swarm Orchestration Tool",
                "sub_competencies": [], "created_at": "2024-01-01T00:00:00"
            }
        )

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db

        with get_client() as client:
            resp = client.post(
                "/",
                json={"name": "Docker Swarm Orchestration Tool", "category_id": 1},
                headers=AUTH
            )

        assert resp.status_code in (200, 201)
        assert resp.json()["id"] == 37, (
            "RC2 FAIL: 'Docker Swarm Orchestration Tool' n'a pas resolu vers Docker (id=37)."
        )
        app.dependency_overrides.pop(get_db, None)

    def test_no_false_positive_on_short_common_words(self, mocker):
        """
        Garde-fou : 'Cloud Run' ne doit PAS matcher 'Cloud' (trop court, ambigu).
        Le containment check doit exiger un minimum de 5 chars dans le nom canonique.
        """
        _patch_cache(mocker)

        cloud_generic = _make_comp(999, "Cloud", "")

        async def fake_execute(stmt, *a, **kw):
            result = MagicMock()
            result.scalars.return_value.first.return_value = None
            result.scalars.return_value.all.return_value = [cloud_generic]
            result.scalar.return_value = 0
            return result

        mock_db = AsyncMock()
        mock_db.execute = fake_execute
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        async def fake_refresh(obj):
            obj.id = 120
            obj.name = "Cloud Run"
            obj.aliases = ""
            obj.children = []
            obj.description = None
            obj.color = None
            obj.icon = None
            obj.is_validated = True
            obj.category_id = 1
            obj.parent_id = None

        mock_db.refresh = fake_refresh

        mocker.patch(
            "src.competencies.competencies_router.check_grammatical_conflict",
            return_value=None
        )
        mocker.patch(
            "src.competencies.competencies_router._generate_aliases_for_competency",
            return_value=""
        )
        mocker.patch(
            "src.competencies.competencies_router.serialize_competency",
            return_value={
                "id": 120, "name": "Cloud Run",
                "aliases": "", "sub_competencies": [],
                "created_at": "2024-01-01T00:00:00"
            }
        )

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db

        with get_client() as client:
            resp = client.post(
                "/",
                json={"name": "Cloud Run", "category_id": 1},
                headers=AUTH
            )

        assert resp.status_code in (200, 201)
        # 'Cloud Run' doit creer un NOUVEAU noeud (id=120), pas matcher 'Cloud' (999)
        assert resp.json()["id"] != 999, (
            "RC2 FAIL: faux positif — 'Cloud Run' matche a tort vers 'Cloud' (id=999). "
            "Le containment check doit ignorer les noms canoniques < 5 chars."
        )
        app.dependency_overrides.pop(get_db, None)


# ==============================================================================
# RC3 — bulk_tree : les aliases doivent enrichir les noeuds existants
# ==============================================================================

class TestRC3BulkTreeAliasEnrichment:
    """
    RC3 : Quand bulk_tree importe un noeud avec des aliases plus riches que ceux
    existants en base, il doit MERGER les aliases (union), pas les ecraser.

    Fix attendu : dans bulk_tree, lors du touch d'un noeud existant,
    merger les aliases payload avec les aliases existants.

    Ces tests utilisent la DB SQLite in-memory du conftest pour simuler
    les conditions reelles (plusieurs appels execute() dans bulk_tree).
    """

    def test_bulk_tree_merges_aliases_on_existing_node(self):
        """
        Pre-condition : 'Kubernetes' existe en DB avec aliases='k8s, kube'.
        Action : bulk_tree avec payload {"Kubernetes": {"aliases": "GKE, Google Kubernetes Engine, k8s"}}.
        Resultat attendu : aliases = 'k8s, kube, GKE, Google Kubernetes Engine' (union).
        """
        with get_client() as client:
            # 1. Creer 'Kubernetes' avec aliases initiaux
            resp_create = client.post(
                "/",
                json={"name": "KubernetesRC3Test", "aliases": "k8s-rc3, kube-rc3"},
                headers=AUTH
            )
            assert resp_create.status_code in (200, 201), (
                f"Setup FAIL: {resp_create.text}"
            )
            kube_id = resp_create.json()["id"]

            # 2. Lancer bulk_tree avec aliases enrichis
            resp_bulk = client.post(
                "/bulk_tree",
                json={
                    "tree": {
                        "KubernetesRC3Test": {
                            "aliases": "GKE-rc3, Google Kubernetes Engine RC3, k8s-rc3",
                            "description": "Orchestrateur de conteneurs"
                        }
                    }
                },
                headers=AUTH
            )
            assert resp_bulk.status_code in (200, 202, 204), (
                f"bulk_tree a retourne {resp_bulk.status_code}: {resp_bulk.text}"
            )

            # 3. Verifier les aliases merges via GET
            resp_get = client.get(f"/{kube_id}", headers=AUTH)
            assert resp_get.status_code == 200
            final_aliases_str = resp_get.json().get("aliases", "") or ""
            final_aliases = {
                a.strip().lower()
                for a in final_aliases_str.split(",")
                if a.strip()
            }

            assert "gke-rc3" in final_aliases, (
                f"RC3 FAIL: 'GKE-rc3' n'a pas ete merge. Aliases finaux: '{final_aliases_str}'. "
                f"Le bulk_tree ecrase les aliases au lieu de merger."
            )
            assert "google kubernetes engine rc3" in final_aliases, (
                f"RC3 FAIL: 'Google Kubernetes Engine RC3' n'a pas ete merge. "
                f"Aliases finaux: '{final_aliases_str}'."
            )
            assert "kube-rc3" in final_aliases, (
                f"RC3 FAIL: l'alias existant 'kube-rc3' a ete perdu lors du merge. "
                f"Aliases finaux: '{final_aliases_str}'."
            )
            assert "k8s-rc3" in final_aliases, (
                f"RC3 FAIL: l'alias commun 'k8s-rc3' a ete duplique ou perdu. "
                f"Aliases finaux: '{final_aliases_str}'."
            )

    def test_bulk_tree_preserves_aliases_when_payload_has_none(self):
        """
        Si le payload bulk_tree n'a PAS de champ aliases pour un noeud existant,
        les aliases existants en DB doivent etre preserves.
        """
        with get_client() as client:
            # 1. Creer avec aliases
            resp_create = client.post(
                "/",
                json={"name": "TerraformRC3Test", "aliases": "tf-rc3, hcl-rc3, terraform-cli-rc3"},
                headers=AUTH
            )
            assert resp_create.status_code in (200, 201)
            tf_id = resp_create.json()["id"]

            # 2. bulk_tree sans aliases dans le payload
            resp_bulk = client.post(
                "/bulk_tree",
                json={
                    "tree": {
                        "TerraformRC3Test": {
                            "description": "Infrastructure as Code"
                        }
                    }
                },
                headers=AUTH
            )
            assert resp_bulk.status_code in (200, 202, 204)

            # 3. Les aliases doivent etre preserves
            resp_get = client.get(f"/{tf_id}", headers=AUTH)
            final_aliases_str = resp_get.json().get("aliases", "") or ""
            final_aliases = {
                a.strip().lower()
                for a in final_aliases_str.split(",")
                if a.strip()
            }

            assert "tf-rc3" in final_aliases, (
                f"RC3 FAIL: alias 'tf-rc3' perdu quand payload n'a pas d'aliases. "
                f"Aliases finaux: '{final_aliases_str}'."
            )
            assert "hcl-rc3" in final_aliases, (
                f"RC3 FAIL: alias 'hcl-rc3' perdu quand payload n'a pas d'aliases. "
                f"Aliases finaux: '{final_aliases_str}'."
            )
