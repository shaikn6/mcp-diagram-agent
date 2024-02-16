"""Shared pytest fixtures for MCP Diagram Agent tests."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from src.diagram_generator import DiagramGenerator
from src.models import DiagramRequest

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_SPEC: dict[str, Any] = {
    "summary": "A three-tier web architecture with load balancer and database.",
    "nodes": [
        {
            "id": "browser",
            "label": "Web Browser",
            "layer": "client",
            "shape": "rectangle",
        },
        {
            "id": "lb",
            "label": "Load Balancer",
            "layer": "gateway",
            "shape": "rectangle",
        },
        {
            "id": "api",
            "label": "API Server",
            "layer": "service",
            "shape": "rectangle",
        },
        {
            "id": "db",
            "label": "PostgreSQL",
            "layer": "data",
            "shape": "rectangle",
        },
    ],
    "edges": [
        {"from": "browser", "to": "lb", "label": "HTTPS", "style": "solid"},
        {"from": "lb", "to": "api", "label": "HTTP", "style": "solid"},
        {"from": "api", "to": "db", "label": "SQL", "style": "solid"},
    ],
}


@pytest.fixture
def sample_spec() -> dict[str, Any]:
    return SAMPLE_SPEC


@pytest.fixture
def basic_request() -> DiagramRequest:
    return DiagramRequest(
        description="A web app with load balancer, API server, and PostgreSQL database",
        style="technical",
        max_elements=20,
    )


@pytest.fixture
def mock_anthropic_client(sample_spec: dict[str, Any]) -> MagicMock:
    """Return a MagicMock that mimics anthropic.Anthropic with a canned response."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(sample_spec))]

    mock_messages = MagicMock()
    mock_messages.create.return_value = mock_message

    mock_client = MagicMock()
    mock_client.messages = mock_messages
    return mock_client


@pytest.fixture
def generator(mock_anthropic_client: MagicMock) -> DiagramGenerator:
    """Return a DiagramGenerator backed by the mock Anthropic client."""
    return DiagramGenerator(client=mock_anthropic_client)
