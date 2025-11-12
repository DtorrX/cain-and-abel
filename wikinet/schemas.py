"""Pydantic schemas for nodes and edges."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Node:
    id: str
    label: str
    description: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def dict(self) -> Dict[str, Any]:  # pragma: no cover - convenience
        return asdict(self)


@dataclass
class Edge:
    source: str
    target: str
    relation: str
    pid: str
    source_system: str
    evidence_url: str
    retrieved_at: str
    data: Dict[str, Any] = field(default_factory=dict)

    def dict(self) -> Dict[str, Any]:
        return asdict(self)


__all__ = ["Node", "Edge"]
