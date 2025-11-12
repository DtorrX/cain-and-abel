from wikinet.resolver import Resolver
from wikinet.http import HTTPClient
from wikinet.resolver import Resolver


class DummyHTTP(HTTPClient):
    def __init__(self, payload):
        self.payload = payload

    def get_json(self, url, params=None, headers=None, use_cache=True):
        return self.payload


def test_resolve_title(monkeypatch):
    payload = {
        "query": {
            "pages": {
                "1": {"pageprops": {"wikibase_item": "Q7259"}}
            }
        }
    }
    resolver = Resolver(DummyHTTP(payload))
    assert resolver.resolve_title("Ada Lovelace") == "Q7259"


def test_resolve_search(monkeypatch):
    payload = {
        "search": [
            {"id": "Q7259", "label": "Ada Lovelace"}
        ]
    }
    resolver = Resolver(DummyHTTP(payload))
    assert resolver.resolve_search("Ada") == "Q7259"

