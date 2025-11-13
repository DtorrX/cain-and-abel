#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Visualize and graph a network from multiple possible inputs:
- nodes.json  (list of {id, label, description, ...})
- edges.json  (list of {source, target, label/type/weight, ...})
- legend.json (optional mapping: categories -> styles; also per-id overrides)
- graph.dot   (Graphviz DOT)
- graph.graphml (GraphML)

Outputs:
- network_static.png           : static overview (top hubs labeled)
- network_interactive.html     : interactive PyVis graph
- network_metrics.csv          : degree/centrality table
"""

import argparse
import json
import os
import sys
from typing import Dict, Any, List, Tuple, Optional

import networkx as nx

# Optional imports guarded at runtime
def _has_pyvis():
    try:
        import pyvis  # noqa
        return True
    except Exception:
        return False

def _has_agraph():
    try:
        import pygraphviz  # noqa
        return True
    except Exception:
        return False

def safe_load_json(path: str) -> Optional[Any]:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_nodes(nodes_path: str) -> Dict[str, Dict[str, Any]]:
    nodes = {}
    data = safe_load_json(nodes_path)
    if not data:
        return nodes
    for item in data:
        # minimal schema
        nid = str(item.get("id") or item.get("qid") or item.get("node") or "").strip()
        if not nid:
            continue
        nodes[nid] = {
            "label": item.get("label", nid),
            "description": item.get("description") or "",
            # carry any extra attributes
            **{k: v for k, v in item.items() if k not in {"id", "label", "description"}}
        }
    return nodes

def _edge_endpoints(e: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    # Try common key variants
    s = e.get("source") or e.get("src") or e.get("from") or e.get("u")
    t = e.get("target") or e.get("dst") or e.get("to") or e.get("v")
    return (str(s).strip() if s else None, str(t).strip() if t else None)

def load_edges(edges_path: str) -> List[Tuple[str, str, Dict[str, Any]]]:
    edges = []
    data = safe_load_json(edges_path)
    if not data:
        return edges
    for item in data:
        s, t = _edge_endpoints(item)
        if not (s and t):
            continue
        attrs = dict(item)
        for k in ["source", "src", "from", "u", "target", "dst", "to", "v"]:
            attrs.pop(k, None)
        edges.append((s, t, attrs))
    return edges

def load_legend(legend_path: str) -> Dict[str, Any]:
    """
    Expected patterns (all optional, best-effort):
    {
      "category_styles": { "Royal": {"shape":"dot","color":"#..."},
                           "Institution": {...}, ... },
      "node_overrides": { "Q556607": {"category":"Royal"},
                          "Q57655":   {"category":"Royal"}, ... },
      "edge_styles":    { "spouse": {"dashed": true},
                          "parent": {"width": 2} }
    }
    """
    data = safe_load_json(legend_path)
    return data or {}

def merge_from_dot(path: str, G: nx.MultiDiGraph) -> None:
    if not os.path.exists(path):
        return
    if _has_agraph():
        H = nx.drawing.nx_agraph.read_dot(path)
    else:
        # Pure networkx dot reader (limited), fallback to pydot
        try:
            from networkx.drawing.nx_pydot import read_dot  # type: ignore
            H = read_dot(path)
        except Exception:
            print("WARNING: Could not import pydot/pygraphviz; skipping DOT.", file=sys.stderr)
            return
    G.update(H)

def merge_from_graphml(path: str, G: nx.MultiDiGraph) -> None:
    if not os.path.exists(path):
        return
    H = nx.read_graphml(path)
    G.update(H)

def apply_nodes_edges(
    G: nx.MultiDiGraph,
    nodes: Dict[str, Dict[str, Any]],
    edges: List[Tuple[str, str, Dict[str, Any]]],
    legend: Dict[str, Any]
) -> None:
    # Per-node overrides from legend
    overrides = (legend.get("node_overrides") or {}) if legend else {}

    for nid, attrs in nodes.items():
        merged = dict(attrs)
        if nid in overrides:
            merged.update(overrides[nid])
        # Ensure basic label
        merged.setdefault("label", nid)
        G.add_node(nid, **merged)

    for (s, t, attrs) in edges:
        G.add_edge(s, t, **attrs)

def coerce_directed(G: nx.Graph) -> nx.MultiDiGraph:
    # If any edge has a direction hint, we’ll treat as directed
    is_directed = G.is_directed()
    if not is_directed:
        for u, v, d in G.edges(data=True):
            if any(k in d for k in ("dir", "arrowhead", "directed", "type", "relation")):
                is_directed = True
                break
    return G if isinstance(G, nx.MultiDiGraph) and is_directed else nx.MultiDiGraph(G) if is_directed else nx.MultiDiGraph(G.to_undirected())

def compute_metrics(G: nx.Graph) -> Dict[str, Dict[str, float]]:
    # Use a simplified giant-component for centrality stability
    if G.number_of_nodes() == 0:
        return {}
    try:
        if G.is_directed():
            UG = G.to_undirected(as_view=True)
        else:
            UG = G
        comp = max((UG.subgraph(c).copy() for c in nx.connected_components(UG)), key=lambda H: H.number_of_nodes())
    except nx.NetworkXError:
        comp = G.copy()

    deg = dict(comp.degree())
    bet = nx.betweenness_centrality(comp, k=min(500, comp.number_of_nodes()), seed=42) if comp.number_of_nodes() > 1000 else nx.betweenness_centrality(comp)
    pr = nx.pagerank(comp) if comp.number_of_nodes() < 10000 else {}
    out = {}
    for n in G.nodes():
        out[n] = {
            "degree": float(deg.get(n, 0)),
            "betweenness": float(bet.get(n, 0.0)),
            "pagerank": float(pr.get(n, 0.0)),
        }
    return out

def write_metrics_csv(metrics: Dict[str, Dict[str, float]], outpath: str) -> None:
    import csv
    if not metrics:
        return
    with open(outpath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "degree", "betweenness", "pagerank"])
        for nid, m in sorted(metrics.items(), key=lambda kv: (-kv[1]["degree"], kv[0])):
            w.writerow([nid, m["degree"], m["betweenness"], m["pagerank"]])

def draw_static(G: nx.Graph, metrics: Dict[str, Dict[str, float]], outpath: str, top_k_labels: int = 30) -> None:
    import matplotlib.pyplot as plt

    if G.number_of_nodes() == 0:
        print("WARNING: Graph empty; skipping static plot.")
        return

    # Layout: spring (deterministic seed)
    pos = nx.spring_layout(G, seed=42, k=None)

    # Node size by (1 + degree)^1.3, scaled
    deg = {n: metrics.get(n, {}).get("degree", 0.0) for n in G.nodes()}
    sizes = [80.0 * (1.0 + deg.get(n, 0.0)) ** 1.3 for n in G.nodes()]

    plt.figure(figsize=(14, 10), dpi=150)
    nx.draw_networkx_edges(G, pos, alpha=0.25, width=0.6)
    nx.draw_networkx_nodes(G, pos, node_size=sizes, alpha=0.9)

    # Label top hubs
    hubs = sorted(G.nodes(), key=lambda n: (-deg.get(n, 0.0), n))[:top_k_labels]
    labels = {n: (G.nodes[n].get("label") or str(n)) for n in hubs}
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=8)

    plt.axis("off")
    plt.tight_layout()
    plt.savefig(outpath, bbox_inches="tight")
    plt.close()

def draw_interactive(G: nx.Graph, metrics: Dict[str, Dict[str, float]], outpath: str, legend: Dict[str, Any]) -> None:
    if not _has_pyvis():
        print("INFO: pyvis not installed; skipping interactive export. Install with `pip install pyvis`.")
        return
    from pyvis.network import Network

    net = Network(height="800px", width="100%", bgcolor="#111111", font_color="#EEEEEE", notebook=False, directed=G.is_directed())
    net.barnes_hut()

    # Optional style helpers
    cat_styles = (legend or {}).get("category_styles") or {}
    edge_styles = (legend or {}).get("edge_styles") or {}

    # Add nodes
    for n, d in G.nodes(data=True):
        title_bits = []
        if d.get("description"):
            title_bits.append(d["description"])
        # include metrics in tooltip
        m = metrics.get(n, {})
        title_bits.append(f"degree={m.get('degree', 0):.0f}, betweenness={m.get('betweenness', 0):.4f}, pagerank={m.get('pagerank', 0):.6f}")
        title = "<br>".join(title_bits)

        label = d.get("label") or str(n)
        category = d.get("category") or d.get("type") or d.get("group")

        style = (cat_styles.get(category) if category else {}) if cat_styles else {}
        node_kwargs = {
            "label": label,
            "title": title,
            "shape": style.get("shape", "dot"),
        }
        if "color" in style:
            node_kwargs["color"] = style["color"]
        if "size" in style:
            node_kwargs["value"] = style["size"]

        net.add_node(str(n), **node_kwargs)

    # Add edges
    for u, v, d in G.edges(data=True):
        etype = d.get("type") or d.get("relation") or d.get("label") or d.get("predicate")
        e_style = edge_styles.get(etype, {}) if edge_styles else {}
        e_kwargs = {}
        if e_style.get("dashed") is True:
            e_kwargs["dashes"] = True
        if "width" in e_style:
            e_kwargs["width"] = e_style["width"]
        if etype:
            e_kwargs["title"] = str(etype)
        net.add_edge(str(u), str(v), **e_kwargs)

    net.set_options("""
    const options = {
      nodes: { scaling: { min: 5, max: 50 } },
      edges: { color: { inherit: true }, smooth: { type: "continuous" } },
      physics: { stabilization: { iterations: 250 }, barnesHut: { springLength: 120 } },
      interaction: { tooltipDelay: 120, hideEdgesOnDrag: false, multiselect: true }
    }""")
    net.show(outpath)

def main():
    p = argparse.ArgumentParser(description="Visualize and graph a network from multiple inputs.")
    p.add_argument("--nodes", default="nodes.json", help="Path to nodes.json")
    p.add_argument("--edges", default="edges.json", help="Path to edges.json")
    p.add_argument("--legend", default="legend.json", help="Path to legend.json (optional)")
    p.add_argument("--dot", default="graph.dot", help="Path to graph.dot (optional)")
    p.add_argument("--graphml", default="graph.graphml", help="Path to graph.graphml (optional)")
    p.add_argument("--out-png", default="network_static.png", help="Static PNG output")
    p.add_argument("--out-html", default="network_interactive.html", help="Interactive HTML output (pyvis)")
    p.add_argument("--out-metrics", default="network_metrics.csv", help="CSV with metrics")
    p.add_argument("--label-top", type=int, default=30, help="Label top-K hubs in PNG")
    args = p.parse_args()

    # Build a working graph
    G = nx.MultiDiGraph()

    # Merge DOT + GraphML if present
    merge_from_dot(args.dot, G)
    merge_from_graphml(args.graphml, G)

    # Load JSON inputs
    nodes = load_nodes(args.nodes)
    edges = load_edges(args.edges)
    legend = load_legend(args.legend)

    # Apply nodes/edges
    apply_nodes_edges(G, nodes, edges, legend)

    # Coerce to directed if hints present
    G = coerce_directed(G)

    # Compute metrics
    metrics = compute_metrics(G)
    if metrics:
        write_metrics_csv(metrics, args.out_metrics)
        print(f"[✓] Wrote metrics: {args.out_metrics}")

    # Static plot
    draw_static(G, metrics, args.out_png, top_k_labels=args.label_top)
    print(f"[✓] Wrote static plot: {args.out_png}")

    # Interactive (if pyvis installed)
    draw_interactive(G, metrics, args.out_html, legend)
    if _has_pyvis():
        print(f"[✓] Wrote interactive HTML: {args.out_html} (open in a browser)")
    else:
        print("[i] Install pyvis for interactive HTML: pip install pyvis")

if __name__ == "__main__":
    main()

