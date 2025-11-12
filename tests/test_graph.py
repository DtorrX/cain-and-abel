import networkx as nx

from wikinet.graph import GraphBuilder
from wikinet.schemas import Edge


class DummyResolver:
    def resolve_seeds(self, seeds):
        return list(seeds)


class DummyWikidata:
    def __init__(self, edges, labels):
        self.edges = edges
        self.labels = labels

    def fetch_relations(self, qids, include_family=True, include_political=True):
        return [edge for edge in self.edges if edge.source in qids]

    def fetch_labels(self, qids):
        return self.labels


class DummyWikipedia:
    def extract_edges(self, title):
        return {}


def test_graph_builder_creates_nodes_and_edges():
    edges = [
        Edge(
            source="Q1",
            target="Q2",
            relation="father",
            pid="P22",
            source_system="wikidata",
            evidence_url="https://example.com",
            retrieved_at="2024-01-01T00:00:00Z",
        )
    ]
    labels = {"Q1": {"label": "Person A"}, "Q2": {"label": "Person B"}}
    builder = GraphBuilder(
        DummyResolver(),
        DummyWikidata(edges, labels),
        DummyWikipedia(),
        max_depth=1,
    )
    graph = builder.crawl(["Q1"])
    assert graph.number_of_nodes() == 2
    assert graph.number_of_edges() == 1
    data = graph.get_edge_data("Q1", "Q2", 0)
    assert data["relation"] == "father"
