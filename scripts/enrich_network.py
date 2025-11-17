"""Enrich raw Wikidata network JSON with analytics for visualization.

This script computes graph metrics (degrees, centrality, power score),
infers categorical attributes (role, country, communities), and annotates
edges with semantic types/layers. Output is written to enriched JSON files
consumed by the D3 visualization. Use ``--taxonomy`` to override the
keyword heuristics so the same enrichment pipeline works for royal families,
Israeli defense firms, political parties, or any other sector.

Run:
    python scripts/enrich_network.py \
        --nodes out/uae_sample/nodes.json \
        --edges out/uae_sample/edges.json \
        --out-nodes out/uae_sample/enriched_nodes.json \
        --out-edges out/uae_sample/enriched_edges.json
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import networkx as nx
from networkx.algorithms import community

# ---------------------------------------------------------------------------
# Configuration constants — tweak here to adjust scoring/heuristics
# ---------------------------------------------------------------------------

ROLE_KEYWORDS: Dict[str, Sequence[str]] = {
    "monarch": ("monarch", "sovereign", "king", "queen", "ruler", "emir", "sheikh", "sultan"),
    "royal_family": ("prince", "princess", "royal", "emirati royal", "al nahyan", "al maktoum"),
    "politician": ("politician", "prime minister", "minister", "ruler of", "governor", "president", "member of knesset"),
    "business_elite": ("business", "investor", "ceo", "entrepreneur", "billionaire", "financier"),
    "military": ("general", "army", "commander", "defense", "military", "idf"),
    "cleric": ("imam", "cleric", "sheikh", "mufti", "religious"),
    "bureaucrat": ("civil servant", "bureaucrat", "official", "administrator"),
    "defense_industry": ("defense", "aerospace", "arms", "missile", "intelligence", "contractor", "security"),
}

COUNTRY_KEYWORDS: Dict[str, Sequence[str]] = {
    "United Arab Emirates": ("emirati", "uae", "abu dhabi", "dubai"),
    "Saudi Arabia": ("saudi", "saudi arabia"),
    "Qatar": ("qatari", "qatar"),
    "Bahrain": ("bahrain", "bahraini"),
    "Kuwait": ("kuwait", "kuwaiti"),
    "Israel": ("israel", "israeli", "idf", "tel aviv", "ra'anana"),
    "United States": ("usa", "u.s.", "united states", "american", "washington"),
    "United Kingdom": ("uk", "british", "united kingdom", "london"),
}

EDGE_TYPE_BY_PID: Dict[str, str] = {
    "P22": "family",  # father
    "P25": "family",  # mother
    "P26": "marriage",  # spouse
    "P40": "family",  # child
    "P1038": "family",  # relative
    "P3373": "family",  # sibling
    "P1037": "business",  # main employer
    "P463": "ngo",  # member of
    "P108": "business",  # employer
    "P39": "political",  # position held
    "P102": "political",  # party
    "P488": "corporate_governance",  # chairperson
    "P355": "corporate_structure",  # subsidiary
    "P749": "corporate_structure",  # parent organization
    "P127": "ownership",  # owned by
    "P2388": "political",  # officeholder
}

EDGE_TYPE_BY_RELATION: Dict[str, str] = {
    "father": "family",
    "mother": "family",
    "relative": "family",
    "sibling": "family",
    "spouse": "marriage",
    "business": "business",
    "employer": "business",
    "member": "ngo",
    "position": "political",
    "subsidiary": "corporate_structure",
    "parent": "corporate_structure",
    "chair": "corporate_governance",
    "owner": "ownership",
}

EDGE_WEIGHT_BY_TYPE: Dict[str, int] = {
    "family": 4,
    "marriage": 5,
    "business": 3,
    "political": 3,
    "ngo": 2,
    "corporate_structure": 3,
    "corporate_governance": 3,
    "ownership": 4,
    "unknown": 1,
}

LAYER_BY_TYPE: Dict[str, str] = {
    "family": "royal",
    "marriage": "royal",
    "business": "business",
    "political": "political",
    "ngo": "ngo",
    "corporate_structure": "business",
    "corporate_governance": "business",
    "ownership": "business",
    "unknown": "other",
}

DEFAULT_ROLE = "other"
DEFAULT_COUNTRY = "Unknown"
DEFAULT_EDGE_TYPE = "unknown"


@dataclass
class TimeRange:
    start: Optional[int] = None
    end: Optional[int] = None


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _gather_strings(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    for val in values:
        if isinstance(val, str):
            out.append(val)
        elif isinstance(val, (list, tuple, set)):
            out.extend(_gather_strings(val))
    return out


def infer_role(attrs: Dict[str, Any]) -> str:
    """Best-effort classification of a node's role using keyword rules."""

    candidates = []
    for key in ("role", "roles", "occupation", "occupations", "position", "positions", "description", "categories"):
        value = attrs.get(key)
        if value:
            candidates.extend(_gather_strings([value]))

    text = " ".join(candidates).lower()
    for role, keywords in ROLE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return role
    if "royal" in text or "sheikh" in text:
        return "royal_family"
    return DEFAULT_ROLE


