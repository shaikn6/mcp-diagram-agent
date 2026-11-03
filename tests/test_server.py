"""Tests for the FastAPI REST server and MCP tool handler."""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from src.diagram_generator import DiagramGenerator
from src.models import (
    DiagramResponse,
    ElementType,
    ExcalidrawDocument,
    ExcalidrawElement,
)
from src.server import call_tool, create_app, list_tools

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(element_count: int = 4) -> DiagramResponse:
    """Build a fake DiagramResponse for mocking."""
    elements = [
        ExcalidrawElement(
            id=f"el{i}",
            type=ElementType.RECTANGLE,
            x=float(i * 200),
            y=100.0,
            width=180.0,
            height=80.0,
            text=f"Node {i}",
        )
        for i in range(element_count)
    ]
    doc = ExcalidrawDocument(elements=elements)
    return DiagramResponse.from_document(
        doc, summary="Test diagram", model="claude-3-5-sonnet-20241022"
    )


# ---------------------------------------------------------------------------
# FastAPI tests
# ---------------------------------------------------------------------------


@pytest.fixture
def client_with_mock(auth_headers: dict[str, str]) -> TestClient:
    """TestClient with the DiagramGenerator mocked out."""
    app = create_app()
    with TestClient(app, raise_server_exceptions=False, headers=auth_headers) as tc:
        yield tc


@pytest.fixture
def patched_client(sample_spec: dict[str, Any], auth_headers: dict[str, str]) -> TestClient:
    """TestClient where the generator always returns a predictable response."""
    mock_resp = _make_mock_response()
    app = create_app()
    with patch("src.server._get_generator") as mock_get_gen:
        mock_gen = MagicMock()
        mock_gen.agenerate = AsyncMock(return_value=mock_resp)
        mock_get_gen.return_value = mock_gen
        with TestClient(app, headers=auth_headers) as tc:
            yield tc


class TestHealthEndpoint:
    def test_health_returns_200(self, client_with_mock: TestClient) -> None:
        resp = client_with_mock.get("/health")
        assert resp.status_code == 200

    def test_health_body(self, client_with_mock: TestClient) -> None:
        resp = client_with_mock.get("/health")
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "mcp-diagram-agent"
        assert "version" in body


class TestGenerateEndpoint:
    def test_generate_success(self, patched_client: TestClient) -> None:
        payload = {"description": "A web app with load balancer and database backend"}
        resp = patched_client.post("/generate", json=payload)
        assert resp.status_code == 200

    def test_generate_returns_excalidraw_format(self, patched_client: TestClient) -> None:
        payload = {"description": "A web app with load balancer and database backend"}
        resp = patched_client.post("/generate", json=payload)
        body = resp.json()
        assert "diagram" in body
        assert body["diagram"]["type"] == "excalidraw"
        assert isinstance(body["diagram"]["elements"], list)
        assert body["element_count"] == 4

    def test_generate_with_all_params(self, patched_client: TestClient) -> None:
        payload = {
            "description": "Microservices system with API gateway, auth, and Kafka",
            "style": "detailed",
            "max_elements": 25,
        }
        resp = patched_client.post("/generate", json=payload)
        assert resp.status_code == 200

    def test_generate_invalid_style_returns_422(self, client_with_mock: TestClient) -> None:
        payload = {
            "description": "A web app with load balancer and database backend",
            "style": "invalid_style",
        }
        resp = client_with_mock.post("/generate", json=payload)
        assert resp.status_code == 422

    def test_generate_description_too_short_returns_422(self, client_with_mock: TestClient) -> None:
        payload = {"description": "short"}
        resp = client_with_mock.post("/generate", json=payload)
        assert resp.status_code == 422

    def test_generate_missing_description_returns_422(self, client_with_mock: TestClient) -> None:
        resp = client_with_mock.post("/generate", json={})
        assert resp.status_code == 422

    def test_generate_max_elements_out_of_range_returns_422(
        self, client_with_mock: TestClient
    ) -> None:
        payload = {
            "description": "A web app with load balancer and database backend",
            "max_elements": 999,
        }
        resp = client_with_mock.post("/generate", json=payload)
        assert resp.status_code == 422

    def test_generate_propagates_generator_error(self, client_with_mock: TestClient) -> None:
        with patch("src.server._get_generator") as mock_get_gen:
            mock_gen = MagicMock()
            mock_gen.agenerate = AsyncMock(side_effect=RuntimeError("Claude API error"))
            mock_get_gen.return_value = mock_gen
            payload = {"description": "A web app with load balancer and database backend"}
            resp = client_with_mock.post("/generate", json=payload)
        assert resp.status_code == 500


