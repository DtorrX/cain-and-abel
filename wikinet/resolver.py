"""Resolve seeds to Wikidata Q-IDs."""

from __future__ import annotations

from typing import Iterable, List, Optional

from .http import HTTPClient

WIKI_API = "https://{lang}.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"


class Resolver:
    def __init__(self, http: HTTPClient, lang: str = "en") -> None:
        self.http = http
        self.lang = lang

    def resolve_title(self, title: str, lang: Optional[str] = None) -> str:
        lang = lang or self.lang
        data = self.http.get_json(
            WIKI_API.format(lang=lang),
            params={
                "action": "query",
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "titles": title,
                "format": "json",
            },
        )
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            qid = page.get("pageprops", {}).get("wikibase_item")
            if qid:
                return qid
        raise ValueError(f"Could not resolve Q-ID for title '{title}'")

    def resolve_search(self, query: str) -> str:
        data = self.http.get_json(
            WIKIDATA_API,
            params={
                "action": "wbsearchentities",
                "format": "json",
                "language": self.lang,
                "type": "item",
                "search": query,
            },
        )
        results = data.get("search", [])
        if not results:
            raise ValueError(f"No Wikidata entity found for '{query}'")
        return results[0]["id"]

    def resolve_category(self, category: str, limit: int = 200) -> List[str]:
        titles: List[str] = []
        cont = None
        while True:
            params = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": f"Category:{category}",
                "cmlimit": min(50, limit),
                "format": "json",
                "cmnamespace": 0,
            }
            if cont:
                params.update(cont)
            data = self.http.get_json(WIKI_API.format(lang=self.lang), params=params)
            members = data.get("query", {}).get("categorymembers", [])
            for member in members:
                titles.append(member["title"])
                if len(titles) >= limit:
                    return titles
            cont = data.get("continue")
            if not cont:
                return titles

    def resolve_seed(self, seed: str) -> str:
        if seed.startswith("Q"):
            return seed
        try:
            return self.resolve_title(seed)
        except ValueError:
            return self.resolve_search(seed)

    def resolve_seeds(self, seeds: Iterable[str]) -> List[str]:
        return [self.resolve_seed(seed) for seed in seeds]


__all__ = ["Resolver"]
