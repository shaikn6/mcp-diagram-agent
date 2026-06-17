"""MCP server + FastAPI REST layer for the Diagram Agent."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from mcp.server import Server
from mcp.server.stdio import stdio_server
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
        model = os.environ.get("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
        _generator = DiagramGenerator(api_key=api_key, model=model)
    return _generator


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp_server = Server("mcp-diagram-agent")


@mcp_server.list_tools()  # type: ignore[misc, no-untyped-call]
async def list_tools() -> list[Tool]:
    """Advertise the generate_diagram tool to MCP clients."""
    return [
        Tool(
            name="generate_diagram",
            description=(
                "Convert a natural language system architecture description into an "
                "Excalidraw-compatible JSON diagram. Returns the full Excalidraw document "
                "that can be imported directly into excalidraw.com."
            ),
            inputSchema={
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
    ]


@mcp_server.call_tool()  # type: ignore[misc]
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


async def run_mcp_server() -> None:
    """Start the MCP server over stdio (used by MCP clients like Claude Desktop)."""
    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
        allow_credentials=True,
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
