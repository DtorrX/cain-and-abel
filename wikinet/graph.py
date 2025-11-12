"""Graph construction utilities."""

from __future__ import annotations

import json
import os
from collections import deque
from typing import Iterable, Optional, Set, Tuple

import networkx as nx

from .resolver import Resolver
from .utils import console, logger
from .wikidata import WikidataClient
from .wikipedia import WikipediaClient


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
    ) -> None:
        self.resolver = resolver
        self.wikidata = wikidata
        self.wikipedia = wikipedia
        self.include_family = include_family
        self.include_political = include_political
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.max_edges = max_edges

    def _should_continue(self, graph: nx.MultiDiGraph) -> bool:
        if self.max_nodes and graph.number_of_nodes() >= self.max_nodes:
            return False
        if self.max_edges and graph.number_of_edges() >= self.max_edges:
            return False
        return True

    def crawl(self, seeds: Iterable[str]) -> nx.MultiDiGraph:
        qids = self.resolver.resolve_seeds(seeds)
        graph = nx.MultiDiGraph()
        queue: deque[Tuple[str, int]] = deque((qid, 0) for qid in qids)
        visited: Set[str] = set()

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
            edges = self.wikidata.fetch_relations([qid], self.include_family, self.include_political)
            neighbor_ids = {edge.target for edge in edges} | {edge.source for edge in edges}
            labels = self.wikidata.fetch_labels(neighbor_ids | {qid})
            for node_id in neighbor_ids | {qid}:
                data = labels.get(node_id, {})
                graph.add_node(
                    node_id,
                    label=data.get("label", node_id),
                    description=data.get("description"),
                )
            for edge in edges:
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
                except Exception as exc:
                    logger.debug("Infobox fallback failed for %s: %s", qid, exc)
            if depth < self.max_depth:
                for edge in edges:
                    if edge.target not in visited and self._should_continue(graph):
                        queue.append((edge.target, depth + 1))
        return graph


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


__all__ = ["GraphBuilder", "load_graph"]
