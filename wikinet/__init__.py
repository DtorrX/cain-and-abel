"""wikinet package initialization."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__", "run_pipeline", "run_enrichment", "run_document_ingest"]


def __getattr__(name: str):
    if name in {"run_pipeline", "run_enrichment", "run_document_ingest"}:
        from . import api

        return getattr(api, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


try:
    __version__ = version("wikinet")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.1.0"
