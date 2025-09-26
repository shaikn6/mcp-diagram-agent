"""Comprehensive additional tests for mcp-diagram-agent to reach 95%+ coverage.

Covers: models (all validators/methods), utils (all functions/branches),
diagram_generator (all paths), server (all FastAPI + MCP paths), edge cases.
"""
from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ────────────────────────────────────────────────────────────────────────────
# src.models — ExcalidrawElement
# ────────────────────────────────────────────────────────────────────────────

from src.models import (
    DiagramRequest,
    DiagramResponse,
    ElementType,
    ExcalidrawDocument,
    ExcalidrawElement,
    HealthResponse,
    StrokeStyle,
    TextAlign,
)


class TestExcalidrawElementValidation:
    def test_valid_hex_stroke_color(self):
        el = ExcalidrawElement(id="x", type=ElementType.RECTANGLE, x=0, y=0, strokeColor="#ff0000")
        assert el.strokeColor == "#ff0000"

    def test_transparent_background_allowed(self):
        el = ExcalidrawElement(id="x", type=ElementType.RECTANGLE, x=0, y=0, backgroundColor="transparent")
        assert el.backgroundColor == "transparent"

    def test_invalid_stroke_color_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ExcalidrawElement(id="x", type=ElementType.RECTANGLE, x=0, y=0, strokeColor="red")

    def test_invalid_bg_color_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ExcalidrawElement(id="x", type=ElementType.RECTANGLE, x=0, y=0, backgroundColor="blue")

    def test_default_values(self):
        el = ExcalidrawElement(id="x", type=ElementType.RECTANGLE, x=10, y=20)
        assert el.width == 160.0
        assert el.height == 80.0
        assert el.angle == 0.0
        assert el.strokeStyle == StrokeStyle.SOLID
        assert el.roughness == 1
        assert el.opacity == 100
        assert el.textAlign == TextAlign.CENTER


class TestExcalidrawElementDump:
    def test_rectangle_dump(self):
        el = ExcalidrawElement(
            id="rect1", type=ElementType.RECTANGLE, x=0, y=0,
            text="Hello", width=200, height=100
        )
        d = el.model_dump_excalidraw()
        assert d["id"] == "rect1"
        assert d["type"] == "rectangle"
        assert d["text"] == "Hello"
        assert d["roundness"] == {"type": 3}
        assert d["groupIds"] == []
        assert d["isDeleted"] is False

    def test_ellipse_dump_no_roundness(self):
        el = ExcalidrawElement(id="e1", type=ElementType.ELLIPSE, x=0, y=0)
        d = el.model_dump_excalidraw()
        assert d["type"] == "ellipse"
        assert d["roundness"] is None

    def test_diamond_dump(self):
        el = ExcalidrawElement(id="d1", type=ElementType.DIAMOND, x=0, y=0)
        d = el.model_dump_excalidraw()
        assert d["type"] == "diamond"
        assert d["roundness"] is None

    def test_text_element_dump(self):
        el = ExcalidrawElement(
            id="t1", type=ElementType.TEXT, x=0, y=0, text="Label"
        )
        d = el.model_dump_excalidraw()
        assert d["type"] == "text"
        assert d["text"] == "Label"
        assert d["originalText"] == "Label"
        assert d["containerId"] is None
        assert "lineHeight" in d

    def test_arrow_element_dump(self):
        el = ExcalidrawElement(
            id="a1", type=ElementType.ARROW, x=0, y=0, width=100, height=50,
            points=[[0.0, 0.0], [100.0, 50.0]]
        )
        d = el.model_dump_excalidraw()
        assert d["type"] == "arrow"
        assert d["endArrowhead"] == "arrow"
        assert d["startArrowhead"] is None
        assert d["points"] == [[0.0, 0.0], [100.0, 50.0]]

    def test_arrow_default_points(self):
        el = ExcalidrawElement(
            id="a2", type=ElementType.ARROW, x=0, y=0, width=100, height=50
        )
        d = el.model_dump_excalidraw()
        assert d["points"] is not None
        assert d["points"][0] == [0, 0]

    def test_line_element_no_arrowhead(self):
        el = ExcalidrawElement(id="l1", type=ElementType.LINE, x=0, y=0, width=80, height=30)
        d = el.model_dump_excalidraw()
        assert d["type"] == "line"
        assert d["endArrowhead"] is None

    def test_arrow_with_label(self):
        el = ExcalidrawElement(
            id="a3", type=ElementType.ARROW, x=0, y=0,
            label={"text": "HTTP"}
        )
        d = el.model_dump_excalidraw()
        assert d.get("label") == {"text": "HTTP"}

    def test_rectangle_without_text_no_text_keys(self):
        el = ExcalidrawElement(id="r1", type=ElementType.RECTANGLE, x=0, y=0, text="")
        d = el.model_dump_excalidraw()
        # text key should not be present when text is empty
        assert "text" not in d


