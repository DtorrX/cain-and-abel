.PHONY: install test lint crawl_uae_family export_uae_family_chart demo_uae_family_chart

install:
	pip install -e .[visual]

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

test:
	pytest -q

lint:
	python -m compileall wikinet
