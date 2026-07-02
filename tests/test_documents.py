"""Tests for document intel extraction."""

from pathlib import Path

from wikinet.documents.extract import collect_document_paths, extract_text
from wikinet.documents.ingest import ingest_documents
from wikinet.documents.parse import (
    intel_to_graph_payload,
    load_patterns,
    parse_document_intel,
)

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


def test_parse_court_document_intel():
    intel = parse_document_intel(
        source_path=Path("/tmp/sample_complaint.txt"),
        text=SAMPLE_COURT_DOC,
    )
    assert intel.case_numbers
    assert any("district court" in court.lower() for court in intel.courts)
    assert "2024-01-15" not in intel.dates  # January format
    assert any("January" in date for date in intel.dates)
    assert intel.amounts
    labels = {entity.label for entity in intel.entities}
    assert "Meridian Holdings LLC" in labels
    assert "John A. Smith" in labels
    assert "Apex Defense Corp" in labels or "Apex Defense Corp." in labels
    relations = {rel.relation for rel in intel.relationships}
    assert "director_of" in relations
    assert "employed_by" in relations
    assert "owned_by" in relations


def test_intel_to_graph_payload():
    intel = parse_document_intel(
        source_path=Path("/tmp/sample_complaint.txt"),
        text=SAMPLE_COURT_DOC,
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


def test_ingest_documents_exports_graph(tmp_path):
    doc = tmp_path / "complaint.txt"
    doc.write_text(SAMPLE_COURT_DOC, encoding="utf-8")
    out_dir = tmp_path / "out"
    result = ingest_documents([str(doc)], out_dir=str(out_dir))
    assert (out_dir / "nodes.json").exists()
    assert (out_dir / "edges.json").exists()
    assert (out_dir / "document_intel.json").exists()
    assert len(result.documents) == 1
    assert result.nodes_added > 0


def test_load_custom_patterns(tmp_path):
    custom = tmp_path / "patterns.json"
    custom.write_text('{"case_number": ["(?i)custom case ([0-9]+)"]}', encoding="utf-8")
    patterns = load_patterns(custom)
    intel = parse_document_intel(
        source_path=Path("/tmp/custom.txt"),
        text="Custom case 999 filed today.",
        patterns=patterns,
    )
    assert intel.case_numbers == ["999"]
