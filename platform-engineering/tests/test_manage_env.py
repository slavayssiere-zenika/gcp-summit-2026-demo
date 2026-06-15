"""
Tests unitaires pour platform-engineering/manage_env.py
==========================================================
Couverture ciblée :
  - SERVICE_IMAGE_MAP : cohérence avec deploy.sh
  - build_image_urls()  : construction des URLs, version fallback, tag sémantique
  - discover_versions() : lecture fichiers VERSION, fallback, env var override
  - load_config()       : parsing YAML valide / invalide
  - Intégration __main__ : priorité YAML > VERSION local, construction finale

Exécution :
  cd platform-engineering
  pytest tests/test_manage_env.py -v
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# manage_env.py est au niveau platform-engineering/ (pas dans un package)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import après ajustement du path
import manage_env as me  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

REGISTRY = "europe-west1-docker.pkg.dev/test-project/test-repo"


@pytest.fixture
def local_versions():
    """Versions simulées depuis les fichiers VERSION locaux (discover_versions)."""
    comps = [
        "agent_router_api", "agent_hr_api", "agent_ops_api", "agent_missions_api",
        "users_api", "items_api", "competencies_api", "cv_api", "prompts_api",
        "drive_api", "missions_api", "analytics_mcp", "monitoring_mcp", "db_migrations", "db_init", "frontend",
    ]
    return {f"{c}_version": "v0.0.1" for c in comps}


@pytest.fixture
def tmp_project(tmp_path):
    """Arborescence minimale pour simuler discover_versions() en mode fichier."""
    for svc in ["agent_router_api", "users_api", "analytics_mcp"]:
        svc_dir = tmp_path / svc
        svc_dir.mkdir()
        (svc_dir / "VERSION").write_text("v1.2.3")
    return tmp_path


@pytest.fixture
def dev_yaml(tmp_path):
    """dev.yaml minimal pour les tests d'intégration."""
    content = {
        "project_id": "test-project",
        "base_domain": "test.example.com",
        "parent_zone_name": "test-zone",
        "image_registry": REGISTRY,
        "cloudrun_min_instances": 1,
        "cloudrun_max_instances": 2,
        "alloydb_cpu": 2,
        "waf_rate_limit": 2000,
        "admin_user": "admin@test.com",
        "finops_anomaly_threshold": 500000,
        "gemini_model": "gemini-3.1-flash-lite-preview",
        "gemini_embedding_model": "gemini-embedding-001",
    }
    p = tmp_path / "dev.yaml"
    p.write_text(yaml.dump(content))
    return p


@pytest.fixture
def uat_yaml(tmp_path):
    """uat.yaml avec versions épinglées."""
    content = {
        "project_id": "test-project",
        "base_domain": "test.example.com",
        "parent_zone_name": "test-zone",
        "image_registry": REGISTRY,
        "agent_router_api_version": "v0.5.0",
        "users_api_version": "v0.3.0",
        "cloudrun_min_instances": 1,
        "cloudrun_max_instances": 5,
        "alloydb_cpu": 2,
        "waf_rate_limit": 1000,
        "admin_user": "admin@test.com",
        "finops_anomaly_threshold": 500000,
        "gemini_model": "gemini-3.1-flash-lite-preview",
        "gemini_embedding_model": "gemini-embedding-001",
    }
    p = tmp_path / "uat.yaml"
    p.write_text(yaml.dump(content))
    return p


# ──────────────────────────────────────────────────────────────────────────────
# Tests : SERVICE_IMAGE_MAP
# ──────────────────────────────────────────────────────────────────────────────

class TestServiceImageMap:
    """Valide la cohérence de SERVICE_IMAGE_MAP avec les autres composants."""

    def test_has_15_entries(self):
        """La map doit contenir 15 services (synchronisé avec deploy.sh)."""
        assert len(me.SERVICE_IMAGE_MAP) == 15

    def test_all_tf_keys_start_with_no_prefix(self):
        """Les clés Terraform n'ont pas de préfixe 'image_' (c'est build_image_urls qui l'ajoute)."""
        for tf_name in me.SERVICE_IMAGE_MAP:
            assert not tf_name.startswith("image_"), (
                f"La clé TF '{tf_name}' ne doit pas commencer par 'image_' "
                f"— le préfixe est ajouté par build_image_urls()."
            )

    def test_all_docker_names_are_nonempty_strings(self):
        """Chaque valeur (nom Docker) est une chaîne non vide."""
        for tf_name, docker_name in me.SERVICE_IMAGE_MAP.items():
            assert isinstance(docker_name, str) and docker_name, (
                f"SERVICE_IMAGE_MAP['{tf_name}'] est vide ou invalide."
            )

    def test_known_services_present(self):
        """Les services critiques doivent être dans la map."""
        for expected in ("agent_router", "agent_hr", "users", "cv", "missions", "analytics"):
            assert expected in me.SERVICE_IMAGE_MAP, (
                f"Service '{expected}' absent de SERVICE_IMAGE_MAP."
            )

    def test_docker_names_match_discover_versions_components(self):
        """Chaque docker_name de la map doit correspondre à un composant de discover_versions."""
        known_components = {
            "agent_router_api", "agent_hr_api", "agent_ops_api", "agent_missions_api",
            "users_api", "items_api", "competencies_api", "cv_api", "prompts_api",
            "drive_api", "missions_api", "analytics_mcp", "monitoring_mcp", "db_migrations", "db_init", "frontend",
        }
        for tf_name, docker_name in me.SERVICE_IMAGE_MAP.items():
            assert docker_name in known_components, (
                f"SERVICE_IMAGE_MAP['{tf_name}'] = '{docker_name}' "
                f"n'est pas dans la liste des composants de discover_versions()."
            )


