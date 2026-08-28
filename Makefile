PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python

.PHONY: setup source-integrity profile build-base validate-base build rerun-proof phase3-acceptance final-acceptance lint test clean

OUTPUT_DIR ?= output/quality
EVIDENCE_DIR ?= docs/evidence/phase_01
OUTPUT_DB ?= output/warehouse/phase_02.duckdb
PHASE2_EVIDENCE_DIR ?= output/warehouse/phase_02_evidence
PHASE3_OUTPUT_DB ?= output/warehouse/phase_03.duckdb
PHASE3_EVIDENCE_DIR ?= output/warehouse/phase_03_evidence
PHASE3_CANONICAL_EVIDENCE_DIR ?= docs/evidence/phase_03
ACCEPT_ALLOW_NETWORK ?= 0
ACCEPT_PYTHON ?= python3

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

build:
	$(VENV_PYTHON) -m lion_de_exam.incremental build --output-db "$(PHASE3_OUTPUT_DB)" --evidence-dir "$(PHASE3_EVIDENCE_DIR)"

rerun-proof:
	$(VENV_PYTHON) -m lion_de_exam.incremental rerun-proof --output-db "$(PHASE3_OUTPUT_DB)" --evidence-dir "$(PHASE3_EVIDENCE_DIR)"

phase3-acceptance:
	$(VENV_PYTHON) -m lion_de_exam.incremental acceptance --canonical-evidence-dir "$(PHASE3_CANONICAL_EVIDENCE_DIR)"

final-acceptance:
	@test -n "$(ACCEPT_COMMIT)" || { echo "ACCEPT_COMMIT is required" >&2; exit 2; }
	@test -n "$(ACCEPT_OUTPUT)" || { echo "ACCEPT_OUTPUT is required" >&2; exit 2; }
	@test "$(ACCEPT_ALLOW_NETWORK)" = "0" -o "$(ACCEPT_ALLOW_NETWORK)" = "1" || { echo "ACCEPT_ALLOW_NETWORK must be 0 or 1" >&2; exit 2; }
	$(PYTHON) scripts/final_acceptance.py \
		--source-repo . \
		--tested-commit "$(ACCEPT_COMMIT)" \
		--output-json "$(ACCEPT_OUTPUT)" \
		--python "$(ACCEPT_PYTHON)" \
		$(if $(filter 1,$(ACCEPT_ALLOW_NETWORK)),--allow-network-install,)

lint:
	$(VENV_PYTHON) -m ruff check src tests scripts

test:
	$(VENV_PYTHON) -m pytest

clean:
	$(VENV_PYTHON) -c "from pathlib import Path; import shutil; [shutil.rmtree(p) for p in (Path('.pytest_cache'), Path('.ruff_cache')) if p.exists()]"
