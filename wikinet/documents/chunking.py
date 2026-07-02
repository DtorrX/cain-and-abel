"""Split long document text into Ollama-sized chunks."""

from __future__ import annotations

import re
from typing import List

DEFAULT_CHUNK_CHARS = 12_000
DEFAULT_CHUNK_OVERLAP = 800
PAGE_MARKER_RE = re.compile(r"^\[Page (\d+)\]", re.MULTILINE)


def chunk_text(
    text: str,
    *,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """Split text into overlapping chunks, preferring page and paragraph boundaries."""

    normalized = text.strip()
    if not normalized:
        return []
    if len(normalized) <= chunk_chars:
        return [normalized]

    segments = _split_segments(normalized)
    if not segments:
        return [normalized[:chunk_chars]]

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for segment in segments:
        segment_len = len(segment) + (2 if current else 0)
        if current and current_len + segment_len > chunk_chars:
            chunks.append("\n\n".join(current))
            current = _tail_overlap(current, overlap)
            current_len = sum(len(part) + 2 for part in current) - (2 if current else 0)

        if len(segment) > chunk_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            chunks.extend(_split_oversized_segment(segment, chunk_chars, overlap))
            continue

        current.append(segment)
        current_len += segment_len

    if current:
        chunks.append("\n\n".join(current))

    return [chunk for chunk in chunks if chunk.strip()]


def _split_segments(text: str) -> List[str]:
    if PAGE_MARKER_RE.search(text):
        parts = re.split(r"(?=\[Page \d+\])", text)
        return [part.strip() for part in parts if part.strip()]
    return [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]


def _tail_overlap(segments: List[str], overlap: int) -> List[str]:
    if overlap <= 0 or not segments:
        return []
    tail = segments[-1]
    if len(tail) <= overlap:
        return [tail]
    return [tail[-overlap:]]


def _split_oversized_segment(segment: str, chunk_chars: int, overlap: int) -> List[str]:
    chunks: List[str] = []
    start = 0
    while start < len(segment):
        end = min(len(segment), start + chunk_chars)
        chunks.append(segment[start:end].strip())
        if end >= len(segment):
            break
        start = max(end - overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


__all__ = ["DEFAULT_CHUNK_CHARS", "DEFAULT_CHUNK_OVERLAP", "chunk_text"]