class TestDocsEndpoints:
    def test_openapi_docs_available(self, client_with_mock: TestClient) -> None:
        resp = client_with_mock.get("/docs")
        assert resp.status_code == 200

    def test_redoc_available(self, client_with_mock: TestClient) -> None:
        resp = client_with_mock.get("/redoc")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# MCP tool handler tests
# ---------------------------------------------------------------------------


class TestMCPListTools:
    @pytest.mark.asyncio
    async def test_list_tools_returns_generate_diagram(self) -> None:
        tools = await list_tools()
        assert len(tools) == 1
        assert tools[0].name == "generate_diagram"

    @pytest.mark.asyncio
    async def test_generate_diagram_tool_has_input_schema(self) -> None:
        tools = await list_tools()
        schema = tools[0].input_schema
        assert "description" in schema["properties"]
        assert "description" in schema["required"]


class TestMCPCallTool:
    @pytest.mark.asyncio
    async def test_call_unknown_tool_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown tool"):
            await call_tool("nonexistent_tool", {})

    @pytest.mark.asyncio
    async def test_call_generate_diagram_success(self, sample_spec: dict[str, Any]) -> None:
        mock_resp = _make_mock_response(3)
        with patch("src.server._get_generator") as mock_get_gen:
            mock_gen = MagicMock()
            mock_gen.agenerate = AsyncMock(return_value=mock_resp)
            mock_get_gen.return_value = mock_gen

            results = await call_tool(
                "generate_diagram",
                {"description": "Three-tier web architecture with load balancer"},
            )

        assert len(results) == 1
        text_content = results[0]
        assert text_content.type == "text"
        parsed = json.loads(text_content.text)
        assert "diagram" in parsed
        assert parsed["element_count"] == 3

    @pytest.mark.asyncio
    async def test_call_generate_diagram_invalid_args_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid request arguments"):
            await call_tool("generate_diagram", {"description": "too short"})


# ---------------------------------------------------------------------------
# Malformed LLM output -> 422 (not 500)
# ---------------------------------------------------------------------------


def _post_generate(llm_output: Any) -> Any:
    """POST /generate with a real DiagramGenerator whose Anthropic client is faked."""
    message = MagicMock()
    message.content = [MagicMock(text=json.dumps(llm_output))]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = message
    headers = {"Authorization": f"Bearer {os.environ['MCP_API_KEY']}"}
    with patch("src.server._get_generator", return_value=DiagramGenerator(client=fake_client)):
        with TestClient(create_app(), raise_server_exceptions=False) as tc:
            return tc.post(
                "/generate",
                json={"description": "A web app with an API and a DB"},
                headers=headers,
            )


class TestSpecValidation:
    @pytest.mark.parametrize(
        "bad_spec",
        [
            {"nodes": "x"},
            {"nodes": [None]},
            {"nodes": []},
            {"nodes": [{"label": "no id"}]},
            {"nodes": [{"id": "a"}], "edges": "x"},
            [None],
        ],
    )
    def test_malformed_spec_returns_422(self, bad_spec: Any) -> None:
        resp = _post_generate(bad_spec)
        assert resp.status_code == 422
        assert "invalid diagram spec" in resp.json()["detail"]

    def test_duplicate_node_ids_return_422(self) -> None:
        resp = _post_generate({"nodes": [{"id": "a", "label": "A"}, {"id": "a", "label": "B"}]})
        assert resp.status_code == 422
        assert "duplicate node id 'a'" in resp.json()["detail"]

    def test_valid_spec_still_returns_200(self, sample_spec: dict[str, Any]) -> None:
        resp = _post_generate(sample_spec)
        assert resp.status_code == 200
        assert resp.json()["element_count"] == 7


