"""Command line interface for wikinet."""

from __future__ import annotations

import argparse
import json
import os
from typing import Iterable, List, Sequence

import networkx as nx

from .cache import CacheManager
from .cia import CIAWorldLeadersClient, GovernmentIndex
from .export import export_graph
from .graph import GraphBuilder, load_graph
from .http import HTTPClient
from .resolver import Resolver
from .utils import RateLimiter, console, logger, set_log_level
from .wikidata import WikidataClient
from .wikipedia import WikipediaClient
from . import api as wikinet_api


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wikinet", description="Wikidata/Wikipedia network crawler")
    sub = parser.add_subparsers(dest="command", required=True)

    crawl = sub.add_parser("crawl", help="Crawl Wikidata relations")
    crawl.add_argument("--seed", action="append", help="Seed page title or Q-ID", dest="seeds")
    crawl.add_argument("--category", action="append", help="Wikipedia category seed (without prefix)")
    crawl.add_argument("--qid", action="append", help="Direct Wikidata Q-ID seed")
    crawl.add_argument("--lang", default="en", help="Wikipedia language (default: en)")
    crawl.add_argument("--max-depth", type=int, default=1)
    crawl.add_argument("--max-nodes", type=int)
    crawl.add_argument("--max-edges", type=int)
    crawl.add_argument(
        "--mode",
        default="family,political",
        help="family, political, security, corporate, or full (comma-separated)",
    )
    crawl.add_argument("--rate", type=float, default=5.0, help="Max requests per second")
    crawl.add_argument("--out", required=True, help="Output directory")
    crawl.add_argument("--cache-dir", help="Cache directory (default: .wikinet-cache)")
    crawl.add_argument("--resume", action="store_true", help="Merge with existing output")
    crawl.add_argument(
        "--log-level",
        default=os.getenv("WIKINET_LOG_LEVEL", "INFO"),
        help="Python logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    crawl.add_argument(
        "--report-path",
        help="Optional JSON file to store crawl diagnostics (relations, depth histogram, etc.)",
    )

    validate = sub.add_parser("validate", help="Validate exported graph")
    validate.add_argument("path", help="Output directory to validate")

    enrich = sub.add_parser("enrich", help="Enrich an exported graph with analytics")
    enrich.add_argument("out_dir", help="Directory containing nodes.json and edges.json")
    enrich.add_argument("--taxonomy", help="Optional taxonomy JSON for role mapping")

    return parser


def _collect_seeds(args: argparse.Namespace, resolver: Resolver) -> List[str]:
    seeds: List[str] = []
    if args.seeds:
        seeds.extend(args.seeds)
    if args.qid:
        seeds.extend(args.qid)
    if args.category:
        for category in args.category:
            console.log(f"Resolving category {category}")
            seeds.extend(resolver.resolve_category(category))
    if not seeds:
        raise SystemExit("Provide --seed, --qid, or --category")
    return seeds


def _parse_mode(mode: str) -> dict[str, bool]:
    parts = {m.strip().lower() for m in mode.split(",") if m.strip()}
    if not parts:
        parts = {"family", "political"}
    if "full" in parts:
        parts = {"family", "political", "security", "corporate"}
    return {
        "include_family": "family" in parts,
        "include_political": "political" in parts,
        "include_security": "security" in parts,
        "include_corporate": "corporate" in parts,
    }


def run_crawl(args: argparse.Namespace) -> None:
    set_log_level(args.log_level)
    cache = CacheManager(args.cache_dir)
    rate_limiter = RateLimiter(rate=args.rate)
    http = HTTPClient(cache=cache, rate_limiter=rate_limiter)
    resolver = Resolver(http, lang=args.lang)
    wikidata_client = WikidataClient(http)
    wikipedia_client = WikipediaClient(http, lang=args.lang)
    modes = _parse_mode(args.mode)

    government_index: GovernmentIndex | None = None
    cia_client = CIAWorldLeadersClient(http)
    officials = cia_client.fetch()
    if officials:
        government_index = GovernmentIndex(officials)
        console.log(f"Loaded {len(officials)} CIA world leaders entries")
    else:
        console.log("[yellow]CIA world leaders dataset unavailable[/yellow]")

    builder = GraphBuilder(
        resolver,
        wikidata_client,
        wikipedia_client,
        include_family=modes["include_family"],
        include_political=modes["include_political"],
        include_security=modes["include_security"],
        include_corporate=modes["include_corporate"],
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
        max_edges=args.max_edges,
        government_index=government_index,
    )

    seeds = _collect_seeds(args, resolver)
    result = builder.crawl(seeds)
    graph = result.graph
    if args.resume:
        existing = load_graph(args.out)
        graph = nx.compose(existing, graph)
    paths = export_graph(graph, args.out)
    console.log(f"Export completed with {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges")
    console.log(paths)
    result.stats.total_nodes = graph.number_of_nodes()
    result.stats.total_edges = graph.number_of_edges()
    result.stats.log()
    if args.report_path:
        with open(args.report_path, "w", encoding="utf-8") as fh:
            json.dump(result.stats.to_dict(), fh, indent=2)
        console.log(f"Diagnostics report saved to {args.report_path}")


def run_validate(path: str) -> None:
    nodes_path = os.path.join(path, "nodes.json")
    edges_path = os.path.join(path, "edges.json")
    if not os.path.exists(nodes_path) or not os.path.exists(edges_path):
        raise SystemExit("Missing nodes.json or edges.json")
    with open(nodes_path, "r", encoding="utf-8") as fh:
        nodes = json.load(fh)
    with open(edges_path, "r", encoding="utf-8") as fh:
        edges = json.load(fh)
    node_ids = {node["id"] for node in nodes}
    missing = [edge for edge in edges if edge["source"] not in node_ids or edge["target"] not in node_ids]
    console.log(f"Nodes: {len(nodes)} Edges: {len(edges)}")
    if missing:
        raise SystemExit(f"Edges reference missing nodes: {missing[:3]}")
    console.log("Validation OK")


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "crawl":
        run_crawl(args)
    elif args.command == "validate":
        run_validate(args.path)
    elif args.command == "enrich":
        wikinet_api.run_enrichment(args.out_dir, args.taxonomy)
    else:  # pragma: no cover - defensive
        parser.print_help()


if __name__ == "__main__":  # pragma: no cover
    main()