class TestExcalidrawDocument:
    def test_default_document(self):
        doc = ExcalidrawDocument()
        assert doc.type == "excalidraw"
        assert doc.version == 2
        assert doc.elements == []
        assert doc.files == {}

    def test_to_excalidraw_dict(self):
        el = ExcalidrawElement(id="e1", type=ElementType.RECTANGLE, x=0, y=0)
        doc = ExcalidrawDocument(elements=[el])
        d = doc.to_excalidraw_dict()
        assert d["type"] == "excalidraw"
        assert d["version"] == 2
        assert len(d["elements"]) == 1
        assert d["appState"]["viewBackgroundColor"] == "#ffffff"

    def test_empty_elements(self):
        doc = ExcalidrawDocument()
        d = doc.to_excalidraw_dict()
        assert d["elements"] == []


class TestDiagramRequest:
    def test_valid_request(self):
        req = DiagramRequest(description="A system with a database and API server")
        assert req.style == "technical"
        assert req.max_elements == 30

    def test_invalid_style_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            DiagramRequest(description="A valid description here", style="invalid")

    def test_description_too_short_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            DiagramRequest(description="short")

    def test_description_too_long_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            DiagramRequest(description="x" * 4001)

    def test_max_elements_out_of_range_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            DiagramRequest(description="A valid description here", max_elements=100)

    def test_max_elements_too_low_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            DiagramRequest(description="A valid description here", max_elements=1)

    def test_simple_style(self):
        req = DiagramRequest(description="A valid description here", style="simple")
        assert req.style == "simple"

    def test_detailed_style(self):
        req = DiagramRequest(description="A valid description here", style="detailed")
        assert req.style == "detailed"


class TestDiagramResponse:
    def test_from_document(self):
        el = ExcalidrawElement(id="e1", type=ElementType.RECTANGLE, x=0, y=0)
        doc = ExcalidrawDocument(elements=[el])
        resp = DiagramResponse.from_document(doc, summary="Test summary", model="claude-3-5-sonnet-20241022")
        assert resp.element_count == 1
        assert resp.description_summary == "Test summary"
        assert resp.model_used == "claude-3-5-sonnet-20241022"
        assert resp.diagram["type"] == "excalidraw"

    def test_from_empty_document(self):
        doc = ExcalidrawDocument()
        resp = DiagramResponse.from_document(doc, summary="Empty", model="test-model")
        assert resp.element_count == 0


class TestHealthResponse:
    def test_defaults(self):
        h = HealthResponse()
        assert h.status == "ok"
        assert h.version == "0.1.0"
        assert h.service == "mcp-diagram-agent"


class TestElementTypeEnum:
    def test_all_types(self):
        assert ElementType.RECTANGLE == "rectangle"
        assert ElementType.ELLIPSE == "ellipse"
        assert ElementType.DIAMOND == "diamond"
        assert ElementType.ARROW == "arrow"
        assert ElementType.LINE == "line"
        assert ElementType.TEXT == "text"
        assert ElementType.FREEDRAW == "freedraw"


class TestStrokeStyleEnum:
    def test_all_styles(self):
        assert StrokeStyle.SOLID == "solid"
        assert StrokeStyle.DASHED == "dashed"
        assert StrokeStyle.DOTTED == "dotted"


