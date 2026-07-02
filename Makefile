.PHONY: install install-dev install-documents install-visual test lint typecheck run-demo setup-local ingest-demo \
	crawl_uae_family export_uae_family_chart demo_uae_family_chart .demo_copy

install:
	python -m pip install -e .

install-dev:
	python -m pip install -e ".[dev]"

install-documents:
	python -m pip install -e ".[documents]"

install-visual:
	python -m pip install -e ".[visual]"

setup-local:
	bash scripts/setup_local.sh

ingest-demo:
	bash scripts/run_local_ingest.sh docs/sample_complaint.txt out/local_ingest

test:
	python -m pytest

lint:
	python -m ruff check wikinet tests scripts

typecheck:
	python -m mypy wikinet

run-demo:
	@$(MAKE) demo_uae_family_chart

crawl_uae_family:
	@if [ -d .venv ]; then . .venv/bin/activate; fi; \
	wikinet crawl \
		--seed "House of Nahyan" \
		--seed "Mohammed bin Rashid Al Maktoum" \
		--max-depth 2 \
		--mode family,political \
		--out out/uae

export_uae_family_chart: crawl_uae_family
	@if [ -d .venv ]; then . .venv/bin/activate; fi; \
	python scripts/export_family_chart.py \
		--nodes out/uae/nodes.json \
		--edges out/uae/edges.json \
		--out out/uae/family_chart.json

.demo_copy:
	@mkdir -p out/uae
	@cp web/family_chart_viewer.html out/uae/index.html

DemoMessage = "Serving ./out/uae at http://localhost:8000/out/uae/"

demo_uae_family_chart: export_uae_family_chart .demo_copy
	@echo $(DemoMessage)
	python3 -m http.server 8000
