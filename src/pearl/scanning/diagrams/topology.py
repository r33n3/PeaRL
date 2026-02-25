"""Topology draw.io diagram generator.

Generates an AI deployment topology diagram from scan results showing:
- All discovered components grouped by layer
- Data flow arrows between components
- MCP servers, models, context, code as distinct shapes
- Trust boundaries between layers
- Severity indicators on components with findings
"""

from __future__ import annotations

from typing import Any

from pearl.scanning.diagrams.drawio import (
    DiagramEdge,
    DiagramGroup,
    DiagramNode,
    build_drawio_xml,
    edge_style,
    node_style,
    _uid,
)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

_LAYER_DEFS = [
    {
        "id": "layer_user",
        "label": "User / External Layer",
        "types": set(),  # virtual — always shown
        "color": "#E3F2FD",
    },
    {
        "id": "layer_gateway",
        "label": "Gateway & Guardrails",
        "types": {"guardrails", "config"},
        "color": "#FFF3E0",
    },
    {
        "id": "layer_agent",
        "label": "Agent & Orchestration",
        "types": {"workflow", "skill", "memory"},
        "color": "#E8F5E9",
    },
    {
        "id": "layer_model",
        "label": "Model & Context",
        "types": {"model", "context"},
        "color": "#F3E5F5",
    },
    {
        "id": "layer_data",
        "label": "Data & Knowledge",
        "types": {"knowledge", "infrastructure"},
        "color": "#E0F2F1",
    },
    {
        "id": "layer_tools",
        "label": "Tools & MCP Servers",
        "types": {"mcp_server", "code"},
        "color": "#FBE9E7",
    },
]

_NODE_W = 140
_NODE_H = 70
_GAP_X = 40
_GAP_Y = 20
_LEFT = 60
_GROUP_PAD = 30


