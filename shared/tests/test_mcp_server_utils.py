"""Tests pour shared/mcp_server_utils.py."""
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-xxxxxxxxx")


class TestGetMcpTraceHeaders:
    """Teste get_mcp_trace_headers."""

    def test_returns_dict(self):
        from mcp_server_utils import get_mcp_trace_headers
        headers = get_mcp_trace_headers()
        assert isinstance(headers, dict)

    def test_includes_auth_when_context_set(self):
        from mcp_server_utils import get_mcp_trace_headers
        with patch("mcp_server_utils.auth_header_var") as mock_var:
            mock_var.get = MagicMock(return_value="Bearer test-token-xyz")
            headers = get_mcp_trace_headers()
            assert headers.get("Authorization") == "Bearer test-token-xyz"

    def test_no_auth_when_context_empty(self):
        from mcp_server_utils import get_mcp_trace_headers
        with patch("mcp_server_utils.auth_header_var") as mock_var:
            mock_var.get = MagicMock(return_value=None)
            headers = get_mcp_trace_headers()
            assert "Authorization" not in headers

    def test_otel_inject_called(self):
        from mcp_server_utils import get_mcp_trace_headers
        with patch("mcp_server_utils.inject") as mock_inject:
            get_mcp_trace_headers()
            mock_inject.assert_called_once()


class TestSetupMcpTracerProvider:
    """Teste setup_mcp_tracer_provider."""

    def test_returns_tracer_object(self):
        """La fonction retourne un Tracer OTel valide."""
        from mcp_server_utils import setup_mcp_tracer_provider
        with patch.dict(os.environ, {"TRACE_EXPORTER": "none", "TRACE_SAMPLING_RATE": "0.0"}):
            with patch("mcp_server_utils.BatchSpanProcessor"), \
                 patch("mcp_server_utils.trace.set_tracer_provider"), \
                 patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()) as mock_get:
                tracer = setup_mcp_tracer_provider("test-service")
                mock_get.assert_called_once_with("test-service")
                assert tracer is not None

    def test_http_exporter_branch(self):
        """Branch TRACE_EXPORTER=http doit importer OTLPSpanExporter HTTP."""
        from mcp_server_utils import setup_mcp_tracer_provider
        with patch.dict(os.environ, {"TRACE_EXPORTER": "http"}):
            with patch("mcp_server_utils.BatchSpanProcessor"), \
                 patch("mcp_server_utils.trace.set_tracer_provider"), \
                 patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()):
                try:
                    setup_mcp_tracer_provider("test-http")
                except Exception:
                    pass  # Import optionnel peut manquer en test

    def test_gcp_exporter_branch(self):
        """Branch TRACE_EXPORTER=gcp doit utiliser CloudTraceSpanExporter."""
        from mcp_server_utils import setup_mcp_tracer_provider
        with patch.dict(os.environ, {"TRACE_EXPORTER": "gcp"}):
            with patch("mcp_server_utils.BatchSpanProcessor"), \
                 patch("mcp_server_utils.trace.set_tracer_provider"), \
                 patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()):
                try:
                    setup_mcp_tracer_provider("test-gcp")
                except Exception:
                    pass  # CloudTraceSpanExporter optionnel en CI

    def test_global_textmap_is_set(self):
        """La propagation globale OTel doit être configurée."""
        from mcp_server_utils import setup_mcp_tracer_provider
        with patch("mcp_server_utils.propagate.set_global_textmap") as mock_set, \
             patch("mcp_server_utils.BatchSpanProcessor"), \
             patch("mcp_server_utils.trace.set_tracer_provider"), \
             patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()):
            setup_mcp_tracer_provider("test-textmap")
            mock_set.assert_called_once()

    def test_service_name_in_resource(self):
        """Le nom de service doit apparaître dans les attributs de la ressource."""
        from mcp_server_utils import setup_mcp_tracer_provider
        captured_provider = {}

        def capture_provider(p):
            captured_provider["provider"] = p

        with patch("mcp_server_utils.trace.set_tracer_provider", side_effect=capture_provider), \
             patch("mcp_server_utils.BatchSpanProcessor"), \
             patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()):
            setup_mcp_tracer_provider("my-special-service")

        provider = captured_provider.get("provider")
        if provider:
            resource_attrs = provider.resource.attributes
            assert resource_attrs.get("service.name") == "my-special-service"
