"""CIA World Leaders integration and government tagging utilities."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from .http import HTTPClient, HTTPError
from .utils import logger

CIA_WORLD_LEADERS_URL = "https://data.opensanctions.org/datasets/latest/us_cia_world_leaders/entities.ftm.json"
LEGACY_CIA_URL = "https://www.cia.gov/resources/world-leaders/page-data/index/page-data.json"

GOVERNMENT_KEYWORDS = (
    "minister",
    "prime minister",
    "president",
    "secretary",
    "governor",
    "chancellor",
    "king",
    "queen",
    "emir",
    "sultan",
    "speaker",
    "cabinet",
    "council",
    "parliament",
    "vice president",
    "deputy",
    "head of government",
    "chief of state",
)

MILITARY_KEYWORDS = (
    "defense",
    "armed forces",
    "military",
    "army",
    "navy",
    "air force",
    "commander",
    "general",
    "admiral",
    "marshal",
    "brigadier",
    "chief of staff",
)

BUREAUCRAT_KEYWORDS = (
    "interior",
    "finance",
    "treasury",
    "economy",
    "planning",
    "civil service",
    "intelligence",
    "security",
    "central bank",
    "bank",
    "agency",
    "authority",
    "commission",
    "administration",
    "director",
)


@dataclass(frozen=True)
class CIAOfficial:
    """Structured representation of a CIA world leaders entry."""

    country: str
    position: str
    name: str
    categories: tuple[str, ...]

    @property
    def key(self) -> tuple[str, str]:
        return (self.country, self.name)


def _normalize(text: str) -> str:
    cleaned = unicodedata.normalize("NFKD", text)
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
    cleaned = cleaned.lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _category_keys(position: str) -> Set[str]:
    pos = position.lower()
    categories: Set[str] = set()
    if any(keyword in pos for keyword in MILITARY_KEYWORDS):
        categories.add("military")
    if any(keyword in pos for keyword in BUREAUCRAT_KEYWORDS):
        categories.add("bureaucrat")
    if any(keyword in pos for keyword in GOVERNMENT_KEYWORDS) or not categories:
        categories.add("government")
    return categories


class CIAWorldLeadersClient:
    """Fetch and parse the CIA World Leaders dataset."""

    def __init__(self, http: HTTPClient, cache_path: Path | None = None) -> None:
        self.http = http
        self.cache_path = cache_path or CACHE_PATH

    def fetch(self) -> List[CIAOfficial]:
        """Fetch the CIA leadership dataset and return structured officials.

        The preferred source is the OpenSanctions mirror of the CIA roster, which
        exposes newline-delimited FollowTheMoney entities. If that endpoint fails
        or returns no entries, we fall back to the legacy CIA site structure to
        preserve functionality.
        """

        officials = self._fetch_opensanctions()
        if officials:
            return officials
        logger.info("Falling back to legacy CIA world leaders endpoint")
        return self._fetch_legacy()

    def _fetch_opensanctions(self) -> List[CIAOfficial]:
        try:
            resp = self.http.request(
                "GET",
                CIA_WORLD_LEADERS_URL,
                headers={"Accept": "application/json"},
            )
        except HTTPError as exc:  # pragma: no cover - network failures handled by caller
            logger.warning("OpenSanctions CIA World Leaders fetch failed: %s", exc)
            return []

        text = getattr(resp, "text", "")
        if not text:
            return []

        officials: List[CIAOfficial] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entity = json.loads(line)
            except json.JSONDecodeError:
                continue
            official = self._official_from_entity(entity)
            if official:
                officials.append(official)
        return officials

    def _official_from_entity(self, entity: Mapping[str, Any]) -> Optional[CIAOfficial]:
        if not isinstance(entity, Mapping):
            return None
        props = entity.get("properties")
        if not isinstance(props, Mapping):
            return None

        def _first(key: str) -> Optional[str]:
            value = props.get(key)
            if isinstance(value, list):
                for candidate in value:
                    if isinstance(candidate, str) and candidate.strip():
                        return candidate.strip()
            elif isinstance(value, str) and value.strip():
                return value.strip()
            return None

        name = _first("name") or _first("alias")
        position = _first("position") or _first("title") or _first("summary")
        country = _first("country") or _first("jurisdiction") or _first("nationality")

        if not name or not position or not country:
            return None

        categories = tuple(sorted(_category_keys(position)))
        return CIAOfficial(country=country, position=position, name=name, categories=categories)

    def _fetch_legacy(self) -> List[CIAOfficial]:
        try:
            payload = self.http.get_json(
                LEGACY_CIA_URL,
                headers={"Accept": "application/json"},
            )
        except HTTPError as exc:  # pragma: no cover - network failures handled by caller
            logger.warning("Legacy CIA World Leaders fetch failed: %s", exc)
            return []

        countries = self._extract_countries(payload)
        officials: List[CIAOfficial] = []
        for country in countries:
            country_name = country.get("name") or country.get("country") or country.get("countryName")
            if not country_name:
                continue
            for entry in self._extract_people(country):
                name = entry.get("name") or entry.get("person") or entry.get("leader")
                position = entry.get("title") or entry.get("position") or entry.get("role")
                if not name or not position:
                    continue
                categories = tuple(sorted(_category_keys(position)))
                officials.append(
                    CIAOfficial(
                        country=country_name.strip(),
                        position=position.strip(),
                        name=name.strip(),
                        categories=categories,
                    )
                )
        return officials

    def _extract_countries(self, payload: Mapping[str, object]) -> List[Mapping[str, object]]:
        """Walk nested payload to find the list of countries."""

        queue: List[object] = [payload]
        while queue:
            current = queue.pop(0)
            if isinstance(current, Mapping):
                if "countries" in current and isinstance(current["countries"], list):
                    countries = [c for c in current["countries"] if isinstance(c, Mapping)]
                    if countries:
                        return countries
                queue.extend(current.values())
            elif isinstance(current, list):
                queue.extend(current)
        return []

    def _extract_people(self, country: Mapping[str, object]) -> Iterable[Mapping[str, str]]:
        """Yield person dictionaries from a country entry regardless of nesting."""

        queue: List[object] = [country]
        while queue:
            current = queue.pop(0)
            if isinstance(current, Mapping):
                keys = {k.lower() for k in current.keys()}
                if {"name", "title"}.issubset(keys) or {"name", "position"}.issubset(keys):
                    yield {k: str(v) for k, v in current.items() if isinstance(v, (str, int))}
                else:
                    queue.extend(current.values())
            elif isinstance(current, list):
                queue.extend(current)


class GovernmentIndex:
    """Index CIA officials for quick lookups and graph annotations."""

    def __init__(self, officials: Sequence[CIAOfficial]) -> None:
        self._officials = list(officials)
        self._by_country: Dict[str, List[CIAOfficial]] = {}
        self._by_name: Dict[str, List[CIAOfficial]] = {}
        self._by_qid: Dict[str, List[CIAOfficial]] = {}
        self._resolution_cache: Dict[tuple[str, str], Optional[str]] = {}
        self._country_lookup: Dict[str, str] = {}
        for official in self._officials:
            self._by_country.setdefault(official.country, []).append(official)
            name_key = _normalize(official.name)
            self._by_name.setdefault(name_key, []).append(official)
            for key in self._country_keys(official.country):
                self._country_lookup.setdefault(key, official.country)

    @staticmethod
    def _country_keys(country: str) -> Set[str]:
        base = _normalize(country)
        keys = {base}
        prefixes = (
            "the ",
            "republic of ",
            "kingdom of ",
            "state of ",
            "federal republic of ",
            "people s republic of ",
        )
        for prefix in prefixes:
            if base.startswith(prefix):
                keys.add(base[len(prefix) :])
        return {k for k in keys if k}

    def officials_by_country(self, country: str) -> List[CIAOfficial]:
        return self._by_country.get(country, [])

    def countries_for_labels(self, labels: Iterable[str]) -> Set[str]:
        matches: Set[str] = set()
        for label in labels:
            if not label:
                continue
            key = _normalize(label)
            if key in self._country_lookup:
                matches.add(self._country_lookup[key])
                continue
            for candidate_key, country in self._country_lookup.items():
                if key.endswith(candidate_key) or candidate_key.endswith(key):
                    matches.add(country)
        return matches

    def lookup_by_name(self, name: str) -> List[CIAOfficial]:
        return self._by_name.get(_normalize(name), [])

    def record_qid(self, qid: str, official: CIAOfficial) -> None:
        self._by_qid.setdefault(qid, []).append(official)

    def associate_qid(self, qid: str, label: Optional[str]) -> None:
        if not label:
            return
        for official in self.lookup_by_name(label):
            self.record_qid(qid, official)

    def officials_for_qid(self, qid: str, label: Optional[str] = None) -> List[CIAOfficial]:
        officials = list(self._by_qid.get(qid, []))
        if not officials and label:
            officials = self.lookup_by_name(label)
        return officials

    def resolve_official(self, official: CIAOfficial, resolver) -> Optional[str]:
        cache_key = official.key
        if cache_key in self._resolution_cache:
            return self._resolution_cache[cache_key]
        try:
            qid = resolver.resolve_seed(official.name)
        except ValueError:
            qid = None
        if qid:
            self.record_qid(qid, official)
        self._resolution_cache[cache_key] = qid
        return qid

    def annotate_graph_node(self, graph, node_id: str, label: Optional[str]) -> None:
        officials = self.officials_for_qid(node_id, label)
        if not officials:
            return
        categories: Set[str] = set()
        roles: Set[str] = set()
        countries: Set[str] = set()
        for official in officials:
            categories.update(official.categories)
            countries.add(official.country)
            roles.add(f"{official.country}: {official.position}")
        try:
            node_attrs = graph.nodes[node_id]  # type: ignore[index]
        except TypeError:
            node_attrs = getattr(graph, "_nodes", {}).setdefault(node_id, {})
        existing_layers = set(node_attrs.get("layers", []))
        node_attrs["layers"] = sorted(existing_layers | categories)
        existing_roles = set(node_attrs.get("government_roles", []))
        node_attrs["government_roles"] = sorted(existing_roles | roles)
        existing_countries = set(node_attrs.get("government_countries", []))
        node_attrs["government_countries"] = sorted(existing_countries | countries)


__all__ = [
    "CIAWorldLeadersClient",
    "CIAOfficial",
    "GovernmentIndex",
    "CIA_WORLD_LEADERS_URL",
    "LEGACY_CIA_URL",
]
