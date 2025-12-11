"""Family chart export helpers inspired by the family-chart library.

The original `family-chart` project focuses on laying out kinship graphs so
they are easy to read. We mirror its core ideas—explicit unions/partnerships,
clear parent->child links, and simple 2D layout hints—while keeping the
implementation lightweight and dependency-free for this codebase.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Iterable, List, Mapping, MutableMapping, Tuple

import networkx as nx

from .wikidata import FAMILY_PROPS


FAMILY_RELATIONS = set(FAMILY_PROPS.values())
PARENTAL_RELATIONS = {"father", "mother", "child"}
PARTNER_RELATIONS = {"spouse", "partner"}
SIBLING_RELATIONS = {"sibling", "relative"}


def _parent_child_pairs(graph: nx.MultiDiGraph) -> List[Tuple[str, str, Mapping[str, object]]]:
    """Extract parent->child relationships with normalized direction.

    The graph stores assorted kinship edges. This helper standardizes them into
    explicit parent->child tuples so downstream code can attach children to the
    proper union/household nodes.
    """

    pairs: List[Tuple[str, str, Mapping[str, object]]] = []
    for u, v, data in graph.edges(data=True):
        relation = data.get("relation")
        if relation not in PARENTAL_RELATIONS:
            continue
        if relation == "child":
            parent, child = u, v
        else:  # father/mother edges point from child -> parent
            parent, child = v, u
        pairs.append((parent, child, data))
    return pairs


def _partnerships(graph: nx.MultiDiGraph) -> Dict[Tuple[str, str], Dict[str, object]]:
    """Return deduplicated partnership edges as sorted tuples."""

    unions: Dict[Tuple[str, str], Dict[str, object]] = {}
    for u, v, data in graph.edges(data=True):
        relation = data.get("relation")
        if relation not in PARTNER_RELATIONS:
            continue
        key = tuple(sorted((u, v)))
        unions.setdefault(key, {"partners": list(key), "relations": set()})
        unions[key]["relations"].add(relation)
    # Convert relation sets to sorted lists for JSON stability
    for entry in unions.values():
        entry["relations"] = sorted(entry["relations"])
    return unions


def _sibling_edges(graph: nx.MultiDiGraph) -> List[Dict[str, object]]:
    edges: List[Dict[str, object]] = []
    seen: set[Tuple[str, str]] = set()
    for u, v, data in graph.edges(data=True):
        relation = data.get("relation")
        if relation not in SIBLING_RELATIONS:
            continue
        key = tuple(sorted((u, v)))
        if key in seen:
            continue
        seen.add(key)
        edges.append({"from": key[0], "to": key[1], "type": relation})
    return edges


def _compute_layout(nodes: Iterable[Tuple[str, MutableMapping[str, object]]]) -> Dict[str, Dict[str, int]]:
    """Build a deterministic, generation-aware layout.

    Y coordinates follow the annotated ``family_hierarchy_level`` when present;
    X coordinates are stable alphabetical positions within a level. This mirrors
    the spirit of family-chart layouts without pulling in browser-side logic.
    """

    levels: Dict[int, List[str]] = {}
    for node_id, attrs in nodes:
        level = attrs.get("family_hierarchy_level")
        if level is None:
            level = 0
        levels.setdefault(int(level), []).append(node_id)

    layout: Dict[str, Dict[str, int]] = {}
    for level, members in sorted(levels.items()):
        for x, node_id in enumerate(sorted(members)):
            layout[node_id] = {"x": x, "y": level}
    return layout


def build_family_chart(graph: nx.MultiDiGraph) -> Dict[str, object]:
    """Project a rich graph into a family-chart-friendly structure.

    The output mirrors the building blocks of ``family-chart``: people nodes,
    union nodes (for partnerships), explicit parent links, sibling edges, and
    lightweight layout hints. Everything is represented with plain Python data
    structures so it can be serialized directly to JSON.
    """

    people: Dict[str, Dict[str, object]] = {}
    for node_id, attrs in graph.nodes(data=True):
        people[node_id] = {
            "id": node_id,
            "label": attrs.get("label", node_id),
            "description": attrs.get("description"),
            "clusters": attrs.get("clusters", []),
            "family_hierarchy_level": attrs.get("family_hierarchy_level"),
        }

    partnerships = _partnerships(graph)
    parent_edges = _parent_child_pairs(graph)
    sibling_edges = _sibling_edges(graph)

    unions: Dict[str, Dict[str, object]] = {}
    for idx, ((a, b), meta) in enumerate(sorted(partnerships.items())):
        union_id = f"union_{idx + 1}"
        unions[union_id] = {
            "id": union_id,
            "partners": list(meta["partners"]),
            "relations": meta["relations"],
            "children": [],
        }

    # Attach children to unions when both parents are known partners
    partner_lookup: Dict[frozenset[str], str] = {
        frozenset(entry["partners"]): union_id for union_id, entry in unions.items()
    }
    parent_map: Dict[str, List[str]] = {}
    for parent, child, data in parent_edges:
        parent_map.setdefault(child, []).append(parent)
    for child, parents in parent_map.items():
        parent_set = frozenset(sorted(parents))
        union_id = partner_lookup.get(parent_set)
        if union_id:
            unions[union_id]["children"].append(child)

    # Build relationship edges for downstream rendering
    relationships: List[Dict[str, object]] = []
    for parent, child, data in parent_edges:
        relationships.append(
            {
                "from": parent,
                "to": child,
                "type": "parent",
                "relation": data.get("relation"),
            }
        )

    # Add union->child edges so front-ends can keep households together
    for union in unions.values():
        for child in sorted(set(union["children"])):
            relationships.append({"from": union["id"], "to": child, "type": "union_child"})

    layout = _compute_layout(graph.nodes(data=True))
    family_edges = sum(
        1 for _, _, data in graph.edges(data=True) if data.get("relation") in FAMILY_RELATIONS
    )

    return {
        "people": list(people.values()),
        "unions": list(unions.values()),
        "relationships": relationships + sibling_edges,
        "layout": layout,
        "summary": {
            "people": len(people),
            "families": len(unions),
            "parent_edges": len(parent_edges),
            "sibling_edges": len(sibling_edges),
            "family_edges": family_edges,
        },
    }


def export_family_chart(graph: nx.MultiDiGraph, out_dir: str) -> str:
    """Write a family-chart compatible JSON document to ``out_dir``."""

    chart = build_family_chart(graph)
    chart_path = os.path.join(out_dir, "family_chart.json")
    with open(chart_path, "w", encoding="utf-8") as fh:
        json.dump(chart, fh, indent=2)
    return chart_path


__all__ = ["build_family_chart", "export_family_chart"]