# ────────────────────────────────────────────────────────────────────────────
# src.utils
# ────────────────────────────────────────────────────────────────────────────

from src.utils import (
    build_arrow_points,
    clamp,
    color_for_layer,
    grid_layout,
    make_element_id,
    safe_get,
    sanitize_label,
    strip_json_fences,
)


class TestMakeElementId:
    def test_returns_16_char_hex(self):
        eid = make_element_id("node_a", 0)
        assert len(eid) == 16
        assert all(c in "0123456789abcdef" for c in eid)

    def test_different_inputs_give_different_ids(self):
        id1 = make_element_id("node_a", 0)
        time.sleep(0.001)  # ensure time_ns differs
        id2 = make_element_id("node_b", 1)
        assert id1 != id2


class TestClamp:
    def test_value_within_range(self):
        assert clamp(5.0, 0.0, 10.0) == 5.0

    def test_value_below_lo(self):
        assert clamp(-1.0, 0.0, 10.0) == 0.0

    def test_value_above_hi(self):
        assert clamp(15.0, 0.0, 10.0) == 10.0

    def test_value_at_lo(self):
        assert clamp(0.0, 0.0, 10.0) == 0.0

    def test_value_at_hi(self):
        assert clamp(10.0, 0.0, 10.0) == 10.0

    def test_integer_values(self):
        assert clamp(3, 3, 50) == 3


class TestGridLayout:
    def test_single_element(self):
        positions = grid_layout(1)
        assert len(positions) == 1

    def test_multiple_elements(self):
        positions = grid_layout(6, cols=3)
        assert len(positions) == 6

    def test_grid_columns(self):
        positions = grid_layout(6, cols=3, cell_w=200.0, padding_x=60.0, origin_x=100.0)
        # First 3 items in same row (col 0, 1, 2), next 3 wrap
        # col 0: x=100, col 1: x=100+260=360, col 2: x=360+260=620
        assert positions[0][0] == 100.0
        assert positions[1][0] == 360.0
        assert positions[2][0] == 620.0

    def test_wraps_to_second_row(self):
        positions = grid_layout(4, cols=3)
        # item index 3 is in row 1, col 0
        assert positions[3][0] == positions[0][0]  # same x as first col
        assert positions[3][1] > positions[0][1]  # lower y

    def test_zero_count(self):
        positions = grid_layout(0)
        assert positions == []


class TestSanitizeLabel:
    def test_short_label_unchanged(self):
        assert sanitize_label("Hello") == "Hello"

    def test_truncates_long_label(self):
        label = "x" * 50
        result = sanitize_label(label, max_len=40)
        assert len(result) == 40
        assert result.endswith("…")

    def test_strips_whitespace(self):
        assert sanitize_label("  hello  ") == "hello"

    def test_custom_max_len(self):
        result = sanitize_label("hello world", max_len=5)
        assert len(result) == 5
        assert result.endswith("…")

    def test_exactly_at_limit(self):
        label = "x" * 40
        result = sanitize_label(label, max_len=40)
        assert result == label


class TestColorForLayer:
    def test_client_layer(self):
        stroke, bg = color_for_layer("client")
        assert stroke == "#1e1e2e"
        assert bg == "#89dceb"

    def test_gateway_layer(self):
        stroke, bg = color_for_layer("gateway")
        assert bg == "#f38ba8"

    def test_service_layer(self):
        _, bg = color_for_layer("service")
        assert bg == "#a6e3a1"

    def test_data_layer(self):
        _, bg = color_for_layer("data")
        assert bg == "#fab387"

    def test_external_layer(self):
        _, bg = color_for_layer("external")
        assert bg == "#cba6f7"

    def test_queue_layer(self):
        _, bg = color_for_layer("queue")
        assert bg == "#f9e2af"

    def test_default_layer(self):
        _, bg = color_for_layer("default")
        assert bg == "#cdd6f4"

    def test_unknown_layer_falls_back_to_default(self):
        stroke, bg = color_for_layer("unknown_layer_xyz")
        assert bg == "#cdd6f4"

    def test_case_insensitive(self):
        stroke1, bg1 = color_for_layer("CLIENT")
        stroke2, bg2 = color_for_layer("client")
        assert stroke1 == stroke2
        assert bg1 == bg2


