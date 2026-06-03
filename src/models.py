"""Pydantic models for the MCP Diagram Agent."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ElementType(StrEnum):
    """Supported Excalidraw element types."""

    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"
    DIAMOND = "diamond"
    ARROW = "arrow"
    LINE = "line"
    TEXT = "text"
    FREEDRAW = "freedraw"


class StrokeStyle(StrEnum):
    """Stroke style options."""

    SOLID = "solid"
    DASHED = "dashed"
    DOTTED = "dotted"


class TextAlign(StrEnum):
    """Text alignment options."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class ExcalidrawElement(BaseModel):
    """Represents a single element in an Excalidraw diagram."""

    id: str = Field(..., description="Unique identifier for the element")
    type: ElementType = Field(..., description="Type of the Excalidraw element")
    x: float = Field(..., description="X coordinate of the element")
    y: float = Field(..., description="Y coordinate of the element")
    width: float = Field(default=160.0, ge=0, description="Width of the element")
    height: float = Field(default=80.0, ge=0, description="Height of the element")
    angle: float = Field(default=0.0, description="Rotation angle in radians")
    strokeColor: str = Field(default="#1e1e2e", description="Stroke color (hex)")
    backgroundColor: str = Field(default="#cba6f7", description="Background fill color (hex)")
    fillStyle: str = Field(default="solid", description="Fill style")
    strokeWidth: float = Field(default=2.0, ge=0, description="Stroke width in pixels")
    strokeStyle: StrokeStyle = Field(default=StrokeStyle.SOLID, description="Stroke style")
    roughness: int = Field(default=1, ge=0, le=2, description="Roughness level 0-2")
    opacity: int = Field(default=100, ge=0, le=100, description="Opacity 0-100")
    text: str = Field(default="", description="Text content for text/labeled elements")
    fontSize: float = Field(default=16.0, ge=4, description="Font size in pixels")
    fontFamily: int = Field(
        default=1, description="Font family (1=Virgil, 2=Helvetica, 3=Cascadia)"
    )
    textAlign: TextAlign = Field(default=TextAlign.CENTER, description="Text alignment")
    verticalAlign: str = Field(default="middle", description="Vertical alignment")
    startBinding: dict[str, Any] | None = Field(
        default=None, description="Start binding for arrows"
    )
    endBinding: dict[str, Any] | None = Field(default=None, description="End binding for arrows")
    points: list[list[float]] | None = Field(
        default=None, description="Points for line/arrow elements"
    )
    label: dict[str, Any] | None = Field(default=None, description="Label configuration for arrows")

    @field_validator("strokeColor", "backgroundColor")
    @classmethod
    def validate_color(cls, v: str) -> str:
        """Ensure color is a valid hex color or 'transparent'."""
        if v == "transparent":
            return v
        if not v.startswith("#"):
            raise ValueError(f"Color must be a hex string starting with '#', got: {v}")
        return v

    def model_dump_excalidraw(self) -> dict[str, Any]:
        """Return a dict in Excalidraw-compatible format."""
        base: dict[str, Any] = {
            "id": self.id,
            "type": self.type.value,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "angle": self.angle,
            "strokeColor": self.strokeColor,
            "backgroundColor": self.backgroundColor,
            "fillStyle": self.fillStyle,
            "strokeWidth": self.strokeWidth,
            "strokeStyle": self.strokeStyle.value,
            "roughness": self.roughness,
            "opacity": self.opacity,
            "groupIds": [],
            "frameId": None,
            "roundness": {"type": 3} if self.type == ElementType.RECTANGLE else None,
            "seed": 1,
            "version": 1,
            "versionNonce": 1,
            "isDeleted": False,
            "boundElements": [],
            "updated": 1,
            "link": None,
            "locked": False,
        }

        if self.type == ElementType.TEXT:
            base.update(
                {
                    "text": self.text,
                    "fontSize": self.fontSize,
                    "fontFamily": self.fontFamily,
                    "textAlign": self.textAlign.value,
                    "verticalAlign": self.verticalAlign,
                    "containerId": None,
                    "originalText": self.text,
                    "lineHeight": 1.25,
                }
            )
        elif self.type in (ElementType.ARROW, ElementType.LINE):
            pts = self.points or [[0, 0], [self.width, self.height]]
            base.update(
                {
                    "points": pts,
                    "lastCommittedPoint": None,
                    "startBinding": self.startBinding,
                    "endBinding": self.endBinding,
                    "startArrowhead": None,
                    "endArrowhead": "arrow" if self.type == ElementType.ARROW else None,
                }
            )
            if self.label:
                base["label"] = self.label
        else:
            # Shapes with text label
            if self.text:
                base.update(
                    {
                        "text": self.text,
                        "fontSize": self.fontSize,
                        "fontFamily": self.fontFamily,
                        "textAlign": self.textAlign.value,
                        "verticalAlign": self.verticalAlign,
                        "containerId": None,
                        "originalText": self.text,
                        "lineHeight": 1.25,
                    }
                )

        return base


class ExcalidrawDocument(BaseModel):
    """Complete Excalidraw diagram document."""

    type: str = Field(default="excalidraw", description="Document type identifier")
    version: int = Field(default=2, description="Excalidraw file format version")
    source: str = Field(
        default="https://github.com/shaikn6/mcp-diagram-agent",
        description="Source URL",
    )
    elements: list[ExcalidrawElement] = Field(
        default_factory=list, description="List of diagram elements"
    )
    appState: dict[str, Any] = Field(
        default_factory=lambda: {
            "gridSize": None,
            "viewBackgroundColor": "#ffffff",
        },
        description="Excalidraw application state",
    )
    files: dict[str, Any] = Field(default_factory=dict, description="Embedded files")

    def to_excalidraw_dict(self) -> dict[str, Any]:
        """Serialize to Excalidraw JSON format."""
        return {
            "type": self.type,
            "version": self.version,
            "source": self.source,
            "elements": [el.model_dump_excalidraw() for el in self.elements],
            "appState": self.appState,
            "files": self.files,
        }


class DiagramRequest(BaseModel):
    """Request model for diagram generation."""

    description: str = Field(
        ...,
        min_length=10,
        max_length=4000,
        description="Natural language description of the system architecture",
        examples=[
            "A microservices architecture with API gateway, auth service, and PostgreSQL database"
        ],
    )
    style: str = Field(
        default="technical",
        description="Diagram style: 'technical', 'simple', or 'detailed'",
        pattern="^(technical|simple|detailed)$",
    )
    max_elements: int = Field(
        default=30,
        ge=3,
        le=50,
        description="Maximum number of diagram elements to generate",
    )


class DiagramResponse(BaseModel):
    """Response model for diagram generation."""

    diagram: dict[str, Any] = Field(..., description="Excalidraw-compatible JSON document")
    element_count: int = Field(..., ge=0, description="Number of elements in the diagram")
    description_summary: str = Field(..., description="Brief summary of what was generated")
    model_used: str = Field(..., description="Claude model used for generation")

    @classmethod
    def from_document(
        cls,
        document: ExcalidrawDocument,
        summary: str,
        model: str,
    ) -> DiagramResponse:
        """Construct a response from an ExcalidrawDocument."""
        return cls(
            diagram=document.to_excalidraw_dict(),
            element_count=len(document.elements),
            description_summary=summary,
            model_used=model,
        )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(default="ok")
    version: str = Field(default="0.1.0")
    service: str = Field(default="mcp-diagram-agent")