def generate_topology_diagram(
    components: dict[str, str],
    interactions: list[dict[str, Any]] | None = None,
    findings_by_component: dict[str, str] | None = None,
    title: str = "AI Deployment Topology",
    environment: str = "dev",
) -> str:
    """Generate an AI deployment topology draw.io diagram.

    Args:
        components: Dict mapping component name to component type string.
        interactions: Optional list of interaction dicts with keys:
            source, target, interaction_type, data_types.
        findings_by_component: Optional dict mapping component name to
            highest severity found (for coloring).
        title: Diagram title.
        environment: Environment name (dev, preprod, prod).

    Returns:
        Complete draw.io XML string.
    """
    interactions = interactions or []
    findings_by_component = findings_by_component or {}

    nodes: list[DiagramNode] = []
    edges: list[DiagramEdge] = []
    groups: list[DiagramGroup] = []
    node_ids: dict[str, str] = {}

    # Title
    title_id = _uid()
    nodes.append(DiagramNode(
        id=title_id,
        label=f"{title} [{environment.upper()}]",
        x=_LEFT,
        y=20,
        width=600,
        height=40,
        style=(
            "text;fontSize=20;fontStyle=1;fillColor=none;"
            "strokeColor=none;fontColor=#1A237E;align=left;"
        ),
    ))

    # ---- Assign components to layers ----
    layer_members: dict[str, list[tuple[str, str]]] = {
        layer["id"]: [] for layer in _LAYER_DEFS
    }
    unassigned: list[tuple[str, str]] = []

    for comp_name, comp_type in components.items():
        placed = False
        for layer in _LAYER_DEFS:
            if comp_type in layer["types"]:
                layer_members[layer["id"]].append((comp_name, comp_type))
                placed = True
                break
        if not placed:
            unassigned.append((comp_name, comp_type))

    # Always add a "User" node in the user layer
    user_id = _uid()
    node_ids["__user__"] = user_id

    # ---- Layout layers top-to-bottom ----
    current_y = 80

    for layer in _LAYER_DEFS:
        lid = layer["id"]
        members = layer_members.get(lid, [])

        # User layer always gets a user node
        if lid == "layer_user":
            groups.append(DiagramGroup(
                id=lid,
                label=layer["label"],
                x=_LEFT,
                y=current_y,
                width=_NODE_W + _GROUP_PAD * 2,
                height=_NODE_H + _GROUP_PAD * 2 + 30,
                style=(
                    f"rounded=1;dashed=1;dashPattern=8 4;fillColor={layer['color']};"
                    "strokeColor=#90A4AE;fontSize=13;fontStyle=1;"
                    "verticalAlign=top;align=left;spacingLeft=10;"
                    "spacingTop=5;container=1;collapsible=0;"
                ),
            ))
            nodes.append(DiagramNode(
                id=user_id,
                label="User / Client",
                x=_GROUP_PAD,
                y=_GROUP_PAD + 30,
                width=_NODE_W,
                height=_NODE_H,
                style=(
                    "shape=mxgraph.general.user;"
                    "fillColor=#1976D2;fontColor=#FFFFFF;fontSize=12;"
                    "fontStyle=1;strokeColor=#0D47A1;strokeWidth=2;"
                    "rounded=1;whiteSpace=wrap;shadow=1;"
                ),
                parent=lid,
            ))
            current_y += _NODE_H + _GROUP_PAD * 2 + 30 + _GAP_Y
            continue

        if not members:
            continue

        cols = min(len(members), 5)
        rows = (len(members) + cols - 1) // cols
        group_w = cols * (_NODE_W + _GAP_X) + _GROUP_PAD * 2
        group_h = rows * (_NODE_H + _GAP_Y) + _GROUP_PAD * 2 + 30

        groups.append(DiagramGroup(
            id=lid,
            label=layer["label"],
            x=_LEFT,
            y=current_y,
            width=group_w,
            height=group_h,
            style=(
                f"rounded=1;dashed=1;dashPattern=8 4;fillColor={layer['color']};"
                "strokeColor=#90A4AE;fontSize=13;fontStyle=1;"
                "verticalAlign=top;align=left;spacingLeft=10;"
                "spacingTop=5;container=1;collapsible=0;"
            ),
        ))

        for idx, (comp_name, comp_type) in enumerate(members):
            col = idx % cols
            row = idx // cols
            nx = _GROUP_PAD + col * (_NODE_W + _GAP_X)
            ny = _GROUP_PAD + 30 + row * (_NODE_H + _GAP_Y)

            cell_id = _uid()
            node_ids[comp_name] = cell_id

            severity = findings_by_component.get(comp_name)

            nodes.append(DiagramNode(
                id=cell_id,
                label=comp_name,
                x=nx,
                y=ny,
                width=_NODE_W,
                height=_NODE_H,
                style=node_style(comp_type, severity=severity),
                tooltip=f"Type: {comp_type}" + (f"\nSeverity: {severity}" if severity else ""),
                parent=lid,
            ))

        current_y += group_h + _GAP_Y

    # Unassigned
    for comp_name, comp_type in unassigned:
        cell_id = _uid()
        node_ids[comp_name] = cell_id
        severity = findings_by_component.get(comp_name)
        nodes.append(DiagramNode(
            id=cell_id,
            label=comp_name,
            x=_LEFT,
            y=current_y,
            width=_NODE_W,
            height=_NODE_H,
            style=node_style(comp_type, severity=severity),
        ))
        current_y += _NODE_H + _GAP_Y

    # ---- Draw interactions ----
    for interaction in interactions:
        source = interaction.get("source", "")
        target = interaction.get("target", "")
        int_type = interaction.get("interaction_type", "data_flow")
        data_types = interaction.get("data_types", [])

        source_id = node_ids.get(source)
        target_id = node_ids.get(target)
        if not source_id or not target_id:
            continue

        label = int_type
        if data_types:
            label += f"\n[{', '.join(data_types[:2])}]"

        edges.append(DiagramEdge(
            id=_uid(),
            source=source_id,
            target=target_id,
            label=label,
            style=edge_style(extra="endArrow=block;endFill=1;curved=1;"),
        ))

    # ---- Default data flow: user -> first gateway component ----
    gateway_members = layer_members.get("layer_gateway", [])
    if gateway_members:
        first_gw = gateway_members[0][0]
        gw_id = node_ids.get(first_gw)
        if gw_id:
            edges.append(DiagramEdge(
                id=_uid(),
                source=user_id,
                target=gw_id,
                label="request",
                style=edge_style(extra="endArrow=block;endFill=1;"),
            ))

    # ---- Legend ----
    legend_y = current_y + 20
    nodes.append(DiagramNode(
        id=_uid(),
        label=(
            f"<b>Topology: {environment.upper()}</b><br>"
            "Purple=Model  Blue=Context  Orange=MCP  Green=Workflow<br>"
            "Teal=Knowledge  Grey=Code  Brown=Config<br>"
            '<font color="#FF0000">Red border</font>=Critical findings  '
            '<font color="#FF6600">Orange border</font>=High findings'
        ),
        x=_LEFT,
        y=legend_y,
        width=500,
        height=70,
        style=(
            "text;html=1;fillColor=#F5F5F5;strokeColor=#CCCCCC;"
            "rounded=1;fontSize=11;align=left;spacingLeft=10;"
            "verticalAlign=top;spacingTop=5;"
        ),
    ))

    return build_drawio_xml(
        nodes=nodes,
        edges=edges,
        groups=groups,
        diagram_name=title,
        page_width=1600,
        page_height=max(1200, int(legend_y + 120)),
    )
