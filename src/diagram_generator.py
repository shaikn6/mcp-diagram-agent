"""Diagram generator: converts natural language → Excalidraw JSON via Claude."""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from .models import (
    DiagramRequest,
    DiagramResponse,
    ElementType,
    ExcalidrawDocument,
    ExcalidrawElement,
    StrokeStyle,
)
from .utils import (
    build_arrow_points,
    clamp,
    color_for_layer,
    make_element_id,
    sanitize_label,
    strip_json_fences,
)

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

_SYSTEM_PROMPT = """\
You are an expert software architect who generates Excalidraw diagram specifications.

Given a system architecture description, you MUST return a single valid JSON object
that represents the diagram elements. Do NOT wrap the JSON in markdown fences.

The JSON schema must be:
{
  "summary": "<one-sentence summary of the architecture>",
  "nodes": [
    {
      "id": "<short_snake_case_id>",
      "label": "<display label, max 40 chars>",
      "layer": "<one of: client | gateway | service | data | external | queue | default>",
      "shape": "<one of: rectangle | ellipse | diamond>",
      "description": "<optional short description>"
    }
  ],
  "edges": [
    {
      "from": "<source_node_id>",
      "to": "<target_node_id>",
      "label": "<optional edge label, max 30 chars>",
      "style": "<one of: solid | dashed | dotted>"
    }
  ]
}

Rules:
- Every "from" and "to" in edges MUST reference a valid node id from "nodes".
- Use layer semantics: client (browsers/mobile), gateway (API GW/LB), service (microservices),
  data (databases/caches), external (third-party), queue (message brokers), default (other).
- Keep labels concise and human-readable.
- Do not include more nodes than requested by the user.
- Arrange nodes logically: clients → gateways → services → data.
- Return ONLY the JSON object, no explanation.
"""


def _build_user_prompt(request: DiagramRequest) -> str:
    return (
        f"Architecture description: {request.description}\n\n"
        f"Style: {request.style}\n"
        f"Maximum nodes to generate: {request.max_elements // 2} nodes "
        f"(total elements including arrows may reach {request.max_elements}).\n\n"
        "Return the JSON specification now."
    )