# ---------------------------------------------------------------------------
# Authentication + rate limiting
# ---------------------------------------------------------------------------

from src.server import _FixedWindowRateLimiter, _rate_limit_per_min, _rate_limiter

_AUTH_PAYLOAD = {"description": "A web app with load balancer and database backend"}


@pytest.fixture
def mock_gen_app() -> Any:
    """A real app whose generator is mocked, for exercising auth/rate-limit guards."""
    mock_resp = _make_mock_response()
    app = create_app()
    with patch("src.server._get_generator") as mock_get_gen:
        mock_gen = MagicMock()
        mock_gen.agenerate = AsyncMock(return_value=mock_resp)
        mock_get_gen.return_value = mock_gen
        yield app


class TestGenerateAuth:
    def test_missing_key_returns_401(self, mock_gen_app: Any) -> None:
        with TestClient(mock_gen_app, raise_server_exceptions=False) as tc:
            resp = tc.post("/generate", json=_AUTH_PAYLOAD)
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, mock_gen_app: Any) -> None:
        with TestClient(mock_gen_app, raise_server_exceptions=False) as tc:
            resp = tc.post(
                "/generate", json=_AUTH_PAYLOAD, headers={"Authorization": "Bearer wrong"}
            )
        assert resp.status_code == 401

    def test_x_api_key_header_accepted(self, mock_gen_app: Any) -> None:
        key = os.environ["MCP_API_KEY"]
        with TestClient(mock_gen_app) as tc:
            resp = tc.post("/generate", json=_AUTH_PAYLOAD, headers={"X-API-Key": key})
        assert resp.status_code == 200

    def test_unconfigured_key_returns_503(
        self, mock_gen_app: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MCP_API_KEY", raising=False)
        with TestClient(mock_gen_app, raise_server_exceptions=False) as tc:
            resp = tc.post("/generate", json=_AUTH_PAYLOAD, headers={"X-API-Key": "anything"})
        assert resp.status_code == 503

    def test_health_open_without_key(self, mock_gen_app: Any) -> None:
        with TestClient(mock_gen_app) as tc:
            resp = tc.get("/health")
        assert resp.status_code == 200


class TestRateLimit:
    def test_exceeding_limit_returns_429(
        self, mock_gen_app: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MCP_RATE_LIMIT_PER_MIN", "2")
        _rate_limiter.reset()
        headers = {"Authorization": f"Bearer {os.environ['MCP_API_KEY']}"}
        with TestClient(mock_gen_app) as tc:
            assert tc.post("/generate", json=_AUTH_PAYLOAD, headers=headers).status_code == 200
            assert tc.post("/generate", json=_AUTH_PAYLOAD, headers=headers).status_code == 200
            resp = tc.post("/generate", json=_AUTH_PAYLOAD, headers=headers)
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["detail"]


class TestRateLimiterUnit:
    def test_allows_up_to_limit_then_blocks(self) -> None:
        rl = _FixedWindowRateLimiter()
        assert rl.allow("k", 2, now=0.0) is True
        assert rl.allow("k", 2, now=1.0) is True
        assert rl.allow("k", 2, now=2.0) is False

    def test_new_window_resets_count(self) -> None:
        rl = _FixedWindowRateLimiter()
        assert rl.allow("k", 1, now=0.0) is True
        assert rl.allow("k", 1, now=1.0) is False
        assert rl.allow("k", 1, now=60.0) is True

    def test_reset_clears_state(self) -> None:
        rl = _FixedWindowRateLimiter()
        rl.allow("k", 1, now=0.0)
        rl.reset()
        assert rl.allow("k", 1, now=0.0) is True


class TestRateLimitConfig:
    def test_default_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_RATE_LIMIT_PER_MIN", raising=False)
        assert _rate_limit_per_min() == 30

    def test_default_when_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_RATE_LIMIT_PER_MIN", "abc")
        assert _rate_limit_per_min() == 30

    def test_default_when_non_positive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_RATE_LIMIT_PER_MIN", "0")
        assert _rate_limit_per_min() == 30

    def test_honors_configured_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_RATE_LIMIT_PER_MIN", "5")
        assert _rate_limit_per_min() == 5
