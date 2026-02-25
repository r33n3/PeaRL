"""Core draw.io XML generation utilities.

Generates valid draw.io / diagrams.net XML from structured data.
The XML format is based on mxGraph and can be opened directly
in draw.io desktop or web app.
"""

from __future__ import annotations

import html
import uuid
from dataclasses import dataclass, field
from typing import Any


def _uid() -> str:
    """Generate a short unique ID for mxCell elements."""
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

SEVERITY_COLORS = {
    "critical": "#FF0000",
    "high": "#FF6600",
    "medium": "#FFB300",
    "low": "#4CAF50",
    "info": "#2196F3",
}

COMPONENT_COLORS = {
    "model": "#7B1FA2",       # Deep purple
    "context": "#1565C0",     # Blue
    "mcp_server": "#E65100",  # Deep orange
    "workflow": "#2E7D32",    # Green
    "knowledge": "#00695C",   # Teal
    "code": "#37474F",        # Blue grey
    "config": "#795548",      # Brown
    "memory": "#5C6BC0",      # Indigo
    "guardrails": "#00838F",  # Cyan
    "skill": "#AD1457",       # Pink
    "infrastructure": "#546E7A",  # Grey
}

COMPONENT_SHAPES = {
    "model": "shape=mxgraph.aws4.machine_learning;",
    "context": "shape=document;",
    "mcp_server": "shape=mxgraph.general.plugin;",
    "workflow": "shape=mxgraph.flowchart.process;",
    "knowledge": "shape=cylinder3;",
    "code": "shape=mxgraph.general.code;",
    "config": "shape=mxgraph.general.gear;",
    "memory": "shape=mxgraph.aws4.cache_node;",
    "guardrails": "shape=mxgraph.general.shield;",
    "skill": "shape=mxgraph.general.tool;",
    "infrastructure": "shape=mxgraph.general.server;",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DiagramNode:
    """A node in a draw.io diagram."""

    id: str
    label: str
    x: float = 0
    y: float = 0
    width: float = 120
    height: float = 60
    style: str = ""
    tooltip: str = ""
    parent: str = "1"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagramEdge:
    """An edge in a draw.io diagram."""

    id: str
    source: str
    target: str
    label: str = ""
    style: str = ""
    tooltip: str = ""
    parent: str = "1"


@dataclass
class DiagramGroup:
    """A group (container) in a draw.io diagram — used for trust boundaries."""

    id: str
    label: str
    x: float = 0
    y: float = 0
    width: float = 300
    height: float = 200
    style: str = ""
    parent: str = "1"


# ---------------------------------------------------------------------------
# XML generation
# ---------------------------------------------------------------------------

def _escape(text: str) -> str:
    """XML-escape text for draw.io labels."""
    return html.escape(str(text), quote=True)


def _cell_xml(
    cell_id: str,
    value: str = "",
    style: str = "",
    vertex: bool = False,
    edge: bool = False,
    parent: str = "1",
    source: str = "",
    target: str = "",
    x: float = 0,
    y: float = 0,
    width: float = 120,
    height: float = 60,
    tooltip: str = "",
) -> str:
    """Generate a single mxCell XML element."""
    parts = [f'        <mxCell id="{cell_id}" value="{_escape(value)}"']

    if style:
        parts.append(f' style="{_escape(style)}"')

    if vertex:
        parts.append(' vertex="1"')
    if edge:
        parts.append(' edge="1"')

    parts.append(f' parent="{parent}"')

    if source:
        parts.append(f' source="{source}"')
    if target:
        parts.append(f' target="{target}"')

    if tooltip:
        parts.append(f' tooltip="{_escape(tooltip)}"')

    parts.append(">\n")

    if vertex:
        parts.append(
            f'          <mxGeometry x="{x}" y="{y}" '
            f'width="{width}" height="{height}" as="geometry" />\n'
        )
    elif edge:
        parts.append('          <mxGeometry relative="1" as="geometry" />\n')

    parts.append("        </mxCell>\n")

    return "".join(parts)


def build_drawio_xml(
    nodes: list[DiagramNode],
    edges: list[DiagramEdge],
    groups: list[DiagramGroup] | None = None,
    diagram_name: str = "Diagram",
    page_width: int = 1600,
    page_height: int = 1200,
) -> str:
    """Build a complete draw.io XML document.

    Args:
        nodes: Diagram nodes.
        edges: Diagram edges.
        groups: Optional groups (trust boundaries, containers).
        diagram_name: Name shown in draw.io tab.
        page_width: Page width in pixels.
        page_height: Page height in pixels.

    Returns:
        Complete draw.io XML string.
    """
    cells: list[str] = []

    # Root cells (required by draw.io)
    cells.append('        <mxCell id="0" />\n')
    cells.append('        <mxCell id="1" parent="0" />\n')

    # Groups (rendered first so children sit on top)
    if groups:
        for group in groups:
            style = group.style or (
                "rounded=1;whiteSpace=wrap;dashed=1;dashPattern=8 4;"
                "strokeColor=#999999;fillColor=none;fontSize=14;"
                "fontStyle=1;verticalAlign=top;align=left;spacingLeft=10;"
                "spacingTop=5;container=1;collapsible=0;"
            )
            cells.append(_cell_xml(
                cell_id=group.id,
                value=group.label,
                style=style,
                vertex=True,
                parent=group.parent,
                x=group.x, y=group.y,
                width=group.width, height=group.height,
            ))

    # Nodes
    for node in nodes:
        cells.append(_cell_xml(
            cell_id=node.id,
            value=node.label,
            style=node.style,
            vertex=True,
            parent=node.parent,
            x=node.x, y=node.y,
            width=node.width, height=node.height,
            tooltip=node.tooltip,
        ))

    # Edges
    for edge in edges:
        cells.append(_cell_xml(
            cell_id=edge.id,
            value=edge.label,
            style=edge.style,
            edge=True,
            parent=edge.parent,
            source=edge.source,
            target=edge.target,
            tooltip=edge.tooltip,
        ))

    cells_xml = "".join(cells)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<mxfile host="PeaRL" version="1.0">\n'
        f'  <diagram name="{_escape(diagram_name)}" id="{_uid()}">\n'
        f'    <mxGraphModel dx="1422" dy="762" grid="1" gridSize="10" '
        f'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" '
        f'pageScale="1" pageWidth="{page_width}" pageHeight="{page_height}" '
        f'math="0" shadow="0">\n'
        f'      <root>\n'
        f'{cells_xml}'
        f'      </root>\n'
        f'    </mxGraphModel>\n'
        f'  </diagram>\n'
        f'</mxfile>\n'
    )


