import networkx as nx

from wikinet.cia import CIAOfficial, CIAWorldLeadersClient, GovernmentIndex, CIA_WORLD_LEADERS_URL


class DummyHTTP:
    def __init__(self, payload):
        self.payload = payload
        self.requested = None

    def get_json(self, url, headers=None):
        self.requested = (url, headers)
        return self.payload


def test_cia_client_parses_officials():
    payload = {
        "result": {
            "data": {
                "worldLeadersLeadershipData": {
                    "countries": [
                        {
                            "name": "United Arab Emirates",
                            "sections": [
                                {
                                    "entries": [
                                        {"name": "Mohammed bin Zayed", "title": "President"},
                                        {"name": "Tahnoun bin Zayed", "title": "National Security Advisor"},
                                    ]
                                },
                                {
                                    "entries": [
                                        {"name": "Mohammed bin Rashid", "title": "Prime Minister"},
                                    ]
                                },
                            ],
                        }
                    ]
                }
            }
        }
    }
    http = DummyHTTP(payload)
    client = CIAWorldLeadersClient(http)
    officials = client.fetch()
    assert http.requested[0] == CIA_WORLD_LEADERS_URL
    names = {official.name for official in officials}
    assert "Mohammed bin Zayed" in names
    defense_categories = next(official.categories for official in officials if official.name == "Tahnoun bin Zayed")
    assert "bureaucrat" in defense_categories or "military" in defense_categories


def test_government_index_matches_and_annotates():
    officials = [
        CIAOfficial(
            country="United Arab Emirates",
            position="Minister of Defense",
            name="Mohammed bin Zayed",
            categories=("government", "military"),
        ),
        CIAOfficial(
            country="United Arab Emirates",
            position="Director of Intelligence",
            name="Tahnoun bin Zayed",
            categories=("government", "bureaucrat"),
        ),
    ]
    index = GovernmentIndex(officials)
    countries = index.countries_for_labels(["United Arab Emirates"])
    assert countries == {"United Arab Emirates"}

    class Resolver:
        def resolve_seed(self, seed):
            mapping = {
                "Mohammed bin Zayed": "Q2",
                "Tahnoun bin Zayed": "Q3",
            }
            if seed in mapping:
                return mapping[seed]
            raise ValueError(seed)

    resolved = index.resolve_official(officials[0], Resolver())
    assert resolved == "Q2"

    graph = nx.MultiDiGraph()
    graph.add_node("Q2", label="Mohammed bin Zayed")
    index.annotate_graph_node(graph, "Q2", "Mohammed bin Zayed")
    nodes_attr = getattr(graph, "_nodes", None)
    if nodes_attr is not None:
        node_data = nodes_attr.get("Q2", {})
    else:  # pragma: no cover - real networkx path
        node_data = graph.nodes["Q2"]
    assert "government" in node_data.get("layers", [])
    assert any("Minister of Defense" in role for role in node_data.get("government_roles", []))
