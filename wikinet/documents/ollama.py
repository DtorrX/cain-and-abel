"""Ollama LLM-based document intel extraction."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping

import requests

from ..utils import logger
from .parse import (
    DocumentIntel,
    ExtractedEntity,
    ExtractedRelationship,
    _register_entity,
)

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_MAX_CHARS = 24_000

EXTRACTION_SCHEMA: Dict[str, Any] = {
    "case_numbers": [],
    "courts": [],
    "dates": [],
    "amounts": [],
    "entities": [
        {
            "label": "string",
            "entity_type": "person|organization|location|other",
            "roles": ["string"],
            "excerpt": "string",
        }
    ],
    "relationships": [
        {
            "source": "string",
            "target": "string",
            "relation": "string",
            "excerpt": "string",
            "confidence": 0.0,
        }
    ],
}

SYSTEM_PROMPT = """You are an investigative analyst extracting structured intelligence from documents such as court filings, contracts, depositions, and corporate records.

Return ONLY valid JSON. No markdown fences or commentary.

Schema:
{
  "case_numbers": ["string"],
  "courts": ["string"],
  "dates": ["string"],
  "amounts": ["string"],
  "entities": [
    {"label": "string", "entity_type": "person|organization|location|other", "roles": ["string"], "excerpt": "short quote"}
  ],
  "relationships": [
    {"source": "entity label", "target": "entity label", "relation": "snake_case", "excerpt": "short quote", "confidence": 0.0}
  ]
}

Rules:
- Extract parties, people, organizations, courts, docket/case numbers, key dates, and monetary amounts.
- Use snake_case relation names (director_of, employed_by, owned_by, represented_by, plaintiff, defendant).
- Only include information supported by the document text.
- Keep excerpts under 200 characters.
- Do not invent entities or facts not present in the document."""


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + "\n\n[... document truncated for model context ...]", True


def extract_json_payload(raw: str) -> Dict[str, Any]:
    """Parse JSON from an Ollama response, tolerating markdown fences."""

    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise ValueError(f"Ollama response was not valid JSON: {exc}") from exc
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("Ollama response JSON must be an object")
    return payload


class OllamaClient:
    """Thin client for Ollama's chat API."""

    def __init__(
        self,
        *,
        host: str | None = None,
        model: str | None = None,
        timeout: int = 300,
    ) -> None:
        self.host = (host or os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
        self.timeout = timeout

    def chat(
        self,
        messages: List[Mapping[str, str]],
        *,
        json_mode: bool = True,
    ) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"
        url = f"{self.host}/api/chat"
        logger.debug("Ollama chat request model=%s url=%s", self.model, url)
        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        body = response.json()
        message = body.get("message", {})
        content = message.get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama returned an empty response")
        return content

    def extract_intel(
        self, *, title: str, text: str, max_chars: int = DEFAULT_MAX_CHARS
    ) -> Dict[str, Any]:
        clipped, truncated = _truncate_text(text, max_chars)
        user_prompt = (
            f"Extract intelligence from this document ({title}).\n\n"
            f"Document text:\n---\n{clipped}\n---"
        )
        if truncated:
            user_prompt += "\n\nNote: the document was truncated to fit the model context window."
        raw = self.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )
        return extract_json_payload(raw)


def _label_to_entity_type(label: str, hinted: str) -> str:
    hinted = (hinted or "other").lower()
    if hinted in {"person", "organization", "location", "other"}:
        return hinted
    if re.search(r"(?i)\b(inc|llc|ltd|corp|company|holdings|ventures)\b", label):
        return "organization"
    return "person"


