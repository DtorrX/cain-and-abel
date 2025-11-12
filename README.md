# wikinet

Production-grade crawler for building enriched family trees and political networks from Wikidata and Wikipedia.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run a crawl:

```bash
wikinet crawl --seed "House of Khalifa" --max-depth 2 --mode family,political --out out/bahrain
```

Validate the export:

```bash
wikinet validate out/bahrain
```

## Features

- Resolves page titles, categories, and direct Q-IDs to Wikidata items.
- Fetches family (P22, P25, P26, P40, P3373, P1038, P451) and political (P39, P102, P463, P108, P69, P6, P35, P488, P2388) relations in batches.
- Falls back to Wikipedia infobox parsing when SPARQL lacks family data.
- Produces JSON, GraphML, DOT, and optional PNG outputs alongside a styling legend for visualization.
- Uses SQLite-backed caching with retries, throttling, and resumable runs.
- Rich CLI with `crawl` and `validate` commands plus configurable depth and rate limits.
- Pytest suite covering resolver, SPARQL parsing, infobox fallback, graph building, export, and CLI parsing.

## Configuration

Environment variables may be placed in `.env` (optional) to configure proxies or HTTP settings. Use `--cache-dir` to relocate the SQLite cache if working across machines.

| Flag | Description |
| --- | --- |
| `--seed` | Seed page title or Q-ID (repeatable). |
| `--category` | Wikipedia category to expand into seeds. |
| `--qid` | Direct Wikidata Q-ID seed. |
| `--mode` | `family`, `political`, or `family,political` (default). |
| `--max-depth` | BFS depth limit from seed nodes. |
| `--max-nodes` / `--max-edges` | Hard caps for exploration (useful for budgets). |
| `--rate` | Maximum requests per second (default 5). |
| `--resume` | Merge new crawl results with an existing output directory. |
| `--cache-dir` | Custom cache location (default `.wikinet-cache`). |

## Example pipelines

### Bahrain royal network

```bash
wikinet crawl --seed "Royal family of Bahrain" --max-depth 2 --lang en --out out/bahrain
wikinet validate out/bahrain
```

### UAE royal & political elite (test case)

```bash
wikinet crawl --seed "House of Nahyan" --seed "Mohammed bin Rashid Al Maktoum" --max-depth 2 --mode family,political --out out/uae
wikinet validate out/uae
```

The resulting `graph.graphml` and `graph.dot` files can be opened with Gephi, Cytoscape, or Graphviz for exploration. If Graphviz is installed, `graph.png` provides a ready-to-share visualization.

## Tests

```bash
pytest -q
```

## Troubleshooting

- Respect Wikimedia rate limits. Increase `--rate` cautiously; the default 5 req/s stays under the public limit.
- Empty results often indicate ambiguous seeds; try `--qid QXXXX` for disambiguation or add context-specific categories.
- For multilingual investigations, switch `--lang` and re-run.

## Acceptance criteria checklist

- [x] CLI supports crawl and validate workflows
- [x] End-to-end export includes JSON/GraphML/DOT/legend (PNG optional)
- [x] SQLite-backed caching with retries and throttling
- [x] Unit tests for resolver, SPARQL, infobox fallback, graph build, export, CLI
- [x] Documentation with Bahrain and UAE examples
