from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/final_acceptance.py"
SPEC = importlib.util.spec_from_file_location("final_acceptance", SCRIPT)
assert SPEC and SPEC.loader
final_acceptance = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = final_acceptance
SPEC.loader.exec_module(final_acceptance)

VALID_COMMIT = "a" * 40


def _payload() -> dict[str, object]:
    return {
        "artifact_hygiene": {
            "credential_pattern_matches": 0,
            "rejected_artifacts": 0,
        },
        "clone_mode": "local_git_clone_no_local_tracked_only",
        "commands": [
            {
                "exit_status": 0,
                "logical_name": name,
                **({"network_install": True} if name == "dependency_install" else {}),
            }
            for name in final_acceptance.required_command_names()
        ],
        "dependency_versions": {
            "duckdb": "1.5.5",
            "pandas": "2.3.3",
            "pip": "24.0",
            "pytest": "9.1.1",
            "ruff": "0.16.4",
        },
        "documentation": {
            "final_acceptance_validator": "covered_by_full_suite",
            "final_documentation_validator": "covered_by_full_suite",
            "passed": True,
        },
        "known_limitations": ["Dependency ranges are resolved at execution time."],
        "lint": {"passed": True},
        "phase_1": {
            "canonical_bundle_sha256": final_acceptance.PHASE_1_SHA256,
            "detector_count": 47,
            "fresh_profile": True,
        },
        "phase_2": {
            "canonical_bundle_sha256": final_acceptance.PHASE_2_SHA256,
            "check_count": 32,
            "current_members": 7_972,
            "fact_rows": 99_612,
            "fresh_database": True,
            "known_member_versions": 8_745,
            "violations": 0,
        },
        "phase_3": {
            "base_through_day_3": True,
            "canonical_bundle_sha256": final_acceptance.PHASE_3_SHA256,
            "canonical_evidence_byte_identical": True,
            "check_count": 41,
            "fact_rows": 109_888,
            "file_registry": True,
            "full_sequence_replay": True,
            "metrics_source": "committed_bundle_verified_equal_to_clean_runs",
            "quarantined_orders": 2_172,
            "rollback_coverage": "covered_by_full_suite",
            "single_file_replay": True,
            "violations": 0,
        },
        "python_version": "3.12.3",
        "schema_version": 1,
        "source_integrity": {"files_checked": 19, "violations": 0},
        "status": "PASSED",
        "submission_matrix": [
            {"item": "required_deliverables", "present": True, "required": True}
        ],
        "tested_commit": VALID_COMMIT,
        "tests": {
            "passed": True,
            "passed_count": 137,
            "rollback_coverage": "covered_by_full_suite",
        },
    }


@pytest.mark.parametrize("value", ["", "abc", "A" * 40, "g" * 40, "a" * 39, "a" * 41])
def test_invalid_short_or_non_hex_commit_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="40-character lowercase hexadecimal"):
        final_acceptance.validate_full_commit_sha(value)


def test_commit_object_is_verified(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        final_acceptance,
        "_run_git",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="commit\n"),
    )
    final_acceptance.validate_commit_object(tmp_path, VALID_COMMIT)

    monkeypatch.setattr(
        final_acceptance,
        "_run_git",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="blob\n"),
    )
    with pytest.raises(ValueError, match="commit object"):
        final_acceptance.validate_commit_object(tmp_path, VALID_COMMIT)


def test_schema_contract_and_dependency_versions_are_required() -> None:
    payload = _payload()
    final_acceptance.validate_evidence(payload)

    missing_top_level = _payload()
    missing_top_level.pop("phase_3")
    with pytest.raises(ValueError, match="invalid evidence schema"):
        final_acceptance.validate_evidence(missing_top_level)

    missing_dependency = _payload()
    del missing_dependency["dependency_versions"]["ruff"]  # type: ignore[index]
    with pytest.raises(ValueError, match="exactly the required packages"):
        final_acceptance.validate_evidence(missing_dependency)

    wrong_schema = _payload()
    wrong_schema["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version must be 1"):
        final_acceptance.validate_evidence(wrong_schema)

    non_integer_exit = _payload()
    non_integer_exit["commands"][0]["exit_status"] = False  # type: ignore[index]
    with pytest.raises(ValueError, match="exit_status must be an integer"):
        final_acceptance.validate_evidence(non_integer_exit)