def infer_country(attrs: Dict[str, Any]) -> str:
    candidates: List[str] = []
    for key in ("country", "countries", "citizenship", "nationality", "country_of_citizenship", "description"):
        value = attrs.get(key)
        if value:
            candidates.extend(_gather_strings([value]))
    text = " ".join(candidates).lower()
    for country, keywords in COUNTRY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return country
    return attrs.get("country", DEFAULT_COUNTRY)


def parse_year(value: Any) -> Optional[int]:
    if value in (None, "", "null"):
        return None
    if isinstance(value, (int, float)):
        if math.isnan(value):
            return None
        return int(value)
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) >= 3:
            return int(digits[:4])
    return None


def infer_time_range(attrs: Dict[str, Any]) -> TimeRange:
    start = None
    end = None
    for key in ("start_time", "start", "from", "start_year", "inception"):
        start = parse_year(attrs.get(key))
        if start:
            break
    for key in ("end_time", "end", "to", "end_year", "dissolved"):
        end = parse_year(attrs.get(key))
        if end:
            break
    return TimeRange(start=start, end=end)


def infer_edge_type(attrs: Dict[str, Any]) -> str:
    pid = attrs.get("pid") or attrs.get("property")
    if pid and pid in EDGE_TYPE_BY_PID:
        return EDGE_TYPE_BY_PID[pid]
    relation = str(attrs.get("relation") or attrs.get("type") or attrs.get("label") or "").lower()
    for key, edge_type in EDGE_TYPE_BY_RELATION.items():
        if key in relation:
            return edge_type
    return DEFAULT_EDGE_TYPE


def infer_edge_weight(edge_type: str, attrs: Dict[str, Any]) -> int:
    if "weight" in attrs and isinstance(attrs["weight"], (int, float)):
        return int(attrs["weight"])
    base = EDGE_WEIGHT_BY_TYPE.get(edge_type, EDGE_WEIGHT_BY_TYPE[DEFAULT_EDGE_TYPE])
    if attrs.get("confidence"):
        try:
            conf = float(attrs["confidence"])
            return max(1, min(5, int(round(base * conf))))
        except (ValueError, TypeError):
            pass
    return base


def infer_layer(edge_type: str, attrs: Dict[str, Any]) -> str:
    if "layer" in attrs and attrs["layer"]:
        return str(attrs["layer"])
    return LAYER_BY_TYPE.get(edge_type, LAYER_BY_TYPE[DEFAULT_EDGE_TYPE])


def normalize(values: Dict[str, float]) -> Dict[str, float]:
    if not values:
        return {}
    min_v = min(values.values())
    max_v = max(values.values())
    if math.isclose(max_v, min_v):
        return {k: 0.0 for k in values}
    return {k: (v - min_v) / (max_v - min_v) for k, v in values.items()}


def compute_power_score(
    deg_norm: Dict[str, float],
    bet_norm: Dict[str, float],
    role_counts: Dict[str, float],
    dist_norm: Dict[str, float],
) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for node in deg_norm:
        role_component = role_counts.get(node, 0.0)
        distance_component = 1.0 - dist_norm.get(node, 0.0)
        scores[node] = (
            0.45 * deg_norm.get(node, 0.0)
            + 0.35 * bet_norm.get(node, 0.0)
            + 0.10 * role_component
            + 0.10 * distance_component
        )
    return scores


