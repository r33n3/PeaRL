"""Threat model draw.io diagram generator.

Generates a layered threat model diagram from attack surface analysis results.
The diagram shows:
- Trust boundaries as dashed containers
- Components grouped by type
- Attack vectors as red arrows from entry points
- Vulnerability paths as highlighted chains
- Severity-coded coloring throughout
"""

from __future__ import annotations

from typing import Any

from pearl.scanning.diagrams.drawio import (
    DiagramEdge,
    DiagramGroup,
    DiagramNode,
    SEVERITY_COLORS,
    build_drawio_xml,
    edge_style,
    node_style,
    _uid,
)


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

_LEFT_MARGIN = 60
_TOP_MARGIN = 80
_NODE_W = 140
_NODE_H = 70
_NODE_GAP_X = 40
_NODE_GAP_Y = 30
_GROUP_PAD = 30

# Trust boundary definitions
_TRUST_BOUNDARIES = [
    {
        "id": "tb_external",
        "label": "External / Untrusted",
        "types": {"mcp_server", "knowledge", "infrastructure"},
    },
    {
        "id": "tb_internal",
        "label": "Internal / Trusted",
        "types": {"model", "context", "code", "config", "guardrails"},
    },
    {
        "id": "tb_agent",
        "label": "Agent Layer",
        "types": {"workflow", "skill", "memory"},
    },
]