def test_canonical_json_is_sorted_utf8_lf_and_has_trailing_newline() -> None:
    encoded = final_acceptance.canonical_json(_payload())
    assert encoded.endswith(b"\n")
    assert b"\r\n" not in encoded
    expected = json.dumps(_payload(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    assert encoded == expected.encode()


@pytest.mark.parametrize("include_file_names", [False, True])
def test_evidence_bundle_is_recomputed_from_bytes(
    tmp_path: Path, include_file_names: bool
) -> None:
    names = ("first.json", "second.json")
    contents = {"first.json": b'{"value": 1}\n', "second.json": b'{"value": 2}\n'}
    bundle = hashlib.sha256()
    entries = []
    for name in names:
        (tmp_path / name).write_bytes(contents[name])
        entries.append({"file": name, "sha256": hashlib.sha256(contents[name]).hexdigest()})
        if include_file_names:
            bundle.update(name.encode() + b"\n")
        bundle.update(contents[name])
    expected = bundle.hexdigest()
    (tmp_path / "evidence_manifest.json").write_text(
        json.dumps({"canonical_bundle_sha256": expected, "files": entries}),
        encoding="utf-8",
    )

    assert (
        final_acceptance._verify_evidence_bundle(
            tmp_path,
            expected,
            names,
            include_file_names=include_file_names,
        )
        == expected
    )

    (tmp_path / "second.json").write_bytes(b'{"value": 3}\n')
    with pytest.raises(final_acceptance.AcceptanceError, match="evidence file checksum mismatch"):
        final_acceptance._verify_evidence_bundle(
            tmp_path,
            expected,
            names,
            include_file_names=include_file_names,
        )


def test_volatile_keys_and_absolute_paths_are_rejected() -> None:
    volatile = _payload()
    volatile["documentation"]["runtime_timestamp"] = (  # type: ignore[index]
        "2026-08-28T00:00:00Z"
    )
    with pytest.raises(ValueError, match="volatile evidence key"):
        final_acceptance.validate_evidence(volatile)

    absolute = _payload()
    absolute["known_limitations"] = ["/tmp/private-run"]
    with pytest.raises(ValueError, match="absolute paths"):
        final_acceptance.validate_evidence(absolute)

    credential = _payload()
    credential["known_limitations"] = ["ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890"]
    with pytest.raises(ValueError, match="credential value"):
        final_acceptance.validate_evidence(credential)


def test_passed_evidence_requires_zero_exit_status_and_clean_metrics() -> None:
    failed_command = _payload()
    failed_command["commands"][1]["exit_status"] = 1  # type: ignore[index]
    with pytest.raises(ValueError, match="every command to exit zero"):
        final_acceptance.validate_evidence(failed_command)

    wrong_metric = _payload()
    wrong_metric["phase_3"]["fact_rows"] = 1  # type: ignore[index]
    with pytest.raises(ValueError, match="invalid phase_3 results"):
        final_acceptance.validate_evidence(wrong_metric)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("docs/ai/transcripts/phase_07.jsonl", None),
        ("LionDEExam/candidate_package/dataset/orders.csv", None),
        ("output/runtime.duckdb", "runtime_output"),
        ("output/data.parquet", "runtime_output"),
        ("cache/results.sqlite3", "runtime_output"),
        ("logs/run.log", "runtime_output"),
        (".venv/bin/python", "runtime_or_cache_directory"),
        (".pytest_cache/state", "runtime_or_cache_directory"),
        (".coverage.worker-1", "secret_or_runtime_file"),
        ("secrets/private.pem", "credential_file"),
        (".env.production", "secret_or_runtime_file"),
    ],
)
def test_artifact_hygiene_classification(path: str, expected: str | None) -> None:
    assert final_acceptance.classify_tracked_artifact(path) == expected


