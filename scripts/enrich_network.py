"""Enrich exported wikinet graphs with analytics and lightweight labels.

The helpers here can be imported (``from scripts.enrich_network import enrich``)
for programmatic use and are also wired into ``wikinet enrich`` on the CLI.
The goal is to stay simple and fast while adding useful signals for the D3
viewer: graph metrics, role guesses, and relation counts.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence

import networkx as nx

FAMILY_RELATIONS = {"father", "mother", "child", "spouse", "partner", "relative", "sibling", "P22", "P25", "P26", "P40", "P1038", "P3373"}
POLITICAL_RELATIONS = {"position_held", "member_of_party", "member_of", "officeholder", "head_of_state", "head_of_government", "P39", "P102", "P463", "P2388", "P6", "P35"}
SECURITY_RELATIONS = {"military_branch", "military_rank", "affiliation", "military_service", "participant", "P241", "P410", "P1416", "P797", "P710"}
CORPORATE_RELATIONS = {"owned_by", "subsidiary", "parent", "product_or_service", "founded_by", "director_manager", "P127", "P355", "P749", "P1056", "P112", "P1037"}


@dataclass
class Metrics:
    degree: Dict[str, float]
    betweenness: Dict[str, float]
    core: Dict[str, int]
    community: Dict[str, int]


def load_graph(nodes_path: Path, edges_path: Path) -> nx.MultiDiGraph:
    with nodes_path.open("r", encoding="utf-8") as fh:
        nodes = json.load(fh)
    with edges_path.open("r", encoding="utf-8") as fh:
        edges = json.load(fh)
    graph = nx.MultiDiGraph()
    for node in nodes:
        graph.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    for edge in edges:
        graph.add_edge(edge["source"], edge["target"], **{k: v for k, v in edge.items() if k not in {"source", "target"}})
    return graph


def compute_metrics(graph: nx.MultiDiGraph) -> Metrics:
    nodes = list(graph.nodes())
    n = len(nodes)
    degree_count: Dict[str, float] = {str(node): 0.0 for node in nodes}
    for u, v, _ in graph.edges(data=True):
        degree_count[str(u)] += 1
        degree_count[str(v)] += 1
    degree = {node: (deg / max(n - 1, 1)) for node, deg in degree_count.items()}

    betweenness = {node: 0.0 for node in nodes}
    core = {node: 0 for node in nodes}
    community_map: Dict[str, int] = {}

    # If a full networkx install is available, use richer metrics
    if hasattr(nx, "betweenness_centrality"):
        try:
            undirected = graph.to_undirected()  # type: ignore[attr-defined]
            betweenness = nx.betweenness_centrality(undirected, normalized=True)
            core = nx.core_number(undirected)
            comms = []
            if hasattr(getattr(nx, "algorithms", None), "community"):
                from networkx.algorithms import community as nx_community

                comms = nx_community.greedy_modularity_communities(undirected)  # type: ignore[arg-type]
            for idx, comm in enumerate(comms):
                for node in comm:
                    community_map[str(node)] = idx
        except Exception:
            pass

    return Metrics(degree=degree, betweenness=betweenness, core=core, community=community_map)


def _count_matching_edges(graph: nx.MultiDiGraph, node: str, relation_set: set[str]) -> int:
    count = 0
    for u, _, data in graph.edges(data=True):
        if str(u) != str(node):
            continue
        relation = str(data.get("relation") or data.get("pid") or "")
        if relation in relation_set:
            count += 1
    return count


def _role_from_attributes(attrs: Mapping[str, object], counts: Mapping[str, int], taxonomy: Mapping[str, Sequence[str]] | None) -> tuple[str, List[str]]:
    text_blobs: List[str] = []
    for key in ("label", "description", "government_roles", "occupation", "positions", "categories", "layers"):
        value = attrs.get(key)
        if isinstance(value, str):
            text_blobs.append(value)
        elif isinstance(value, (list, tuple, set)):
            text_blobs.extend([str(v) for v in value])
    text = " ".join(text_blobs).lower()
    roles: List[str] = []
    taxonomy = taxonomy or {}
    for role, keywords in taxonomy.items():
        if any(keyword.lower() in text for keyword in keywords):
            roles.append(role)
    if counts.get("corporate_links"):
        roles.append("corporate")
    if counts.get("security_links") or "military" in text:
        roles.append("security")
    if counts.get("positions") or "government" in text:
        roles.append("political")
    if counts.get("children") or counts.get("spouses"):
        roles.append("family")
    if not roles:
        roles.append("other")
    primary = roles[0]
    secondary = sorted(set(roles[1:]))
    return primary, secondary


def _importance_score(metrics: Metrics, node: str, primary_role: str) -> float:
    deg = metrics.degree.get(node, 0.0)
    bet = metrics.betweenness.get(node, 0.0)
    core = metrics.core.get(node, 0)
    role_bonus = {"political": 0.2, "security": 0.2, "corporate": 0.1}.get(primary_role, 0.0)
    return round(deg + bet + (core * 0.05) + role_bonus, 4)


def enrich(graph: nx.MultiDiGraph, taxonomy: Mapping[str, Sequence[str]] | None = None) -> tuple[List[MutableMapping[str, object]], List[MutableMapping[str, object]]]:
    metrics = compute_metrics(graph)
    enriched_nodes: List[MutableMapping[str, object]] = []
    for node, data in graph.nodes(data=True):
        counts = {
            "children": _count_matching_edges(graph, node, {"child", "P40"}),
            "spouses": _count_matching_edges(graph, node, {"spouse", "P26"}),
            "positions": _count_matching_edges(graph, node, POLITICAL_RELATIONS),
            "corporate_links": _count_matching_edges(graph, node, CORPORATE_RELATIONS),
            "security_links": _count_matching_edges(graph, node, SECURITY_RELATIONS),
        }
        primary_role, secondary_roles = _role_from_attributes(data, counts, taxonomy)
        record: MutableMapping[str, object] = {
            "id": node,
            **data,
            **counts,
            "degree_centrality": metrics.degree.get(node, 0.0),
            "betweenness_centrality": metrics.betweenness.get(node, 0.0),
            "core_number": metrics.core.get(node, 0),
            "community": metrics.community.get(node),
            "primary_role": primary_role,
            "secondary_roles": secondary_roles,
        }
        record["importance_score"] = _importance_score(metrics, node, primary_role)
        enriched_nodes.append(record)

    enriched_edges: List[MutableMapping[str, object]] = []
    for u, v, data in graph.edges(data=True):
        relation = str(data.get("relation") or data.get("pid") or "")
        if relation in FAMILY_RELATIONS:
            layer = "family"
        elif relation in POLITICAL_RELATIONS:
            layer = "political"
        elif relation in SECURITY_RELATIONS:
            layer = "security"
        elif relation in CORPORATE_RELATIONS:
            layer = "corporate"
        else:
            layer = "other"
        enriched_edges.append({"source": u, "target": v, "layer": layer, **data})

    return enriched_nodes, enriched_edges


def write_enriched(out_dir: Path, nodes: Sequence[Mapping[str, object]], edges: Sequence[Mapping[str, object]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "enriched_nodes.json").open("w", encoding="utf-8") as fh:
        json.dump(list(nodes), fh, ensure_ascii=False, indent=2)
    with (out_dir / "enriched_edges.json").open("w", encoding="utf-8") as fh:
        json.dump(list(edges), fh, ensure_ascii=False, indent=2)


def run(nodes_path: Path, edges_path: Path, taxonomy_path: Path | None = None) -> tuple[List[MutableMapping[str, object]], List[MutableMapping[str, object]]]:
    graph = load_graph(nodes_path, edges_path)
    taxonomy = None
    if taxonomy_path and taxonomy_path.exists():
        with taxonomy_path.open("r", encoding="utf-8") as fh:
            taxonomy = json.load(fh)
    return enrich(graph, taxonomy)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Enrich wikinet exports")
    parser.add_argument("--nodes", required=True, help="Path to nodes.json")
    parser.add_argument("--edges", required=True, help="Path to edges.json")
    parser.add_argument("--out-dir", required=True, help="Directory to write enriched files")
    parser.add_argument("--taxonomy", help="Optional taxonomy JSON")
    args = parser.parse_args(argv)

    enriched_nodes, enriched_edges = run(Path(args.nodes), Path(args.edges), Path(args.taxonomy) if args.taxonomy else None)
    write_enriched(Path(args.out_dir), enriched_nodes, enriched_edges)


if __name__ == "__main__":  # pragma: no cover
    main()