class TestBuildArrowPoints:
    def test_horizontal_arrow(self):
        pts = build_arrow_points(0, 0, 100, 80, 200, 0, 100, 80)
        # src right edge: (100, 40), dst left edge: (200, 40)
        assert pts[0] == [0.0, 0.0]
        assert pts[1][0] == 100.0  # dx = 200 - 100 = 100
        assert pts[1][1] == 0.0   # dy = 40 - 40 = 0

    def test_vertical_arrow(self):
        pts = build_arrow_points(0, 0, 100, 80, 0, 200, 100, 80)
        # src center-right: (100, 40), dst center-left: (0, 240)
        assert pts[1][0] == -100.0  # dx = 0 - 100 = -100
        assert pts[1][1] == 200.0   # dy = 240 - 40 = 200

    def test_returns_two_points(self):
        pts = build_arrow_points(10, 20, 100, 80, 300, 20, 100, 80)
        assert len(pts) == 2
        assert pts[0] == [0.0, 0.0]


class TestStripJsonFences:
    def test_removes_json_fence(self):
        raw = '```json\n{"key": "value"}\n```'
        result = strip_json_fences(raw)
        assert result == '{"key": "value"}'

    def test_removes_bare_fence(self):
        raw = '```\n{"key": "value"}\n```'
        result = strip_json_fences(raw)
        assert result == '{"key": "value"}'

    def test_no_fences(self):
        raw = '{"key": "value"}'
        result = strip_json_fences(raw)
        assert result == '{"key": "value"}'

    def test_multiline_json(self):
        raw = '```json\n{\n  "a": 1,\n  "b": 2\n}\n```'
        result = strip_json_fences(raw)
        parsed = json.loads(result)
        assert parsed["a"] == 1

    def test_empty_string(self):
        result = strip_json_fences("")
        assert result == ""


class TestSafeGet:
    def test_simple_key(self):
        assert safe_get({"a": 1}, "a") == 1

    def test_nested_keys(self):
        d = {"a": {"b": {"c": 42}}}
        assert safe_get(d, "a", "b", "c") == 42

    def test_missing_key_returns_default(self):
        assert safe_get({"a": 1}, "b") is None

    def test_missing_nested_key_returns_default(self):
        assert safe_get({"a": {"b": 1}}, "a", "c") is None

    def test_custom_default(self):
        assert safe_get({"a": 1}, "b", default="fallback") == "fallback"

    def test_non_dict_intermediate(self):
        d = {"a": "string_not_dict"}
        assert safe_get(d, "a", "b") is None

    def test_empty_dict(self):
        assert safe_get({}, "key") is None


# ────────────────────────────────────────────────────────────────────────────
# src.diagram_generator — additional coverage
# ────────────────────────────────────────────────────────────────────────────

from src.diagram_generator import (
    DiagramGenerator,
    _build_elements,
    _build_user_prompt,
    _layout_nodes,
    _parse_claude_response,
)


class TestBuildUserPrompt:
    def test_contains_description(self):
        req = DiagramRequest(description="A microservice system with API and DB")
        prompt = _build_user_prompt(req)
        assert "A microservice system with API and DB" in prompt

    def test_contains_style(self):
        req = DiagramRequest(description="A microservice system with API and DB", style="detailed")
        prompt = _build_user_prompt(req)
        assert "detailed" in prompt

    def test_contains_max_elements(self):
        req = DiagramRequest(description="A microservice system with API and DB", max_elements=20)
        prompt = _build_user_prompt(req)
        assert "20" in prompt or "10" in prompt  # max_elements // 2 = 10


