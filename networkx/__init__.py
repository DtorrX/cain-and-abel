"""Lightweight fallback implementation of NetworkX MultiDiGraph."""

from __future__ import annotations

import importlib.util
import os

_spec = importlib.util.find_spec("networkx")
if _spec and _spec.origin and os.path.abspath(_spec.origin) != os.path.abspath(__file__):  # pragma: no cover
    module = importlib.util.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(module)
    locals().update(module.__dict__)
else:  # pragma: no cover - fallback stub
    from collections import defaultdict
    from typing import Any, Dict, Iterable, Iterator, List, Tuple

    class MultiDiGraph:
        def __init__(self) -> None:
            self._nodes: Dict[Any, Dict[str, Any]] = {}
            self._adj: Dict[Any, Dict[Any, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

        def add_node(self, node: Any, **attrs: Any) -> None:
            data = self._nodes.get(node, {})
            data.update(attrs)
            self._nodes[node] = data

        def add_edge(self, u: Any, v: Any, **attrs: Any) -> None:
            self.add_node(u)
            self.add_node(v)
            self._adj[u][v].append(attrs)

        def nodes(self, data: bool = False) -> Iterable:
            if data:
                return [(n, attrs) for n, attrs in self._nodes.items()]
            return list(self._nodes.keys())

        def edges(self, data: bool = False):
            items = []
            for u, targets in self._adj.items():
                for v, edges in targets.items():
                    for attrs in edges:
                        items.append((u, v, attrs if data else None))
            if data:
                return [(u, v, attrs) for u, v, attrs in items]
            return [(u, v) for u, v, _ in items]

        def number_of_nodes(self) -> int:
            return len(self._nodes)

        def number_of_edges(self) -> int:
            return sum(len(edges) for targets in self._adj.values() for edges in targets.values())

        def get_edge_data(self, u: Any, v: Any, key: int | None = None):
            edges = self._adj.get(u, {}).get(v, [])
            if key is None:
                return edges
            if key < len(edges):
                return edges[key]
            return None

    def compose(g1: MultiDiGraph, g2: MultiDiGraph) -> MultiDiGraph:
        result = MultiDiGraph()
        for node, attrs in g1.nodes(data=True):
            result.add_node(node, **attrs)
        for node, attrs in g2.nodes(data=True):
            existing = result._nodes.get(node, {})
            existing.update(attrs)
            result._nodes[node] = existing
        for u, v, attrs in g1.edges(data=True):
            result.add_edge(u, v, **attrs)
        for u, v, attrs in g2.edges(data=True):
            result.add_edge(u, v, **attrs)
        return result

    def write_graphml(graph: MultiDiGraph, path: str) -> None:
        import xml.etree.ElementTree as ET

        root = ET.Element("graphml")
        g_elem = ET.SubElement(root, "graph", edgedefault="directed")
        for node_id, attrs in graph.nodes(data=True):
            node_elem = ET.SubElement(g_elem, "node", id=str(node_id))
            for key, value in attrs.items():
                data_elem = ET.SubElement(node_elem, "data", key=key)
                data_elem.text = str(value)
        for u, v, attrs in graph.edges(data=True):
            edge_elem = ET.SubElement(g_elem, "edge", source=str(u), target=str(v))
            for key, value in attrs.items():
                data_elem = ET.SubElement(edge_elem, "data", key=key)
                data_elem.text = str(value)
        tree = ET.ElementTree(root)
        tree.write(path, encoding="utf-8", xml_declaration=True)

    __all__ = ["MultiDiGraph", "compose", "write_graphml"]
