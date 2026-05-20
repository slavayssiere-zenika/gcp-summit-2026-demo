"""
test_mock_gemini_config.py — Tests unitaires pour config.py.

Couvre les deux modes d'exécution :
  - PRD : GEMINI_API_BASE_URL et VERTEX_API_BASE_URL absents → comportement original.
  - Perf-test local : variables présentes → HttpOptions avec baseUrl → redirection mock.

Ces tests rejouent l'initialisation de config.py via importlib.reload pour isoler
l'effet de chaque variable d'environnement.
"""
import importlib
import os
from unittest.mock import MagicMock, patch


# ── Helpers ────────────────────────────────────────────────────────────────────

def _reload_config(env_overrides: dict) -> object:
    """Recharge src.services.config avec les env vars fournies et retourne le module."""
    env = {
        "SECRET_KEY": "test-secret-key-xxxx",
        "GEMINI_API_BASE_URL": "",
        "VERTEX_API_BASE_URL": "",
        "GOOGLE_API_KEY": "",
        "GCP_PROJECT_ID": "",
        "VERTEX_LOCATION": "europe-west1",
        **env_overrides,
    }
    with patch.dict(os.environ, env, clear=False):
        import src.services.config as cfg
        importlib.reload(cfg)
        return cfg


# ── Tests PRD mode ─────────────────────────────────────────────────────────────

class TestConfigPRDMode:
    """
    Simule l'environnement Cloud Run PRD :
    - GOOGLE_API_KEY défini, GCP_PROJECT_ID défini
    - GEMINI_API_BASE_URL et VERTEX_API_BASE_URL ABSENTS
    """

    def test_gemini_client_uses_real_key_no_http_options(self):
        """PRD : client Gemini créé avec la vraie clé, _http_opts=None."""
        mock_client_cls = MagicMock()
        mock_instance = MagicMock()
        mock_client_cls.return_value = mock_instance

        with patch("google.genai.Client", mock_client_cls):
            cfg = _reload_config({"GOOGLE_API_KEY": "real-api-key-prd"})

        # Client créé avec api_key réelle
        calls = mock_client_cls.call_args_list
        gemini_calls = [c for c in calls if c.kwargs.get("api_key") == "real-api-key-prd"]
        assert gemini_calls, "genai.Client doit être appelé avec api_key=real-api-key-prd en PRD"

        # http_options doit être None (pas de redirection)
        assert cfg.GEMINI_API_BASE_URL == ""
        gemini_call = gemini_calls[0]
        assert gemini_call.kwargs.get("http_options") is None, (
            "http_options doit être None en PRD (pas de GEMINI_API_BASE_URL)"
        )

    def test_gemini_client_is_none_when_no_api_key_and_no_base_url(self):
        """
        PRD safe-failure : sans GOOGLE_API_KEY et sans GEMINI_API_BASE_URL,
        client doit être None (comportement original préservé → 503 explicite).
        """
        mock_client_cls = MagicMock()

        with patch("google.genai.Client", mock_client_cls):
            cfg = _reload_config({"GOOGLE_API_KEY": "", "GEMINI_API_BASE_URL": ""})

        assert cfg.client is None, (
            "client doit être None si ni GOOGLE_API_KEY ni GEMINI_API_BASE_URL ne sont définis. "
            "Cela préserve le comportement original (503 explicite au lieu de 401 opaque)."
        )

    def test_vertex_batch_client_none_when_no_project(self):
        """PRD safe-failure : vertex_batch_client=None si GCP_PROJECT_ID absent."""
        mock_client_cls = MagicMock()

        with patch("google.genai.Client", mock_client_cls):
            _reload_config({"GCP_PROJECT_ID": "", "GOOGLE_API_KEY": "key"})

        # vertex_batch_client non créé — aucun appel vertexai=True attendu
        vertex_calls = [c for c in mock_client_cls.call_args_list if c.kwargs.get("vertexai") is True]
        assert not vertex_calls, (
            "genai.Client(vertexai=True) ne doit pas être appelé si GCP_PROJECT_ID est absent."
        )

    def test_vertex_batch_client_created_with_vertexai_mode(self):
        """PRD : vertex_batch_client créé avec vertexai=True et project/location réels."""
        mock_client_cls = MagicMock()
        mock_instance = MagicMock()
        mock_client_cls.return_value = mock_instance

        with patch("google.genai.Client", mock_client_cls):
            _reload_config({
                "GCP_PROJECT_ID": "my-prd-project",
                "VERTEX_LOCATION": "europe-west1",
                "GOOGLE_API_KEY": "real-key",
                "VERTEX_API_BASE_URL": "",
            })

        # Trouver l'appel vertexai=True
        vertex_calls = [c for c in mock_client_cls.call_args_list if c.kwargs.get("vertexai") is True]
        assert vertex_calls, "genai.Client doit être appelé avec vertexai=True pour vertex_batch_client"

        vertex_call = vertex_calls[0]
        assert vertex_call.kwargs.get("project") == "my-prd-project"
        assert vertex_call.kwargs.get("location") == "europe-west1"
        assert vertex_call.kwargs.get("http_options") is None, (
            "http_options doit être None pour vertex_batch_client en PRD"
        )