def node_style(
    component_type: str,
    severity: str | None = None,
    extra: str = "",
) -> str:
    """Build a draw.io style string for a component node.

    Args:
        component_type: Component type key (model, context, mcp_server, etc.).
        severity: Optional severity to set stroke color.
        extra: Extra style properties to append.

    Returns:
        CSS-like draw.io style string.
    """
    fill = COMPONENT_COLORS.get(component_type, "#BBBBBB")
    shape = COMPONENT_SHAPES.get(component_type, "")
    stroke = SEVERITY_COLORS.get(severity, "#333333") if severity else "#333333"

    parts = [
        shape,
        f"fillColor={fill};",
        f"strokeColor={stroke};",
        "fontColor=#FFFFFF;",
        "fontSize=12;",
        "fontStyle=1;",
        "rounded=1;",
        "whiteSpace=wrap;",
        "shadow=1;",
    ]

    if severity in ("critical", "high"):
        parts.append("strokeWidth=3;")
    else:
        parts.append("strokeWidth=2;")

    if extra:
        parts.append(extra)

    return "".join(parts)


def edge_style(
    severity: str | None = None,
    dashed: bool = False,
    label_bg: bool = True,
    extra: str = "",
) -> str:
    """Build a draw.io style string for an edge.

    Args:
        severity: Optional severity for color.
        dashed: Whether to use dashed line.
        label_bg: Whether to add label background.
        extra: Extra style properties.

    Returns:
        CSS-like draw.io style string.
    """
    color = SEVERITY_COLORS.get(severity, "#666666") if severity else "#666666"

    parts = [
        "edgeStyle=orthogonalEdgeStyle;",
        "rounded=1;",
        f"strokeColor={color};",
        "fontSize=10;",
    ]

    if severity in ("critical", "high"):
        parts.append("strokeWidth=3;")
    else:
        parts.append("strokeWidth=2;")

    if dashed:
        parts.append("dashed=1;dashPattern=8 4;")

    if label_bg:
        parts.append("labelBackgroundColor=#FFFFFF;")

    if extra:
        parts.append(extra)

    return "".join(parts)
