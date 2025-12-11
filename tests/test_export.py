import json
import os

import networkx as nx

from wikinet.export import export_graph, sanitize_graph_for_graphml


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


def test_graphml_sanitization_preserves_lists(tmp_path):
    graph = nx.MultiDiGraph()
    graph.add_node("Q1", tags=["royal", "security"], label="Node1")
    graph.add_node("Q2", label="Node2")
    graph.add_edge("Q1", "Q2", relation="ally", metadata={"strength": 5})

    sanitized = sanitize_graph_for_graphml(graph)
    # GraphML accepts the sanitized graph
    nx.write_graphml(sanitized, tmp_path / "graph.graphml")

    # Original graph keeps structured attributes in JSON export
    paths = export_graph(graph, tmp_path)
    with open(paths["nodes"], "r", encoding="utf-8") as fh:
        nodes = json.load(fh)
    tag_field = next(node["tags"] for node in nodes if node["id"] == "Q1")
    assert tag_field == ["royal", "security"]
