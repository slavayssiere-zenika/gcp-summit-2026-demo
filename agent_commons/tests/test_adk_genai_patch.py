# Copyright 2026 Zenika — Golden Rules Compliance Test
import os
import pytest
from opentelemetry import trace


try:
    from google.adk.plugins.auto_tracing_plugin import AutoTracingPlugin
    HAS_AUTO_TRACING_PLUGIN = True
except ImportError:
    HAS_AUTO_TRACING_PLUGIN = False


@pytest.mark.skipif(not HAS_AUTO_TRACING_PLUGIN, reason="AutoTracingPlugin non disponible dans cette version de l'ADK")
def test_adk_genai_patch_validation():
    """Vérifie que le correctif d'agent_commons sur BaseApiClient._ensure_httpx_ssl_ctx
    intercepte le rebinding défectueux de l'ADK et permet l'instanciation de genai.Client().
    """
    # 0. Importer agent_commons pour appliquer activement les monkeypatches du projet
    import agent_commons  # noqa: F401

    # 1. Configurer un environnement avec une clé d'API factice
    os.environ["ADK_AUTO_TRACING"] = "true"
    os.environ["GEMINI_API_KEY"] = "fake-api-key-for-test-validation"

    # 2. Importer les modules requis après l'application du patch
    from google import genai
    from google.genai._api_client import BaseApiClient

    # 3. Simuler le rebinding de l'ADK qui détruit le descripteur staticmethod
    tracer = trace.get_tracer("test-tracer")
    plugin = AutoTracingPlugin(tracer=tracer)

    current_method = BaseApiClient._ensure_httpx_ssl_ctx

    plugin._rebind(BaseApiClient, "_ensure_httpx_ssl_ctx", current_method)

    # 4. Tenter l'instanciation du client
    # Si le patch fonctionne, cela réussit. S'il ne fonctionne pas, cela lève un TypeError.
    try:
        client = genai.Client()
        assert client is not None
    except TypeError as e:
        pytest.fail(f"Le correctif d'auto-tracing ADK a échoué. TypeError : {e}")


def test_get_api_client_direct_static_call():
    """Vérifie que la fonction _patched_get_api_client gère correctement
    un appel statique standard (sans instance 'self' passée en premier argument).
    """
    import agent_commons  # noqa: F401
    from google import genai
    from unittest.mock import MagicMock, patch

    # On mock l'appel à la fonction originale pour s'assurer qu'elle reçoit les bons arguments
    mock_original = MagicMock()
    with patch("agent_commons._original_get_api_client", mock_original):
        # Appel statique avec vertexai en positionnel
        genai.Client._get_api_client(True, "api-key")
        mock_original.assert_called_once_with(True, "api-key")
        mock_original.reset_mock()

        # Appel statique avec vertexai en keyword
        genai.Client._get_api_client(vertexai=False)
        mock_original.assert_called_once_with(vertexai=False)


def test_get_api_client_bound_instance_call():
    """Vérifie que la fonction _patched_get_api_client gère correctement
    un appel "bound" (où l'instance 'self' est passée par erreur en premier argument
    suite au rebinding d'auto-tracing de l'ADK).
    """
    import agent_commons  # noqa: F401
    from unittest.mock import MagicMock, patch

    mock_original = MagicMock()
    mock_client_instance = MagicMock()
    # On mock l'instance de Client pour qu'elle ait un nom de classe "Client"
    mock_client_instance.__class__.__name__ = "Client"

    with patch("agent_commons._original_get_api_client", mock_original):
        # Simulation d'un appel bound : _get_api_client(self, vertexai, api_key)
        # Ici on passe explicitement mock_client_instance en premier argument
        agent_commons._patched_get_api_client(mock_client_instance, True, "api-key")
        # Le premier argument 'self' doit être éliminé de l'appel à l'original
        mock_original.assert_called_once_with(True, "api-key")
        mock_original.reset_mock()

        # Simulation d'un appel bound avec arguments nommés
        agent_commons._patched_get_api_client(mock_client_instance, vertexai=False)
        mock_original.assert_called_once_with(vertexai=False)


def test_ensure_httpx_ssl_ctx_direct_static_call():
    """Vérifie que la fonction _patched_ensure_httpx_ssl_ctx gère correctement
    un appel statique standard (sans instance 'self' passée en premier argument).
    """
    import agent_commons  # noqa: F401
    from google.genai._api_client import BaseApiClient
    from google.genai.types import HttpOptions
    from unittest.mock import MagicMock, patch

    mock_original = MagicMock()
    mock_options = MagicMock(spec=HttpOptions)
    mock_options.__class__.__name__ = "HttpOptions"

    with patch("agent_commons._original_ensure_httpx_ssl_ctx", mock_original):
        # Appel statique standard
        BaseApiClient._ensure_httpx_ssl_ctx(mock_options)
        mock_original.assert_called_once_with(mock_options)


def test_ensure_httpx_ssl_ctx_bound_instance_call():
    """Vérifie que la fonction _patched_ensure_httpx_ssl_ctx gère correctement
    un appel "bound" (où l'instance 'self' de BaseApiClient est passée par erreur
    en premier argument suite au rebinding d'auto-tracing de l'ADK).
    """
    import agent_commons  # noqa: F401
    from google.genai._api_client import BaseApiClient
    from google.genai.types import HttpOptions
    from unittest.mock import MagicMock, patch

    mock_original = MagicMock()
    mock_base_api_client_instance = MagicMock(spec=BaseApiClient)
    mock_base_api_client_instance.__class__.__name__ = "BaseApiClient"
    mock_options = MagicMock(spec=HttpOptions)
    mock_options.__class__.__name__ = "HttpOptions"

    with patch("agent_commons._original_ensure_httpx_ssl_ctx", mock_original):
        # Simulation d'un appel bound : _ensure_httpx_ssl_ctx(self, options)
        agent_commons._patched_ensure_httpx_ssl_ctx(mock_base_api_client_instance, mock_options)
        # Le premier argument 'self' doit être éliminé de l'appel à l'original
        mock_original.assert_called_once_with(mock_options)

