import json
import os
from datetime import datetime, timedelta

import networkx as nx

from wikinet.cia import (
    CIAOfficial,
    CIAWorldLeadersClient,
    GovernmentIndex,
    CIA_WORLD_LEADERS_URL,
)


class DummyHTTP:
    def __init__(self, payload=None, text=None, error=None):
        self.payload = payload
        self.text = text
        self.requested = None
        self.error = error

    def get_json(self, url, headers=None):
        if self.error:
            raise self.error
        self.requested = (url, headers)
        return self.payload or {}

    def request(self, method, url, headers=None, **kwargs):
        if self.error:
            raise self.error
        self.requested = (url, headers)
        return self.payload or {}

    def request(self, method, url, headers=None, **kwargs):
        self.requested = (url, headers)

        class Resp:
            def __init__(self, text):
                self.text = text

        return Resp(self.text or "")


def test_cia_client_parses_officials():
    entities = [
        {
            "properties": {
                "name": ["Mohammed bin Zayed"],
                "position": ["President"],
                "country": ["United Arab Emirates"],
            }
        },
        {
            "properties": {
                "name": ["Tahnoun bin Zayed"],
                "position": ["National Security Advisor"],
                "country": ["United Arab Emirates"],
            }
        },
    ]
    http = DummyHTTP(text="\n".join(json.dumps(entry) for entry in entities))
    client = CIAWorldLeadersClient(http)
    officials = client.fetch()
    assert http.requested[0] == CIA_WORLD_LEADERS_URL
    names = {official.name for official in officials}
    assert "Mohammed bin Zayed" in names
    defense_categories = next(official.categories for official in officials if official.name == "Tahnoun bin Zayed")
    assert "bureaucrat" in defense_categories or "military" in defense_categories


def test_cia_cache_preferred_when_fresh(tmp_path):
    cache_path = tmp_path / "cache.json"
    now = datetime.now().timestamp()
    cache_payload = [
        {"country": "UAE", "position": "President", "name": "MBZ", "categories": ["government"]}
    ]
    cache_path.write_text(json.dumps(cache_payload), encoding="utf-8")
    os.utime(cache_path, (now, now))
    http = DummyHTTP(text="")
    client = CIAWorldLeadersClient(http, cache_path=cache_path)
    officials = client.fetch()
    assert officials[0].name == "MBZ"
    assert http.requested is None


def test_cia_cache_fallback_on_error(tmp_path):
    cache_path = tmp_path / "cache.json"
    stale_time = (datetime.now() - timedelta(days=30)).timestamp()
    cache_payload = [
        {"country": "UAE", "position": "Advisor", "name": "Tahnoun", "categories": ["security"]}
    ]
    cache_path.write_text(json.dumps(cache_payload), encoding="utf-8")
    os.utime(cache_path, (stale_time, stale_time))
    http = DummyHTTP(error=Exception("boom"))
    client = CIAWorldLeadersClient(http, cache_path=cache_path)
    officials = client.fetch()
    assert officials and officials[0].name == "Tahnoun"


def test_cia_cache_refreshed_on_success(tmp_path):
    cache_path = tmp_path / "cache.json"
    entities = [
        {
            "properties": {
                "name": ["Leader"],
                "position": ["President"],
                "country": ["Freedonia"],
            }
        }
    ]
    http = DummyHTTP(text="\n".join(json.dumps(entry) for entry in entities))
    client = CIAWorldLeadersClient(http, cache_path=cache_path)
    officials = client.fetch()
    assert officials[0].country == "Freedonia"
    assert cache_path.exists()


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
