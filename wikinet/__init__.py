"""wikinet package initialization."""

from importlib.metadata import PackageNotFoundError, version

from .api import run_enrichment, run_pipeline

__all__ = ["__version__", "run_pipeline", "run_enrichment"]

try:
    __version__ = version("wikinet")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.1.0"
