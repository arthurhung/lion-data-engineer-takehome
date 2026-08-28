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
EVIDENCE = ROOT / "docs/evidence/phase_08/final_acceptance.json"
REPORT = ROOT / "docs/final_acceptance.md"
README = ROOT / "README.md"
SESSION_INDEX = ROOT / "docs/ai/session_index.md"
TRANSCRIPT = ROOT / "docs/ai/transcripts/phase_08_clean_room_final_acceptance.jsonl"
TESTED_COMMIT = "7b75354fd4f4c51a24485c771412200d8dc57e4a"
EVIDENCE_COMMIT = "b6b5ccbeabf8e580b33d907820a933c2dc588ca4"
CLARIFICATION_COMMIT = "da87484f01f1c51a443b97245c4efc71e1e1a53e"
EVIDENCE_SHA256 = "13da90163628e9f7627a33799e259ddc9a82736a025cc0d4bfaac46ac7b34ab7"
EVIDENCE_BYTES = 6_562
TRANSCRIPT_TASK_ID = "01a0458a-b830-7a03-a8be-f5acbe34a07c"
TRANSCRIPT_RECORDS = 1_178
TRANSCRIPT_BYTES = 4_299_586
TRANSCRIPT_SHA256 = "ffd93e2195baa3257bc06f9228da5a05ffa657fce14588663844c98bcfd9a18d"
CLOSEOUT_COMMIT = "6c0d0ba0f5a9645930bc8703003e6a4963153e29"
CLOSEOUT_SUBJECT = "docs: record Phase 8 AI collaboration evidence"
METADATA_PIN_MARKER = "this final metadata pin commit; Git history is authoritative"
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


def test_promoted_formal_evidence_is_canonical_valid_and_pinned() -> None:
    raw = EVIDENCE.read_bytes()
    payload = json.loads(raw)
    final_acceptance.validate_evidence(payload)
    assert raw == final_acceptance.canonical_json(payload)
    assert len(raw) == EVIDENCE_BYTES
    assert hashlib.sha256(raw).hexdigest() == EVIDENCE_SHA256
    assert payload["status"] == "PASSED"
    assert payload["tested_commit"] == TESTED_COMMIT
    assert payload["tests"] == {
        "passed": True,
        "passed_count": 93,
        "rollback_coverage": "covered_by_full_suite",
    }
    assert len(payload["commands"]) == 9
    assert all(command["exit_status"] == 0 for command in payload["commands"])


