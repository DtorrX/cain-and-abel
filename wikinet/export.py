"""Graph export utilities."""

from __future__ import annotations

import json
import os
from typing import Dict

import networkx as nx

from .family_chart import export_family_chart
from .utils import console

EDGE_STYLES = {
    "father": {"color": "#1f77b4", "style": "solid"},
    "mother": {"color": "#ff7f0e", "style": "solid"},
    "spouse": {"color": "#2ca02c", "style": "solid"},
    "child": {"color": "#d62728", "style": "solid"},
    "sibling": {"color": "#9467bd", "style": "dashed"},
    "relative": {"color": "#8c564b", "style": "dotted"},
    "partner": {"color": "#e377c2", "style": "solid"},
    "position_held": {"color": "#7f7f7f", "style": "solid"},
    "member_of_party": {"color": "#bcbd22", "style": "solid"},
    "member_of": {"color": "#17becf", "style": "solid"},
    "employer": {"color": "#aec7e8", "style": "solid"},
    "educated_at": {"color": "#ffbb78", "style": "solid"},
    "head_of_government": {"color": "#98df8a", "style": "solid"},
    "head_of_state": {"color": "#ff9896", "style": "solid"},
    "chairperson": {"color": "#c5b0d5", "style": "solid"},
    "officeholder": {"color": "#c49c94", "style": "solid"},
}

NODE_LAYERS = {
    "government": {"color": "#004170"},
    "military": {"color": "#8b0000"},
    "bureaucrat": {"color": "#556b2f"},
}

LEGEND = {"edges": EDGE_STYLES, "node_layers": NODE_LAYERS}


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def sanitize_graph_for_graphml(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Return a deep-copied graph with GraphML-safe attributes.

    NetworkX's GraphML writer only accepts scalar attributes. To avoid losing
    rich metadata (lists, dicts, sets) we serialize non-scalar attributes to
    JSON strings in a cloned graph while keeping the original graph intact for
    the JSON exports.
    """

    def _sanitize_value(value: object) -> object:
        if _is_scalar(value):
            return value
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            return json.dumps(str(value), ensure_ascii=False)

    safe = graph.__class__()
    for node, data in graph.nodes(data=True):
        safe.add_node(node, **{key: _sanitize_value(val) for key, val in data.items()})
    for u, v, data in graph.edges(data=True):
        safe.add_edge(u, v, **{key: _sanitize_value(val) for key, val in data.items()})
    return safe


def export_graph(graph: nx.MultiDiGraph, out_dir: str) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    nodes_path = os.path.join(out_dir, "nodes.json")
    edges_path = os.path.join(out_dir, "edges.json")
    graphml_path = os.path.join(out_dir, "graph.graphml")
    dot_path = os.path.join(out_dir, "graph.dot")
    legend_path = os.path.join(out_dir, "legend.json")

    nodes = []
    for node_id, data in graph.nodes(data=True):
        record = {"id": node_id}
        record.update(data)
        nodes.append(record)
    edges = []
    for u, v, data in graph.edges(data=True):
        record = {"source": u, "target": v}
        record.update(data)
        edges.append(record)

    with open(nodes_path, "w", encoding="utf-8") as fh:
        json.dump(nodes, fh, indent=2)
    with open(edges_path, "w", encoding="utf-8") as fh:
        json.dump(edges, fh, indent=2)
    nx.write_graphml(sanitize_graph_for_graphml(graph), graphml_path)
    dot_written = False
    try:
        from networkx.drawing.nx_pydot import write_dot

        write_dot(graph, dot_path)
        dot_written = True
        console.log("DOT export ready", dot_path)
    except Exception as exc:  # pragma: no cover - optional dependency
        console.log("[yellow]DOT export via pydot failed[/yellow]", exc)
    if not dot_written:
        with open(dot_path, "w", encoding="utf-8") as fh:
            fh.write("digraph wikinet {\n")
            for node_id, data in graph.nodes(data=True):
                label = data.get("label", node_id).replace("\"", "'")
                fh.write(f'  "{node_id}" [label="{label}"];\n')
            for u, v, data in graph.edges(data=True):
                relation = data.get("relation", "related_to")
                fh.write(f'  "{u}" -> "{v}" [label="{relation}"];\n')
            fh.write("}\n")
        dot_written = True
    try:
        import subprocess

        subprocess.run(["dot", "-Tpng", dot_path, "-o", os.path.join(out_dir, "graph.png")], check=True)
    except Exception:  # pragma: no cover
        console.log("[yellow]Graphviz PNG export skipped[/yellow]")

    with open(legend_path, "w", encoding="utf-8") as fh:
        json.dump(LEGEND, fh, indent=2)

    family_chart_path = export_family_chart(graph, out_dir)

    return {
        "nodes": nodes_path,
        "edges": edges_path,
        "graphml": graphml_path,
        "dot": dot_path,
        "legend": legend_path,
        "family_chart": family_chart_path,
    }


__all__ = [
    "export_graph",
    "sanitize_graph_for_graphml",
    "LEGEND",
    "EDGE_STYLES",
    "NODE_LAYERS",
]