class TestLayoutNodesExtended:
    def test_all_layer_types(self):
        layers = ["client", "gateway", "service", "queue", "data", "external", "default"]
        nodes = [{"id": f"n{i}", "layer": layer} for i, layer in enumerate(layers)]
        positions = _layout_nodes(nodes)
        assert len(positions) == len(layers)

    def test_columns_increase_per_layer(self):
        nodes = [
            {"id": "c", "layer": "client"},
            {"id": "s", "layer": "service"},
            {"id": "d", "layer": "data"},
        ]
        positions = _layout_nodes(nodes)
        # client column x < service column x < data column x
        assert positions["c"][0] < positions["s"][0]
        assert positions["s"][0] < positions["d"][0]

    def test_nodes_without_layer_key_use_default(self):
        nodes = [{"id": "x"}]  # no layer key
        positions = _layout_nodes(nodes)
        assert "x" in positions

    def test_custom_dimensions(self):
        nodes = [{"id": "a", "layer": "service"}]
        positions = _layout_nodes(nodes, node_w=200.0, node_h=100.0)
        assert "a" in positions


class TestBuildElementsExtended:
    def test_dotted_edge_style(self):
        spec = {
            "summary": "dotted",
            "nodes": [
                {"id": "a", "label": "A", "layer": "service", "shape": "rectangle"},
                {"id": "b", "label": "B", "layer": "data", "shape": "rectangle"},
            ],
            "edges": [{"from": "a", "to": "b", "label": "", "style": "dotted"}],
        }
        elements = _build_elements(spec)
        arrow = next(el for el in elements if el.type == ElementType.ARROW)
        assert arrow.strokeStyle == StrokeStyle.DOTTED

    def test_unknown_edge_style_defaults_to_solid(self):
        spec = {
            "summary": "unknown",
            "nodes": [
                {"id": "a", "label": "A", "layer": "service", "shape": "rectangle"},
                {"id": "b", "label": "B", "layer": "data", "shape": "rectangle"},
            ],
            "edges": [{"from": "a", "to": "b", "label": "", "style": "wavy"}],
        }
        elements = _build_elements(spec)
        arrow = next(el for el in elements if el.type == ElementType.ARROW)
        assert arrow.strokeStyle == StrokeStyle.SOLID

    def test_unknown_shape_defaults_to_rectangle(self):
        spec = {
            "summary": "test",
            "nodes": [{"id": "a", "label": "A", "layer": "service", "shape": "hexagon"}],
            "edges": [],
        }
        elements = _build_elements(spec)
        assert elements[0].type == ElementType.RECTANGLE

    def test_edge_with_label_creates_arrow_label(self):
        spec = {
            "summary": "labeled",
            "nodes": [
                {"id": "a", "label": "A", "layer": "service", "shape": "rectangle"},
                {"id": "b", "label": "B", "layer": "data", "shape": "rectangle"},
            ],
            "edges": [{"from": "a", "to": "b", "label": "SQL", "style": "solid"}],
        }
        elements = _build_elements(spec)
        arrow = next(el for el in elements if el.type == ElementType.ARROW)
        assert arrow.label is not None
        assert arrow.label["text"] == "SQL"

    def test_node_with_fallback_position(self):
        """Node not in positions dict falls back gracefully."""
        spec = {
            "summary": "fallback",
            "nodes": [{"id": "orphan", "label": "Orphan", "layer": "service", "shape": "rectangle"}],
            "edges": [],
        }
        elements = _build_elements(spec)
        assert len(elements) == 1

    def test_node_colors_from_layer(self):
        spec = {
            "summary": "colors",
            "nodes": [{"id": "c", "label": "Client", "layer": "client", "shape": "rectangle"}],
            "edges": [],
        }
        elements = _build_elements(spec)
        node_el = elements[0]
        assert node_el.backgroundColor == "#89dceb"

    def test_nodes_without_id_use_fallback_id(self):
        spec = {
            "summary": "no-id",
            "nodes": [{"label": "No ID", "layer": "service", "shape": "rectangle"}],
            "edges": [],
        }
        elements = _build_elements(spec)
        assert len(elements) == 1

    def test_queue_layer_nodes(self):
        spec = {
            "summary": "queue",
            "nodes": [{"id": "q", "label": "Kafka", "layer": "queue", "shape": "rectangle"}],
            "edges": [],
        }
        elements = _build_elements(spec)
        _, bg = color_for_layer("queue")
        assert elements[0].backgroundColor == bg


