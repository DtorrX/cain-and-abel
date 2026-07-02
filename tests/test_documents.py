"""Tests for document intel extraction."""

import json
from pathlib import Path

from wikinet.documents.chunking import chunk_text
from wikinet.documents.extract import collect_document_paths, extract_text
from wikinet.documents.ingest import ingest_documents
from wikinet.documents.ollama import (
    build_document_intel_from_payload,
    extract_json_payload,
    merge_chunk_payloads,
    parse_document_intel_ollama,
)
from wikinet.documents.parse import intel_to_graph_payload, parse_document_intel

SAMPLE_COURT_DOC = """
IN THE UNITED STATES DISTRICT COURT FOR THE SOUTHERN DISTRICT OF NEW YORK

Civil Action No. 24-CV-01982

Plaintiff: Meridian Holdings LLC
Defendant: John A. Smith

COMPLAINT

Plaintiff Meridian Holdings LLC alleges that John A. Smith, director of Apex Defense Corp.,
was employed by Apex Defense Corp. and represented by Jane Q. Counsel, Esq.

On January 15, 2024, the parties agreed to damages of $2,500,000.

Apex Defense Corp. is owned by Global Ventures Inc.
"""

SAMPLE_OLLAMA_PAYLOAD = {
    "case_numbers": ["24-CV-01982"],
    "courts": ["UNITED STATES DISTRICT COURT FOR THE SOUTHERN DISTRICT OF NEW YORK"],
    "dates": ["January 15, 2024"],
    "amounts": ["$2,500,000"],
    "entities": [
        {
            "label": "Meridian Holdings LLC",
            "entity_type": "organization",
            "roles": ["plaintiff"],
            "excerpt": "Plaintiff: Meridian Holdings LLC",
        },
        {
            "label": "John A. Smith",
            "entity_type": "person",
            "roles": ["defendant"],
            "excerpt": "Defendant: John A. Smith",
        },
        {
            "label": "Apex Defense Corp.",
            "entity_type": "organization",
            "roles": [],
            "excerpt": "director of Apex Defense Corp.",
        },
        {
            "label": "Global Ventures Inc.",
            "entity_type": "organization",
            "roles": [],
            "excerpt": "owned by Global Ventures Inc.",
        },
    ],
    "relationships": [
        {
            "source": "John A. Smith",
            "target": "Apex Defense Corp.",
            "relation": "director_of",
            "excerpt": "John A. Smith, director of Apex Defense Corp.",
            "confidence": 0.9,
        },
        {
            "source": "John A. Smith",
            "target": "Apex Defense Corp.",
            "relation": "employed_by",
            "excerpt": "was employed by Apex Defense Corp.",
            "confidence": 0.9,
        },
        {
            "source": "Apex Defense Corp.",
            "target": "Global Ventures Inc.",
            "relation": "owned_by",
            "excerpt": "Apex Defense Corp. is owned by Global Ventures Inc.",
            "confidence": 0.85,
        },
    ],
}


class FakeOllamaClient:
    model = "test-model"

    def __init__(self, payloads: list[dict] | None = None) -> None:
        self.payloads = payloads or [SAMPLE_OLLAMA_PAYLOAD]
        self.calls: list[dict[str, object]] = []

    def extract_intel(self, *, title: str, text: str, chunk_chars: int, chunk_overlap: int):
        self.calls.append(
            {
                "title": title,
                "text_len": len(text),
                "chunk_chars": chunk_chars,
                "chunk_overlap": chunk_overlap,
            }
        )
        return merge_chunk_payloads(self.payloads), len(self.payloads)


def test_parse_document_intel_ollama_mock():
    intel = parse_document_intel(
        source_path=Path("/tmp/sample_complaint.txt"),
        text=SAMPLE_COURT_DOC,
        ollama_client=FakeOllamaClient(),
    )
    assert intel.parser == "ollama"
    assert intel.model == "test-model"
    assert intel.case_numbers == ["24-CV-01982"]
    labels = {entity.label for entity in intel.entities}
    assert "John A. Smith" in labels
    assert "Meridian Holdings LLC" in labels
    relations = {rel.relation for rel in intel.relationships}
    assert "director_of" in relations
    assert "owned_by" in relations


def test_build_document_intel_from_payload():
    intel = build_document_intel_from_payload(
        source_path=Path("/tmp/sample.txt"),
        text=SAMPLE_COURT_DOC,
        payload=SAMPLE_OLLAMA_PAYLOAD,
        model="llama3.2",
        chunks_processed=3,
    )
    assert intel.entities
    assert intel.relationships
    assert intel.chunks_processed == 3


def test_extract_json_payload_strips_markdown_fence():
    raw = "```json\n" + json.dumps(SAMPLE_OLLAMA_PAYLOAD) + "\n```"
    payload = extract_json_payload(raw)
    assert payload["case_numbers"] == ["24-CV-01982"]


