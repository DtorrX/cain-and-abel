"""Orchestrate document ingestion into wikinet graphs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

import networkx as nx

from ..export import export_graph
from ..graph import load_graph
from ..resolver import Resolver
from ..utils import console, timestamp
from .extract import collect_document_paths, extract_text
from .parse import DocumentIntel, intel_to_graph_payload, load_patterns, parse_document_intel


@dataclass
class DocumentIngestResult:
    """Summary of a document ingest run."""

    documents: List[DocumentIntel] = field(default_factory=list)
    nodes_added: int = 0
    edges_added: int = 0
    resolved_entities: int = 0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "documents": [doc.to_dict() for doc in self.documents],
            "nodes_added": self.nodes_added,
            "edges_added": self.edges_added,
            "resolved_entities": self.resolved_entities,
            "warnings": list(self.warnings),
        }


def _records_to_graph(
    nodes: Sequence[Mapping[str, object]],
    edges: Sequence[Mapping[str, object]],
) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    for node in nodes:
        node_id = str(node["id"])
        graph.add_node(node_id, **{k: v for k, v in node.items() if k != "id"})
    for edge in edges:
        graph.add_edge(
            str(edge["source"]),
            str(edge["target"]),
            **{k: v for k, v in edge.items() if k not in {"source", "target"}},
        )
    return graph


def _merge_graphs(base: nx.MultiDiGraph, incoming: nx.MultiDiGraph) -> nx.MultiDiGraph:
    merged = nx.compose(base, incoming)
    for u, v, key, data in incoming.edges(keys=True, data=True):
        if not merged.has_edge(u, v, key=key):
            merged.add_edge(u, v, key=key, **data)
    return merged


def _try_resolve_entities(
    graph: nx.MultiDiGraph,
    resolver: Resolver,
    *,
    entity_types: Optional[Iterable[str]] = None,
) -> int:
    allowed = set(entity_types or {"person", "organization"})
    resolved = 0
    for node_id, data in list(graph.nodes(data=True)):
        if data.get("entity_type") not in allowed:
            continue
        if str(node_id).startswith("Q"):
            continue
        label = data.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        try:
            qid = resolver.resolve_seed(label)
        except Exception:
            continue
        if qid == node_id:
            continue
        attrs = dict(data)
        attrs["document_entity_id"] = node_id
        attrs["resolved_from"] = label
        graph.add_node(qid, **attrs)
        for u, _v, edge_data in list(graph.in_edges(node_id, data=True)):
            graph.add_edge(u, qid, **edge_data)
        for _u, v, edge_data in list(graph.out_edges(node_id, data=True)):
            graph.add_edge(qid, v, **edge_data)
        if node_id in graph:
            graph.remove_node(node_id)
        resolved += 1
    return resolved


def ingest_documents(
    paths: Sequence[str],
    *,
    out_dir: str,
    patterns_path: str | None = None,
    merge_into: str | None = None,
    resolve_entities: bool = False,
    resolver: Resolver | None = None,
    report_path: str | None = None,
) -> DocumentIngestResult:
    """Parse documents and export (or merge) a wikinet graph."""

    doc_paths = collect_document_paths(paths)
    patterns = load_patterns(Path(patterns_path) if patterns_path else None)
    result = DocumentIngestResult()
    all_nodes: List[MutableMapping[str, object]] = []
    all_edges: List[MutableMapping[str, object]] = []
    retrieved_at = timestamp()

    for doc_path in doc_paths:
        console.log(f"Parsing document {doc_path}")
        try:
            text = extract_text(doc_path)
        except Exception as exc:
            warning = f"Failed to extract text from {doc_path}: {exc}"
            result.warnings.append(warning)
            console.log(f"[yellow]{warning}[/yellow]")
            continue
        intel = parse_document_intel(source_path=doc_path, text=text, patterns=patterns)
        result.documents.append(intel)
        result.warnings.extend(intel.warnings)
        nodes, edges = intel_to_graph_payload(intel, retrieved_at=retrieved_at)
        all_nodes.extend(nodes)
        all_edges.extend(edges)

    if not result.documents:
        raise SystemExit("No documents were successfully parsed")

    doc_graph = _records_to_graph(all_nodes, all_edges)
    if merge_into and os.path.isdir(merge_into):
        existing = load_graph(merge_into)
        graph = _merge_graphs(existing, doc_graph)
        out_dir = merge_into
    else:
        graph = doc_graph

    if resolve_entities:
        if resolver is None:
            raise ValueError("resolver is required when resolve_entities=True")
        result.resolved_entities = _try_resolve_entities(graph, resolver)

    os.makedirs(out_dir, exist_ok=True)
    export_graph(graph, out_dir)
    intel_report_path = os.path.join(out_dir, "document_intel.json")
    with open(intel_report_path, "w", encoding="utf-8") as fh:
        json.dump(result.to_dict(), fh, indent=2)
    if report_path:
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(result.to_dict(), fh, indent=2)

    result.nodes_added = graph.number_of_nodes()
    result.edges_added = graph.number_of_edges()
    console.log(
        f"Document ingest complete: {len(result.documents)} docs, "
        f"{result.nodes_added} nodes, {result.edges_added} edges"
    )
    console.log(f"Intel report: {intel_report_path}")
    return result


def merge_into_graph(
    base_dir: str,
    doc_nodes: Sequence[Mapping[str, object]],
    doc_edges: Sequence[Mapping[str, object]],
) -> nx.MultiDiGraph:
    """Merge document-derived records into an existing export directory."""

    base = load_graph(base_dir)
    incoming = _records_to_graph(doc_nodes, doc_edges)
    return _merge_graphs(base, incoming)


__all__ = ["DocumentIngestResult", "ingest_documents", "merge_into_graph"]
