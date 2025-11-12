from wikinet.wikidata import WikidataClient, FAMILY_PROPS
from wikinet.http import HTTPClient


class DummyHTTP(HTTPClient):
    def __init__(self, payload):
        self.payload = payload

    def get_json(self, url, params=None, headers=None, use_cache=True):
        return self.payload


def test_fetch_relations_parses_edges():
    data = {
        "results": {
            "bindings": [
                {
                    "src": {"value": "http://www.wikidata.org/entity/Q1"},
                    "dst": {"value": "http://www.wikidata.org/entity/Q2"},
                    "p": {"value": "http://www.wikidata.org/prop/direct/P22"},
                    "srcLabel": {"value": "Source"},
                    "dstLabel": {"value": "Target"},
                }
            ]
        }
    }
    client = WikidataClient(DummyHTTP(data))
    edges = client.fetch_relations(["Q1"], include_family=True, include_political=False)
    assert edges[0].relation == FAMILY_PROPS["P22"]
    assert edges[0].source == "Q1"
    assert edges[0].target == "Q2"
