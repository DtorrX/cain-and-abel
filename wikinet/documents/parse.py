"""Document intel schemas and parsing entrypoints."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Mapping, MutableMapping, Sequence, Tuple

from ..utils import timestamp

ParserName = Literal["ollama", "rules"]

NAME_FRAGMENT = r"[A-Z][\w'.-]*"
PERSON_NAME = rf"(?:{NAME_FRAGMENT}(?:\s+{NAME_FRAGMENT}){{0,4}})"
ORG_NAME = rf"(?:{NAME_FRAGMENT}(?:\s+{NAME_FRAGMENT}){{0,6}}(?:\s+(?:Inc\.?|LLC|L\.L\.C\.|Ltd\.?|Corp\.?|Corporation|Company|Co\.?))?)"

DEFAULT_LEGAL_PATTERNS: Dict[str, object] = {
    "case_number": [
        r"(?i)\b(?:case|docket|file|matter)\s*(?:no\.?|number|#)\s*[:.]?\s*([A-Z0-9][\w./-]{2,})",
        r"(?i)\b(?:civil|criminal)\s+(?:action|case)\s+no\.?\s*([A-Z0-9][\w./-]{2,})",
    ],
    "court": [
        r"(?i)\b((?:United States|U\.S\.) District Court[^,\n]{0,80})",
        r"(?i)\b((?:Supreme|Superior|Circuit|Appellate|Family|Probate) Court[^,\n]{0,80})",
    ],
    "party_roles": {
        "plaintiff": [r"(?i)\bplaintiffs?\b", r"(?i)\bpetitioners?\b", r"(?i)\bclaimants?\b"],
        "defendant": [r"(?i)\bdefendants?\b", r"(?i)\brespondents?\b"],
    },
    "relationship_phrases": [
        {
            "relation": "director_of",
            "pattern": rf"\b({PERSON_NAME})\s*,?\s*(?i:director of)\s+({ORG_NAME})",
        },
        {
            "relation": "employed_by",
            "pattern": rf"\b({PERSON_NAME})\s*,?\s*(?:(?i:was)\s+)?(?i:employed by|employee of)\s+({ORG_NAME})",
        },
        {
            "relation": "officer_of",
            "pattern": rf"\b({PERSON_NAME})\s*,?\s*(?i:chief executive officer|ceo|cfo|president|chairman) of\s+({ORG_NAME})",
        },
        {
            "relation": "owned_by",
            "pattern": rf"\b({ORG_NAME})\s+(?:(?i:is)\s+)?(?i:owned by)\s+({ORG_NAME})",
        },
        {
            "relation": "subsidiary_of",
            "pattern": rf"\b({ORG_NAME})\s*,?\s*(?i:a subsidiary of)\s+({ORG_NAME})",
        },
        {
            "relation": "represented_by",
            "pattern": rf"\b({PERSON_NAME})\s*,?\s*(?i:represented by)\s+({PERSON_NAME})",
        },
        {
            "relation": "spouse_of",
            "pattern": rf"\b({PERSON_NAME})\s*,?\s*(?i:spouse of)\s+({PERSON_NAME})",
        },
        {"relation": "on_behalf_of", "pattern": rf"(?i:on behalf of)\s+({ORG_NAME})"},
    ],
    "organization_suffixes": [
        r"\b([A-Z][\w&'.-]+(?:\s+[A-Z][\w&'.-]+){0,5}\s+(?:Inc\.?|LLC|L\.L\.C\.|Ltd\.?|Corp\.?|Corporation|Company|Co\.?|LP|LLP|PLC))\b",
    ],
    "person_titles": [
        r"\b(?:Mr\.|Ms\.|Mrs\.|Dr\.|Hon\.|Judge|Justice)\s+([A-Z][\w'.-]+(?:\s+[A-Z][\w'.-]+){0,3})\b",
        r"\b([A-Z][\w'.-]+(?:\s+[A-Z][\w'.-]+){0,3})\s*,\s*(?:Esq\.|Attorney|Counsel)\b",
    ],
}

NOISE_WORDS = {
    "complaint",
    "plaintiff",
    "defendant",
    "alleges",
    "that",
    "was",
    "and",
    "by",
    "is",
    "the",
    "parties",
    "agreed",
    "damages",
    "on",
    "january",
}


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


def load_patterns(patterns_path: Path | None = None) -> Dict[str, object]:
    if patterns_path and patterns_path.exists():
        with patterns_path.open("r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        merged = DEFAULT_LEGAL_PATTERNS.copy()
        merged.update(loaded)
        return merged
    return DEFAULT_LEGAL_PATTERNS.copy()


def _clean_label(label: str) -> str:
    label = re.sub(r"\s+", " ", label.strip(" .,;"))
    if len(label) < 2 or len(label) > 120:
        return ""
    lower = label.lower()
    if any(
        word in lower.split() for word in NOISE_WORDS if word in {"complaint", "alleges", "damages"}
    ):
        return ""
    if lower in NOISE_WORDS:
        return ""
    return label


def _entity_id(doc_id: str, label: str) -> str:
    digest = hashlib.sha1(f"{doc_id}:{label.lower()}".encode("utf-8")).hexdigest()[:12]
    return f"docent:{digest}"


def _excerpt(text: str, start: int, end: int, radius: int = 80) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    snippet = text[left:right].replace("\n", " ")
    return re.sub(r"\s+", " ", snippet).strip()


def _find_matches(text: str, patterns: Sequence[str]) -> List[str]:
    found: List[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = match.group(1) if match.lastindex else match.group(0)
            value = value.strip(" .,;")
            if value and value not in found:
                found.append(value)
    return found


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
    label = _clean_label(label) if apply_clean else re.sub(r"\s+", " ", label.strip(" .,;"))
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


def parse_document_intel(
    *,
    source_path: Path,
    text: str,
    patterns: Mapping[str, object] | None = None,
    parser: ParserName = "ollama",
    ollama_client: object | None = None,
    max_chars: int | None = None,
) -> DocumentIntel:
    """Parse a single document body into structured intel."""

    if parser == "rules":
        from .parse_rules import parse_document_intel_rules

        return parse_document_intel_rules(source_path=source_path, text=text, patterns=patterns)

    from .ollama import DEFAULT_MAX_CHARS, parse_document_intel_ollama

    return parse_document_intel_ollama(
        source_path=source_path,
        text=text,
        ollama_client=ollama_client,  # type: ignore[arg-type]
        max_chars=max_chars or DEFAULT_MAX_CHARS,
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
    "DEFAULT_LEGAL_PATTERNS",
    "DocumentIntel",
    "ExtractedEntity",
    "ExtractedRelationship",
    "ParserName",
    "intel_to_graph_payload",
    "load_patterns",
    "parse_document_intel",
]