def compute_distances_to_monarchs(G: nx.Graph, monarch_nodes: Sequence[str]) -> Dict[str, float]:
    if not monarch_nodes:
        return {n: 0.0 for n in G.nodes}
    undirected = G.to_undirected()
    dist: Dict[str, float] = {}
    for source in monarch_nodes:
        lengths = nx.single_source_shortest_path_length(undirected, source)
        for node, length in lengths.items():
            if node not in dist or length < dist[node]:
                dist[node] = float(length)
    max_dist = max(dist.values()) if dist else 1.0
    return {n: dist.get(n, max_dist) for n in G.nodes}


# ---------------------------------------------------------------------------
# Main enrichment routine
# ---------------------------------------------------------------------------


def enrich(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    graph = nx.MultiDiGraph()

    for node in nodes:
        node_id = str(node.get("id"))
        if not node_id:
            continue
        graph.add_node(node_id, **node)

    for edge in edges:
        src = str(edge.get("source") or edge.get("sourceId") or "")
        dst = str(edge.get("target") or edge.get("targetId") or "")
        if not (src and dst):
            continue
        graph.add_edge(src, dst, **edge)

    # Degrees (directed + undirected views)
    deg = dict(graph.degree())
    in_deg = dict(graph.in_degree())
    out_deg = dict(graph.out_degree())

    # Betweenness centrality (sample if large)
    node_count = graph.number_of_nodes()
    undirected_view = graph.to_undirected()
    if node_count > 1500:
        bet = nx.betweenness_centrality(undirected_view, k=min(500, node_count), seed=42)
    else:
        bet = nx.betweenness_centrality(undirected_view)

    deg_norm = normalize(deg)
    bet_norm = normalize(bet)

    # Role + country inference, track role counts for scoring
    role_counts: Dict[str, float] = {}
    roles: Dict[str, str] = {}
    countries: Dict[str, str] = {}

    for node_id, attrs in list(graph.nodes(data=True)):
        role = attrs.get("role") or infer_role(attrs)
        country = attrs.get("country") or infer_country(attrs)
        roles[node_id] = role
        countries[node_id] = country
        role_counts[node_id] = 1.0 if role != DEFAULT_ROLE else 0.3
        graph.nodes[node_id]["role"] = role
        graph.nodes[node_id]["country"] = country

    monarch_nodes = [nid for nid, role in roles.items() if role == "monarch"]
    if not monarch_nodes and deg:
        monarch_nodes = [max(deg, key=deg.get)]
    dist_raw = compute_distances_to_monarchs(graph, monarch_nodes)
    dist_norm = normalize(dist_raw)

    # Role count uses optional list field for additional boost
    for node_id, attrs in list(graph.nodes(data=True)):
        extra_roles = attrs.get("roles")
        if isinstance(extra_roles, Sequence) and not isinstance(extra_roles, str):
            role_counts[node_id] = max(role_counts.get(node_id, 0.0), min(1.0, len(extra_roles) / 3))

    scores = compute_power_score(deg_norm, bet_norm, role_counts, dist_norm)

    # Community detection (Louvain -> fallback greedy modularity)
    community_id: Dict[str, int] = {}
    try:
        communities = community.louvain_communities(undirected_view, seed=42)
    except Exception:
        communities = community.greedy_modularity_communities(undirected_view)
    for idx, members in enumerate(communities):
        for member in members:
            community_id[member] = idx

    # Assemble enriched node output
    enriched_nodes: List[Dict[str, Any]] = []
    for node_id, attrs in graph.nodes(data=True):
        node_out = dict(attrs)
        node_out["id"] = node_id
        node_out["degree"] = float(deg.get(node_id, 0))
        node_out["in_degree"] = float(in_deg.get(node_id, 0))
        node_out["out_degree"] = float(out_deg.get(node_id, 0))
        node_out["betweenness_centrality"] = float(bet.get(node_id, 0.0))
        node_out["power_score"] = round(float(scores.get(node_id, 0.0)), 6)
        node_out["community_id"] = int(community_id.get(node_id, -1))
        node_out["distance_to_monarch"] = float(dist_raw.get(node_id, 0.0))
        node_out.setdefault("role", roles.get(node_id, DEFAULT_ROLE))
        node_out.setdefault("country", countries.get(node_id, DEFAULT_COUNTRY))

        # Collate aliases for search index convenience
        aliases = set()
        for key in ("aliases", "alias", "also_known_as"):
            value = attrs.get(key)
            if isinstance(value, str):
                aliases.add(value)
            elif isinstance(value, Iterable):
                for item in value:
                    if isinstance(item, str):
                        aliases.add(item)
        node_out["aliases"] = sorted(aliases)

        enriched_nodes.append(node_out)

    # Edge enrichment
    enriched_edges: List[Dict[str, Any]] = []
    for edge_id, (src, dst, attrs) in enumerate(graph.edges(data=True)):
        edge_out = dict(attrs)
        edge_out["source"] = src
        edge_out["target"] = dst
        edge_type = infer_edge_type(attrs)
        edge_out["type"] = edge_type
        edge_out["layer"] = infer_layer(edge_type, attrs)
        edge_out["weight"] = infer_edge_weight(edge_type, attrs)
        timerange = infer_time_range(attrs)
        if timerange.start is not None:
            edge_out["start_year"] = timerange.start
        if timerange.end is not None:
            edge_out["end_year"] = timerange.end
        if "id" not in edge_out:
            edge_out["id"] = attrs.get("id") or f"e{edge_id}"
        enriched_edges.append(edge_out)

    return enriched_nodes, enriched_edges


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def apply_taxonomy_overrides(config_path: Optional[Path]) -> None:
    """Override keyword heuristics for arbitrary verticals (e.g. defense sector)."""

    if not config_path:
        return
    overrides = load_json(config_path)
    if not isinstance(overrides, dict):
        raise ValueError("Taxonomy overrides must be provided as an object/dict")

    def _normalize_mapping(value: Dict[str, Iterable[str]]) -> Dict[str, Tuple[str, ...]]:
        return {
            str(key): tuple(str(item).lower() for item in items)
            for key, items in value.items()
        }

    if "role_keywords" in overrides:
        ROLE_KEYWORDS.update(_normalize_mapping(overrides["role_keywords"]))
    if "country_keywords" in overrides:
        COUNTRY_KEYWORDS.update(_normalize_mapping(overrides["country_keywords"]))
    if "edge_type_by_pid" in overrides:
        EDGE_TYPE_BY_PID.update({str(k): str(v) for k, v in overrides["edge_type_by_pid"].items()})
    if "edge_type_by_relation" in overrides:
        EDGE_TYPE_BY_RELATION.update({str(k).lower(): str(v) for k, v in overrides["edge_type_by_relation"].items()})
    if "edge_weight_by_type" in overrides:
        EDGE_WEIGHT_BY_TYPE.update({str(k): int(v) for k, v in overrides["edge_weight_by_type"].items()})
    if "layer_by_type" in overrides:
        LAYER_BY_TYPE.update({str(k): str(v) for k, v in overrides["layer_by_type"].items()})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich Wikidata network JSON for visualization.")
    parser.add_argument("--nodes", type=Path, required=True, help="Path to nodes.json")
    parser.add_argument("--edges", type=Path, required=True, help="Path to edges.json")
    parser.add_argument("--out-nodes", type=Path, required=True, help="Destination for enriched nodes JSON")
    parser.add_argument("--out-edges", type=Path, required=True, help="Destination for enriched edges JSON")
    parser.add_argument(
        "--taxonomy",
        type=Path,
        help="Optional JSON file with overrides for role/country keywords and edge typing",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    apply_taxonomy_overrides(args.taxonomy)
    raw_nodes = load_json(args.nodes)
    raw_edges = load_json(args.edges)

    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ValueError("nodes.json and edges.json must contain lists")

    enriched_nodes, enriched_edges = enrich(raw_nodes, raw_edges)
    save_json(args.out_nodes, enriched_nodes)
    save_json(args.out_edges, enriched_edges)
    print(f"[✓] Wrote {len(enriched_nodes)} enriched nodes → {args.out_nodes}")
    print(f"[✓] Wrote {len(enriched_edges)} enriched edges → {args.out_edges}")


if __name__ == "__main__":
    main()
