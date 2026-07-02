"""Rule-based intel extraction from document text (fallback parser)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, List, Mapping

from .parse import (
    DEFAULT_LEGAL_PATTERNS,
    DocumentIntel,
    ExtractedEntity,
    ExtractedRelationship,
    _excerpt,
    _find_matches,
    _register_entity,
)

DATE_PATTERNS = [
    r"\b(\d{4}-\d{2}-\d{2})\b",
    r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b",
    r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4})\b",
]

MONEY_PATTERN = r"(?i)\$[\d,]+(?:\.\d{2})?(?:\s*(?:million|billion|thousand))?"

ROLE_LINE_PATTERN = re.compile(
    r"(?im)^\s*(plaintiffs?|defendants?|petitioners?|respondents?|claimants?)\s*[:,]\s*(.+?)\s*$"
)


def _extract_party_lines(text: str, doc_id: str, registry: Dict[str, ExtractedEntity]) -> None:
    for match in ROLE_LINE_PATTERN.finditer(text):
        role = match.group(1).lower().rstrip("s")
        if role.endswith("t"):
            role = role + "s"
        parties = re.split(r",|\band\b|;", match.group(2))
        for party in parties:
            party = party.strip(" .")
            if party:
                _register_entity(
                    registry,
                    doc_id,
                    party,
                    "organization"
                    if re.search(r"(?i)\b(inc|llc|ltd|corp|company)\b", party)
                    else "person",
                    role=role,
                    excerpt=_excerpt(text, match.start(), match.end()),
                )


def parse_document_intel_rules(
    *,
    source_path: Path,
    text: str,
    patterns: Mapping[str, object] | None = None,
) -> DocumentIntel:
    """Parse a document using regex/rule-based extraction."""

    patterns = dict(patterns or DEFAULT_LEGAL_PATTERNS)
    doc_hash = hashlib.sha1(str(source_path).encode("utf-8")).hexdigest()[:12]
    document_id = f"doc:{doc_hash}"
    intel = DocumentIntel(
        document_id=document_id,
        source_path=str(source_path),
        title=source_path.name,
        text_length=len(text),
        parser="rules",
    )
    if not text.strip():
        intel.warnings.append("Document contained no extractable text")
        return intel

    intel.case_numbers = _find_matches(text, patterns.get("case_number", []))  # type: ignore[arg-type]
    intel.courts = _find_matches(text, patterns.get("court", []))  # type: ignore[arg-type]
    for pattern in DATE_PATTERNS:
        intel.dates.extend(_find_matches(text, [pattern]))
    intel.dates = list(dict.fromkeys(intel.dates))
    intel.amounts = [match.group(0) for match in re.finditer(MONEY_PATTERN, text)]

    registry: Dict[str, ExtractedEntity] = {}
    _extract_party_lines(text, document_id, registry)

    for pattern in patterns.get("organization_suffixes", []):  # type: ignore[union-attr]
        for match in re.finditer(pattern, text):
            label = match.group(1)
            _register_entity(
                registry,
                document_id,
                label,
                "organization",
                excerpt=_excerpt(text, match.start(), match.end()),
            )

    for pattern in patterns.get("person_titles", []):  # type: ignore[union-attr]
        for match in re.finditer(pattern, text):
            label = match.group(1)
            _register_entity(
                registry,
                document_id,
                label,
                "person",
                excerpt=_excerpt(text, match.start(), match.end()),
            )

    relationships: List[ExtractedRelationship] = []
    for item in patterns.get("relationship_phrases", []):  # type: ignore[union-attr]
        relation = str(item["relation"])
        pattern = str(item["pattern"])
        for match in re.finditer(pattern, text):
            excerpt = _excerpt(text, match.start(), match.end())
            if relation == "on_behalf_of":
                target_label = match.group(1)
                source_id = document_id
                target_id = _register_entity(
                    registry, document_id, target_label, "organization", excerpt=excerpt
                )
                if target_id:
                    relationships.append(
                        ExtractedRelationship(
                            source_id=source_id,
                            target_id=target_id,
                            relation=relation,
                            pid="DOC",
                            excerpt=excerpt,
                            confidence=0.65,
                        )
                    )
                continue
            source_label = match.group(1)
            target_label = match.group(2)
            source_id = _register_entity(
                registry,
                document_id,
                source_label,
                "person",
                excerpt=excerpt,
            )
            target_id = _register_entity(
                registry,
                document_id,
                target_label,
                "organization"
                if re.search(r"(?i)\b(inc|llc|ltd|corp|company)\b", target_label)
                else "person",
                excerpt=excerpt,
            )
            if source_id and target_id:
                relationships.append(
                    ExtractedRelationship(
                        source_id=source_id,
                        target_id=target_id,
                        relation=relation,
                        pid="DOC",
                        excerpt=excerpt,
                    )
                )

    intel.entities = list(registry.values())
    intel.relationships = relationships
    return intel


__all__ = ["parse_document_intel_rules"]
