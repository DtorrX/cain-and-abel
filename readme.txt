SYSTEM (role: architect-instructor)
You are an elite founder-engineer. Generate a production-quality Python 3.10+ project that crawls Wikidata + Wikipedia to build family trees and political network graphs for people/entities starting from seed inputs (names, page titles, categories, or Wikidata Q-IDs). Ship code that runs end-to-end with CLI, caching, unit tests, and docs.
Objectives
Resolve seeds → Wikidata Q-IDs.
Pull family relations via Wikidata properties:
father (P22), mother (P25), spouse (P26), child (P40), sibling (P3373), relative (P1038), partner (P451).
Pull political network edges:
position held (P39 → office Q-ID), member of political party (P102), member of (P463), employer (P108), educated at (P69), head of government/state (P6/P35), chairperson (P488), occupant (P2388).
Fallback to Wikipedia infobox parsing for missing relations (via MediaWiki API + infobox fields like father, mother, spouse, children, relations).
Build a directed multigraph using networkx with typed edges & provenance.
Output:
nodes.json & edges.json (normalized schema)
graph.graphml
graph.dot and (if Graphviz present) graph.png
CLI:
wikinet crawl --seed "Royal family of Bahrain" --max-depth 2 --mode family,political --lang en --out out/bahrain
wikinet crawl --category "House of Khalifa" --max-depth 2 --include-linked true
wikinet crawl --qid Q9696 --mode political
Flags: --max-nodes, --max-edges, --rate, --resume, --cache-dir, --lang, --only-family, --only-political.
Caching & resilience:
On-disk cache (SQLite or jsonl) for API and SPARQL responses (hash key = request).
Exponential backoff, retry on 429/5xx.
Respect User-Agent and throttle (default 5 req/s cap, configurable).
Disambiguation:
Prefer Wikidata Q-ID resolution.
If multiple candidates, rank by sitelinks count, label match score, and category/context overlap; log ambiguities.
Provenance:
Each edge stores: source_system (“wikidata”/“wikipedia”), property (e.g., P22), evidence_url, retrieved_at.
Validation:
wikinet validate out/bahrain checks schema, orphan nodes, and basic graph stats.
Include pytest tests (at least 6) for: Q-ID resolution, SPARQL parsing, infobox fallback, graph building, export, and CLI argument parsing.
Docs:
README.md with quick start, examples (Bahrain/UAE royals), and troubleshooting.
Mention rate limits and how to switch languages (--lang ar, --lang en).
Implementation details
Wikidata SPARQL endpoint: https://query.wikidata.org/sparql.
MediaWiki API for Wikipedia: https://{lang}.wikipedia.org/w/api.php.
Libraries: requests, networkx, pydantic, rich (logging/UX), tqdm, python-dotenv, optional pygraphviz. Avoid heavy RDF frameworks.
Project layout:
wikinet/
  __init__.py
  cli.py
  resolver.py         # names/pages/categories → Q-IDs
  wikidata.py         # SPARQL queries
  wikipedia.py        # infobox + page parsing
  graph.py            # model + builders
  export.py           # JSON, GraphML, DOT/PNG
  cache.py            # file/sqlite cache
  schemas.py          # pydantic Node/Edge
  utils.py
tests/
  test_resolver.py
  test_wikidata.py
  test_wikipedia.py
  test_graph.py
  test_export.py
  test_cli.py
pyproject.toml
README.md
.env.example
Provide ready-to-run SPARQL templates to fetch relations for a set of Q-IDs in batches.
Edge typing example:
("QX", "QY", {"relation":"father", "pid":"P22"})
("QX", "QZ", {"relation":"position_held", "pid":"P39", "office_qid":"Q..."} )
Export legend.json mapping relation → style (for DOT).
Ensure idempotent runs (--resume reads cache and appends new nodes only).
Ship a Makefile or uv/pip commands and minimal sample run in README.
Deliverables
Full codebase, fully runnable.
Example command lines to generate Bahrain & UAE royal graphs.
Tests passing via pytest -q.
Clear acceptance criteria in README.

Next-Step Insight (when Codex generates the full project)
Add edge styling rules (e.g., red = family, blue = political) in legend.json and apply in DOT/PNG export.
Implement rate limiting & caching (SQLite or disk JSONL) and a --resume flag.
Add language switching for Arabic (--lang ar) to resolve titles in local languages while still fetching English labels as fallback.
Expand relationship coverage (e.g., P3372 “genealogical ancestor”, P7/P35/P6 transitions, dynastic houses).
Ship pytest and a Makefile/uv project file to harden reproducibility.
Add a Streamlit or FastAPI frontend to browse graphs and click through to Wikipedia/Wikidata.
