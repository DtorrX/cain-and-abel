import json
from pathlib import Path

import json
from pathlib import Path

import networkx as nx

from wikinet import cli


def test_build_parser_has_commands():
    parser = cli.build_parser()
    args = parser.parse_args(["validate", "out"])
    assert args.command == "validate"


def test_validate_command(tmp_path):
    nodes = [{"id": "Q1"}]
    edges = [{"source": "Q1", "target": "Q1"}]
    out_dir = tmp_path / "graph"
    out_dir.mkdir()
    (out_dir / "nodes.json").write_text(json.dumps(nodes))
    (out_dir / "edges.json").write_text(json.dumps(edges))
    cli.run_validate(str(out_dir))


def test_crawl_invokes_builder(monkeypatch, tmp_path):
    called = {}

    def fake_collect(args, resolver):
        return ["Q1"]

    class DummyBuilder:
        def __init__(self, *a, **kw):
            called["init"] = True

        def crawl(self, seeds):
            called["seeds"] = seeds
            graph = nx.MultiDiGraph()
            graph.add_node("Q1", label="Node")
            return graph

    def fake_export(graph, out_dir):
        called["export"] = out_dir
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / "nodes.json").write_text("[]")
        (Path(out_dir) / "edges.json").write_text("[]")
        (Path(out_dir) / "graph.graphml").write_text("<graphml/>")
        (Path(out_dir) / "graph.dot").write_text("digraph {}")
        (Path(out_dir) / "legend.json").write_text("{}")
        return {}

    monkeypatch.setattr(cli, "_collect_seeds", fake_collect)
    monkeypatch.setattr(cli, "GraphBuilder", DummyBuilder)
    monkeypatch.setattr(cli, "export_graph", fake_export)

    args = cli.build_parser().parse_args(["crawl", "--seed", "Q1", "--out", str(tmp_path / "out")])
    cli.run_crawl(args)
    assert called["init"]
    assert called["seeds"] == ["Q1"]
    assert "export" in called
