import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from agent_commons.exception_handler import make_global_exception_handler
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException


@pytest.fixture
def mock_request():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": [(b"authorization", b"Bearer test-token")],
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_global_exception_handler_http_exception(mock_request):
    handler = make_global_exception_handler("test_service")
    exc = HTTPException(status_code=404, detail="Not Found")

    with patch("agent_commons.exception_handler.report_exception_to_prompts_api") as mock_report:
        response = await handler(mock_request, exc)

        assert response.status_code == 404
        assert response.body == b'{"detail":"Not Found"}'
        mock_report.assert_not_called()


@pytest.mark.asyncio
async def test_global_exception_handler_validation_error(mock_request):
    handler = make_global_exception_handler("test_service")
    exc = RequestValidationError(errors=[{"loc": ["body"], "msg": "field required", "type": "value_error.missing"}])

    with patch("agent_commons.exception_handler.report_exception_to_prompts_api") as mock_report:
        response = await handler(mock_request, exc)

        assert response.status_code == 422
        assert b"field required" in response.body
        mock_report.assert_not_called()


@pytest.mark.asyncio
async def test_global_exception_handler_unhandled_exception(mock_request):
    handler = make_global_exception_handler("test_service")
    exc = ValueError("Something went terribly wrong")

    with patch("agent_commons.exception_handler.report_exception_to_prompts_api", new_callable=AsyncMock) as mock_report:
        response = await handler(mock_request, exc)

        assert response.status_code == 500
        assert response.body == b'{"detail":"Internal server error","service":"test_service"}'
        mock_report.assert_called_once()
        args, _ = mock_report.call_args
        assert args[0] == "test_service"
        assert args[1] == "Something went terribly wrong"
        assert "ValueError" in args[2]
        assert args[3] == "test-token"
