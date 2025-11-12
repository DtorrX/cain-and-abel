import json
import os

import networkx as nx

from wikinet.export import export_graph


def test_export_creates_files(tmp_path):
    graph = nx.MultiDiGraph()
    graph.add_node("Q1", label="Node1")
    graph.add_node("Q2", label="Node2")
    graph.add_edge(
        "Q1",
        "Q2",
        relation="father",
        pid="P22",
        source_system="wikidata",
        evidence_url="https://example.com",
        retrieved_at="2024-01-01T00:00:00Z",
    )
    paths = export_graph(graph, tmp_path)
    for key in ("nodes", "edges", "graphml", "legend"):
        assert (tmp_path / os.path.basename(paths[key])).exists()
    with open(tmp_path / "nodes.json", "r", encoding="utf-8") as fh:
        data = json.load(fh)
        assert data[0]["label"] == "Node1"
