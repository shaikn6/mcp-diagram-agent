"""Tests for the FastAPI REST server and MCP tool handler."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
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
    return DiagramResponse.from_document(doc, summary="Test diagram", model="claude-3-5-sonnet-20241022")


# ---------------------------------------------------------------------------
# FastAPI tests
# ---------------------------------------------------------------------------


@pytest.fixture
def client_with_mock() -> TestClient:
    """TestClient with the DiagramGenerator mocked out."""
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc


@pytest.fixture
def patched_client(sample_spec: dict[str, Any]) -> TestClient:
    """TestClient where the generator always returns a predictable response."""
    mock_resp = _make_mock_response()
    app = create_app()
    with patch("src.server._get_generator") as mock_get_gen:
        mock_gen = MagicMock()
        mock_gen.agenerate = AsyncMock(return_value=mock_resp)
        mock_get_gen.return_value = mock_gen
        with TestClient(app) as tc:
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

    def test_generate_max_elements_out_of_range_returns_422(self, client_with_mock: TestClient) -> None:
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
        schema = tools[0].inputSchema
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
