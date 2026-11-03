"""MCP server + FastAPI REST layer for the Diagram Agent."""

from __future__ import annotations

import hmac
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.mcpserver import MCPServer
from mcp.types import (
    TextContent,
    Tool,
)

from .diagram_generator import DiagramGenerator
from .models import DiagramRequest, DiagramResponse, HealthResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared generator instance (initialised at startup)
# ---------------------------------------------------------------------------

_generator: DiagramGenerator | None = None


def _get_generator() -> DiagramGenerator:
    global _generator
    if _generator is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")
        _generator = DiagramGenerator(api_key=api_key, model=model)
    return _generator


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp_server = MCPServer("mcp-diagram-agent")

_GENERATE_DIAGRAM_TOOL = Tool(
    name="generate_diagram",
    description=(
        "Convert a natural language system architecture description into an "
        "Excalidraw-compatible JSON diagram. Returns the full Excalidraw document "
        "that can be imported directly into excalidraw.com."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Natural language description of the system architecture",
                "minLength": 10,
                "maxLength": 4000,
            },
            "style": {
                "type": "string",
                "enum": ["technical", "simple", "detailed"],
                "description": "Diagram complexity level",
                "default": "technical",
            },
            "max_elements": {
                "type": "integer",
                "description": "Maximum number of diagram elements",
                "minimum": 3,
                "maximum": 50,
                "default": 30,
            },
        },
        "required": ["description"],
    },
)


async def list_tools() -> list[Tool]:
    """Advertise the generate_diagram tool to MCP clients."""
    return [_GENERATE_DIAGRAM_TOOL]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool invocations from MCP clients."""
    if name != "generate_diagram":
        raise ValueError(f"Unknown tool: {name!r}")

    try:
        req = DiagramRequest(**arguments)
    except Exception as exc:
        raise ValueError(f"Invalid request arguments: {exc}") from exc

    generator = _get_generator()
    response = await generator.agenerate(req)

    import json

    return [
        TextContent(
            type="text",
            text=json.dumps(
                {
                    "diagram": response.diagram,
                    "element_count": response.element_count,
                    "description_summary": response.description_summary,
                    "model_used": response.model_used,
                },
                indent=2,
            ),
        )
    ]


async def generate_diagram(
    description: str,
    style: str = "technical",
    max_elements: int = 30,
) -> list[TextContent]:
    """Convert a natural language system architecture description into an
    Excalidraw-compatible JSON diagram.

    Args:
        description: Natural language description of the system architecture.
        style: Diagram complexity level (technical, simple, or detailed).
        max_elements: Maximum number of diagram elements.
    """
    return await call_tool(
        "generate_diagram",
        {
            "description": description,
            "style": style,
            "max_elements": max_elements,
        },
    )


mcp_server.add_tool(
    generate_diagram,
    name=_GENERATE_DIAGRAM_TOOL.name,
    description=_GENERATE_DIAGRAM_TOOL.description,
)


async def run_mcp_server() -> None:
    """Start the MCP server over stdio (used by MCP clients like Claude Desktop)."""
    await mcp_server.run_stdio_async()


# ---------------------------------------------------------------------------
# Authentication + rate limiting (protect /generate from unbilled abuse)
# ---------------------------------------------------------------------------

_DEFAULT_RATE_LIMIT_PER_MIN = 30


class _FixedWindowRateLimiter:
    """In-process fixed-window rate limiter keyed by an opaque string."""

    def __init__(self) -> None:
        self._hits: dict[str, tuple[int, int]] = {}

    def allow(self, key: str, limit: int, *, now: float | None = None) -> bool:
        current = int(now if now is not None else time.time())
        window = current - (current % 60)
        start, count = self._hits.get(key, (window, 0))
        if start != window:
            start, count = window, 0
        count += 1
        self._hits[key] = (start, count)
        return count <= limit

    def reset(self) -> None:
        self._hits.clear()


_rate_limiter = _FixedWindowRateLimiter()


def _rate_limit_per_min() -> int:
    """Resolve the per-minute request budget from the environment."""
    try:
        value = int(os.environ.get("MCP_RATE_LIMIT_PER_MIN", ""))
    except ValueError:
        return _DEFAULT_RATE_LIMIT_PER_MIN
    return value if value > 0 else _DEFAULT_RATE_LIMIT_PER_MIN


def _presented_key(request: Request) -> str | None:
    """Extract the caller's API key from the Authorization or X-API-Key header."""
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()
        if token:
            return token
    api_key = request.headers.get("X-API-Key", "").strip()
    return api_key or None


async def rate_limit(request: Request) -> None:
    """Fixed-window rate limit keyed by API key, falling back to client IP."""
    key = _presented_key(request)
    if key is None:
        key = request.client.host if request.client else "unknown"
    limit = _rate_limit_per_min()
    if not _rate_limiter.allow(key, limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: max {limit} requests per minute.",
        )


async def require_api_key(request: Request) -> None:
    """Fail-closed API-key auth: 503 if unconfigured, 401 if missing/wrong."""
    configured = os.environ.get("MCP_API_KEY", "")
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not configured: MCP_API_KEY is unset.",
        )
    presented = _presented_key(request)
    if presented is None or not hmac.compare_digest(presented, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )


# ---------------------------------------------------------------------------
# FastAPI REST API
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Warm up the generator on startup."""
    _get_generator()
    logger.info("MCP Diagram Agent started")
    yield
    logger.info("MCP Diagram Agent shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="MCP Diagram Agent",
        description=(
            "Convert natural language system architecture descriptions into "
            "Excalidraw-compatible diagrams using Claude AI."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Default to no cross-origin access; operators opt in via CORS_ORIGINS.
    cors_raw = os.environ.get("CORS_ORIGINS", "")
    cors_origins = [o.strip() for o in cors_raw.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        # Wildcard origin + credentials is a browser-rejected, security-unsound
        # combination — only allow credentialed requests once origins are restricted.
        allow_credentials=cors_origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["meta"])
    async def health() -> HealthResponse:
        """Liveness probe."""
        return HealthResponse()

    @app.post(
        "/generate",
        response_model=DiagramResponse,
        status_code=status.HTTP_200_OK,
        tags=["diagram"],
        summary="Generate an Excalidraw diagram from a natural language description",
        dependencies=[Depends(rate_limit), Depends(require_api_key)],
    )
    async def generate(request: DiagramRequest) -> DiagramResponse:
        """Generate an Excalidraw diagram.

        Provide a natural language description of your system architecture and
        receive an Excalidraw JSON document that can be imported at excalidraw.com.
        """
        try:
            generator = _get_generator()
            return await generator.agenerate(request)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected error during diagram generation")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error. Check server logs for details.",
            ) from exc

    return app


app = create_app()


def main() -> None:
    """Entry-point for the REST API server."""
    host = os.environ.get("HOST", "0.0.0.0")  # noqa: S104
    port = int(os.environ.get("PORT", "8000"))
    log_level = os.environ.get("LOG_LEVEL", "info").lower()

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    uvicorn.run(
        "src.server:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=os.environ.get("RELOAD", "false").lower() == "true",
    )


if __name__ == "__main__":
    import asyncio
    import sys

    if "--mcp" in sys.argv:
        asyncio.run(run_mcp_server())
    else:
        main()