def _parse_claude_response(raw: str) -> dict[str, Any]:
    """Parse Claude's JSON response, stripping any accidental markdown fences."""
    cleaned = strip_json_fences(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Claude response as JSON: %s", exc)
        logger.debug("Raw response: %s", raw)
        raise ValueError(f"Claude returned non-JSON output: {exc}") from exc


def _layout_nodes(
    nodes: list[dict[str, Any]],
    *,
    node_w: float = 180.0,
    node_h: float = 80.0,
) -> dict[str, tuple[float, float]]:
    """Assign (x, y) positions to nodes using a layered layout."""
    # Group nodes by layer order
    layer_order = ["client", "gateway", "service", "queue", "data", "external", "default"]
    groups: dict[str, list[dict[str, Any]]] = {k: [] for k in layer_order}
    for node in nodes:
        layer = node.get("layer", "default").lower()
        bucket = layer if layer in groups else "default"
        groups[bucket].append(node)

    positions: dict[str, tuple[float, float]] = {}
    col_gap = 280.0
    row_gap = 140.0
    col_x = 80.0

    for layer in layer_order:
        layer_nodes = groups[layer]
        if not layer_nodes:
            continue
        for row_idx, node in enumerate(layer_nodes):
            y = 80.0 + row_idx * (node_h + row_gap)
            positions[node["id"]] = (col_x, y)
        col_x += node_w + col_gap

    return positions


def _build_elements(
    spec: dict[str, Any],
    *,
    node_w: float = 180.0,
    node_h: float = 80.0,
) -> list[ExcalidrawElement]:
    """Convert the spec dict into a list of ExcalidrawElement objects."""
    nodes: list[dict[str, Any]] = spec.get("nodes", [])
    edges: list[dict[str, Any]] = spec.get("edges", [])

    positions = _layout_nodes(nodes, node_w=node_w, node_h=node_h)
    elements: list[ExcalidrawElement] = []
    node_element_map: dict[str, ExcalidrawElement] = {}

    # --- Build node elements ---
    for idx, node in enumerate(nodes):
        node_id = node.get("id", f"node_{idx}")
        label = sanitize_label(node.get("label", node_id))
        layer = node.get("layer", "default")
        shape_str = node.get("shape", "rectangle").lower()
        stroke, bg = color_for_layer(layer)

        x, y = positions.get(node_id, (80.0 + idx * 240.0, 80.0))

        shape_map = {
            "rectangle": ElementType.RECTANGLE,
            "ellipse": ElementType.ELLIPSE,
            "diamond": ElementType.DIAMOND,
        }
        el_type = shape_map.get(shape_str, ElementType.RECTANGLE)

        el = ExcalidrawElement(
            id=make_element_id(node_id, idx),
            type=el_type,
            x=x,
            y=y,
            width=node_w,
            height=node_h,
            strokeColor=stroke,
            backgroundColor=bg,
            text=label,
            fontSize=14.0,
            roughness=1,
            opacity=100,
        )
        elements.append(el)
        node_element_map[node_id] = el

    # --- Build edge (arrow) elements ---
    for idx, edge in enumerate(edges):
        src_id = edge.get("from", "")
        dst_id = edge.get("to", "")

        src_el = node_element_map.get(src_id)
        dst_el = node_element_map.get(dst_id)

        if src_el is None or dst_el is None:
            logger.warning("Skipping edge %s→%s: node not found", src_id, dst_id)
            continue

        edge_label = edge.get("label", "")
        style_str = edge.get("style", "solid").lower()
        style_map = {
            "solid": StrokeStyle.SOLID,
            "dashed": StrokeStyle.DASHED,
            "dotted": StrokeStyle.DOTTED,
        }
        stroke_style = style_map.get(style_str, StrokeStyle.SOLID)

        pts = build_arrow_points(
            src_el.x, src_el.y, src_el.width, src_el.height,
            dst_el.x, dst_el.y, dst_el.width, dst_el.height,
        )

        arrow_el = ExcalidrawElement(
            id=make_element_id(f"arrow_{src_id}_{dst_id}", idx),
            type=ElementType.ARROW,
            x=src_el.x + src_el.width,
            y=src_el.y + src_el.height / 2,
            width=abs(pts[1][0]),
            height=abs(pts[1][1]),
            strokeColor="#1e1e2e",
            backgroundColor="transparent",
            strokeStyle=stroke_style,
            strokeWidth=2.0,
            points=pts,
            roughness=1,
            opacity=100,
            text="",
            label={"text": sanitize_label(edge_label, max_len=30)} if edge_label else None,
        )
        elements.append(arrow_el)

    return elements


class DiagramGenerator:
    """Generates Excalidraw diagrams from natural language via the Claude API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self._model = model
        self._client: anthropic.Anthropic = client or anthropic.Anthropic(api_key=api_key)

    @property
    def model(self) -> str:
        return self._model

    def generate(self, request: DiagramRequest) -> DiagramResponse:
        """Call Claude and return a complete DiagramResponse (sync)."""
        logger.info("Generating diagram for: %.80s…", request.description)

        message = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": _build_user_prompt(request)},
            ],
        )

        raw_text: str = message.content[0].text  # type: ignore[attr-defined]
        logger.debug("Claude response (%d chars)", len(raw_text))

        spec = _parse_claude_response(raw_text)
        elements = _build_elements(spec, node_w=180.0, node_h=80.0)

        # Cap to max_elements
        max_el = clamp(request.max_elements, 3, 50)
        if len(elements) > max_el:
            logger.warning("Trimming %d elements to %d", len(elements), max_el)
            elements = elements[:max_el]

        document = ExcalidrawDocument(elements=elements)
        summary = spec.get("summary", "Architecture diagram generated by Claude")

        response = DiagramResponse.from_document(document, summary=summary, model=self._model)
        logger.info("Generated diagram with %d elements", response.element_count)
        return response

    async def agenerate(self, request: DiagramRequest) -> DiagramResponse:
        """Async wrapper — runs the sync generate() in the same thread.

        For true async, replace with AsyncAnthropic client usage.
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.generate, request)
