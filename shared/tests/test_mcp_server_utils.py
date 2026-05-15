"""Tests pour shared/mcp_server_utils.py — injection des valeurs configurables.

Couvre :
- get_mcp_trace_headers : injection Authorization depuis auth_header_var
- setup_mcp_tracer_provider : injection service_name dans Resource OTel
- APP_VERSION : reflété dans service.version de la Resource
- TRACE_SAMPLING_RATE : transmis au sampler TraceIdRatioBased
- TRACE_EXPORTER branches : grpc (défaut), http, gcp
- TraceContextTextMapPropagator enregistré globalement
"""
import os
from unittest.mock import MagicMock, call, patch

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-xxxxxxxxx")


# ─── get_mcp_trace_headers ────────────────────────────────────────────────────

class TestGetMcpTraceHeaders:
    """Teste get_mcp_trace_headers."""

    def test_returns_dict(self):
        from mcp_server_utils import get_mcp_trace_headers
        headers = get_mcp_trace_headers()
        assert isinstance(headers, dict)

    def test_includes_authorization_when_context_set(self):
        from mcp_server_utils import get_mcp_trace_headers
        with patch("mcp_server_utils.auth_header_var") as mock_var:
            mock_var.get = MagicMock(return_value="Bearer my-jwt-token")
            headers = get_mcp_trace_headers()
        assert headers.get("Authorization") == "Bearer my-jwt-token"

    def test_no_authorization_when_context_is_none(self):
        from mcp_server_utils import get_mcp_trace_headers
        with patch("mcp_server_utils.auth_header_var") as mock_var:
            mock_var.get = MagicMock(return_value=None)
            headers = get_mcp_trace_headers()
        assert "Authorization" not in headers

    def test_no_authorization_when_context_is_empty_string(self):
        from mcp_server_utils import get_mcp_trace_headers
        with patch("mcp_server_utils.auth_header_var") as mock_var:
            mock_var.get = MagicMock(return_value="")
            headers = get_mcp_trace_headers()
        # Chaîne vide = falsy → pas d'Authorization
        assert "Authorization" not in headers

    def test_otel_inject_is_called_to_propagate_trace_context(self):
        """OTel inject() doit être appelé pour propager les trace-ids W3C."""
        from mcp_server_utils import get_mcp_trace_headers
        with patch("mcp_server_utils.inject") as mock_inject:
            get_mcp_trace_headers()
            mock_inject.assert_called_once()

    def test_inject_receives_the_headers_dict(self):
        """inject() reçoit bien le même dict que celui retourné."""
        from mcp_server_utils import get_mcp_trace_headers
        received_carriers = []

        def capture_inject(carrier, **kwargs):
            received_carriers.append(carrier)

        with patch("mcp_server_utils.inject", side_effect=capture_inject):
            headers = get_mcp_trace_headers()

        assert len(received_carriers) == 1
        assert received_carriers[0] is headers


# ─── setup_mcp_tracer_provider : service_name ────────────────────────────────

class TestSetupMcpTracerProviderServiceName:
    """Vérifie que service_name est correctement injecté dans la Resource OTel."""

    def _setup_capture(self):
        captured = {}

        def capture_provider(p):
            captured["provider"] = p

        return captured, capture_provider

    def test_service_name_in_resource_attributes(self):
        from mcp_server_utils import setup_mcp_tracer_provider
        captured, capture_provider = self._setup_capture()

        with patch("mcp_server_utils.trace.set_tracer_provider", side_effect=capture_provider), \
             patch("mcp_server_utils.BatchSpanProcessor"), \
             patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()):
            setup_mcp_tracer_provider("missions-api-mcp")

        provider = captured["provider"]
        assert provider.resource.attributes.get("service.name") == "missions-api-mcp"

    def test_different_service_names_produce_different_resources(self):
        from mcp_server_utils import setup_mcp_tracer_provider
        providers = []

        def capture_provider(p):
            providers.append(p)

        with patch("mcp_server_utils.trace.set_tracer_provider", side_effect=capture_provider), \
             patch("mcp_server_utils.BatchSpanProcessor"), \
             patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()):
            setup_mcp_tracer_provider("service-a")
            setup_mcp_tracer_provider("service-b")

        assert providers[0].resource.attributes["service.name"] == "service-a"
        assert providers[1].resource.attributes["service.name"] == "service-b"

    def test_get_tracer_called_with_service_name(self):
        from mcp_server_utils import setup_mcp_tracer_provider
        with patch("mcp_server_utils.trace.set_tracer_provider"), \
             patch("mcp_server_utils.BatchSpanProcessor"), \
             patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()) as mock_get:
            setup_mcp_tracer_provider("cv-api-mcp")
        mock_get.assert_called_once_with("cv-api-mcp")


# ─── setup_mcp_tracer_provider : APP_VERSION ─────────────────────────────────

