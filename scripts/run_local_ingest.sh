#!/usr/bin/env bash
# Local setup + ingest helper for wikinet
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT"
export PATH="$HOME/.local/bin:$PATH"

DOC="${1:-docs/sample_complaint.txt}"
OUT="${2:-out/local_ingest}"

export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2}"

echo "==> Installing wikinet..."
python3 -m pip install -q -e ".[documents,dev]"

if ! curl -sf "$OLLAMA_HOST/api/tags" >/dev/null; then
  echo "ERROR: Ollama is required but not reachable at $OLLAMA_HOST"
  echo "Start Ollama, pull a model (e.g. ollama pull llama3.2), and retry."
  exit 1
fi

echo "==> Ingesting: $DOC -> $OUT (Ollama model=$OLLAMA_MODEL)"
python3 -m wikinet.cli ingest "$DOC" \
  --ollama-host "$OLLAMA_HOST" \
  --ollama-model "$OLLAMA_MODEL" \
  --out "$OUT" \
  --log-level INFO

python3 -m wikinet.cli validate "$OUT"
echo "==> Done. See $OUT/document_intel.json"
