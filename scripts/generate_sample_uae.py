"""Generate an illustrative UAE royal family graph without network access."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import networkx as nx

from wikinet.export import export_graph

OUT = os.path.join("out", "uae_sample")

def main() -> None:
    graph = nx.MultiDiGraph()
    nodes = {
        "QMohammed": "Sheikh Mohammed bin Rashid Al Maktoum",
        "QHamdan": "Sheikh Hamdan bin Mohammed Al Maktoum",
        "QMaktoum": "Sheikh Maktoum bin Mohammed Al Maktoum",
        "QLatifa": "Sheikha Latifa bint Mohammed Al Maktoum",
        "QHind": "Sheikha Hind bint Maktoum bin Juma Al Maktoum",
        "QZayed": "Sheikh Zayed bin Sultan Al Nahyan",
        "QMohammedNahyan": "Sheikh Mohammed bin Zayed Al Nahyan",
        "QTahnoon": "Sheikh Tahnoun bin Zayed Al Nahyan",
        "QHazza": "Sheikh Hazza bin Zayed Al Nahyan",
        "QMansour": "Sheikh Mansour bin Zayed Al Nahyan",
    }
    for qid, label in nodes.items():
        graph.add_node(qid, label=label)

    def add_edge(src, dst, relation, pid):
        graph.add_edge(
            src,
            dst,
            relation=relation,
            pid=pid,
            source_system="manual",
            evidence_url="https://example.com/uae",
            retrieved_at="2024-01-01T00:00:00Z",
        )

    add_edge("QMohammed", "QHamdan", "father", "P22")
    add_edge("QMohammed", "QMaktoum", "father", "P22")
    add_edge("QMohammed", "QLatifa", "father", "P22")
    add_edge("QMohammed", "QHind", "spouse", "P26")
    add_edge("QZayed", "QMohammedNahyan", "father", "P22")
    add_edge("QZayed", "QTahnoon", "father", "P22")
    add_edge("QZayed", "QHazza", "father", "P22")
    add_edge("QZayed", "QMansour", "father", "P22")
    add_edge("QMohammedNahyan", "QMohammed", "relative", "P1038")
    add_edge("QMohammedNahyan", "QHazza", "sibling", "P3373")
    add_edge("QMohammedNahyan", "QTahnoon", "sibling", "P3373")
    add_edge("QMohammedNahyan", "QMansour", "sibling", "P3373")

    export_graph(graph, OUT)

if __name__ == "__main__":
    main()
