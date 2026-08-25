PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python

.PHONY: setup source-integrity lint test clean

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install -e ".[dev]"

source-integrity:
	shasum -a 256 -c docs/source_manifest.sha256

lint:
	$(VENV_PYTHON) -m ruff check src tests

test:
	$(VENV_PYTHON) -m pytest

clean:
	$(VENV_PYTHON) -c "from pathlib import Path; import shutil; [shutil.rmtree(p) for p in (Path('.pytest_cache'), Path('.ruff_cache')) if p.exists()]"
