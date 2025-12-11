"""High-level API helpers for wikinet."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Sequence

import networkx as nx

from .cache import CacheManager
from .cia import CIAWorldLeadersClient, GovernmentIndex
from .export import export_graph
from .graph import GraphBuilder
from .http import HTTPClient
from .resolver import Resolver
from .utils import RateLimiter, console
from .wikidata import WikidataClient
from .wikipedia import WikipediaClient
from scripts import enrich_network


def run_pipeline(
    *,
    seeds: Iterable[str],
    mode: str = "family,political",
    max_depth: int = 1,
    out_dir: str,
    use_cia: bool = True,
    cache_dir: str | None = None,
    rate: float = 5.0,
    max_nodes: int | None = None,
    max_edges: int | None = None,
    lang: str = "en",
) -> nx.MultiDiGraph:
    """End-to-end helper that mirrors ``wikinet crawl``."""

    cache = CacheManager(cache_dir)
    rate_limiter = RateLimiter(rate=rate)
    http = HTTPClient(cache=cache, rate_limiter=rate_limiter)
    resolver = Resolver(http, lang=lang)
    wikidata_client = WikidataClient(http)
    wikipedia_client = WikipediaClient(http, lang=lang)

    from .cli import _parse_mode  # lazy import to avoid cycles

    modes = _parse_mode(mode)
    government_index = None
    if use_cia:
        cia_client = CIAWorldLeadersClient(http)
        officials = cia_client.fetch()
        if officials:
            government_index = GovernmentIndex(officials)
            console.log(f"Loaded {len(officials)} CIA world leaders entries")

    builder = GraphBuilder(
        resolver,
        wikidata_client,
        wikipedia_client,
        include_family=modes["include_family"],
        include_political=modes["include_political"],
        include_security=modes["include_security"],
        include_corporate=modes["include_corporate"],
        max_depth=max_depth,
        max_nodes=max_nodes,
        max_edges=max_edges,
        government_index=government_index,
    )
    graph = builder.crawl(list(seeds)).graph
    export_graph(graph, out_dir)
    return graph


def run_enrichment(out_dir: str, taxonomy_path: str | None = None) -> None:
    nodes_path = Path(out_dir) / "nodes.json"
    edges_path = Path(out_dir) / "edges.json"
    if not nodes_path.exists() or not edges_path.exists():
        raise FileNotFoundError("Expected nodes.json and edges.json in output directory")
    taxonomy = Path(taxonomy_path) if taxonomy_path else None
    enriched_nodes, enriched_edges = enrich_network.run(nodes_path, edges_path, taxonomy)
    enrich_network.write_enriched(Path(out_dir), enriched_nodes, enriched_edges)

    with open(Path(out_dir) / "legend.json", "r", encoding="utf-8") as fh:
        legend = json.load(fh)
    legend["enriched"] = True
    with open(Path(out_dir) / "legend.json", "w", encoding="utf-8") as fh:
        json.dump(legend, fh, indent=2)


__all__ = ["run_pipeline", "run_enrichment"]
