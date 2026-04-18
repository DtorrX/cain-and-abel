# wikinet

Production-grade crawler for building enriched socio-political and corporate networks from Wikidata, Wikipedia, and the CIA World Leaders dataset. The crawler is designed to be cost-conscious, observable, and adaptable so you can pivot quickly from royal families to Israeli defense companies (or any other vertical) without rewriting core logic.

**Requirements:** Python 3.10 or newer (see `requires-python` in [pyproject.toml](pyproject.toml)).

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e .
```

For linting, formatting, types, and tests, use the dev extra (or `make install-dev`):

```bash
pip install -e ".[dev]"
# optional: Graphviz + Python bindings for richer DOT/PNG (see below)
pip install -e ".[visual]"
```

Run a crawl:

```bash
wikinet crawl --seed "House of Khalifa" --max-depth 2 --mode family,political --out out/bahrain
```

Validate the export:

```bash
wikinet validate out/bahrain
```

Full-mode crawl + enrichment:

```bash
# Combine family, political, security, and corporate layers
wikinet crawl --seed "Mohammed bin Zayed Al Nahyan" --mode full --max-depth 1 --out out/uae_full
wikinet enrich out/uae_full --taxonomy configs/gulf_taxonomy.json
```

## Local development (macOS)

1. **Python:** Install Python 3.10+ (e.g. [python.org](https://www.python.org/downloads/) or `brew install python@3.12`), then create a venv as in Quick start.
2. **Install targets:**

   | Command | Purpose |
   | --- | --- |
   | `make install` | Editable install: `pip install -e .` |
   | `make install-dev` | Adds dev tools (pytest, ruff, mypy, stubs): `pip install -e ".[dev]"` |
   | `make install-visual` | Adds `pydot` + `pygraphviz` for visualization helpers |
   | `make test` / `make lint` / `make typecheck` | Pytest, Ruff, Mypy (`wikinet` package only) |

3. **Graphviz, pydot, and pygraphviz**

   - **PNG export:** After a crawl, the exporter shells out to the Graphviz `dot` binary when present. On macOS: `brew install graphviz`.
   - **DOT via NetworkX:** The exporter prefers `networkx.drawing.nx_pydot.write_dot`, which needs the **pydot** Python package (included in the `visual` extra) plus the system `graphviz` install so pydot can talk to `dot`.
   - **pygraphviz:** Optional native bindings; included in `visual` for compatibility with sample scripts (for example under `out/uae_sample/`). It requires Graphviz headers; if `pip install pygraphviz` fails, rely on **pydot** + **brew graphviz** for CLI exports—the exporter falls back to a minimal hand-written DOT file if pydot is unavailable.

4. **Pre-commit (optional):** `pip install pre-commit && pre-commit install` then `pre-commit run --all-files`.

5. **Observability:** Set `WIKINET_LOG_LEVEL=DEBUG` or pass `--log-level DEBUG` on `crawl`. Crawl boundaries and HTTP retries emit grep-friendly lines via `wikinet.utils.log_fields` (for example `crawl_start | out=... seeds=...` and `http_retry | url=... status_code=...`).

## Repository layout

| Path | Role |
| --- | --- |
| [wikinet/](wikinet/) | Library and CLI: HTTP/cache, Wikidata/Wikipedia clients, graph build, export, `family_chart` |
| [tests/](tests/) | Pytest suite |
| [scripts/](scripts/) | `enrich_network`, `export_family_chart`, sample generators (also used by `wikinet enrich`) |
| [web/](web/) | D3-based dashboard (`family_chart_viewer.html`) copied next to crawl output as `index.html` |
| [configs/](configs/) | Sample taxonomy JSON for enrichment |
| `out/` | Default crawl output (gitignored once generated) |

## Features

- Resolves page titles, Wikipedia categories, and explicit Q-IDs to Wikidata entities with transparent logging.
- Fetches family, political, corporate governance, ownership, and business relations in batches while preserving the PID metadata that proves provenance.
- Falls back to Wikipedia infobox parsing when SPARQL results are sparse so that seed relationships are still represented (and clearly tagged as infobox-derived).
- Optionally augments seeds with the CIA World Leaders roster to automatically include ministers, defense chiefs, or other officials relevant to your investigation.
- Produces JSON, GraphML, DOT, and optional PNG outputs alongside a styling legend for visualization. A crawl diagnostics report (relation histograms, depth counts, warnings) can also be emitted for QA. Family crawls additionally emit a `family_chart.json` inspired by the [family-chart](https://github.com/donatso/family-chart) format so you can plug results straight into lightweight tree viewers.
- Uses SQLite-backed caching with retries, throttling, and resumable runs to stay frugal on bandwidth/API quotas.
- Rich CLI with `crawl`, `validate`, and configurable log levels, request budgets, and edge filters.
- Pytest suite covering resolver, SPARQL, infobox fallback, graph building, export, and CLI parsing.

### Conceptual pipeline

1. **Resolve** – Normalize arbitrary seeds (titles, categories, Q-IDs) into Wikidata IDs.
2. **Expand** – Use `GraphBuilder` to traverse Wikidata properties and optional CIA world-leader hints. Every edge keeps its relation type and PID so downstream tooling knows *why* two nodes are connected.
3. **Export** – Persist nodes/edges/GraphML/DOT/legend and, optionally, a `diagnostics.json` file summarizing the crawl.
4. **Enrich (optional)** – Run `scripts/enrich_network.py` to compute centrality, roles, country attribution, corporate layers, etc. Use `--taxonomy` to retarget the heuristics toward new verticals like Israeli defense primes or Latin American political families.

## Configuration

Environment variables may be placed in `.env` (optional) to configure proxies or HTTP settings. Use `--cache-dir` to relocate the SQLite cache if working across machines.

| Flag | Description |
| --- | --- |
| `--seed` | Seed page title or Q-ID (repeatable). |
| `--category` | Wikipedia category to expand into seeds. |
| `--qid` | Direct Wikidata Q-ID seed. |
| `--mode` | `family`, `political`, `security`, `corporate`, `full`, or comma-separated mix (default `family,political`). |
| `--max-depth` | BFS depth limit from seed nodes. |
| `--max-nodes` / `--max-edges` | Hard caps for exploration (useful for budgets). |
| `--rate` | Maximum requests per second (default 5). |
| `--resume` | Merge new crawl results with an existing output directory. |
| `--cache-dir` | Custom cache location (default `.wikinet-cache`). |
| `--log-level` | Toggle verbosity (DEBUG for deep dives, INFO for defaults). |
| `--report-path` | Persist crawl diagnostics (relation histograms, depth counts, warnings). |

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

## Family network dashboard (D3)

The viewer at [web/family_chart_viewer.html](web/family_chart_viewer.html) is a **self-contained** dashboard: it loads [D3 v7](https://d3js.org/) from jsDelivr (no `npm install` required to view). It supports both JSON shapes you might have next to `index.html`:

| Source | `family_chart.json` shape |
| --- | --- |
| `wikinet crawl` → `export_graph` | Object: `people`, `unions`, `relationships`, `layout`, `summary` |
| `python scripts/export_family_chart.py …` | Legacy array: `[{ id, data, rels }, …]` (same shape the old [family-chart](https://github.com/donatso/family-chart) npm widget used) |

Features: force-directed graph with **zoom/pan**, **search** (dims non-matches), **drag** nodes, summary chips, edge legend, hover detail. Union nodes (native export) render as compact “household” nodes.

```bash
make run-demo
# Open http://localhost:8000/out/uae/ in your browser (serve repo root, as the Makefile does)
```

`make run-demo` runs the same steps as `make demo_uae_family_chart`: crawl UAE seeds, regenerate `family_chart.json` via the script, copy the dashboard to `out/uae/index.html`, and start `python3 -m http.server 8000`.

**Note:** If you only ran `wikinet crawl … --out out/my_run` without the script exporter, overwrite or copy `family_chart.json` from that directory—the dashboard still works on the **native** object format produced by the crawler.

### `family_chart.json` schema

The viewer expects a list of people with identifiers, presentation data, and relationships:

```jsonc
[
  {
    "id": "Q123",
    "data": {
      "first name": "Fatima",
      "last name": "bint Zayed",
      "label": "Sheikha Fatima bint Zayed Al Nahyan",
      "birthday": "1949-07-15",
      "gender": "F",
      "qid": "Q123"
    },
    "rels": {
      "spouses": ["Q456"],
      "children": ["Q789"],
      "parents": ["Q001", "Q002"]
    }
  }
]
```

To adapt the viewer to any crawl, replace `out/uae` with your run directory (e.g., `out/bahrain`), rerun the exporter target, and open `http://localhost:8000/out/<run>/`.

