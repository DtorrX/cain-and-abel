"""Utilities to interact with Wikidata's SPARQL endpoint."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .http import HTTPClient
from .schemas import Edge, Node
from .utils import logger, timestamp

WDQS_ENDPOINT = "https://query.wikidata.org/sparql"

FAMILY_PROPS = {
    "P22": "father",
    "P25": "mother",
    "P26": "spouse",
    "P40": "child",
    "P3373": "sibling",
    "P1038": "relative",
    "P451": "partner",
}

POLITICAL_PROPS = {
    "P39": "position_held",
    "P102": "member_of_party",
    "P463": "member_of",
    "P108": "employer",
    "P69": "educated_at",
    "P6": "head_of_government",
    "P35": "head_of_state",
    "P488": "chairperson",
    "P2388": "officeholder",
}

SECURITY_PROPS = {
    "P241": "military_branch",
    "P410": "military_rank",
    "P463": "member_of",
    "P1027": "conferred_by",
    "P1416": "affiliation",
    "P797": "military_service",
    "P611": "religious_order",
    "P710": "participant",
}

CORPORATE_PROPS = {
    "P127": "owned_by",
    "P355": "subsidiary",
    "P749": "parent",
    "P1056": "product_or_service",
    "P112": "founded_by",
    "P1037": "director_manager",
    "P1444": "destination_point",
}

ALL_PROPERTIES = {**FAMILY_PROPS, **POLITICAL_PROPS, **SECURITY_PROPS, **CORPORATE_PROPS}

BATCH_RELATIONS_TEMPLATE = """
SELECT ?src ?p ?dst ?srcLabel ?dstLabel WHERE {
  VALUES (?src) { %VALUES% }
  VALUES ?p { %PROPS% }
  OPTIONAL { ?src ?p ?dst . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,ar,fr". }
}
"""

LABEL_TEMPLATE = """
SELECT ?entity ?entityLabel ?entityDescription WHERE {
  VALUES (?entity) { %VALUES% }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,ar,fr". }
}
"""


class WikidataClient:
    def __init__(self, http: HTTPClient) -> None:
        self.http = http

    def _run_query(self, query: str) -> Dict:
        logger.debug("Executing SPARQL query: %s", query)
        return self.http.get_json(
            WDQS_ENDPOINT,
            params={"query": query, "format": "json"},
            headers={"Accept": "application/sparql-results+json"},
        )

    def fetch_labels(self, qids: Iterable[str]) -> Dict[str, Dict[str, str]]:
        values = " ".join(f"(wd:{qid})" for qid in set(qids))
        if not values:
            return {}
        query = LABEL_TEMPLATE.replace("%VALUES%", values)
        data = self._run_query(query)
        result: Dict[str, Dict[str, str]] = {}
        for binding in data.get("results", {}).get("bindings", []):
            qid = binding["entity"]["value"].split("/")[-1]
            result[qid] = {
                "label": binding.get("entityLabel", {}).get("value", qid),
                "description": binding.get("entityDescription", {}).get("value"),
            }
        return result

    def fetch_relations(
        self,
        qids: List[str],
        include_family: bool = True,
        include_political: bool = True,
        include_security: bool = False,
        include_corporate: bool = False,
    ) -> List[Edge]:
        props = []
        if include_family:
            props.extend(FAMILY_PROPS.keys())
        if include_political:
            props.extend(POLITICAL_PROPS.keys())
        if include_security:
            props.extend(SECURITY_PROPS.keys())
        if include_corporate:
            props.extend(CORPORATE_PROPS.keys())
        if not props:
            return []
        values = " ".join(f"(wd:{qid})" for qid in qids)
        prop_values = " ".join(f"wdt:{pid}" for pid in props)
        query = (
            BATCH_RELATIONS_TEMPLATE
            .replace("%VALUES%", values)
            .replace("%PROPS%", prop_values)
        )
        data = self._run_query(query)
        edges: List[Edge] = []
        for binding in data.get("results", {}).get("bindings", []):
            if "dst" not in binding:
                continue
            src = binding["src"]["value"].split("/")[-1]
            dst = binding["dst"]["value"].split("/")[-1]
            pid = binding["p"]["value"].split("/")[-1]
            relation = ALL_PROPERTIES.get(pid, pid)
            edges.append(
                Edge(
                    source=src,
                    target=dst,
                    relation=relation,
                    pid=pid,
                    source_system="wikidata",
                    evidence_url=f"https://www.wikidata.org/wiki/{src}",
                    retrieved_at=timestamp(),
                    data={
                        "src_label": binding.get("srcLabel", {}).get("value"),
                        "dst_label": binding.get("dstLabel", {}).get("value"),
                    },
                )
            )
        return edges


__all__ = [
    "WikidataClient",
    "FAMILY_PROPS",
    "POLITICAL_PROPS",
    "SECURITY_PROPS",
    "CORPORATE_PROPS",
    "ALL_PROPERTIES",
    "BATCH_RELATIONS_TEMPLATE",
]
