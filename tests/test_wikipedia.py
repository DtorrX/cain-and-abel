from wikinet.wikipedia import WikipediaClient
from wikinet.http import HTTPClient


class DummyHTTP(HTTPClient):
    def __init__(self, wikitext):
        self.wikitext = wikitext

    def get_json(self, url, params=None, headers=None, use_cache=True):
        return {"parse": {"wikitext": {"*": self.wikitext}}}


def test_infobox_extraction():
    wikitext = """{{Infobox person\n| name = Test\n| father = [[John Doe]]\n| mother = [[Jane Doe]]\n| spouse = [[Alex Doe]]\n}}"""
    client = WikipediaClient(DummyHTTP(wikitext))
    info = client.fetch_infobox("Test")
    assert info["father"] == "[[John Doe]]"
    edges = client.extract_edges("Test")
    assert "father" in edges
    assert edges["father"]["source_system"] == "wikipedia"
