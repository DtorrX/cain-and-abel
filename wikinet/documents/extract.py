"""Extract plain text from arbitrary document files."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Iterable, List

SUPPORTED_EXTENSIONS = {".txt", ".md", ".html", ".htm", ".pdf", ".docx", ".rtf", ".json"}


def _read_text_file(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def _strip_rtf(raw: str) -> str:
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", raw)
    text = re.sub(r"\\[a-z]+\d* ?|-?\d+;", " ", text)
    text = re.sub(r"[{}]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_pdf_pages(path: Path) -> List[str]:
    """Return per-page plain text for a PDF (empty pages omitted)."""

    try:
        from pypdf import PdfReader  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "PDF support requires the documents extra: pip install -e '.[documents]'"
        ) from exc
    reader = PdfReader(str(path))
    pages: List[str] = []
    for page in reader.pages:
        page_text = (page.extract_text() or "").strip()
        if page_text:
            pages.append(page_text)
    return pages


def _extract_pdf(path: Path) -> str:
    pages = extract_pdf_pages(path)
    if not pages:
        return ""
    return "\n\n".join(f"[Page {index}]\n{page}" for index, page in enumerate(pages, start=1))


def _extract_docx(path: Path) -> str:
    try:
        from docx import Document  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "DOCX support requires the documents extra: pip install -e '.[documents]'"
        ) from exc
    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text).strip()


def extract_text(path: Path) -> str:
    """Return normalized plain text for a single file."""

    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return _read_text_file(path)
    if suffix in {".html", ".htm"}:
        return _strip_html(_read_text_file(path))
    if suffix == ".rtf":
        return _strip_rtf(_read_text_file(path))
    if suffix == ".json":
        return _read_text_file(path)
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    raise ValueError(f"Unsupported document type: {suffix or '(no extension)'}")


def collect_document_paths(paths: Iterable[str]) -> List[Path]:
    """Expand files and directories into a sorted list of document paths."""

    discovered: List[Path] = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Path not found: {path}")
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                    discovered.append(child)
        elif path.is_file():
            discovered.append(path)
        else:
            raise ValueError(f"Not a file or directory: {path}")
    if not discovered:
        raise ValueError(
            "No supported documents found (.txt, .md, .html, .pdf, .docx, .rtf, .json)"
        )
    return discovered


__all__ = [
    "SUPPORTED_EXTENSIONS",
    "collect_document_paths",
    "extract_pdf_pages",
    "extract_text",
]
