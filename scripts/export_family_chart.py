#!/usr/bin/env python3
"""Export Wikinet nodes/edges into the family-chart JSON format.

This stays defensive about field names so that older runs (or merged
outputs) still work. It only depends on `nodes.json` and `edges.json`
and emits a `family_chart.json` that the `family-chart` viewer can render.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, MutableMapping, MutableSet, Tuple

# Accepted keys for node identifiers and edge endpoints
NODE_ID_KEYS = ("id", "qid", "wikidata_id", "wikidata_qid")
EDGE_SOURCE_KEYS = ("source", "src", "from")
EDGE_TARGET_KEYS = ("target", "dst", "to")
EDGE_PID_KEYS = ("pid", "property_id", "property")

PARENT_PIDS = {"P22", "P25"}
CHILD_PIDS = {"P40"}
SPOUSE_PIDS = {"P26"}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def pick_first(mapping: MutableMapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def normalize_id(raw_id: Any) -> str | None:
    if raw_id is None:
        return None
    return str(raw_id)


def extract_node_id(node: MutableMapping[str, Any]) -> str | None:
    return normalize_id(pick_first(node, NODE_ID_KEYS))


def extract_edge_endpoints(edge: MutableMapping[str, Any]) -> Tuple[str | None, str | None]:
    src = normalize_id(pick_first(edge, EDGE_SOURCE_KEYS))
    dst = normalize_id(pick_first(edge, EDGE_TARGET_KEYS))
    return src, dst


def extract_pid(edge: MutableMapping[str, Any]) -> str | None:
    raw = pick_first(edge, EDGE_PID_KEYS)
    return normalize_id(raw)


def split_name(label: str) -> Tuple[str, str]:
    if not label:
        return "", ""
    parts = label.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def collect_people(nodes: List[MutableMapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    people: Dict[str, Dict[str, Any]] = {}
    for node in nodes:
        node_id = extract_node_id(node)
        if not node_id:
            continue
        label = str(node.get("label") or node.get("name") or node_id)
        first, last = split_name(label)
        birthdate = (
            node.get("birth_date")
            or node.get("date_of_birth")
            or node.get("dob")
            or ""
        )
        gender = node.get("gender") or node.get("sex") or ""
        people[node_id] = {
            "label": label,
            "first name": first,
            "last name": last,
            "birthday": str(birthdate) if birthdate is not None else "",
            "gender": str(gender) if gender is not None else "",
            "qid": node_id,
        }
    return people


def update_relationships(
    src: str,
    dst: str,
    pid: str,
    parents: Dict[str, MutableSet[str]],
    children: Dict[str, MutableSet[str]],
    spouses: Dict[str, MutableSet[str]],
) -> None:
    if pid in SPOUSE_PIDS:
        spouses[src].add(dst)
        spouses[dst].add(src)
    elif pid in PARENT_PIDS:
        # Most Wikidata exports store child -> parent for P22/P25
        parents[src].add(dst)
        children[dst].add(src)
    elif pid in CHILD_PIDS:
        # P40 is parent -> child
        parents[dst].add(src)
        children[src].add(dst)


def build_family_chart(
    nodes: List[MutableMapping[str, Any]], edges: List[MutableMapping[str, Any]]
) -> List[Dict[str, Any]]:
    people = collect_people(nodes)
    parents: Dict[str, MutableSet[str]] = {pid: set() for pid in people}
    children: Dict[str, MutableSet[str]] = {pid: set() for pid in people}
    spouses: Dict[str, MutableSet[str]] = {pid: set() for pid in people}

    for edge in edges:
        pid = extract_pid(edge)
        if not pid:
            continue
        pid = pid.strip()
        if pid not in PARENT_PIDS | CHILD_PIDS | SPOUSE_PIDS:
            continue
        src, dst = extract_edge_endpoints(edge)
        if not src or not dst:
            continue
        if src not in people or dst not in people:
            continue
        update_relationships(src, dst, pid, parents, children, spouses)

    family_chart: List[Dict[str, Any]] = []
    for node_id, data in people.items():
        family_chart.append(
            {
                "id": node_id,
                "data": data,
                "rels": {
                    "spouses": sorted(spouses[node_id]),
                    "children": sorted(children[node_id]),
                    "parents": sorted(parents[node_id]),
                },
            }
        )
    return family_chart


def main() -> None:
    parser = argparse.ArgumentParser(description="Export family-chart JSON from Wikinet outputs")
    parser.add_argument("--nodes", required=True, type=Path, help="Path to nodes.json")
    parser.add_argument("--edges", required=True, type=Path, help="Path to edges.json")
    parser.add_argument("--out", required=True, type=Path, help="Output family_chart.json path")
    args = parser.parse_args()

    nodes_data = load_json(args.nodes)
    edges_data = load_json(args.edges)

    if not isinstance(nodes_data, list) or not isinstance(edges_data, list):
        raise ValueError("nodes.json and edges.json must contain lists")

    family_chart = build_family_chart(nodes_data, edges_data)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(family_chart, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
