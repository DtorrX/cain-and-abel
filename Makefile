.PHONY: install test lint

install:
pip install -e .[visual]

test:
pytest -q

lint:
python -m compileall wikinet