def test_command_matrix_is_complete_and_phase3_runs_once(tmp_path: Path) -> None:
    plan = final_acceptance.acceptance_command_matrix(
        tmp_path / "repo", tmp_path / "venv", tmp_path / "runtime", network=False
    )
    names = [item.logical_name for item in plan]
    assert tuple(names) == final_acceptance.required_command_names()
    assert names.count("phase_3_acceptance") == 1
    install = next(item for item in plan if item.logical_name == "dependency_install")
    assert "--no-index" in install.argv
    assert ".[dev]" in install.argv

    network_plan = final_acceptance.acceptance_command_matrix(
        tmp_path / "repo", tmp_path / "venv", tmp_path / "runtime", network=True
    )
    network_install = next(
        item for item in network_plan if item.logical_name == "dependency_install"
    )
    assert "--no-index" not in network_install.argv


def test_failure_propagates_without_running_followup_commands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        final_acceptance.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 9, "", "failure"),
    )
    spec = final_acceptance.CommandSpec("lint", ("make", "lint"), tmp_path)
    with pytest.raises(final_acceptance.AcceptanceError, match=r"lint \(exit 9\)"):
        final_acceptance._execute(spec, {})


def test_test_count_is_runtime_data_and_not_fixed_to_pre_phase8_baseline() -> None:
    payload = _payload()
    assert payload["tests"]["passed_count"] == 137  # type: ignore[index]
    final_acceptance.validate_evidence(payload)
    assert "62 passed" not in SCRIPT.read_text(encoding="utf-8")


def test_checksum_constants_and_phase7_closeout_pin_are_exact() -> None:
    assert final_acceptance.PHASE_1_SHA256 == (
        "5cd9bf274d171f7007c4b160addb6fe281f3be1da13939b35c52ecf14a1d9ee8"
    )
    assert final_acceptance.PHASE_2_SHA256 == (
        "2d9cf41622428233c7b83d3de7aa0df860912ba457c72be22f3b26758cdd2c1e"
    )
    assert final_acceptance.PHASE_3_SHA256 == (
        "530804916123aacc3fe4aa4c4c9646cc9fdc35b306af6799b06fb23de052720d"
    )
    assert final_acceptance.PHASE_7_CLOSEOUT == (
        "515af728f64e9430dba7784fb9fa5627b98e316b"
    )


def test_output_path_is_required_external_and_non_overwriting(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        final_acceptance.parse_args(
            ["--source-repo", ".", "--tested-commit", VALID_COMMIT, "--python", "python3"]
        )

    source = tmp_path / "source"
    source.mkdir()
    valid = tmp_path / "acceptance.json"
    assert final_acceptance.validate_output_path(valid, source) == valid.resolve()

    inside = source / "acceptance.json"
    with pytest.raises(ValueError, match="outside the source repo"):
        final_acceptance.validate_output_path(inside, source)

    symlink = tmp_path / "acceptance-link.json"
    symlink.symlink_to(tmp_path / "not-created.json")
    with pytest.raises(ValueError, match="symbolic link"):
        final_acceptance.validate_output_path(symlink, source)

    valid.write_text("existing", encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite"):
        final_acceptance.validate_output_path(valid, source)


def test_network_install_defaults_off_and_requires_explicit_flag() -> None:
    base = [
        "--source-repo",
        ".",
        "--tested-commit",
        VALID_COMMIT,
        "--output-json",
        "result.json",
        "--python",
        "python3",
    ]
    assert final_acceptance.parse_args(base).allow_network_install is False
    assert final_acceptance.parse_args([*base, "--allow-network-install"]).allow_network_install


def test_phase8_pending_has_no_committed_passed_evidence() -> None:
    index = (ROOT / "docs/ai/session_index.md").read_text(encoding="utf-8")
    assert "| 8 |" in index
    phase_8_row = next(line for line in index.splitlines() if line.startswith("| 8 |"))
    assert phase_8_row.rstrip().endswith("| implementation_complete_acceptance_pending |")
    assert "pending manual export" in phase_8_row
    assert not (ROOT / "docs/evidence/phase_08/final_acceptance.json").exists()
    assert not (ROOT / "docs/final_acceptance.md").exists()
