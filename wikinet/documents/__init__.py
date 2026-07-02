"""Document ingestion and intel extraction layer."""

from .ingest import DocumentIngestResult, ingest_documents, merge_into_graph
from .ollama import OllamaClient, parse_document_intel_ollama
from .parse import DocumentIntel, parse_document_intel

__all__ = [
    "DocumentIntel",
    "DocumentIngestResult",
    "OllamaClient",
    "ingest_documents",
    "merge_into_graph",
    "parse_document_intel",
    "parse_document_intel_ollama",
]