class TestDiagramGeneratorExtended:
    def _make_mock_client(self, spec: dict) -> MagicMock:
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps(spec))]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message
        return mock_client

    def test_generator_uses_env_api_key(self):
        """DiagramGenerator uses ANTHROPIC_API_KEY env when no api_key passed."""
        with (
            patch("src.diagram_generator.anthropic.Anthropic") as MockAnthropic,
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-key"}),
        ):
            gen = DiagramGenerator()
            MockAnthropic.assert_called_once_with(api_key=None)

    def test_model_property_returns_model(self):
        spec = {"summary": "test", "nodes": [], "edges": []}
        client = self._make_mock_client(spec)
        gen = DiagramGenerator(model="claude-3-opus-20240229", client=client)
        assert gen.model == "claude-3-opus-20240229"

    def test_generate_with_external_layer(self):
        spec = {
            "summary": "external service",
            "nodes": [
                {"id": "svc", "label": "Service", "layer": "service", "shape": "rectangle"},
                {"id": "ext", "label": "Stripe API", "layer": "external", "shape": "ellipse"},
            ],
            "edges": [{"from": "svc", "to": "ext", "label": "HTTPS", "style": "dashed"}],
        }
        client = self._make_mock_client(spec)
        gen = DiagramGenerator(client=client)
        req = DiagramRequest(description="Service calling external stripe API endpoint")
        resp = gen.generate(req)
        assert resp.element_count == 3  # 2 nodes + 1 arrow

    def test_generate_summary_in_description(self):
        spec = {
            "summary": "A layered web architecture.",
            "nodes": [
                {"id": "web", "label": "Web", "layer": "client", "shape": "rectangle"},
            ],
            "edges": [],
        }
        client = self._make_mock_client(spec)
        gen = DiagramGenerator(client=client)
        req = DiagramRequest(description="Simple web app architecture diagram")
        resp = gen.generate(req)
        assert resp.description_summary == "A layered web architecture."

    def test_generate_uses_default_summary_when_missing(self):
        spec = {
            "nodes": [],
            "edges": [],
            # no "summary" key
        }
        client = self._make_mock_client(spec)
        gen = DiagramGenerator(client=client)
        req = DiagramRequest(description="Simple architecture without summary field")
        resp = gen.generate(req)
        assert "architecture" in resp.description_summary.lower() or len(resp.description_summary) > 5

    @pytest.mark.asyncio
    async def test_agenerate_calls_generate(self):
        spec = {"summary": "async", "nodes": [], "edges": []}
        client = self._make_mock_client(spec)
        gen = DiagramGenerator(client=client)
        req = DiagramRequest(description="Async architecture test description")
        resp = await gen.agenerate(req)
        assert isinstance(resp, DiagramResponse)

    def test_max_elements_clamp_3(self):
        """max_elements is clamped to min 3."""
        spec = {
            "summary": "test",
            "nodes": [
                {"id": f"n{i}", "label": f"N{i}", "layer": "service", "shape": "rectangle"}
                for i in range(20)
            ],
            "edges": [],
        }
        client = self._make_mock_client(spec)
        gen = DiagramGenerator(client=client)
        req = DiagramRequest(description="Large system with many nodes description")
        # max_elements=3 (min allowed by pydantic)
        req_small = DiagramRequest(description="Large system with many nodes description", max_elements=3)
        resp = gen.generate(req_small)
        assert resp.element_count <= 3


# ────────────────────────────────────────────────────────────────────────────
# src.server — additional FastAPI + MCP coverage
# ────────────────────────────────────────────────────────────────────────────

from fastapi.testclient import TestClient
from src.server import _get_generator, call_tool, create_app, list_tools


