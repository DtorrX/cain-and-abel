"""Wikipedia integration for infobox fallback."""

from __future__ import annotations

import re
from typing import Dict, Optional

from .http import HTTPClient
from .utils import timestamp

WIKI_API = "https://{lang}.wikipedia.org/w/api.php"
INFOBOX_PATTERN = re.compile(r"\|\s*(?P<key>[A-Za-z0-9_ ]+)\s*=\s*(?P<value>.+)")
RELATION_KEYS = {
    "father": "father",
    "mother": "mother",
    "spouse": "spouse",
    "spouses": "spouse",
    "children": "child",
    "child": "child",
    "relations": "relative",
    "partner": "partner",
}


class WikipediaClient:
    def __init__(self, http: HTTPClient, lang: str = "en") -> None:
        self.http = http
        self.lang = lang

    def fetch_infobox(self, title: str, lang: Optional[str] = None) -> Dict[str, str]:
        lang = lang or self.lang
        data = self.http.get_json(
            WIKI_API.format(lang=lang),
            params={
                "action": "parse",
                "page": title,
                "prop": "wikitext",
                "format": "json",
            },
        )
        wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
        infobox_lines = []
        capture = False
        for line in wikitext.splitlines():
            if line.startswith("{{Infobox"):
                capture = True
                continue
            if capture and line.startswith("{{") and not line.startswith("{{Infobox"):
                break
            if capture and line.startswith("}}"):
                break
            if capture:
                infobox_lines.append(line)
        result: Dict[str, str] = {}
        for line in infobox_lines:
            match = INFOBOX_PATTERN.match(line)
            if not match:
                continue
            key = match.group("key").strip().lower()
            value = re.sub(r"\s*<.*?>", "", match.group("value")).strip()
            if key in RELATION_KEYS:
                result[RELATION_KEYS[key]] = value
        return result

    def extract_edges(self, title: str) -> Dict[str, Dict[str, str]]:
        info = self.fetch_infobox(title)
        edges: Dict[str, Dict[str, str]] = {}
        for relation, value in info.items():
            edges[relation] = {
                "value": value,
                "source_system": "wikipedia",
                "evidence_url": f"https://{self.lang}.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "retrieved_at": timestamp(),
            }
        return edges


__all__ = ["WikipediaClient", "RELATION_KEYS"]
