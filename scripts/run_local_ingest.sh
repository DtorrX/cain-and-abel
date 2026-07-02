#!/usr/bin/env bash
# Local setup + ingest helper for wikinet
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT"
export PATH="$HOME/.local/bin:$PATH"

DOC="${1:-docs/sample_complaint.txt}"
OUT="${2:-out/local_ingest}"
PARSER="${WIKINET_DOC_PARSER:-ollama}"

echo "==> Installing wikinet..."
python3 -m pip install -q -e ".[documents]"

if [[ "$PARSER" == "ollama" ]]; then
  export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
  export OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2}"
  if ! curl -sf "$OLLAMA_HOST/api/tags" >/dev/null; then
    echo "Ollama not reachable at $OLLAMA_HOST — falling back to rules parser"
    PARSER=rules
  fi
fi

echo "==> Ingesting: $DOC -> $OUT (parser=$PARSER)"
if [[ "$PARSER" == "rules" ]]; then
  python3 -m wikinet.cli ingest "$DOC" \
    --parser rules \
    --patterns configs/legal_patterns.json \
    --out "$OUT" \
    --log-level INFO
else
  python3 -m wikinet.cli ingest "$DOC" \
    --parser ollama \
    --ollama-host "$OLLAMA_HOST" \
    --ollama-model "$OLLAMA_MODEL" \
    --out "$OUT" \
    --log-level INFO
fi

python3 -m wikinet.cli validate "$OUT"
echo "==> Done. See $OUT/document_intel.json"