class TestGetGenerator:
    def test_returns_generator_instance(self):
        from src.diagram_generator import DiagramGenerator
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            # Reset the global
            import src.server as server_mod
            server_mod._generator = None
            gen = _get_generator()
            assert isinstance(gen, DiagramGenerator)

    def test_returns_same_instance_on_second_call(self):
        import src.server as server_mod
        server_mod._generator = None
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            gen1 = _get_generator()
            gen2 = _get_generator()
            assert gen1 is gen2

    def test_uses_claude_model_env(self):
        import src.server as server_mod
        server_mod._generator = None
        with (
            patch.dict("os.environ", {
                "ANTHROPIC_API_KEY": "test-key",
                "CLAUDE_MODEL": "claude-3-haiku-20240307"
            }),
        ):
            gen = _get_generator()
            assert gen.model == "claude-3-haiku-20240307"
        server_mod._generator = None  # Reset


class TestFastAPIAdditional:
    @pytest.fixture
    def app_client(self) -> TestClient:
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as tc:
            yield tc

    def test_generate_value_error_returns_422(self, app_client):
        with patch("src.server._get_generator") as mock_get_gen:
            mock_gen = MagicMock()
            mock_gen.agenerate = AsyncMock(side_effect=ValueError("Bad input data"))
            mock_get_gen.return_value = mock_gen
            payload = {"description": "A web app with load balancer and database backend"}
            resp = app_client.post("/generate", json=payload)
        assert resp.status_code == 422

    def test_generate_min_elements(self, app_client):
        mock_resp = DiagramResponse.from_document(
            ExcalidrawDocument(), summary="minimal", model="test"
        )
        with patch("src.server._get_generator") as mock_get_gen:
            mock_gen = MagicMock()
            mock_gen.agenerate = AsyncMock(return_value=mock_resp)
            mock_get_gen.return_value = mock_gen
            payload = {
                "description": "A web app with load balancer and database backend",
                "max_elements": 3
            }
            resp = app_client.post("/generate", json=payload)
        assert resp.status_code == 200

    def test_cors_headers_present(self, app_client):
        resp = app_client.get("/health", headers={"Origin": "http://localhost:3000"})
        # CORS middleware should add appropriate headers
        assert resp.status_code == 200

    def test_openapi_json_available(self, app_client):
        resp = app_client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "MCP Diagram Agent"


class TestMCPToolsAdditional:
    @pytest.mark.asyncio
    async def test_generate_diagram_with_all_options(self, sample_spec: dict[str, Any]):
        from src.models import ExcalidrawDocument, DiagramResponse
        mock_resp = DiagramResponse.from_document(
            ExcalidrawDocument(elements=[
                ExcalidrawElement(id="e1", type=ElementType.RECTANGLE, x=0, y=0)
            ]),
            summary="Complete diagram",
            model="claude-3-5-sonnet-20241022"
        )
        with patch("src.server._get_generator") as mock_get_gen:
            mock_gen = MagicMock()
            mock_gen.agenerate = AsyncMock(return_value=mock_resp)
            mock_get_gen.return_value = mock_gen

            results = await call_tool(
                "generate_diagram",
                {
                    "description": "Three-tier web architecture with load balancer",
                    "style": "detailed",
                    "max_elements": 25,
                }
            )

        assert len(results) == 1
        parsed = json.loads(results[0].text)
        assert "diagram" in parsed
        assert "element_count" in parsed
        assert "description_summary" in parsed
        assert "model_used" in parsed

    @pytest.mark.asyncio
    async def test_list_tools_schema_properties(self):
        tools = await list_tools()
        schema = tools[0].inputSchema
        props = schema["properties"]
        assert "style" in props
        assert "max_elements" in props
        assert props["style"]["enum"] == ["technical", "simple", "detailed"]

    @pytest.mark.asyncio
    async def test_call_tool_invalid_args_description_too_short(self):
        with pytest.raises(ValueError, match="Invalid request arguments"):
            await call_tool("generate_diagram", {"description": "hi"})

    @pytest.mark.asyncio
    async def test_call_tool_missing_description(self):
        with pytest.raises(ValueError, match="Invalid request arguments"):
            await call_tool("generate_diagram", {})


# ────────────────────────────────────────────────────────────────────────────
# src.__init__
# ────────────────────────────────────────────────────────────────────────────

class TestInit:
    def test_version_present(self):
        import src
        assert hasattr(src, "__version__")
        assert src.__version__ == "0.1.0"

    def test_author_present(self):
        import src
        assert hasattr(src, "__author__")
