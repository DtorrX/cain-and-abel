#!/usr/bin/env bash
# One-time local setup for cain-and-abel / wikinet on macOS or Linux.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VENV="$ROOT/.venv"

echo "==> Project: $ROOT"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON not found. Install Python 3.10+ first."
  echo "  macOS: brew install python@3.12"
  exit 1
fi

PY_VERSION="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "==> Python $PY_VERSION"

if [[ ! -d "$VENV" ]]; then
  echo "==> Creating virtualenv at .venv"
  if ! "$PYTHON" -m venv "$VENV" 2>/dev/null; then
    echo "WARN: Could not create .venv (install python3-venv / use Homebrew Python)."
    echo "      Continuing with system/user Python instead."
    VENV=""
  fi
fi

if [[ -n "$VENV" && -f "$VENV/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
fi

PY="$PYTHON"
if command -v python >/dev/null 2>&1; then
  PY=python
fi

echo "==> Upgrading pip"
"$PY" -m pip install -q -U pip

echo "==> Installing wikinet with document + dev extras"
"$PY" -m pip install -q -e ".[documents,dev]"

echo "==> Verifying CLI"
"$PY" -m wikinet.cli --help >/dev/null
"$PY" -m pytest tests/test_documents.py -q

OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
export OLLAMA_HOST
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2}"
export OLLAMA_MODEL

echo ""
echo "==> Ollama check ($OLLAMA_HOST)"
if curl -sf "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
  echo "    Ollama is running."
  if ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
    echo "    Model '$OLLAMA_MODEL' is available."
  else
    echo "    Model '$OLLAMA_MODEL' not found locally. Pull it with:"
    echo "      ollama pull $OLLAMA_MODEL"
  fi
else
  echo "    Ollama is NOT running at $OLLAMA_HOST"
  echo ""
  echo "    Install and start Ollama:"
  echo "      macOS:  brew install ollama && ollama serve"
  echo "      or download from https://ollama.com"
  echo ""
  echo "    Then pull a model:"
  echo "      ollama pull $OLLAMA_MODEL"
fi

echo ""
if [[ -n "$VENV" && -f "$VENV/bin/activate" ]]; then
  echo "==> Setup complete. Activate the venv in new shells:"
  echo "      source $VENV/bin/activate"
else
  echo "==> Setup complete (no venv — using current Python: $(command -v "$PY"))"
fi
echo ""
echo "==> Ingest a document (example):"
echo "      wikinet ingest path/to/94.pdf --out out/my_doc --log-level INFO"
echo ""
echo "==> Or use the helper script:"
echo "      ./scripts/run_local_ingest.sh path/to/94.pdf out/my_doc"
echo ""
echo "==> View results:"
echo "      cat out/my_doc/document_intel.json | head"
echo "      wikinet validate out/my_doc"