def build_document_intel_from_payload(
    *,
    source_path: Path,
    text: str,
    payload: Mapping[str, Any],
    model: str,
    truncated: bool = False,
) -> DocumentIntel:
    doc_hash = hashlib.sha1(str(source_path).encode("utf-8")).hexdigest()[:12]
    document_id = f"doc:{doc_hash}"
    intel = DocumentIntel(
        document_id=document_id,
        source_path=str(source_path),
        title=source_path.name,
        text_length=len(text),
        parser="ollama",
        model=model,
        case_numbers=[str(v) for v in payload.get("case_numbers", []) if v],
        courts=[str(v) for v in payload.get("courts", []) if v],
        dates=[str(v) for v in payload.get("dates", []) if v],
        amounts=[str(v) for v in payload.get("amounts", []) if v],
    )
    if truncated:
        intel.warnings.append("Document text was truncated before sending to Ollama")
    if not text.strip():
        intel.warnings.append("Document contained no extractable text")
        return intel

    registry: Dict[str, ExtractedEntity] = {}
    for item in payload.get("entities", []):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        if not label:
            continue
        entity_type = _label_to_entity_type(label, str(item.get("entity_type", "other")))
        excerpt = str(item.get("excerpt", "")).strip()
        roles = [str(role) for role in item.get("roles", []) if role]
        entity_id = _register_entity(
            registry,
            document_id,
            label,
            entity_type,
            excerpt=excerpt or None,
            apply_clean=False,
        )
        if entity_id and roles:
            registry[entity_id].roles = list(dict.fromkeys(roles))

    label_to_id: Dict[str, str] = {
        entity.label.lower(): entity.entity_id for entity in registry.values()
    }
    relationships: List[ExtractedRelationship] = []
    for item in payload.get("relationships", []):
        if not isinstance(item, dict):
            continue
        source_label = str(item.get("source", "")).strip()
        target_label = str(item.get("target", "")).strip()
        relation = str(item.get("relation", "related_to")).strip().lower().replace(" ", "_")
        excerpt = str(item.get("excerpt", "")).strip()
        confidence_raw = item.get("confidence", 0.75)
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.75

        source_id = label_to_id.get(source_label.lower())
        if not source_id:
            source_id = _register_entity(
                registry,
                document_id,
                source_label,
                _label_to_entity_type(source_label, "person"),
                excerpt=excerpt or None,
                apply_clean=False,
            )
            if source_id:
                label_to_id[source_label.lower()] = source_id

        target_id = label_to_id.get(target_label.lower())
        if not target_id:
            target_id = _register_entity(
                registry,
                document_id,
                target_label,
                _label_to_entity_type(target_label, "organization"),
                excerpt=excerpt or None,
                apply_clean=False,
            )
            if target_id:
                label_to_id[target_label.lower()] = target_id

        if source_id and target_id:
            relationships.append(
                ExtractedRelationship(
                    source_id=source_id,
                    target_id=target_id,
                    relation=relation,
                    pid="DOC",
                    excerpt=excerpt,
                    confidence=max(0.0, min(confidence, 1.0)),
                )
            )

    intel.entities = list(registry.values())
    intel.relationships = relationships
    return intel


def parse_document_intel_ollama(
    *,
    source_path: Path,
    text: str,
    ollama_client: OllamaClient | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> DocumentIntel:
    """Parse a document by calling a local Ollama model."""

    client = ollama_client or OllamaClient()
    clipped, truncated = _truncate_text(text, max_chars)
    if not clipped.strip():
        doc_hash = hashlib.sha1(str(source_path).encode("utf-8")).hexdigest()[:12]
        intel = DocumentIntel(
            document_id=f"doc:{doc_hash}",
            source_path=str(source_path),
            title=source_path.name,
            text_length=len(text),
            parser="ollama",
            model=client.model,
        )
        intel.warnings.append("Document contained no extractable text")
        return intel

    payload = client.extract_intel(title=source_path.name, text=text, max_chars=max_chars)
    return build_document_intel_from_payload(
        source_path=source_path,
        text=text,
        payload=payload,
        model=client.model,
        truncated=truncated,
    )


__all__ = [
    "DEFAULT_MAX_CHARS",
    "DEFAULT_OLLAMA_HOST",
    "DEFAULT_OLLAMA_MODEL",
    "OllamaClient",
    "build_document_intel_from_payload",
    "extract_json_payload",
    "parse_document_intel_ollama",
]
