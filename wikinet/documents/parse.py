"""Document intel schemas and parsing entrypoints."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, MutableMapping, Tuple

from ..utils import timestamp


@dataclass
class ExtractedEntity:
    entity_id: str
    label: str
    entity_type: str
    mentions: int = 1
    roles: List[str] = field(default_factory=list)
    source_excerpts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "entity_id": self.entity_id,
            "label": self.label,
            "entity_type": self.entity_type,
            "mentions": self.mentions,
            "roles": list(self.roles),
            "source_excerpts": list(self.source_excerpts),
        }


@dataclass
class ExtractedRelationship:
    source_id: str
    target_id: str
    relation: str
    pid: str
    excerpt: str
    confidence: float = 0.7

    def to_dict(self) -> Dict[str, object]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "pid": self.pid,
            "excerpt": self.excerpt,
            "confidence": self.confidence,
        }


@dataclass
class DocumentIntel:
    document_id: str
    source_path: str
    title: str
    text_length: int
    parser: str = "ollama"
    model: str | None = None
    chunks_processed: int = 1
    case_numbers: List[str] = field(default_factory=list)
    courts: List[str] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    amounts: List[str] = field(default_factory=list)
    entities: List[ExtractedEntity] = field(default_factory=list)
    relationships: List[ExtractedRelationship] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "document_id": self.document_id,
            "source_path": self.source_path,
            "title": self.title,
            "text_length": self.text_length,
            "parser": self.parser,
            "chunks_processed": self.chunks_processed,
            "case_numbers": list(self.case_numbers),
            "courts": list(self.courts),
            "dates": list(self.dates),
            "amounts": list(self.amounts),
            "entities": [entity.to_dict() for entity in self.entities],
            "relationships": [rel.to_dict() for rel in self.relationships],
            "warnings": list(self.warnings),
        }
        if self.model:
            payload["model"] = self.model
        return payload


def _entity_id(doc_id: str, label: str) -> str:
    digest = hashlib.sha1(f"{doc_id}:{label.lower()}".encode("utf-8")).hexdigest()[:12]
    return f"docent:{digest}"


def _register_entity(
    registry: Dict[str, ExtractedEntity],
    doc_id: str,
    label: str,
    entity_type: str,
    *,
    role: str | None = None,
    excerpt: str | None = None,
    apply_clean: bool = True,
) -> str:
    label = re.sub(r"\s+", " ", label.strip(" .,;")) if not apply_clean else _clean_label(label)
    if not label or len(label) < 2:
        return ""
    entity_id = _entity_id(doc_id, label)
    if entity_id not in registry:
        registry[entity_id] = ExtractedEntity(
            entity_id=entity_id,
            label=label,
            entity_type=entity_type,
        )
    entity = registry[entity_id]
    entity.mentions += 1
    if role and role not in entity.roles:
        entity.roles.append(role)
    if excerpt and excerpt not in entity.source_excerpts:
        entity.source_excerpts.append(excerpt[:240])
    return entity_id


def _clean_label(label: str) -> str:
    label = re.sub(r"\s+", " ", label.strip(" .,;"))
    if len(label) < 2 or len(label) > 120:
        return ""
    return label


def parse_document_intel(
    *,
    source_path: Path,
    text: str,
    ollama_client: object | None = None,
    chunk_chars: int | None = None,
    chunk_overlap: int | None = None,
) -> DocumentIntel:
    """Parse a single document body into structured intel via Ollama."""

    from .ollama import (
        DEFAULT_CHUNK_CHARS,
        DEFAULT_CHUNK_OVERLAP,
        parse_document_intel_ollama,
    )

    return parse_document_intel_ollama(
        source_path=source_path,
        text=text,
        ollama_client=ollama_client,  # type: ignore[arg-type]
        chunk_chars=chunk_chars or DEFAULT_CHUNK_CHARS,
        chunk_overlap=chunk_overlap or DEFAULT_CHUNK_OVERLAP,
    )


def intel_to_graph_payload(
    intel: DocumentIntel,
    *,
    retrieved_at: str | None = None,
) -> Tuple[List[MutableMapping[str, object]], List[MutableMapping[str, object]]]:
    """Convert parsed intel into wikinet node/edge records."""

    retrieved_at = retrieved_at or timestamp()
    nodes: List[MutableMapping[str, object]] = [
        {
            "id": intel.document_id,
            "label": intel.title,
            "description": "source document",
            "entity_type": "document",
            "source_path": intel.source_path,
            "case_numbers": intel.case_numbers,
            "courts": intel.courts,
            "dates": intel.dates,
            "amounts": intel.amounts,
            "parser": intel.parser,
            "chunks_processed": intel.chunks_processed,
            "layers": ["document"],
        }
    ]
    if intel.model:
        nodes[0]["model"] = intel.model

    for entity in intel.entities:
        nodes.append(
            {
                "id": entity.entity_id,
                "label": entity.label,
                "description": f"{entity.entity_type} mentioned in document",
                "entity_type": entity.entity_type,
                "mentions": entity.mentions,
                "roles": entity.roles,
                "source_excerpts": entity.source_excerpts,
                "layers": ["document"],
                "source_documents": [intel.document_id],
            }
        )

    edges: List[MutableMapping[str, object]] = []
    for entity in intel.entities:
        edges.append(
            {
                "source": intel.document_id,
                "target": entity.entity_id,
                "relation": "mentions",
                "pid": "DOC_MENTIONS",
                "source_system": "document",
                "evidence_url": f"file://{intel.source_path}",
                "retrieved_at": retrieved_at,
                "data": {"excerpt": entity.source_excerpts[0] if entity.source_excerpts else ""},
            }
        )
    for rel in intel.relationships:
        edges.append(
            {
                "source": rel.source_id,
                "target": rel.target_id,
                "relation": rel.relation,
                "pid": rel.pid,
                "source_system": "document",
                "evidence_url": f"file://{intel.source_path}",
                "retrieved_at": retrieved_at,
                "data": {"excerpt": rel.excerpt, "confidence": rel.confidence},
            }
        )
    return nodes, edges


__all__ = [
    "DocumentIntel",
    "ExtractedEntity",
    "ExtractedRelationship",
    "intel_to_graph_payload",
    "parse_document_intel",
]