### Israeli defense-industrial complex (arbitrary, non-royal example)

```bash
wikinet crawl \
  --seed "Israel Aerospace Industries" \
  --seed "Rafael Advanced Defense Systems" \
  --category "Defense companies of Israel" \
  --mode family,political \
  --max-depth 1 \
  --report-path out/israel/diagnostics.json \
  --out out/israel

# Optionally enrich with domain-specific taxonomy overrides
python scripts/enrich_network.py \
  --nodes out/israel/nodes.json \
  --edges out/israel/edges.json \
  --out-nodes out/israel/enriched_nodes.json \
  --out-edges out/israel/enriched_edges.json \
  --taxonomy configs/israel_taxonomy.json
```

The diagnostics report captures how many times each relation/property appeared, the BFS depth distribution, and any infobox warnings so you can rapidly judge whether critical relationships were captured.

The resulting `graph.graphml` and `graph.dot` files can be opened with Gephi, Cytoscape, or Graphviz for exploration. If Graphviz is installed, `graph.png` provides a ready-to-share visualization.

### API snippet

```python
from wikinet.api import run_pipeline, run_enrichment

graph = run_pipeline(seeds=["House of Khalifa"], mode="full", max_depth=1, out_dir="out/bahrain_full")
run_enrichment("out/bahrain_full")
```