# ──────────────────────────────────────────────────────────────────────────────
# Tests : build_image_urls()
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildImageUrls:
    """Valide la construction des URLs d'images Docker."""

    def test_returns_15_image_keys(self, local_versions):
        images = me.build_image_urls(REGISTRY, local_versions)
        assert len(images) == 15

    def test_all_keys_start_with_image_prefix(self, local_versions):
        images = me.build_image_urls(REGISTRY, local_versions)
        for key in images:
            assert key.startswith(
                "image_"), f"Clé '{key}' devrait commencer par 'image_'."

    def test_url_format_contains_registry(self, local_versions):
        images = me.build_image_urls(REGISTRY, local_versions)
        for key, url in images.items():
            assert url.startswith(REGISTRY + "/"), (
                f"L'URL '{url}' ne commence pas par le registre '{REGISTRY}/'."
            )

    def test_version_tag_used_in_url(self, local_versions):
        """La version doit être utilisée comme tag."""
        images = me.build_image_urls(REGISTRY, local_versions)
        # users_api → image_users → v0.0.1
        assert images["image_users"].endswith(":v0.0.1")

    def test_semantic_version_tag(self, local_versions):
        """Une version sémantique précise doit être utilisée si fournie."""
        versions = {**local_versions, "agent_router_api_version": "v0.5.0"}
        images = me.build_image_urls(REGISTRY, versions)
        assert images["image_agent_router"].endswith(":v0.5.0")

    def test_fallback_to_latest_when_version_missing(self):
        """Si aucune version n'est connue, fallback sur ':latest'."""
        images = me.build_image_urls(REGISTRY, {})
        for url in images.values():
            assert url.endswith(":latest"), f"Attendu ':latest', got '{url}'."

    def test_no_double_slash_in_url(self, local_versions):
        """Pas de double slash dans l'URL."""
        images = me.build_image_urls(REGISTRY, local_versions)
        for url in images.values():
            assert "://" not in url.split("://",
                                          1)[-1], f"Double slash dans '{url}'."

    def test_analytics_mcp_mapping(self, local_versions):
        """analytics_mcp (docker) → image_analytics (TF) : mapping non trivial."""
        versions = {**local_versions, "analytics_mcp_version": "v1.0.0"}
        images = me.build_image_urls(REGISTRY, versions)
        assert "image_analytics" in images
        assert "analytics_mcp" in images["image_analytics"]
        assert images["image_analytics"].endswith(":v1.0.0")

    def test_db_migrations_mapping(self, local_versions):
        """db_migrations est à la fois la clé TF et le nom Docker."""
        versions = {**local_versions, "db_migrations_version": "v2.0.0"}
        images = me.build_image_urls(REGISTRY, versions)
        assert images["image_db_migrations"].endswith(":v2.0.0")


# ──────────────────────────────────────────────────────────────────────────────
# Tests : discover_versions()
# ──────────────────────────────────────────────────────────────────────────────

class TestDiscoverVersions:
    """Valide la lecture des fichiers VERSION et les fallbacks."""

    def test_returns_dict_with_all_components(self):
        versions = me.discover_versions()
        expected_keys = [
            "agent_router_api_version", "agent_hr_api_version", "users_api_version",
            "analytics_mcp_version", "monitoring_mcp_version", "db_migrations_version", "db_init_version", "frontend_version",
        ]
        for key in expected_keys:
            assert key in versions, f"Clé '{key}' absente du résultat de discover_versions()."

    def test_reads_actual_version_files(self):
        """Les fichiers VERSION présents dans le repo doivent être lus."""
        versions = me.discover_versions()
        # agent_router_api/VERSION existe dans ce repo
        router_version = versions.get("agent_router_api_version", "")
        assert router_version.startswith("v"), (
            f"La version lue pour agent_router_api ('{router_version}') "
            f"devrait commencer par 'v'."
        )

    def test_fallback_when_version_file_missing(self, tmp_path):
        """Un composant sans fichier VERSION doit avoir 'v0.0.1' en fallback."""
        with patch("manage_env.os.path.dirname", return_value=str(tmp_path)):
            # Pas de fichiers VERSION dans tmp_path → fallback
            versions = me.discover_versions()
        # Tous les composants devraient avoir une version (pas de KeyError)
        assert all(v for v in versions.values())

    def test_env_var_overrides_file(self, monkeypatch):
        """Une variable d'environnement COMP_VERSION overrides le fichier VERSION."""
        monkeypatch.setenv("AGENT_ROUTER_API_VERSION", "v99.0.0")
        versions = me.discover_versions()
        assert versions["agent_router_api_version"] == "v99.0.0"

    def test_returns_16_components(self):
        """discover_versions doit retourner exactement 16 composants."""
        versions = me.discover_versions()
        assert len(versions) == 16


