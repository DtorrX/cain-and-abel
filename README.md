# wikinet

Production-grade crawler for building enriched socio-political and corporate networks from Wikidata, Wikipedia, and the CIA World Leaders dataset. The crawler is designed to be cost-conscious, observable, and adaptable so you can pivot quickly from royal families to Israeli defense companies (or any other vertical) without rewriting core logic.

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

- Resolves page titles, Wikipedia categories, and explicit Q-IDs to Wikidata entities with transparent logging.
- Fetches family, political, corporate governance, ownership, and business relations in batches while preserving the PID metadata that proves provenance.
- Falls back to Wikipedia infobox parsing when SPARQL results are sparse so that seed relationships are still represented (and clearly tagged as infobox-derived).
- Optionally augments seeds with the CIA World Leaders roster to automatically include ministers, defense chiefs, or other officials relevant to your investigation.
- Produces JSON, GraphML, DOT, and optional PNG outputs alongside a styling legend for visualization. A crawl diagnostics report (relation histograms, depth counts, warnings) can also be emitted for QA.
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
| `--mode` | `family`, `political`, or `family,political` (default). |
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
pytest -q
```

When running CI locally, consider `pytest -q -k crawl` for just the crawl-specific behavior, or use `pytest -q --maxfail=1` for a faster feedback loop.

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
