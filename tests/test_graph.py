import networkx as nx

from wikinet.cia import CIAOfficial, GovernmentIndex
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
        return {qid: self.labels.get(qid, {}) for qid in qids}


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


def test_graph_builder_integrates_government_index():
    official = CIAOfficial(
        country="United Arab Emirates",
        position="Minister of Defense",
        name="Mohammed bin Zayed Al Nahyan",
        categories=("government", "military"),
    )
    government_index = GovernmentIndex([official])

    class ResolverWithMap:
        def __init__(self):
            self.mapping = {
                "Q1": "Q1",
                "Mohammed bin Zayed Al Nahyan": "Q2",
            }

        def resolve_seed(self, seed):
            if seed in self.mapping:
                return self.mapping[seed]
            if seed.startswith("Q"):
                return seed
            raise ValueError(seed)

        def resolve_seeds(self, seeds):
            return [self.resolve_seed(seed) for seed in seeds]

    labels = {
        "Q1": {"label": "United Arab Emirates"},
        "Q2": {"label": "Mohammed bin Zayed Al Nahyan"},
    }
    builder = GraphBuilder(
        ResolverWithMap(),
        DummyWikidata([], labels),
        DummyWikipedia(),
        max_depth=0,
        government_index=government_index,
    )
    graph = builder.crawl(["Q1"])
    if hasattr(graph, "_nodes"):
        assert "Q2" in graph._nodes
    else:  # pragma: no cover - real networkx path
        assert "Q2" in graph.nodes
    nodes_attr = getattr(graph, "_nodes", None)
    if nodes_attr is not None:
        q2_data = nodes_attr.get("Q2", {})
    else:  # pragma: no cover - real networkx path
        q2_data = graph.nodes["Q2"]
    assert "government" in q2_data.get("layers", [])
    assert "military" in q2_data.get("layers", [])
    assert any("Minister of Defense" in role for role in q2_data.get("government_roles", []))