def test_merge_chunk_payloads_deduplicates_entities():
    payload_a = {
        "case_numbers": ["24-CV-01982"],
        "courts": [],
        "dates": ["January 15, 2024"],
        "amounts": [],
        "entities": [
            {
                "label": "John A. Smith",
                "entity_type": "person",
                "roles": ["defendant"],
                "excerpt": "Defendant: John A. Smith",
            }
        ],
        "relationships": [],
    }
    payload_b = {
        "case_numbers": ["24-CV-01982"],
        "courts": ["UNITED STATES DISTRICT COURT"],
        "dates": ["January 15, 2024"],
        "amounts": ["$2,500,000"],
        "entities": [
            {
                "label": "John A. Smith",
                "entity_type": "person",
                "roles": ["director"],
                "excerpt": "John A. Smith, director",
            },
            {
                "label": "Apex Defense Corp.",
                "entity_type": "organization",
                "roles": [],
                "excerpt": "director of Apex Defense Corp.",
            },
        ],
        "relationships": [
            {
                "source": "John A. Smith",
                "target": "Apex Defense Corp.",
                "relation": "director_of",
                "excerpt": "director of Apex Defense Corp.",
                "confidence": 0.9,
            }
        ],
    }
    merged = merge_chunk_payloads([payload_a, payload_b])
    assert merged["case_numbers"] == ["24-CV-01982"]
    assert merged["courts"] == ["UNITED STATES DISTRICT COURT"]
    assert len(merged["entities"]) == 2
    john = next(item for item in merged["entities"] if item["label"] == "John A. Smith")
    assert "defendant" in john["roles"]
    assert "director" in john["roles"]
    assert len(merged["relationships"]) == 1


def test_chunk_text_splits_long_pdf_like_text():
    pages = [f"[Page {index}]\n{'Lorem ipsum dolor sit amet. ' * 120}" for index in range(1, 11)]
    text = "\n\n".join(pages)
    chunks = chunk_text(text, chunk_chars=4000, overlap=200)
    assert len(chunks) > 1
    assert all(len(chunk) <= 5000 for chunk in chunks)


def test_chunk_text_preserves_short_documents():
    chunks = chunk_text(SAMPLE_COURT_DOC, chunk_chars=12000, overlap=200)
    assert chunks == [SAMPLE_COURT_DOC.strip()]


def test_intel_to_graph_payload():
    intel = parse_document_intel(
        source_path=Path("/tmp/sample_complaint.txt"),
        text=SAMPLE_COURT_DOC,
        ollama_client=FakeOllamaClient(),
    )
    nodes, edges = intel_to_graph_payload(intel)
    assert any(node["id"] == intel.document_id for node in nodes)
    assert any(edge["relation"] == "mentions" for edge in edges)
    assert all(edge["source_system"] == "document" for edge in edges)


def test_collect_document_paths(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "b.md").write_text("world", encoding="utf-8")
    paths = collect_document_paths([str(tmp_path)])
    assert len(paths) == 2


def test_extract_text_html(tmp_path):
    path = tmp_path / "page.html"
    path.write_text("<html><body><p>Hello <b>court</b></p></body></html>", encoding="utf-8")
    text = extract_text(path)
    assert "Hello court" in text


def test_extract_text_pdf_adds_page_markers(monkeypatch, tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    def fake_extract_pdf_pages(path: Path) -> list[str]:
        assert path == pdf_path
        return [
            "Page one content about Meridian Holdings LLC.",
            "Page two content about John A. Smith.",
        ]

    monkeypatch.setattr("wikinet.documents.extract.extract_pdf_pages", fake_extract_pdf_pages)
    text = extract_text(pdf_path)
    assert "[Page 1]" in text
    assert "[Page 2]" in text
    assert "Meridian Holdings LLC" in text
    assert "John A. Smith" in text


def test_ingest_documents_exports_graph(tmp_path):
    doc = tmp_path / "complaint.txt"
    doc.write_text(SAMPLE_COURT_DOC, encoding="utf-8")
    out_dir = tmp_path / "out"
    result = ingest_documents(
        [str(doc)],
        out_dir=str(out_dir),
        ollama_client=FakeOllamaClient(),
    )
    assert (out_dir / "nodes.json").exists()
    assert (out_dir / "edges.json").exists()
    assert (out_dir / "document_intel.json").exists()
    assert len(result.documents) == 1
    assert result.nodes_added > 0
    assert result.edges_added > 0
    report = json.loads((out_dir / "document_intel.json").read_text(encoding="utf-8"))
    assert report["nodes_added"] == result.nodes_added


def test_ingest_documents_chunks_long_text(tmp_path):
    doc = tmp_path / "long_filing.txt"
    doc.write_text("A" * 30_000, encoding="utf-8")
    client = FakeOllamaClient(
        payloads=[
            {
                "case_numbers": [],
                "courts": [],
                "dates": [],
                "amounts": [],
                "entities": [{"label": "Chunk Entity", "entity_type": "organization", "roles": [], "excerpt": "A"}],
                "relationships": [],
            },
            {
                "case_numbers": [],
                "courts": [],
                "dates": [],
                "amounts": [],
                "entities": [{"label": "Chunk Entity", "entity_type": "organization", "roles": [], "excerpt": "B"}],
                "relationships": [],
            },
            {
                "case_numbers": [],
                "courts": [],
                "dates": [],
                "amounts": [],
                "entities": [{"label": "Other Entity", "entity_type": "person", "roles": [], "excerpt": "C"}],
                "relationships": [],
            },
        ]
    )
    out_dir = tmp_path / "out_long"
    result = ingest_documents(
        [str(doc)],
        out_dir=str(out_dir),
        ollama_client=client,
        chunk_chars=12_000,
        chunk_overlap=200,
    )
    assert result.documents[0].chunks_processed == 3
    labels = {entity.label for entity in result.documents[0].entities}
    assert "Chunk Entity" in labels
    assert "Other Entity" in labels


def test_parse_document_intel_ollama_direct():
    intel = parse_document_intel_ollama(
        source_path=Path("/tmp/sample.txt"),
        text=SAMPLE_COURT_DOC,
        ollama_client=FakeOllamaClient(),
    )
    assert intel.parser == "ollama"
    assert intel.case_numbers
