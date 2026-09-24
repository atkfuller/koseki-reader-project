VENV := ./venv/bin
PDF  := data/raw/takagi.pdf

.PHONY: setup pages bench tier1 test clean

setup:
	~/.pyenv/versions/3.11.9/bin/python -m venv venv
	$(VENV)/pip install -q --upgrade pip
	$(VENV)/pip install -q -r requirements-core.txt pytest
	~/.pyenv/versions/3.11.9/bin/python -m venv venvs/ndl
	./venvs/ndl/bin/pip install -q --upgrade pip
	./venvs/ndl/bin/pip install -q -r requirements-ndl.txt
	~/.pyenv/versions/3.11.9/bin/python -m venv venvs/yomitoku
	./venvs/yomitoku/bin/pip install -q --upgrade pip
	./venvs/yomitoku/bin/pip install -q -r requirements-yomitoku.txt

pages:
	mkdir -p data/pages
	pdftoppm -r 300 -png $(PDF) data/pages/p

bench:
	$(VENV)/python scripts/run_bench.py

tier1:
	$(VENV)/python scripts/read_tier1.py

test:
	$(VENV)/python -m pytest tests -q

clean:
	rm -rf out/variants out/bench