# ── Tests Perf-test mode ────────────────────────────────────────────────────────

class TestConfigPerfTestMode:
    """
    Simule l'environnement local perf-test :
    - GEMINI_API_BASE_URL=http://mock_gemini:8099
    - VERTEX_API_BASE_URL=http://mock_gemini:8099
    - GOOGLE_API_KEY absent (pas de vraie clé en local)
    - GCP_PROJECT_ID présent (pour déclencher vertex_batch_client)
    """

    def test_gemini_client_uses_mock_base_url(self):
        """Perf : client Gemini créé avec HttpOptions(baseUrl=mock_gemini) et mock-key-local."""
        mock_client_cls = MagicMock()
        mock_http_opts_cls = MagicMock()
        mock_opts_instance = MagicMock()
        mock_http_opts_cls.return_value = mock_opts_instance

        with patch("google.genai.Client", mock_client_cls), \
                patch("google.genai.types.HttpOptions", mock_http_opts_cls):
            cfg = _reload_config({
                "GOOGLE_API_KEY": "",
                "GEMINI_API_BASE_URL": "http://mock_gemini:8099",
            })

        # HttpOptions doit être instancié avec baseUrl=mock_gemini
        mock_http_opts_cls.assert_called_once_with(baseUrl="http://mock_gemini:8099")

        # Client doit être créé avec api_key=mock-key-local et http_options
        gemini_api_calls = [
            c for c in mock_client_cls.call_args_list
            if c.kwargs.get("api_key") == "mock-key-local"
        ]
        assert gemini_api_calls, "En mode perf, api_key doit être 'mock-key-local'"
        assert gemini_api_calls[0].kwargs.get("http_options") is mock_opts_instance

        assert cfg.GEMINI_API_BASE_URL == "http://mock_gemini:8099"

    def test_vertex_batch_client_uses_mock_base_url(self):
        """Perf : vertex_batch_client créé avec HttpOptions(baseUrl=mock_gemini)."""
        mock_client_cls = MagicMock()
        mock_http_opts_cls = MagicMock()
        mock_opts_instance = MagicMock()
        mock_http_opts_cls.return_value = mock_opts_instance

        with patch("google.genai.Client", mock_client_cls), \
                patch("google.genai.types.HttpOptions", mock_http_opts_cls):
            cfg = _reload_config({
                "GCP_PROJECT_ID": "local-perf-project",
                "VERTEX_LOCATION": "europe-west1",
                "VERTEX_API_BASE_URL": "http://mock_gemini:8099",
                "GOOGLE_API_KEY": "",
                "GEMINI_API_BASE_URL": "http://mock_gemini:8099",
            })

        # Trouver l'appel vertex avec http_options
        vertex_calls = [c for c in mock_client_cls.call_args_list if c.kwargs.get("vertexai") is True]
        assert vertex_calls, "genai.Client(vertexai=True) doit être appelé en mode perf"
        assert vertex_calls[0].kwargs.get("http_options") is mock_opts_instance, (
            "vertex_batch_client doit recevoir http_options=HttpOptions(baseUrl=mock_gemini)"
        )
        assert cfg.VERTEX_API_BASE_URL == "http://mock_gemini:8099"

    def test_gemini_client_not_none_when_only_base_url_set(self):
        """
        Perf : GEMINI_API_BASE_URL seule (sans GOOGLE_API_KEY) doit quand même
        créer un client (avec mock-key-local) — pas de client=None.
        """
        mock_client_cls = MagicMock()

        with patch("google.genai.Client", mock_client_cls):
            cfg = _reload_config({
                "GOOGLE_API_KEY": "",
                "GEMINI_API_BASE_URL": "http://mock_gemini:8099",
            })

        assert cfg.client is not None, (
            "client ne doit pas être None quand GEMINI_API_BASE_URL est défini "
            "(mode perf-test avec mock_gemini actif)."
        )
