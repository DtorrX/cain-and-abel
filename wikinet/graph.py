"""Graph construction utilities."""

from __future__ import annotations

import json
import os
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

import networkx as nx

from .cia import GovernmentIndex
from .resolver import Resolver
from .utils import console, logger
from .wikidata import WikidataClient
from .wikipedia import WikipediaClient


@dataclass
class CrawlStats:
    """Diagnostics collected during a crawl run for debugging/QA."""

    seed_qids: List[str]
    expanded_nodes: int = 0
    relation_counts: Counter[str] = field(default_factory=Counter)
    depth_histogram: Counter[int] = field(default_factory=Counter)
    infobox_edges: int = 0
    warnings: List[str] = field(default_factory=list)
    total_nodes: int = 0
    total_edges: int = 0

    def to_dict(self) -> Dict[str, object]:
        return {
            "seed_qids": self.seed_qids,
            "expanded_nodes": self.expanded_nodes,
            "relation_counts": dict(self.relation_counts),
            "depth_histogram": dict(self.depth_histogram),
            "infobox_edges": self.infobox_edges,
            "warnings": list(self.warnings),
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
        }

    def log(self) -> None:
        """Pretty-print a concise run summary to the console."""

        console.log(
            "Run summary",
            {
                "seeds": len(self.seed_qids),
                "expanded": self.expanded_nodes,
                "depths": dict(self.depth_histogram),
                "edges": self.total_edges,
            },
        )
        if self.relation_counts:
            console.log("Relations", dict(sorted(self.relation_counts.items())))
        if self.infobox_edges:
            console.log(f"Infobox fallback edges: {self.infobox_edges}")
        for warning in self.warnings:
            console.log(f"[yellow]{warning}[/yellow]")


@dataclass
class CrawlResult:
    """Return value for :meth:`GraphBuilder.crawl`. Holds graph + stats."""

    graph: nx.MultiDiGraph
    stats: CrawlStats


class GraphBuilder:
    def __init__(
        self,
        resolver: Resolver,
        wikidata: WikidataClient,
        wikipedia: WikipediaClient,
        *,
        include_family: bool = True,
        include_political: bool = True,
        max_depth: int = 1,
        max_nodes: Optional[int] = None,
        max_edges: Optional[int] = None,
        government_index: GovernmentIndex | None = None,
    ) -> None:
        self.resolver = resolver
        self.wikidata = wikidata
        self.wikipedia = wikipedia
        self.include_family = include_family
        self.include_political = include_political
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.max_edges = max_edges
        self.government_index = government_index

    def _should_continue(self, graph: nx.MultiDiGraph) -> bool:
        if self.max_nodes and graph.number_of_nodes() >= self.max_nodes:
            return False
        if self.max_edges and graph.number_of_edges() >= self.max_edges:
            return False
        return True

    def _augment_with_government_seeds(self, qids: List[str]) -> List[str]:
        assert self.government_index is not None
        labels = self.wikidata.fetch_labels(qids)
        for node_id, data in labels.items():
            self.government_index.associate_qid(node_id, data.get("label"))
        countries = self.government_index.countries_for_labels(
            data.get("label")
            for data in labels.values()
            if data.get("label")
        )
        augmented: List[str] = list(dict.fromkeys(qids))
        for country in countries:
            for official in self.government_index.officials_by_country(country):
                qid = self.government_index.resolve_official(official, self.resolver)
                if qid and qid not in augmented:
                    augmented.append(qid)
        return augmented

    def crawl(self, seeds: Iterable[str]) -> CrawlResult:
        qids = self.resolver.resolve_seeds(seeds)
        if self.government_index:
            qids = self._augment_with_government_seeds(qids)
        graph = nx.MultiDiGraph()
        queue: deque[Tuple[str, int]] = deque((qid, 0) for qid in qids)
        visited: Set[str] = set()
        stats = CrawlStats(seed_qids=list(qids))

        while queue:
            qid, depth = queue.popleft()
            if qid in visited:
                continue
            visited.add(qid)
            if depth > self.max_depth:
                continue
            if not self._should_continue(graph):
                break
            console.log(f"Expanding {qid} at depth {depth}")
            stats.expanded_nodes += 1
            stats.depth_histogram[depth] += 1
            edges = self.wikidata.fetch_relations([qid], self.include_family, self.include_political)
            neighbor_ids = {edge.target for edge in edges} | {edge.source for edge in edges}
            labels = self.wikidata.fetch_labels(neighbor_ids | {qid})
            if self.government_index:
                for node_id in neighbor_ids | {qid}:
                    label = labels.get(node_id, {}).get("label")
                    self.government_index.associate_qid(node_id, label)
            for node_id in neighbor_ids | {qid}:
                data = labels.get(node_id, {})
                graph.add_node(
                    node_id,
                    label=data.get("label", node_id),
                    description=data.get("description"),
                )
                if self.government_index:
                    self.government_index.annotate_graph_node(
                        graph,
                        node_id,
                        data.get("label"),
                    )
            for edge in edges:
                stats.relation_counts[edge.relation] += 1
                graph.add_edge(
                    edge.source,
                    edge.target,
                    **edge.dict(),
                )
                if self.max_edges and graph.number_of_edges() >= self.max_edges:
                    break
            if self.include_family:
                # Infobox fallback for seeds without edges
                try:
                    title = labels.get(qid, {}).get("label", qid)
                    info_edges = self.wikipedia.extract_edges(title)
                    for relation, payload in info_edges.items():
                        target_label = payload["value"]
                        temp_id = f"{qid}:{relation}:{target_label}"[:64]
                        graph.add_node(temp_id, label=target_label, description="infobox placeholder")
                        graph.add_edge(
                            qid,
                            temp_id,
                            relation=relation,
                            pid=relation,
                            source_system=payload["source_system"],
                            evidence_url=payload["evidence_url"],
                            retrieved_at=payload["retrieved_at"],
                            data={"note": "infobox"},
                        )
                        stats.infobox_edges += 1
                except Exception as exc:
                    warning = f"Infobox fallback failed for {qid}: {exc}"
                    logger.debug(warning)
                    stats.warnings.append(warning)
            if depth < self.max_depth:
                for edge in edges:
                    if edge.target not in visited and self._should_continue(graph):
                        queue.append((edge.target, depth + 1))
        stats.total_nodes = graph.number_of_nodes()
        stats.total_edges = graph.number_of_edges()
        return CrawlResult(graph=graph, stats=stats)


def load_graph(path: str) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    nodes_path = os.path.join(path, "nodes.json")
    edges_path = os.path.join(path, "edges.json")
    if os.path.exists(nodes_path):
        with open(nodes_path, "r", encoding="utf-8") as fh:
            for node in json.load(fh):
                graph.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    if os.path.exists(edges_path):
        with open(edges_path, "r", encoding="utf-8") as fh:
            for edge in json.load(fh):
                u = edge.pop("u", edge.pop("source", None))
                v = edge.pop("v", edge.pop("target", None))
                if u and v:
                    graph.add_edge(u, v, **edge)
    return graph


__all__ = ["GraphBuilder", "load_graph", "CrawlResult", "CrawlStats"]