def generate_threat_model_diagram(
    components: dict[str, str],
    attack_vectors: list[dict[str, Any]] | None = None,
    vulnerability_paths: list[dict[str, Any]] | None = None,
    interactions: list[dict[str, Any]] | None = None,
    title: str = "AI Threat Model",
) -> str:
    """Generate a threat model draw.io diagram.

    Args:
        components: Dict mapping component name to component type string.
        attack_vectors: List of attack vector dicts with keys:
            name, vector_type, severity, entry_point, target_components, description.
        vulnerability_paths: List of vulnerability path dicts with keys:
            name, severity, steps, description, threat_category.
        interactions: List of interaction dicts with keys:
            source, target, interaction_type, trust_boundary.
        title: Diagram title.

    Returns:
        Complete draw.io XML string.
    """
    attack_vectors = attack_vectors or []
    vulnerability_paths = vulnerability_paths or []
    interactions = interactions or []

    nodes: list[DiagramNode] = []
    edges: list[DiagramEdge] = []
    groups: list[DiagramGroup] = []
    node_ids: dict[str, str] = {}  # component_name -> cell_id

    # ---- Step 1: Assign components to trust boundaries ----
    boundary_members: dict[str, list[tuple[str, str]]] = {}
    unassigned: list[tuple[str, str]] = []

    for comp_name, comp_type in components.items():
        assigned = False
        for boundary in _TRUST_BOUNDARIES:
            if comp_type in boundary["types"]:
                key = boundary["id"]
                if key not in boundary_members:
                    boundary_members[key] = []
                boundary_members[key].append((comp_name, comp_type))
                assigned = True
                break
        if not assigned:
            unassigned.append((comp_name, comp_type))

    # ---- Step 2: Layout trust boundaries and nodes ----
    current_y = _TOP_MARGIN + 40  # Leave room for title

    # Title node
    title_id = _uid()
    nodes.append(DiagramNode(
        id=title_id,
        label=title,
        x=_LEFT_MARGIN,
        y=20,
        width=500,
        height=40,
        style=(
            "text;fontSize=20;fontStyle=1;fillColor=none;"
            "strokeColor=none;fontColor=#1A237E;align=left;"
        ),
    ))

    for boundary in _TRUST_BOUNDARIES:
        bid = boundary["id"]
        members = boundary_members.get(bid, [])
        if not members:
            continue

        # Calculate group size
        cols = min(len(members), 4)
        rows = (len(members) + cols - 1) // cols
        group_w = cols * (_NODE_W + _NODE_GAP_X) + _GROUP_PAD * 2
        group_h = rows * (_NODE_H + _NODE_GAP_Y) + _GROUP_PAD * 2 + 30  # +30 for label

        groups.append(DiagramGroup(
            id=bid,
            label=boundary["label"],
            x=_LEFT_MARGIN,
            y=current_y,
            width=group_w,
            height=group_h,
        ))

        # Place nodes inside the group
        for idx, (comp_name, comp_type) in enumerate(members):
            col = idx % cols
            row = idx // cols
            nx = _GROUP_PAD + col * (_NODE_W + _NODE_GAP_X)
            ny = _GROUP_PAD + 30 + row * (_NODE_H + _NODE_GAP_Y)

            cell_id = _uid()
            node_ids[comp_name] = cell_id

            # Find if this component has findings (severity)
            comp_severity = _find_component_severity(comp_name, attack_vectors, vulnerability_paths)

            nodes.append(DiagramNode(
                id=cell_id,
                label=comp_name,
                x=nx,
                y=ny,
                width=_NODE_W,
                height=_NODE_H,
                style=node_style(comp_type, severity=comp_severity),
                tooltip=f"Type: {comp_type}",
                parent=bid,
            ))

        current_y += group_h + _NODE_GAP_Y

    # Unassigned components
    for comp_name, comp_type in unassigned:
        cell_id = _uid()
        node_ids[comp_name] = cell_id
        comp_severity = _find_component_severity(comp_name, attack_vectors, vulnerability_paths)
        nodes.append(DiagramNode(
            id=cell_id,
            label=comp_name,
            x=_LEFT_MARGIN,
            y=current_y,
            width=_NODE_W,
            height=_NODE_H,
            style=node_style(comp_type, severity=comp_severity),
            tooltip=f"Type: {comp_type}",
        ))
        current_y += _NODE_H + _NODE_GAP_Y

    # ---- Step 3: Draw interactions ----
    for interaction in interactions:
        source = interaction.get("source", "")
        target = interaction.get("target", "")
        int_type = interaction.get("interaction_type", "data_flow")
        trust_boundary = interaction.get("trust_boundary", False)

        source_id = node_ids.get(source)
        target_id = node_ids.get(target)
        if not source_id or not target_id:
            continue

        style = edge_style(
            dashed=trust_boundary,
            extra="endArrow=block;endFill=1;" if not trust_boundary else "endArrow=open;endFill=0;",
        )

        edges.append(DiagramEdge(
            id=_uid(),
            source=source_id,
            target=target_id,
            label=int_type,
            style=style,
            tooltip=f"{'Crosses trust boundary' if trust_boundary else 'Internal flow'}",
        ))

    # ---- Step 4: Draw attack vectors ----
    # Create entry point nodes for attack vectors
    av_x = _LEFT_MARGIN + 700
    av_y = _TOP_MARGIN + 40

    for av in attack_vectors:
        severity = av.get("severity", "medium")
        entry_point = av.get("entry_point", "unknown")
        name = av.get("name", "Attack Vector")
        description = av.get("description", "")
        targets = av.get("target_components", [])

        # Create entry point node (attacker)
        ep_id = _uid()
        nodes.append(DiagramNode(
            id=ep_id,
            label=f"AV: {name}",
            x=av_x,
            y=av_y,
            width=160,
            height=50,
            style=(
                f"shape=hexagon;fillColor={SEVERITY_COLORS.get(severity, '#FF6600')};"
                "fontColor=#FFFFFF;fontSize=10;fontStyle=1;"
                "strokeColor=#333333;strokeWidth=2;whiteSpace=wrap;"
            ),
            tooltip=description,
        ))

        # Draw edges to targets
        for target_name in targets:
            target_id = node_ids.get(target_name)
            if target_id:
                edges.append(DiagramEdge(
                    id=_uid(),
                    source=ep_id,
                    target=target_id,
                    label="",
                    style=edge_style(severity=severity, extra="endArrow=block;endFill=1;"),
                    tooltip=f"{name}: {entry_point} -> {target_name}",
                ))

        av_y += 70

    # ---- Step 5: Draw vulnerability paths ----
    for vp in vulnerability_paths:
        severity = vp.get("severity", "medium")
        steps = vp.get("steps", [])
        name = vp.get("name", "Vulnerability Path")

        if len(steps) < 2:
            continue

        # Draw path edges with severity coloring
        for i in range(len(steps) - 1):
            source_id = node_ids.get(steps[i])
            target_id = node_ids.get(steps[i + 1])
            if source_id and target_id:
                edges.append(DiagramEdge(
                    id=_uid(),
                    source=source_id,
                    target=target_id,
                    label=f"VP {i + 1}" if i == 0 else "",
                    style=edge_style(
                        severity=severity,
                        dashed=True,
                        extra="endArrow=block;endFill=1;curved=1;",
                    ),
                    tooltip=name,
                ))

    # ---- Step 6: Add legend ----
    legend_y = current_y + 30
    legend_id = _uid()
    nodes.append(DiagramNode(
        id=legend_id,
        label=(
            "<b>Legend</b><br>"
            '<font color="#FF0000">&#9632;</font> Critical  '
            '<font color="#FF6600">&#9632;</font> High  '
            '<font color="#FFB300">&#9632;</font> Medium  '
            '<font color="#4CAF50">&#9632;</font> Low<br>'
            "--- Dashed: Trust boundary crossing<br>"
            "Hexagon: Attack vector entry point"
        ),
        x=_LEFT_MARGIN,
        y=legend_y,
        width=400,
        height=80,
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


def _find_component_severity(
    comp_name: str,
    attack_vectors: list[dict],
    vulnerability_paths: list[dict],
) -> str | None:
    """Find the highest severity affecting a component."""
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
    max_rank = -1
    max_severity = None

    for av in attack_vectors:
        if comp_name in av.get("target_components", []):
            sev = av.get("severity", "medium")
            rank = severity_rank.get(sev, 0)
            if rank > max_rank:
                max_rank = rank
                max_severity = sev

    for vp in vulnerability_paths:
        if comp_name in vp.get("steps", []):
            sev = vp.get("severity", "medium")
            rank = severity_rank.get(sev, 0)
            if rank > max_rank:
                max_rank = rank
                max_severity = sev

    return max_severity
