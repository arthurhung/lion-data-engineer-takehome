PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python

.PHONY: setup source-integrity profile build-base validate-base lint test clean

OUTPUT_DIR ?= output/quality
EVIDENCE_DIR ?= docs/evidence/phase_01
OUTPUT_DB ?= output/warehouse/phase_02.duckdb
PHASE2_EVIDENCE_DIR ?= output/warehouse/phase_02_evidence

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install -e ".[dev]"

source-integrity:
	shasum -a 256 -c docs/source_manifest.sha256

profile:
	$(VENV_PYTHON) -m lion_de_exam.profiling --output-dir "$(OUTPUT_DIR)" --evidence-dir "$(EVIDENCE_DIR)"

build-base:
	$(VENV_PYTHON) -m lion_de_exam.warehouse --output-db "$(OUTPUT_DB)" --evidence-dir "$(PHASE2_EVIDENCE_DIR)"

validate-base:
	$(VENV_PYTHON) -m lion_de_exam.reconciliation --output-db "$(OUTPUT_DB)" --evidence-dir "$(PHASE2_EVIDENCE_DIR)"

lint:
	$(VENV_PYTHON) -m ruff check src tests

test:
	$(VENV_PYTHON) -m pytest

clean:
	$(VENV_PYTHON) -c "from pathlib import Path; import shutil; [shutil.rmtree(p) for p in (Path('.pytest_cache'), Path('.ruff_cache')) if p.exists()]"
