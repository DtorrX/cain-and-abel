import json
from pathlib import Path

import networkx as nx

from scripts import enrich_network


def test_enrichment_metrics_and_roles(tmp_path):
    graph = nx.MultiDiGraph()
    graph.add_node("A", label="Alice", layers=["government"])
    graph.add_node("B", label="Bob")
    graph.add_edge("A", "B", relation="spouse")
    enriched_nodes, enriched_edges = enrich_network.enrich(graph)

    node_map = {n["id"]: n for n in enriched_nodes}
    assert node_map["A"]["children"] == 0
    assert node_map["A"]["spouses"] == 1
    assert node_map["A"]["primary_role"] in {"family", "political"}
    assert node_map["A"]["importance_score"] >= 0
    assert enriched_edges[0]["layer"] == "family"


def test_enrichment_run_writes_files(tmp_path):
    nodes_path = tmp_path / "nodes.json"
    edges_path = tmp_path / "edges.json"
    nodes = [{"id": "A", "label": "Alice"}, {"id": "B", "label": "Bob"}]
    edges = [{"source": "A", "target": "B", "relation": "owned_by"}]
    nodes_path.write_text(json.dumps(nodes), encoding="utf-8")
    edges_path.write_text(json.dumps(edges), encoding="utf-8")

    enriched_nodes, enriched_edges = enrich_network.run(nodes_path, edges_path)
    enrich_network.write_enriched(tmp_path, enriched_nodes, enriched_edges)
    assert (tmp_path / "enriched_nodes.json").exists()
    assert any(edge["layer"] == "corporate" for edge in enriched_edges)
