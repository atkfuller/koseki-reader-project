VENV := ./venv/bin
PDF  := data/raw/takagi.pdf

.PHONY: setup text test clean

setup:
	~/.pyenv/versions/3.11.9/bin/python -m venv venv
	$(VENV)/pip install -q --upgrade pip
	$(VENV)/pip install -q -r requirements-core.txt pytest

text:
	$(VENV)/python scripts/pdf_to_text.py $(PDF)

test:
	$(VENV)/python -m pytest tests -q

clean:
	rm -rf out/text