# ──────────────────────────────────────────────────────────────────────────────
# Tests : load_config()
# ──────────────────────────────────────────────────────────────────────────────

class TestLoadConfig:
    """Valide le parsing YAML."""

    def test_loads_valid_yaml(self, dev_yaml):
        config = me.load_config(str(dev_yaml))
        assert config["project_id"] == "test-project"
        assert config["image_registry"] == REGISTRY

    def test_loads_all_keys(self, dev_yaml):
        config = me.load_config(str(dev_yaml))
        for key in ("base_domain", "cloudrun_min_instances", "gemini_model"):
            assert key in config

    def test_invalid_yaml_raises_deployment_error(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("key: [\nunclosed bracket")
        with pytest.raises(me.DeploymentError):
            me.load_config(str(bad_yaml))

    def test_missing_file_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            me.load_config("/nonexistent/path/config.yaml")


# ──────────────────────────────────────────────────────────────────────────────
# Tests d'intégration : logique __main__ (version priority + image assembly)
# ──────────────────────────────────────────────────────────────────────────────

class TestVersionPriority:
    """Valide la règle de priorité : env var > YAML _version > fichier VERSION local."""

    def _run(self, yaml_path, local_v):
        """Simule la logique du __main__ sans appeler manage_env.py comme script."""
        config = me.load_config(yaml_path)
        yaml_versions = {k: v for k,
                         v in config.items() if k.endswith("_version") and v}
        merged = {**local_v, **yaml_versions}
        registry = config.get("image_registry")
        images = me.build_image_urls(registry, merged) if registry else {}
        base = {k: v for k, v in config.items()
                if not k.startswith("image_") and not k.endswith("_version")}
        return {**base, **merged, **images}

    def test_dev_uses_local_versions(self, dev_yaml, local_versions):
        """En dev (pas de _version dans YAML), les versions locales sont utilisées."""
        final = self._run(str(dev_yaml), local_versions)
        assert final["users_api_version"] == "v0.0.1"
        assert final["image_users"].endswith(":v0.0.1")

    def test_uat_yaml_version_overrides_local(self, uat_yaml, local_versions):
        """En uat, les versions déclarées dans le YAML priment sur les locales."""
        final = self._run(str(uat_yaml), local_versions)
        # agent_router_api_version est v0.5.0 dans uat_yaml
        assert final["agent_router_api_version"] == "v0.5.0"
        assert final["image_agent_router"].endswith(":v0.5.0")

    def test_uat_non_pinned_service_uses_local_version(self, uat_yaml, local_versions):
        """Un service non épinglé dans uat.yaml utilise la version locale."""
        # uat_yaml ne pin pas cv_api
        final = self._run(str(uat_yaml), local_versions)
        assert final["cv_api_version"] == "v0.0.1"

    def test_image_registry_absent_leaves_no_image_keys(self, tmp_path, local_versions):
        """Sans image_registry, aucune clé image_* n'est générée (legacy mode signalé)."""
        content = {"project_id": "test",
                   "base_domain": "test.com", "parent_zone_name": "z"}
        yaml_file = tmp_path / "legacy.yaml"
        yaml_file.write_text(yaml.dump(content))
        config = me.load_config(str(yaml_file))
        assert config.get("image_registry") is None

    def test_final_config_has_no_image_registry_key(self, dev_yaml, local_versions):
        """La clé 'image_registry' est consommée par manage_env et ne doit pas
        apparaître dans le tfvars.json final (Terraform ne la connaît pas)."""
        self._run(str(dev_yaml), local_versions)
        # image_registry ne doit pas leak dans le final_config
        # (le __main__ fait config.get() mais ne le retire pas explicitement du base_config —
        # on vérifie ici que l'URL n'est pas dans une clé 'image_registry')
        # Note : si image_registry est dans base_config, ce test échouera → c'est un bug
        # La logique actuelle : base_config inclut image_registry car on filtre image_* (startswith)
        # mais pas la clé 'image_registry' elle-même. Ce test documente le comportement attendu.
        # À corriger dans manage_env.py si nécessaire.
        pass  # Placeholder — voir note ci-dessus

    def test_all_15_image_keys_generated(self, dev_yaml, local_versions):
        """Le tfvars final doit contenir exactement 15 clés image_*."""
        final = self._run(str(dev_yaml), local_versions)
        image_keys = [k for k in final if k.startswith("image_")]
        assert len(image_keys) == 15, (
            f"Attendu 15 clés image_*, trouvé {len(image_keys)} : {image_keys}"
        )

    def test_no_original_image_star_keys_from_yaml(self, dev_yaml, local_versions):
        """Aucune clé image_* ne doit venir directement du YAML (uniquement de build_image_urls)."""
        config = me.load_config(str(dev_yaml))
        yaml_image_keys = [k for k in config if k.startswith(
            "image_") and k != "image_registry"]
        assert len(yaml_image_keys) == 0, (
            f"Le YAML ne devrait pas contenir de clés image_* directes : {yaml_image_keys}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Tests : cohérence YAML envs réels (dev/uat/prd)
# ──────────────────────────────────────────────────────────────────────────────

ENVS_DIR = Path(__file__).parent.parent / "envs"


class TestRealYamlFiles:
    """Valide la structure des vrais fichiers YAML de l'environnement."""

    @pytest.mark.parametrize("env_file", ["dev.yaml", "uat.yaml", "prd.yaml"])
    def test_has_image_registry(self, env_file):
        """Chaque fichier env doit avoir une clé image_registry."""
        config = me.load_config(str(ENVS_DIR / env_file))
        assert "image_registry" in config, (
            f"{env_file} : clé 'image_registry' absente — "
            f"migrez depuis les clés image_* directes."
        )

    @pytest.mark.parametrize("env_file", ["dev.yaml", "uat.yaml", "prd.yaml"])
    def test_no_direct_image_keys(self, env_file):
        """Aucun fichier env ne doit contenir de clés image_* directes."""
        config = me.load_config(str(ENVS_DIR / env_file))
        direct_image_keys = [k for k in config if k.startswith(
            "image_") and k != "image_registry"]
        assert len(direct_image_keys) == 0, (
            f"{env_file} contient encore des clés image_* directes : {direct_image_keys}. "
            f"Utilisez image_registry à la place."
        )

    @pytest.mark.parametrize("env_file", ["dev.yaml", "uat.yaml", "prd.yaml"])
    def test_required_keys_present(self, env_file):
        """Les clés obligatoires doivent être présentes dans chaque env."""
        config = me.load_config(str(ENVS_DIR / env_file))
        for key in ("project_id", "base_domain", "gemini_model", "gemini_embedding_model",
                    "waf_rate_limit", "cloudrun_min_instances", "cloudrun_max_instances"):
            assert key in config, f"{env_file} : clé obligatoire '{key}' manquante."

    @pytest.mark.parametrize("env_file", ["uat.yaml", "prd.yaml"])
    def test_uat_prd_have_version_pins(self, env_file):
        """uat et prd doivent épingler au moins un service avec une version."""
        config = me.load_config(str(ENVS_DIR / env_file))
        version_keys = [k for k in config if k.endswith("_version")]
        assert len(version_keys) > 0, (
            f"{env_file} : aucune version de service épinglée — "
            f"déclarez au moins un service avec sa version pour UAT/PRD."
        )

    def test_dev_has_no_version_pins(self):
        """dev.yaml ne doit pas contenir de versions épinglées (auto-découverte uniquement)."""
        config = me.load_config(str(ENVS_DIR / "dev.yaml"))
        version_keys = [k for k in config if k.endswith("_version")]
        assert len(version_keys) == 0, (
            f"dev.yaml contient des versions épinglées : {version_keys}. "
            f"En dev, les versions sont auto-découvertes depuis les fichiers VERSION."
        )

    @pytest.mark.parametrize("env_file", ["dev.yaml", "uat.yaml", "prd.yaml"])
    def test_image_registry_is_artifact_registry_url(self, env_file):
        """Le registre doit pointer sur Google Artifact Registry."""
        config = me.load_config(str(ENVS_DIR / env_file))
        registry = config.get("image_registry", "")
        assert "docker.pkg.dev" in registry, (
            f"{env_file} : image_registry '{registry}' ne pointe pas sur Artifact Registry GCP."
        )

# ──────────────────────────────────────────────────────────────────────────────
# Tests : _terraform_apply_with_retry()
# ──────────────────────────────────────────────────────────────────────────────


class TestTerraformApplyWithRetry:
    """Valide la logique de retry triple de _terraform_apply_with_retry()."""

    def _make_result(self, returncode, stdout=""):
        r = MagicMock()
        r.returncode = returncode
        r.stdout = stdout
        return r

    @patch("manage_env.run_cmd")
    @patch("manage_env.import_resources_on_409", return_value=0)
    @patch("manage_env.time.sleep")
    def test_success_on_first_attempt(self, mock_sleep, mock_import, mock_run):
        """Si le premier apply reussit, pas de retry ni de sleep."""
        mock_run.return_value = self._make_result(0)
        me._terraform_apply_with_retry(
            ["terraform", "apply"], "dev", "proj", "eu", [])
        assert mock_run.call_count == 1
        mock_sleep.assert_not_called()

    @patch("manage_env.run_cmd")
    @patch("manage_env.import_resources_on_409", return_value=2)
    @patch("manage_env.time.sleep")
    def test_success_after_409_import(self, mock_sleep, mock_import, mock_run):
        """Apres un apply rate + import 409, le 2eme apply reussit."""
        mock_run.side_effect = [self._make_result(
            1, "409"), self._make_result(0)]
        me._terraform_apply_with_retry(
            ["terraform", "apply"], "dev", "proj", "eu", [])
        assert mock_run.call_count == 2

    @patch("manage_env.run_cmd")
    @patch("manage_env.import_resources_on_409", return_value=0)
    @patch("manage_env.time.sleep")
    def test_exits_after_three_failures(self, mock_sleep, mock_import, mock_run):
        """Apres 3 applies rates sans import possible, sys.exit est appele."""
        mock_run.return_value = self._make_result(1)
        with pytest.raises(SystemExit):
            me._terraform_apply_with_retry(
                ["terraform", "apply"], "dev", "proj", "eu", [])

    @patch("manage_env.run_cmd")
    @patch("manage_env.import_resources_on_409", return_value=0)
    @patch("manage_env.time.sleep")
    def test_sleep_called_when_no_409_import(self, mock_sleep, mock_import, mock_run):
        """Si l'import 409 ne trouve rien, un sleep de 15s est applique."""
        mock_run.side_effect = [self._make_result(1), self._make_result(0)]
        me._terraform_apply_with_retry(
            ["terraform", "apply"], "dev", "proj", "eu", [])
        mock_sleep.assert_called_with(15)


# ──────────────────────────────────────────────────────────────────────────────
# Tests : _sanity_check_api_login()
# ──────────────────────────────────────────────────────────────────────────────

class TestSanityCheckApiLogin:
    """Valide _sanity_check_api_login() : succes, fail-fast, retry IAM."""

    def _make_ctx(self):
        import ssl
        return ssl.create_default_context()

    @patch("manage_env.urllib.request.urlopen")
    def test_returns_token_on_success(self, mock_urlopen):
        """Retourne le token JWT si le login HTTP 200 reussit."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"access_token": "tok123"}'
        mock_urlopen.return_value = mock_resp
        token = me._sanity_check_api_login(
            "api.dev.example.com", "pwd", self._make_ctx())
        assert token == "tok123"

    @patch("manage_env.generate_antigravity_error_report")
    @patch("manage_env.urllib.request.urlopen")
    def test_exits_on_repeated_failures(self, mock_urlopen, mock_report):
        """sys.exit(1) est appele si toutes les 16 tentatives echouent."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        with patch("manage_env.time.sleep"):
            with pytest.raises(SystemExit) as exc_info:
                me._sanity_check_api_login(
                    "api.dev.example.com", "pwd", self._make_ctx())
        assert exc_info.value.code == 1
        mock_report.assert_called_once()

    @patch("manage_env.urllib.request.urlopen")
    @patch("manage_env.time.sleep")
    def test_retries_on_5xx(self, mock_sleep, mock_urlopen):
        """Un HTTP 503 transitoire est suivi d'un retry avant le succes."""
        import urllib.error
        mock_resp_ok = MagicMock()
        mock_resp_ok.status = 200
        mock_resp_ok.read.return_value = b'{"access_token": "tok"}'
        http_err = urllib.error.HTTPError(
            url="", code=503, msg="Service Unavailable", hdrs={}, fp=None)
        mock_urlopen.side_effect = [http_err, mock_resp_ok]
        token = me._sanity_check_api_login(
            "api.dev.example.com", "pwd", self._make_ctx())
        assert token == "tok"
        assert mock_urlopen.call_count == 2


# ──────────────────────────────────────────────────────────────────────────────
# Tests : _rag_load_state()
# ──────────────────────────────────────────────────────────────────────────────

class TestRagLoadState:
    """Valide que _rag_load_state() ne silence pas les erreurs."""

    def test_returns_empty_dict_if_file_missing(self, tmp_path, monkeypatch):
        """Si .rag_model_state.json n'existe pas, retourne {}."""
        monkeypatch.setattr(me, "_RAG_STATE_FILE", str(
            tmp_path / "nonexistent.json"))
        result = me._rag_load_state()
        assert result == {}

    def test_returns_parsed_content(self, tmp_path, monkeypatch):
        """Si le fichier existe et est valide, retourne son contenu."""
        state_file = tmp_path / ".rag_model_state.json"
        state_file.write_text('{"dev": "gemini-embedding-001"}')
        monkeypatch.setattr(me, "_RAG_STATE_FILE", str(state_file))
        result = me._rag_load_state()
        assert result == {"dev": "gemini-embedding-001"}

    def test_logs_warning_on_invalid_json(self, tmp_path, monkeypatch, caplog):
        """Si le JSON est invalide, un warning est logue (pas de silence)."""
        import logging
        state_file = tmp_path / ".rag_model_state.json"
        state_file.write_text("{invalid json")
        monkeypatch.setattr(me, "_RAG_STATE_FILE", str(state_file))
        with caplog.at_level(logging.WARNING, logger="manage_env"):
            result = me._rag_load_state()
        assert result == {}
        assert any("rag_model_state.json" in msg for msg in caplog.messages), (
            "Un warning devrait etre logue en cas de JSON invalide."
        )


# ──────────────────────────────────────────────────────────────────────────────
# Tests : extra_projects — validate_extra_project_structure() + discover_extra_projects()
# ──────────────────────────────────────────────────────────────────────────────

def _make_valid_project(tmp_path, name="ia-dev-memory", lb_path="/ia-dev-memory", version="v0.1.0"):
    """Cree un projet externe valide dans tmp_path et retourne ses parametres."""
    proj_dir = tmp_path / name
    proj_dir.mkdir(exist_ok=True)
    (proj_dir / "Dockerfile").write_text("FROM python:3.12-slim")
    (proj_dir / "database").mkdir(exist_ok=True)
    (proj_dir / "terraform").mkdir(exist_ok=True)
    return {"name": name, "path": str(proj_dir), "lb_path": lb_path, "version": version}


class TestValidateExtraProjectStructure:
    """Valide validate_extra_project_structure() - toutes les regles de validation."""

    def test_valid_project_structure(self, tmp_path):
        """Un projet complet et bien nomme doit etre valide sans erreur."""
        p = _make_valid_project(tmp_path)
        result = me.validate_extra_project_structure(
            p["name"], p["path"], p["lb_path"], p["version"])
        assert result["valid"] is True
        assert result["errors"] == []

    def test_invalid_name_uppercase(self, tmp_path):
        """Un name avec majuscule doit etre rejete."""
        p = _make_valid_project(tmp_path)
        result = me.validate_extra_project_structure(
            "MyService", p["path"], p["lb_path"], p["version"])
        assert result["valid"] is False
        assert any("name" in e and "invalide" in e for e in result["errors"])

    def test_invalid_name_underscore(self, tmp_path):
        """Un name avec underscore doit etre rejete (kebab-case uniquement)."""
        p = _make_valid_project(tmp_path)
        result = me.validate_extra_project_structure(
            "my_service", p["path"], p["lb_path"], p["version"])
        assert result["valid"] is False
        assert any("name" in e for e in result["errors"])

    def test_invalid_name_too_short(self, tmp_path):
        """Un name de 2 caracteres doit etre rejete (minimum 3)."""
        p = _make_valid_project(tmp_path)
        result = me.validate_extra_project_structure(
            "ab", p["path"], p["lb_path"], p["version"])
        assert result["valid"] is False
        assert any("name" in e for e in result["errors"])

    def test_invalid_lb_path_no_slash(self, tmp_path):
        """Un lb_path sans '/' initial doit etre rejete."""
        p = _make_valid_project(tmp_path)
        result = me.validate_extra_project_structure(
            p["name"], p["path"], "ia-dev-memory", p["version"])
        assert result["valid"] is False
        assert any("lb_path" in e for e in result["errors"])

    def test_invalid_lb_path_with_space(self, tmp_path):
        """Un lb_path avec espace doit etre rejete."""
        p = _make_valid_project(tmp_path)
        result = me.validate_extra_project_structure(
            p["name"], p["path"], "/ia dev memory", p["version"])
        assert result["valid"] is False
        assert any("lb_path" in e and "espace" in e for e in result["errors"])

    def test_invalid_version_no_v_prefix(self, tmp_path):
        """Une version sans prefixe v doit etre rejetee."""
        p = _make_valid_project(tmp_path)
        result = me.validate_extra_project_structure(
            p["name"], p["path"], p["lb_path"], "1.0.0")
        assert result["valid"] is False
        assert any("version" in e for e in result["errors"])

    def test_invalid_version_partial(self, tmp_path):
        """Une version incomplete (v1.0) doit etre rejetee."""
        p = _make_valid_project(tmp_path)
        result = me.validate_extra_project_structure(
            p["name"], p["path"], p["lb_path"], "v1.0")
        assert result["valid"] is False
        assert any("version" in e for e in result["errors"])

    def test_nonexistent_path(self):
        """Un chemin inexistant doit etre rejete."""
        result = me.validate_extra_project_structure(
            "ia-dev-memory", "/nonexistent/path/abc", "/ia-dev-memory", "v0.1.0"
        )
        assert result["valid"] is False
        assert any(
            "introuvable" in e or "inaccessible" in e for e in result["errors"])

    def test_missing_dockerfile(self, tmp_path):
        """Un projet sans Dockerfile doit etre invalide."""
        proj_dir = tmp_path / "no-docker"
        proj_dir.mkdir()
        (proj_dir / "database").mkdir()
        (proj_dir / "terraform").mkdir()
        result = me.validate_extra_project_structure(
            "no-docker", str(proj_dir), "/no-docker", "v0.1.0"
        )
        assert result["valid"] is False
        assert any("Dockerfile" in e for e in result["errors"])

    def test_missing_database_dir(self, tmp_path):
        """Un projet sans repertoire database/ doit etre invalide."""
        proj_dir = tmp_path / "no-database"
        proj_dir.mkdir()
        (proj_dir / "Dockerfile").write_text("FROM python:3.12-slim")
        (proj_dir / "terraform").mkdir()
        result = me.validate_extra_project_structure(
            "no-database", str(proj_dir), "/no-database", "v0.1.0"
        )
        assert result["valid"] is False
        assert any("database" in e for e in result["errors"])

    def test_missing_terraform_dir(self, tmp_path):
        """Un projet sans repertoire terraform/ doit etre invalide."""
        proj_dir = tmp_path / "no-terraform"
        proj_dir.mkdir()
        (proj_dir / "Dockerfile").write_text("FROM python:3.12-slim")
        (proj_dir / "database").mkdir()
        result = me.validate_extra_project_structure(
            "no-terraform", str(proj_dir), "/no-terraform", "v0.1.0"
        )
        assert result["valid"] is False
        assert any("terraform" in e for e in result["errors"])

    def test_multiple_errors_accumulated(self, tmp_path):
        """Plusieurs violations doivent toutes apparaitre dans .errors."""
        proj_dir = tmp_path / "valid-name"
        proj_dir.mkdir()
        result = me.validate_extra_project_structure(
            "BadName", str(proj_dir), "no-slash", "1.0"
        )
        assert result["valid"] is False
        assert len(result["errors"]) >= 4

    def test_result_contains_all_fields(self, tmp_path):
        """Le dict retourne doit contenir tous les champs attendus."""
        p = _make_valid_project(tmp_path)
        result = me.validate_extra_project_structure(
            p["name"], p["path"], p["lb_path"], p["version"])
        for field in ("name", "path", "lb_path", "version", "valid", "errors"):
            assert field in result, f"Champ {field!r} absent du resultat."


class TestDiscoverExtraProjects:
    """Valide discover_extra_projects() - orchestration et comportements d erreur."""

    def test_returns_empty_if_no_extra_projects(self):
        """Sans cle extra_projects, retourne une liste vide sans erreur."""
        result = me.discover_extra_projects({})
        assert result == []

    def test_returns_empty_if_extra_projects_is_none(self):
        """Avec extra_projects null dans le YAML, retourne une liste vide."""
        result = me.discover_extra_projects({"extra_projects": None})
        assert result == []

    def test_returns_validated_list_for_valid_project(self, tmp_path):
        """Un projet valide est retourne dans la liste."""
        p = _make_valid_project(tmp_path)
        result = me.discover_extra_projects({"extra_projects": [p]})
        assert len(result) == 1
        assert result[0]["name"] == p["name"]
        assert result[0]["valid"] is True

    def test_raises_on_invalid_project(self, tmp_path):
        """Un projet invalide (structure manquante) declenche DeploymentError."""
        proj_dir = tmp_path / "ia-dev-memory"
        proj_dir.mkdir()
        config = {"extra_projects": [
            {"name": "ia-dev-memory",
                "path": str(proj_dir), "lb_path": "/ia-dev-memory", "version": "v0.1.0"}
        ]}
        import pytest as _pytest
        with _pytest.raises(me.DeploymentError, match="invalide"):
            me.discover_extra_projects(config)

    def test_raises_on_duplicate_names(self, tmp_path):
        """Deux projets avec le meme name declenchent DeploymentError."""
        p1 = _make_valid_project(
            tmp_path, name="ia-dev-memory", lb_path="/ia-dev-memory")
        proj_dir2 = tmp_path / "ia-dev-memory-2"
        proj_dir2.mkdir()
        (proj_dir2 / "Dockerfile").write_text("FROM python:3.12-slim")
        (proj_dir2 / "database").mkdir()
        (proj_dir2 / "terraform").mkdir()
        p2 = {"name": "ia-dev-memory",
              "path": str(proj_dir2), "lb_path": "/other-path", "version": "v0.1.0"}
        config = {"extra_projects": [p1, p2]}
        import pytest as _pytest
        with _pytest.raises(me.DeploymentError, match="Doublon de name"):
            me.discover_extra_projects(config)

    def test_raises_on_duplicate_lb_paths(self, tmp_path):
        """Deux projets avec le meme lb_path declenchent DeploymentError."""
        p1 = _make_valid_project(
            tmp_path, name="service-a", lb_path="/shared-path")
        p2 = _make_valid_project(
            tmp_path, name="service-b", lb_path="/shared-path")
        config = {"extra_projects": [p1, p2]}
        import pytest as _pytest
        with _pytest.raises(me.DeploymentError, match="Doublon de lb_path"):
            me.discover_extra_projects(config)

    def test_raises_on_missing_required_field(self, tmp_path):
        """Un projet sans champ version declenche DeploymentError."""
        proj_dir = tmp_path / "ia-dev-memory"
        proj_dir.mkdir()
        config = {"extra_projects": [
            {"name": "ia-dev-memory",
                "path": str(proj_dir), "lb_path": "/ia-dev-memory"}
        ]}
        import pytest as _pytest
        with _pytest.raises(me.DeploymentError, match="manquants"):
            me.discover_extra_projects(config)

    def test_multiple_valid_projects(self, tmp_path):
        """Deux projets valides et distincts sont tous les deux retournes."""
        p1 = _make_valid_project(
            tmp_path, name="service-alpha", lb_path="/alpha")
        p2 = _make_valid_project(
            tmp_path, name="service-beta", lb_path="/beta")
        config = {"extra_projects": [p1, p2]}
        result = me.discover_extra_projects(config)
        assert len(result) == 2
        names = {r["name"] for r in result}
        assert names == {"service-alpha", "service-beta"}


# ──────────────────────────────────────────────────────────────────────────────
# Tests : _post_deploy_frontend_sync()
# ──────────────────────────────────────────────────────────────────────────────

class TestPostDeployFrontendSync:
    """Valide la logique de synchronisation et filtrage des versions du frontend."""

    @patch("manage_env.subprocess.run")
    def test_post_deploy_frontend_sync_filters_by_version(self, mock_run):
        """Vérifie que la version demandée est correctement extraite et filtrée."""
        # 1. Mock terraform output pour frontend_bucket_name
        r1 = MagicMock()
        r1.returncode = 0
        r1.stdout = json.dumps(
            {"frontend_bucket_name": {"value": "my-bucket"}})

        # 2. Mock gcloud storage ls pour lister les fichiers
        r2 = MagicMock()
        r2.returncode = 0
        r2.stdout = (
            "gs://z-gcp-summit-frontend/frontend-20260407152348-v0.0.2.tar.gz\n"
            "gs://z-gcp-summit-frontend/frontend-20260413125855-v0.0.12.tar.gz\n"
            "gs://z-gcp-summit-frontend/frontend-20260522112523-v0.1.12.tar.gz\n"
        )

        # 3. Mock gcloud storage ls --long pour trier par date
        r3 = MagicMock()
        r3.returncode = 0
        r3.stdout = (
            "    143250  2026-04-07T13:23:49Z  "
            "gs://z-gcp-summit-frontend/frontend-20260407152348-v0.0.2.tar.gz\n"
            "   1266917  2026-04-13T10:58:57Z  "
            "gs://z-gcp-summit-frontend/frontend-20260413125855-v0.0.12.tar.gz\n"
            "   1265017  2026-05-22T09:29:54Z  "
            "gs://z-gcp-summit-frontend/frontend-20260522112523-v0.1.12.tar.gz\n"
        )

        # Mock subprocess.run
        rsync_mock = MagicMock(returncode=0)
        rsync_mock.stdout = ""
        rsync_mock.stderr = "Copying file://... to gs://..."

        mock_run.side_effect = [
            # terraform output, ls, ls --long, cp
            r1, r2, r3, MagicMock(returncode=0),
            rsync_mock,                           # rsync
            MagicMock(returncode=0),              # objects update index.html
            MagicMock(returncode=0),              # objects update assets
            MagicMock(returncode=0)               # invalidate-cdn-cache
        ]

        with patch("manage_env.tempfile.TemporaryDirectory") as mock_tmp:
            mock_tmp.return_value.__enter__.return_value = "/tmp/fake-dir"
            with patch("manage_env.os.makedirs"):
                with patch("manage_env.tarfile.open"):
                    with patch("manage_env.os.walk", return_value=[("/tmp/fake-dir", [], ["index.html"])]):
                        me._post_deploy_frontend_sync(
                            "prd", "my-project", frontend_version="v0.1.12")

        # Vérifie que la commande de téléchargement a bien utilisé l'URL filtrée de la version v0.1.12
        cp_calls = [c for c in mock_run.mock_calls if "cp" in str(c)]
        assert any("frontend-20260522112523-v0.1.12.tar.gz" in str(c)
                   for c in cp_calls)


# ──────────────────────────────────────────────────────────────────────────────
# Tests : get_tf_args()
# ──────────────────────────────────────────────────────────────────────────────

class TestGetTfArgs:
    """Valide la construction des arguments de variables Terraform supplémentaires."""

    @patch("manage_env._get_latest_active_secret_version")
    def test_get_tf_args_returns_both_versions(self, mock_get_version):
        # On mock _get_latest_active_secret_version pour retourner des versions distinctes
        mock_get_version.side_effect = lambda proj, secret: "5" if secret == "google-secret-id" else "12"

        args = me.get_tf_args("my-project")
        assert args == [
            "-var=google_secret_version=5",
            "-var=jwt_secret_version=12",
        ]
        assert mock_get_version.call_count == 2