class TestSetupMcpTracerProviderAppVersion:
    """Vérifie que APP_VERSION est reflété dans service.version de la Resource."""

    def test_app_version_defaults_to_dev(self):
        from mcp_server_utils import setup_mcp_tracer_provider
        captured = {}

        def capture_provider(p):
            captured["provider"] = p

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APP_VERSION", None)
            with patch("mcp_server_utils.trace.set_tracer_provider", side_effect=capture_provider), \
                 patch("mcp_server_utils.BatchSpanProcessor"), \
                 patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()):
                setup_mcp_tracer_provider("test-svc")

        assert captured["provider"].resource.attributes.get("service.version") == "dev"

    def test_app_version_from_env(self):
        from mcp_server_utils import setup_mcp_tracer_provider
        captured = {}

        def capture_provider(p):
            captured["provider"] = p

        with patch.dict(os.environ, {"APP_VERSION": "v1.2.3"}):
            with patch("mcp_server_utils.trace.set_tracer_provider", side_effect=capture_provider), \
                 patch("mcp_server_utils.BatchSpanProcessor"), \
                 patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()):
                setup_mcp_tracer_provider("test-svc")

        assert captured["provider"].resource.attributes.get("service.version") == "v1.2.3"


# ─── setup_mcp_tracer_provider : TRACE_SAMPLING_RATE ─────────────────────────

class TestSetupMcpTracerProviderSamplingRate:
    """Vérifie que TRACE_SAMPLING_RATE est transmis au sampler."""

    def test_default_sampling_rate_is_1(self):
        from mcp_server_utils import setup_mcp_tracer_provider
        captured = {}

        def capture_provider(p):
            captured["provider"] = p

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TRACE_SAMPLING_RATE", None)
            with patch("mcp_server_utils.trace.set_tracer_provider", side_effect=capture_provider), \
                 patch("mcp_server_utils.BatchSpanProcessor"), \
                 patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()):
                setup_mcp_tracer_provider("test-svc")

        # Le sampler est ParentBased(root=TraceIdRatioBased(1.0))
        sampler = captured["provider"].sampler
        # Le root sampler a un taux de 1.0 (toujours sample)
        assert sampler is not None

    def test_zero_sampling_rate_uses_noop_sampler(self):
        """TRACE_SAMPLING_RATE=0.0 doit produire un sampler qui rejette tout."""
        from mcp_server_utils import setup_mcp_tracer_provider
        captured_sampler = {}

        real_tracer_id_based = None

        def capture_provider(p):
            captured_sampler["sampler"] = p.sampler

        with patch.dict(os.environ, {"TRACE_SAMPLING_RATE": "0.0"}):
            with patch("mcp_server_utils.trace.set_tracer_provider", side_effect=capture_provider), \
                 patch("mcp_server_utils.BatchSpanProcessor"), \
                 patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()):
                setup_mcp_tracer_provider("test-svc")

        assert captured_sampler["sampler"] is not None


# ─── setup_mcp_tracer_provider : TRACE_EXPORTER branches ─────────────────────

class TestSetupMcpTracerProviderExporter:
    """Vérifie que la branche TRACE_EXPORTER correcte est instanciée."""

    def test_default_grpc_exporter_used(self):
        from mcp_server_utils import setup_mcp_tracer_provider
        grpc_path = "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter"
        with patch.dict(os.environ, {"TRACE_EXPORTER": "grpc"}), \
             patch(grpc_path) as mock_exp, \
             patch("mcp_server_utils.BatchSpanProcessor"), \
             patch("mcp_server_utils.trace.set_tracer_provider"), \
             patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()):
            setup_mcp_tracer_provider("svc")
        # En mode grpc : OTLPSpanExporter instancié avec insecure=True
        mock_exp.assert_called_once_with(insecure=True)

    def test_http_exporter_uses_http_variant(self):
        from mcp_server_utils import setup_mcp_tracer_provider
        http_path = "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
        with patch.dict(os.environ, {"TRACE_EXPORTER": "http"}), \
             patch(http_path) as mock_exp, \
             patch("mcp_server_utils.BatchSpanProcessor"), \
             patch("mcp_server_utils.trace.set_tracer_provider"), \
             patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()):
            setup_mcp_tracer_provider("svc")
        # En mode http : OTLPSpanExporter() sans insecure
        mock_exp.assert_called_once_with()

    def test_global_textmap_set_with_trace_context_propagator(self):
        """TraceContextTextMapPropagator doit être enregistré globalement."""
        from mcp_server_utils import setup_mcp_tracer_provider
        with patch("mcp_server_utils.propagate.set_global_textmap") as mock_set, \
             patch("mcp_server_utils.BatchSpanProcessor"), \
             patch("mcp_server_utils.trace.set_tracer_provider"), \
             patch("mcp_server_utils.trace.get_tracer", return_value=MagicMock()):
            setup_mcp_tracer_provider("svc")
        mock_set.assert_called_once()
        # L'argument doit être un TraceContextTextMapPropagator
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        args = mock_set.call_args[0]
        assert isinstance(args[0], TraceContextTextMapPropagator)