## Debugging and observability

- Use `--log-level DEBUG` to emit the SPARQL queries, resolver calls, and infobox fallbacks.
- Provide `--report-path` to save a structured JSON blob with counts per relation, warnings, and seed metadata for later audits.
- `wikinet validate out/run` double-checks that every edge references a persisted node.
- The `wikinet.graph.CrawlStats` structure is also accessible directly if you embed Wikinet inside another system (e.g., to push metrics into your own dashboards).

## Working with arbitrary seeds

- `--seed` accepts any Wikipedia title or Wikidata Q-ID. Resolver fallbacks ensure ambiguous strings still map to the most likely entity.
- `--category` can bootstrap entire sectors (e.g., `Defense companies of Israel`, `Women members of the Knesset`).
- CIA world-leader augmentation looks up country labels in the crawl and automatically pulls the ministry/security roster for that country so you always capture the top brass, not just royals.
- Relationship metadata (PID + human-readable relation) is preserved end-to-end. When the exporter writes `edges.json`, every edge still carries `pid`, `relation`, `source_system`, and `evidence_url`.

### Royal-family hierarchy clusters

When `--mode family` is enabled, Wikinet groups kinship edges into clustered
family components and annotates each node with two helpful attributes:

- `clusters`: stable identifiers like `royal_family_1` that keep spouses,
  siblings, parents, and children together for visualization or post-processing
  (e.g., filtering to just the ruling house in Gephi).
- `family_hierarchy_level`: a generation-style level (0 for progenitors,
  +1 for each descendant step) that keeps spouses/partners on the same level
  and walks parent/child edges downward. This makes kinship layers apparent in
  DOT/GraphML exports without extra tooling.

If node relationships appear sparse in your viewer, double-check that you ran
with `--mode family` (or left it at the default `family,political`) and that
the generated `edges.json` carries the expected `relation` keys. The exporter
preserves these attributes so layout tools can color/label edges correctly.

## Enrichment script and taxonomy overrides

The optional `scripts/enrich_network.py` utility annotates the exported graph with graph metrics, inferred roles/countries, semantic edge layers, and time ranges. It now supports a `--taxonomy` flag that points to a JSON file with overrides so you can retarget heuristics away from Gulf royals toward any custom sector:

```json
{
  "role_keywords": {
    "defense_exec": ["defense", "weapons", "missile"],
    "cyber": ["cyber", "infosec", "intelligence"]
  },
  "country_keywords": {
    "Israel": ["idf", "israeli", "tel aviv"],
    "United States": ["pentagon", "dod"]
  },
  "edge_type_by_pid": {
    "P355": "corporate_structure",
    "P127": "ownership"
  }
}
```

Pass that file via `--taxonomy` and the enrichment pipeline will classify nodes and edges using your vocab, enabling quick pivots into new investigative terrains without touching the codebase.

## Tests

```bash
make test
# equivalent: python -m pytest
```

When running CI locally, consider `pytest -q -k crawl` for just the crawl-specific behavior, or use `pytest -q --maxfail=1` for a faster feedback loop.

GitHub Actions runs `ruff check`, `ruff format --check`, `mypy wikinet`, and pytest on Python 3.10 and 3.12 (see [.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Troubleshooting

- Respect Wikimedia rate limits. Increase `--rate` cautiously; the default 5 req/s stays under the public limit.
- Empty results often indicate ambiguous seeds; try `--qid QXXXX` for disambiguation or add context-specific categories.
- For multilingual investigations, switch `--lang` and re-run.
- If you suspect missing relations, inspect the diagnostics report and verify whether the relevant PIDs are in scope. You can add temporary Wikidata properties via `--mode` (set to `family`, `political`, or both) or by editing `wikinet/wikidata.py` to add more PIDs.
- Infobox fallbacks are logged per node; use `--log-level DEBUG` to monitor when they fire.

## Acceptance criteria checklist

- [x] CLI supports crawl and validate workflows
- [x] End-to-end export includes JSON/GraphML/DOT/legend (PNG optional)
- [x] SQLite-backed caching with retries and throttling
- [x] Unit tests for resolver, SPARQL, infobox fallback, graph build, export, CLI
- [x] Documentation with Bahrain, UAE, and Israeli defense examples
