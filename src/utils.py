"""Utility helpers for the MCP Diagram Agent."""

from __future__ import annotations

import hashlib
import time
from typing import Any


def make_element_id(prefix: str, index: int) -> str:
    """Generate a stable, unique element ID."""
    raw = f"{prefix}-{index}-{time.time_ns()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp *value* to the inclusive range [lo, hi]."""
    return max(lo, min(hi, value))


def grid_layout(
    count: int,
    *,
    cols: int = 3,
    cell_w: float = 200.0,
    cell_h: float = 120.0,
    padding_x: float = 60.0,
    padding_y: float = 60.0,
    origin_x: float = 100.0,
    origin_y: float = 100.0,
) -> list[tuple[float, float]]:
    """Return (x, y) positions for *count* elements arranged in a grid.

    Each cell is ``cell_w × cell_h`` with ``padding_x / padding_y`` gaps.
    """
    positions: list[tuple[float, float]] = []
    for i in range(count):
        col = i % cols
        row = i // cols
        x = origin_x + col * (cell_w + padding_x)
        y = origin_y + row * (cell_h + padding_y)
        positions.append((x, y))
    return positions


def sanitize_label(text: str, max_len: int = 40) -> str:
    """Truncate and clean a label so it renders well in Excalidraw."""
    text = text.strip()
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def color_for_layer(layer: str) -> tuple[str, str]:
    """Return (strokeColor, backgroundColor) for a semantic diagram layer.

    Layers: 'client', 'gateway', 'service', 'data', 'external', 'default'
    """
    palette: dict[str, tuple[str, str]] = {
        "client": ("#1e1e2e", "#89dceb"),
        "gateway": ("#1e1e2e", "#f38ba8"),
        "service": ("#1e1e2e", "#a6e3a1"),
        "data": ("#1e1e2e", "#fab387"),
        "external": ("#1e1e2e", "#cba6f7"),
        "queue": ("#1e1e2e", "#f9e2af"),
        "default": ("#1e1e2e", "#cdd6f4"),
    }
    return palette.get(layer.lower(), palette["default"])


def build_arrow_points(
    src_x: float,
    src_y: float,
    src_w: float,
    src_h: float,
    dst_x: float,
    dst_y: float,
    dst_w: float,
    dst_h: float,
) -> list[list[float]]:
    """Compute start/end points for an arrow between two rectangular elements.

    Returns ``[[0, 0], [dx, dy]]`` in arrow-local coordinates (Excalidraw
    arrows are positioned at their start point).
    """
    # Connect center-right of source to center-left of destination
    sx = src_x + src_w
    sy = src_y + src_h / 2
    dx = dst_x
    dy = dst_y + dst_h / 2
    return [[0.0, 0.0], [dx - sx, dy - sy]]


def strip_json_fences(text: str) -> str:
    """Remove markdown code fences from a Claude response, returning raw JSON."""
    lines = text.strip().splitlines()
    # Drop opening ```json or ``` fence
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    # Drop closing ``` fence
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def safe_get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely traverse a nested dict by a sequence of keys."""
    current: Any = d
    for k in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(k, default)
    return current