def test_formal_evidence_commit_exists_and_is_ancestor_of_head() -> None:
    commit = subprocess.run(
        ["git", "cat-file", "-e", f"{TESTED_COMMIT}^{{commit}}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert commit.returncode == 0
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", TESTED_COMMIT, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert ancestor.returncode == 0


def test_formal_evidence_metrics_and_submission_matrix_are_exact() -> None:
    payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert payload["source_integrity"] == {"files_checked": 19, "violations": 0}
    assert payload["phase_1"]["detector_count"] == 47
    assert payload["phase_2"]["fact_rows"] == 99_612
    assert payload["phase_2"]["violations"] == 0
    assert payload["phase_3"]["fact_rows"] == 109_888
    assert payload["phase_3"]["quarantined_orders"] == 2_172
    assert payload["phase_3"]["canonical_evidence_byte_identical"] is True
    assert payload["artifact_hygiene"]["rejected_artifacts"] == 0
    assert payload["artifact_hygiene"]["credential_pattern_matches"] == 0
    assert len(payload["submission_matrix"]) == 25
    assert all(item["present"] for item in payload["submission_matrix"])


def test_acceptance_report_and_lifecycle_pins_are_consistent() -> None:
    report = REPORT.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    index = SESSION_INDEX.read_text(encoding="utf-8")
    phase_8_row = next(line for line in index.splitlines() if line.startswith("| 8 |"))
    for text in (report, readme, phase_8_row):
        assert TESTED_COMMIT in text
        assert EVIDENCE_SHA256 in text
    assert "evidence/phase_08/final_acceptance.json" in report
    assert "ai/transcripts/phase_08_clean_room_final_acceptance.jsonl" in report
    assert "docs/evidence/phase_08/final_acceptance.json" in readme
    assert "Phase 8 clean-room | `Completed`" in readme
    assert "Phase 8 transcript已匯出、驗證並索引" in readme
    assert "93 passed" in report
    assert "93 passed" in readme
    assert "`PASSED`" in report
    assert f"Tested infrastructure commit：`{TESTED_COMMIT}`" in report
    assert f"Acceptance evidence commit：`{EVIDENCE_COMMIT}`" in report
    assert "不是clean-room tested commit" in report
    assert f"`tested_commit`維持`{TESTED_COMMIT}`" in report
    assert (
        "`93 passed`是tested infrastructure commit在\n"
        "  tracked-only clean clone與fresh venv中的full suite結果"
    ) in report
    assert (
        "`96 passed`是正式JSON、Reviewer Markdown與validators加入後，"
        "在acceptance evidence commit工作樹執行的\n"
        "  post-evidence full suite結果"
    ) in report
    assert "101個tracked files、58,943,598 tracked bytes" in report
    assert "tested infrastructure commit的clean-room snapshot" in report
    assert "evidence commit加入final JSON及Markdown後共有103個tracked files" in report
    assert "47個detectors並產生7份canonical evidence files" in report
    assert "Network dependency installation：本次formal run由人工opt-in設為enabled" in report
    assert "只依clone內的\n  `pyproject.toml`安裝dependencies" in report
    assert "不宣稱\n  未來仍會得到exact dependency resolution" in report
    assert "`make phase3-acceptance`驗證`base → day1 → day2 → day3`" in report
    assert (
        "Transaction rollback、failed attempt behavior及stale attempt／"
        "different-SHA regression，則由clean-room\n"
        "  full test suite對Phase 3 incremental behavior提供coverage"
    ) in report
    assert "不宣稱`make phase3-acceptance`另行重跑\n  這些rollback fixtures" in report
    assert phase_8_row.rstrip().endswith("| Completed |")
    assert "pending" not in phase_8_row.lower()
    assert EVIDENCE_COMMIT in phase_8_row
    assert CLARIFICATION_COMMIT in phase_8_row
    assert CLOSEOUT_COMMIT in phase_8_row
    assert METADATA_PIN_MARKER in phase_8_row
    assert "未執行外部submission action" in report


def test_phase_8_transcript_metadata_is_exact_and_nonempty() -> None:
    raw = TRANSCRIPT.read_bytes()
    assert raw
    assert TRANSCRIPT.stat().st_size == TRANSCRIPT_BYTES
    assert len(raw.splitlines()) == TRANSCRIPT_RECORDS
    assert hashlib.sha256(raw).hexdigest() == TRANSCRIPT_SHA256

    first_record = json.loads(next(line for line in raw.splitlines() if line.strip()))
    assert first_record["type"] == "session_meta"
    assert first_record["payload"]["id"] == TRANSCRIPT_TASK_ID
    assert first_record["payload"]["session_id"] == TRANSCRIPT_TASK_ID

    index = SESSION_INDEX.read_text(encoding="utf-8")
    phase_8_row = next(line for line in index.splitlines() if line.startswith("| 8 |"))
    for value in (
        TRANSCRIPT_TASK_ID,
        f"{TRANSCRIPT_RECORDS:,}",
        f"{TRANSCRIPT_BYTES:,}",
        TRANSCRIPT_SHA256,
    ):
        assert value in phase_8_row


def test_phase_8_closeout_commit_is_pinned_and_in_history() -> None:
    commit = subprocess.run(
        ["git", "cat-file", "-e", f"{CLOSEOUT_COMMIT}^{{commit}}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert commit.returncode == 0
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", CLOSEOUT_COMMIT, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert ancestor.returncode == 0
    subject = subprocess.run(
        ["git", "show", "-s", "--format=%s", CLOSEOUT_COMMIT],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert subject == CLOSEOUT_SUBJECT
