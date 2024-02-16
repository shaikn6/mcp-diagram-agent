"""Tests for diagram_generator.py."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from src.diagram_generator import (
    DiagramGenerator,
    _build_elements,
    _layout_nodes,
    _parse_claude_response,
)
from src.models import DiagramRequest, DiagramResponse, ElementType

# ---------------------------------------------------------------------------
# _parse_claude_response
# ---------------------------------------------------------------------------


class TestParseClaudeResponse:
    def test_parses_plain_json(self) -> None:
        raw = '{"summary": "test", "nodes": [], "edges": []}'
        result = _parse_claude_response(raw)
        assert result["summary"] == "test"

    def test_strips_json_code_fence(self) -> None:
        raw = '```json\n{"summary": "fenced", "nodes": [], "edges": []}\n```'
        result = _parse_claude_response(raw)
        assert result["summary"] == "fenced"

    def test_strips_bare_code_fence(self) -> None:
        raw = '```\n{"summary": "bare"}\n```'
        result = _parse_claude_response(raw)
        assert result["summary"] == "bare"

    def test_raises_on_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="non-JSON"):
            _parse_claude_response("this is not json at all")


# ---------------------------------------------------------------------------
# _layout_nodes
# ---------------------------------------------------------------------------


class TestLayoutNodes:
    def test_positions_all_nodes(self) -> None:
        nodes = [
            {"id": "a", "layer": "client"},
            {"id": "b", "layer": "service"},
            {"id": "c", "layer": "data"},
        ]
        positions = _layout_nodes(nodes)
        assert set(positions.keys()) == {"a", "b", "c"}

    def test_same_layer_stacks_vertically(self) -> None:
        nodes = [
            {"id": "s1", "layer": "service"},
            {"id": "s2", "layer": "service"},
        ]
        positions = _layout_nodes(nodes)
        # Same column (same x), different rows (different y)
        assert positions["s1"][0] == positions["s2"][0]
        assert positions["s1"][1] < positions["s2"][1]

    def test_different_layers_in_separate_columns(self) -> None:
        nodes = [
            {"id": "c1", "layer": "client"},
            {"id": "s1", "layer": "service"},
        ]
        positions = _layout_nodes(nodes)
        assert positions["c1"][0] < positions["s1"][0]

    def test_unknown_layer_falls_back_to_default(self) -> None:
        nodes = [{"id": "x", "layer": "unknown_layer"}]
        positions = _layout_nodes(nodes)
        assert "x" in positions


# ---------------------------------------------------------------------------
# _build_elements
# ---------------------------------------------------------------------------


class TestBuildElements:
    def test_creates_correct_element_count(self, sample_spec: dict[str, Any]) -> None:
        # 4 nodes + 3 edges = 7 elements
        elements = _build_elements(sample_spec)
        assert len(elements) == 7

    def test_all_nodes_are_rectangles_by_default(self, sample_spec: dict[str, Any]) -> None:
        elements = _build_elements(sample_spec)
        shapes = [el for el in elements if el.type == ElementType.RECTANGLE]
        assert len(shapes) == 4

    def test_arrows_created_for_edges(self, sample_spec: dict[str, Any]) -> None:
        elements = _build_elements(sample_spec)
        arrows = [el for el in elements if el.type == ElementType.ARROW]
        assert len(arrows) == 3

    def test_skips_edge_with_missing_node(self) -> None:
        spec = {
            "summary": "test",
            "nodes": [{"id": "a", "label": "A", "layer": "service", "shape": "rectangle"}],
            "edges": [{"from": "a", "to": "nonexistent", "label": "", "style": "solid"}],
        }
        elements = _build_elements(spec)
        arrows = [el for el in elements if el.type == ElementType.ARROW]
        assert len(arrows) == 0

    def test_handles_empty_spec(self) -> None:
        spec: dict[str, Any] = {"summary": "empty", "nodes": [], "edges": []}
        elements = _build_elements(spec)
        assert elements == []

    def test_ellipse_shape(self) -> None:
        spec = {
            "summary": "ellipse test",
            "nodes": [{"id": "e1", "label": "Ellipse", "layer": "client", "shape": "ellipse"}],
            "edges": [],
        }
        elements = _build_elements(spec)
        assert elements[0].type == ElementType.ELLIPSE

    def test_diamond_shape(self) -> None:
        spec = {
            "summary": "diamond test",
            "nodes": [{"id": "d1", "label": "Decision", "layer": "default", "shape": "diamond"}],
            "edges": [],
        }
        elements = _build_elements(spec)
        assert elements[0].type == ElementType.DIAMOND

    def test_dashed_edge_style(self) -> None:
        spec = {
            "summary": "style test",
            "nodes": [
                {"id": "a", "label": "A", "layer": "service", "shape": "rectangle"},
                {"id": "b", "label": "B", "layer": "data", "shape": "rectangle"},
            ],
            "edges": [{"from": "a", "to": "b", "label": "async", "style": "dashed"}],
        }
        elements = _build_elements(spec)
        arrow = next(el for el in elements if el.type == ElementType.ARROW)
        from src.models import StrokeStyle
        assert arrow.strokeStyle == StrokeStyle.DASHED


# ---------------------------------------------------------------------------
# DiagramGenerator
# ---------------------------------------------------------------------------


class TestDiagramGenerator:
    def test_generate_returns_diagram_response(
        self,
        generator: DiagramGenerator,
        basic_request: DiagramRequest,
    ) -> None:
        response = generator.generate(basic_request)
        assert isinstance(response, DiagramResponse)

    def test_generate_calls_claude_with_correct_model(
        self,
        mock_anthropic_client: MagicMock,
        basic_request: DiagramRequest,
    ) -> None:
        gen = DiagramGenerator(model="claude-3-5-haiku-20241022", client=mock_anthropic_client)
        gen.generate(basic_request)
        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-3-5-haiku-20241022"

    def test_generate_element_count_is_positive(
        self,
        generator: DiagramGenerator,
        basic_request: DiagramRequest,
    ) -> None:
        response = generator.generate(basic_request)
        assert response.element_count > 0

    def test_generate_diagram_has_excalidraw_schema(
        self,
        generator: DiagramGenerator,
        basic_request: DiagramRequest,
    ) -> None:
        response = generator.generate(basic_request)
        diagram = response.diagram
        assert diagram["type"] == "excalidraw"
        assert diagram["version"] == 2
        assert isinstance(diagram["elements"], list)
        assert "appState" in diagram

    def test_generate_trims_to_max_elements(
        self,
        mock_anthropic_client: MagicMock,
    ) -> None:
        # Build a spec with many nodes
        large_spec = {
            "summary": "big",
            "nodes": [
                {"id": f"n{i}", "label": f"Node {i}", "layer": "service", "shape": "rectangle"}
                for i in range(20)
            ],
            "edges": [],
        }
        mock_anthropic_client.messages.create.return_value.content[0].text = json.dumps(large_spec)
        gen = DiagramGenerator(client=mock_anthropic_client)
        request = DiagramRequest(
            description="big system " * 5,
            style="technical",
            max_elements=5,
        )
        response = gen.generate(request)
        assert response.element_count <= 5

    def test_generate_summary_included(
        self,
        generator: DiagramGenerator,
        basic_request: DiagramRequest,
    ) -> None:
        response = generator.generate(basic_request)
        assert "architecture" in response.description_summary.lower() or len(response.description_summary) > 5

    def test_model_property(self, generator: DiagramGenerator) -> None:
        assert generator.model == "claude-3-5-sonnet-20241022"

    def test_raises_on_non_json_response(self, mock_anthropic_client: MagicMock) -> None:
        mock_anthropic_client.messages.create.return_value.content[0].text = "Sorry, I cannot help."
        gen = DiagramGenerator(client=mock_anthropic_client)
        request = DiagramRequest(description="test architecture description here")
        with pytest.raises(ValueError):
            gen.generate(request)

    @pytest.mark.asyncio
    async def test_agenerate_returns_response(
        self,
        generator: DiagramGenerator,
        basic_request: DiagramRequest,
    ) -> None:
        response = await generator.agenerate(basic_request)
        assert isinstance(response, DiagramResponse)
        assert response.element_count > 0
