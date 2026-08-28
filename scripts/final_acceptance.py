#!/usr/bin/env python3
"""Run Phase 8 acceptance in a tracked-only clone and emit deterministic JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{40}$")
PYTEST_PASSED_RE = re.compile(r"(?P<count>[0-9]+) passed")

PHASE_1_SHA256 = "5cd9bf274d171f7007c4b160addb6fe281f3be1da13939b35c52ecf14a1d9ee8"
PHASE_2_SHA256 = "2d9cf41622428233c7b83d3de7aa0df860912ba457c72be22f3b26758cdd2c1e"
PHASE_3_SHA256 = "530804916123aacc3fe4aa4c4c9646cc9fdc35b306af6799b06fb23de052720d"
PHASE_7_CLOSEOUT = "515af728f64e9430dba7784fb9fa5627b98e316b"

PHASE_1_EVIDENCE_FILES = (
    "source_contract.json",
    "source_profile.json",
    "issue_summary.json",
    "analysis_summary.json",
    "representative_samples.json",
    "treatment_matrix.json",
)
PHASE_2_EVIDENCE_FILES = ("model_summary.json", "validation_summary.json")

EXPECTED_TOP_LEVEL_KEYS = {
    "artifact_hygiene",
    "clone_mode",
    "commands",
    "dependency_versions",
    "documentation",
    "known_limitations",
    "lint",
    "phase_1",
    "phase_2",
    "phase_3",
    "python_version",
    "schema_version",
    "source_integrity",
    "status",
    "submission_matrix",
    "tested_commit",
    "tests",
}

VOLATILE_KEYS = {
    "absolute_path",
    "attempt_id",
    "duration",
    "execution_duration",
    "host",
    "hostname",
    "ingested_at",
    "pip_cache_path",
    "runtime_timestamp",
    "source_repo",
    "temp_directory",
    "temp_path",
    "timestamp",
    "username",
    "venv_path",
}

REJECTED_FILE_SUFFIXES = {
    ".coverage",
    ".db",
    ".duckdb",
    ".log",
    ".parquet",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".wal",
}
REJECTED_FILE_NAMES = {".env", "coverage.xml"}
REJECTED_PATH_PARTS = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "htmlcov",
    "venv",
}

CREDENTIAL_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(rb"(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])"),
    re.compile(rb"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{30,255}(?![A-Za-z0-9])"),
    re.compile(rb"(?<![A-Za-z0-9_-])sk-(?:proj-)?[A-Za-z0-9_-]{20,200}(?![A-Za-z0-9_-])"),
    re.compile(rb"(?<![A-Za-z0-9-])xox[baprs]-[A-Za-z0-9-]{10,255}(?![A-Za-z0-9-])"),
)

SUBMISSION_PATHS = {
    "part_a_implementation": "src/lion_de_exam/incremental.py",
    "part_a_model_design": "docs/part_a_model_design.md",
    "part_a_quality_report": "docs/part_a_quality_report.md",
    "part_a_rerun_evidence": "docs/part_a_rerun_evidence.md",
    "part_b_review": "docs/part_b_code_review.md",
    "part_c_architecture": "docs/part_c_fabric_architecture.md",
    "module_f_diagnosis": "docs/module_f_diagnosis.md",
    "ai_collaboration_report": "docs/ai/collaboration_report.md",
    "ai_session_index": "docs/ai/session_index.md",
    "readme": "README.md",
    "source_manifest": "docs/source_manifest.sha256",
    "phase_1_evidence": "docs/evidence/phase_01/evidence_manifest.json",
    "phase_2_evidence": "docs/evidence/phase_02/evidence_manifest.json",
    "phase_3_evidence": "docs/evidence/phase_03/evidence_manifest.json",
    "phase_4_evidence": "docs/evidence/phase_04/review_manifest.json",
    "phase_0_transcript": "docs/ai/transcripts/phase_00_bootstrap.jsonl",
    "phase_1_transcript": "docs/ai/transcripts/phase_01_profiling_quality_contract.jsonl",
    "phase_1_correction_transcript": (
        "docs/ai/transcripts/phase_01_birth_date_sentinel_correction.jsonl"
    ),
    "phase_2_transcript": "docs/ai/transcripts/phase_02_star_schema_scd2.jsonl",
    "phase_3_transcript": "docs/ai/transcripts/phase_03_incremental_processing.jsonl",
    "phase_4_transcript": "docs/ai/transcripts/phase_04_part_b_code_review.jsonl",
    "phase_5_transcript": "docs/ai/transcripts/phase_05_part_c_fabric_architecture.jsonl",
    "phase_6_transcript": "docs/ai/transcripts/phase_06_module_f.jsonl",
    "phase_7_transcript": "docs/ai/transcripts/phase_07_reviewer_ai_collaboration.jsonl",
    "test_suite": "tests/test_final_acceptance.py",
}


class AcceptanceError(RuntimeError):
    """Expected validation or command failure."""


@dataclass(frozen=True)
class CommandSpec:
    logical_name: str
    argv: tuple[str, ...]
    cwd: Path


@dataclass(frozen=True)
class CommandResult:
    logical_name: str
    exit_status: int
    stdout: str
    stderr: str

    def evidence(self) -> dict[str, object]:
        return {"exit_status": self.exit_status, "logical_name": self.logical_name}


def validate_full_commit_sha(value: str) -> str:
    if not SHA256_RE.fullmatch(value):
        raise ValueError("tested commit must be a full 40-character lowercase hexadecimal SHA")
    return value


def _run_git(repo: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ("git", "-C", str(repo), *arguments),
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise AcceptanceError(f"git command failed: {arguments[0]}")
    return result


def validate_commit_object(repo: Path, commit: str) -> None:
    validate_full_commit_sha(commit)
    if not repo.is_dir():
        raise ValueError("source repo must be an existing directory")
    object_type = _run_git(repo, "cat-file", "-t", commit).stdout.strip()
    if object_type != "commit":
        raise ValueError("tested commit does not resolve to a commit object")


def validate_output_path(output: Path, source_repo: Path) -> Path:
    expanded = output.expanduser()
    lexical = Path(os.path.abspath(expanded))
    resolved = expanded.resolve()
    source = source_repo.resolve()
    if not output.name:
        raise ValueError("output JSON path must include a file name")
    if expanded.is_symlink():
        raise ValueError("output JSON path must not be a symbolic link")
    if not resolved.parent.is_dir():
        raise ValueError("output JSON parent must already exist")
    if resolved.exists():
        raise ValueError("refusing to overwrite an existing output JSON")
    if resolved == source or source in resolved.parents or source in lexical.parents:
        raise ValueError("output JSON must be outside the source repo")
    return resolved


def validate_temp_root(root: Path, source_repo: Path) -> None:
    resolved = root.resolve()
    forbidden = {Path("/").resolve(), Path.home().resolve(), source_repo.resolve()}
    if resolved in forbidden:
        raise AcceptanceError("unsafe temporary root")
    if source_repo.resolve() in resolved.parents:
        raise AcceptanceError("temporary root must not contain the source repo")


def canonical_json(payload: dict[str, object]) -> bytes:
    validate_evidence(payload)
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def _walk_values(value: object, *, key: str | None = None) -> None:
    if key and key.lower() in VOLATILE_KEYS:
        raise ValueError(f"volatile evidence key is forbidden: {key}")
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _walk_values(child_value, key=str(child_key))
    elif isinstance(value, list):
        for item in value:
            _walk_values(item)
    elif isinstance(value, str):
        if value.startswith("/") or PureWindowsPath(value).is_absolute():
            raise ValueError("absolute paths are forbidden in evidence")
        if re.search(r"(?:^|[\\/])Users[\\/]", value):
            raise ValueError("user-specific paths are forbidden in evidence")
        encoded = value.encode("utf-8")
        if any(pattern.search(encoded) for pattern in CREDENTIAL_PATTERNS):
            raise ValueError("possible credential value is forbidden in evidence")


def validate_evidence(payload: dict[str, object]) -> None:
    if set(payload) != EXPECTED_TOP_LEVEL_KEYS:
        missing = sorted(EXPECTED_TOP_LEVEL_KEYS - set(payload))
        extra = sorted(set(payload) - EXPECTED_TOP_LEVEL_KEYS)
        raise ValueError(f"invalid evidence schema; missing={missing}, extra={extra}")
    if payload["status"] not in {"PASSED", "FAILED"}:
        raise ValueError("status must be PASSED or FAILED")
    if payload["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    validate_full_commit_sha(str(payload["tested_commit"]))
    if payload["clone_mode"] != "local_git_clone_no_local_tracked_only":
        raise ValueError("unexpected clone mode")
    dependencies = payload["dependency_versions"]
    if not isinstance(dependencies, dict):
        raise ValueError("dependency_versions must be an object")
    expected_dependencies = {"duckdb", "pandas", "pip", "pytest", "ruff"}
    if set(dependencies) != expected_dependencies:
        raise ValueError("dependency_versions must contain exactly the required packages")
    commands = payload["commands"]
    if not isinstance(commands, list):
        raise ValueError("commands must be a list")
    logical_names = {item.get("logical_name") for item in commands if isinstance(item, dict)}
    if len(commands) != len(required_command_names()) or logical_names != set(
        required_command_names()
    ):
        raise ValueError("command matrix is incomplete or contains unexpected entries")
    if any(type(item.get("exit_status")) is not int for item in commands):
        raise ValueError("every command exit_status must be an integer")
    dependency_install = next(
        item
        for item in commands
        if isinstance(item, dict) and item.get("logical_name") == "dependency_install"
    )
    if not isinstance(dependency_install.get("network_install"), bool):
        raise ValueError("dependency_install must record whether network access was enabled")
    if payload["status"] == "PASSED":
        if any(item.get("exit_status") != 0 for item in commands):
            raise ValueError("PASSED evidence requires every command to exit zero")
        if payload["python_version"] == "unavailable" or any(
            not isinstance(value, str) or not value or value == "unavailable"
            for value in dependencies.values()
        ):
            raise ValueError("PASSED evidence requires resolved dependency versions")
        expected_sections = {
            "source_integrity": {"files_checked": 19, "violations": 0},
            "lint": {"passed": True},
            "phase_1": {
                "canonical_bundle_sha256": PHASE_1_SHA256,
                "detector_count": 47,
                "fresh_profile": True,
            },
            "phase_2": {
                "canonical_bundle_sha256": PHASE_2_SHA256,
                "check_count": 32,
                "current_members": 7_972,
                "fact_rows": 99_612,
                "fresh_database": True,
                "known_member_versions": 8_745,
                "violations": 0,
            },
        }
        for section, expected in expected_sections.items():
            if payload[section] != expected:
                raise ValueError(f"PASSED evidence has invalid {section} results")
        phase_3 = payload["phase_3"]
        expected_phase_3 = {
            "base_through_day_3": True,
            "canonical_bundle_sha256": PHASE_3_SHA256,
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
        }
        if phase_3 != expected_phase_3:
            raise ValueError("PASSED evidence has invalid phase_3 results")
        tests = payload["tests"]
        if (
            not isinstance(tests, dict)
            or tests.get("passed") is not True
            or not isinstance(tests.get("passed_count"), int)
            or tests["passed_count"] <= 0
            or tests.get("rollback_coverage") != "covered_by_full_suite"
        ):
            raise ValueError("PASSED evidence has invalid test results")
        documentation = payload["documentation"]
        if not isinstance(documentation, dict) or documentation.get("passed") is not True:
            raise ValueError("PASSED evidence requires documentation validation")
        hygiene = payload["artifact_hygiene"]
        if (
            not isinstance(hygiene, dict)
            or hygiene.get("credential_pattern_matches") != 0
            or hygiene.get("rejected_artifacts") != 0
        ):
            raise ValueError("PASSED evidence requires clean tracked artifact hygiene")
        submission = payload["submission_matrix"]
        if not isinstance(submission, list) or not submission or any(
            not isinstance(item, dict)
            or item.get("required") is not True
            or item.get("present") is not True
            for item in submission
        ):
            raise ValueError("PASSED evidence requires a complete submission matrix")
    _walk_values(payload)


def required_command_names() -> tuple[str, ...]:
    return (
        "dependency_install",
        "source_integrity",
        "lint",
        "tests",
        "phase_1_profile",
        "phase_2_build",
        "phase_2_validate",
        "phase_3_acceptance",
        "final_git_clean",
    )


def acceptance_command_matrix(
    repo: Path, venv: Path, runtime: Path, network: bool
) -> list[CommandSpec]:
    python = venv / "bin" / "python"
    install = [str(python), "-m", "pip", "install"]
    if not network:
        install.append("--no-index")
    install.extend(("-e", ".[dev]"))
    make_prefix = ("make", f"VENV={venv}")
    return [
        CommandSpec("dependency_install", tuple(install), repo),
        CommandSpec("source_integrity", ("make", "source-integrity"), repo),
        CommandSpec("lint", (*make_prefix, "lint"), repo),
        CommandSpec("tests", (*make_prefix, "test"), repo),
        CommandSpec(
            "phase_1_profile",
            (
                *make_prefix,
                "profile",
                f"OUTPUT_DIR={runtime / 'phase_1_output'}",
                f"EVIDENCE_DIR={runtime / 'phase_1_evidence'}",
            ),
            repo,
        ),
        CommandSpec(
            "phase_2_build",
            (
                *make_prefix,
                "build-base",
                f"OUTPUT_DB={runtime / 'phase_2.duckdb'}",
                f"PHASE2_EVIDENCE_DIR={runtime / 'phase_2_evidence'}",
            ),
            repo,
        ),
        CommandSpec(
            "phase_2_validate",
            (
                *make_prefix,
                "validate-base",
                f"OUTPUT_DB={runtime / 'phase_2.duckdb'}",
                f"PHASE2_EVIDENCE_DIR={runtime / 'phase_2_evidence'}",
            ),
            repo,
        ),
        CommandSpec("phase_3_acceptance", (*make_prefix, "phase3-acceptance"), repo),
        CommandSpec("final_git_clean", ("git", "status", "--porcelain"), repo),
    ]


def _execute(spec: CommandSpec, env: dict[str, str]) -> CommandResult:
    result = subprocess.run(
        spec.argv,
        cwd=spec.cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    command_result = CommandResult(
        spec.logical_name, result.returncode, result.stdout, result.stderr
    )
    if result.returncode != 0:
        raise AcceptanceError(
            f"acceptance command failed: {spec.logical_name} (exit {result.returncode})"
        )
    if spec.logical_name == "final_git_clean" and result.stdout.strip():
        raise AcceptanceError("clean clone working tree changed during acceptance")
    return command_result


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _table_count(summary: dict[str, Any], table_name: str) -> int:
    return next(
        int(row["row_count"]) for row in summary["table_counts"] if row["table_name"] == table_name
    )


def _validation_counts(summary: dict[str, Any]) -> tuple[int, int]:
    checks = summary["checks"]
    return len(checks), sum(int(row["violation_count"]) for row in checks)


def _verify_evidence_bundle(
    directory: Path,
    expected: str,
    file_names: tuple[str, ...],
    *,
    include_file_names: bool,
) -> str:
    manifest_path = directory / "evidence_manifest.json"
    manifest = _load_json(manifest_path)
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise AcceptanceError(f"invalid evidence manifest: {directory.name}")
    entry_digests = {
        entry.get("file"): entry.get("sha256") for entry in entries if isinstance(entry, dict)
    }
    if set(entry_digests) != set(file_names):
        raise AcceptanceError(f"evidence manifest file set mismatch: {directory.name}")

    bundle = hashlib.sha256()
    for file_name in file_names:
        content = (directory / file_name).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if entry_digests[file_name] != digest:
            raise AcceptanceError(f"evidence file checksum mismatch: {file_name}")
        if include_file_names:
            bundle.update(file_name.encode("utf-8") + b"\n")
        bundle.update(content)

    actual = bundle.hexdigest()
    declared = manifest.get("canonical_bundle_sha256")
    if actual != expected or declared != expected:
        raise AcceptanceError(f"canonical checksum mismatch: {directory.name}")
    return actual


def _phase_3_checksum(stdout: str) -> str:
    match = re.search(r"canonical_evidence_sha256=([0-9a-f]{64})", stdout)
    if not match or match.group(1) != PHASE_3_SHA256:
        raise AcceptanceError("Phase 3 clean-run canonical checksum mismatch")
    return match.group(1)


def _resolved_versions(python: Path, env: dict[str, str]) -> tuple[str, dict[str, str]]:
    code = (
        "import importlib.metadata as m, json, platform; "
        "print(json.dumps({'python': platform.python_version(), "
        "'versions': {n: m.version(n) for n in "
        "('pip','duckdb','pandas','pytest','ruff')}}))"
    )
    result = subprocess.run(
        (str(python), "-c", code),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AcceptanceError("failed to collect fresh-environment dependency versions")
    payload = json.loads(result.stdout)
    return str(payload["python"]), {str(k): str(v) for k, v in payload["versions"].items()}


def classify_tracked_artifact(path: str) -> str | None:
    candidate = Path(path)
    lowered_parts = {part.lower() for part in candidate.parts}
    name = candidate.name.lower()
    if lowered_parts & REJECTED_PATH_PARTS:
        return "runtime_or_cache_directory"
    if (
        name in REJECTED_FILE_NAMES
        or name.startswith(".coverage.")
        or name.startswith(".env.")
    ):
        return "secret_or_runtime_file"
    if any(name.endswith(suffix) for suffix in REJECTED_FILE_SUFFIXES):
        return "runtime_output"
    if candidate.suffix.lower() in {".key", ".pem"}:
        return "credential_file"
    return None


def _tracked_hygiene(repo: Path) -> dict[str, object]:
    tracked_raw = _run_git(repo, "ls-files", "-z").stdout
    tracked = [path for path in tracked_raw.split("\0") if path]
    rejected = [
        {"classification": classification, "path": path}
        for path in tracked
        if (classification := classify_tracked_artifact(path))
    ]
    if rejected:
        raise AcceptanceError("tracked runtime, cache, secret, or credential artifact found")

    credential_matches = 0
    for path in tracked:
        data = (repo / path).read_bytes()
        credential_matches += sum(len(pattern.findall(data)) for pattern in CREDENTIAL_PATTERNS)
    if credential_matches:
        raise AcceptanceError("possible credential value found in tracked content")

    sizes: list[tuple[int, str]] = []
    for line in _run_git(repo, "ls-tree", "-r", "-l", "HEAD").stdout.splitlines():
        metadata, path = line.split("\t", 1)
        size = int(metadata.split()[-1])
        sizes.append((size, path))
    transcript_size = sum(size for size, path in sizes if path.endswith(".jsonl"))
    largest = [
        {"bytes": size, "path": path}
        for size, path in sorted(sizes, key=lambda item: (-item[0], item[1]))[:10]
    ]
    return {
        "credential_pattern_matches": credential_matches,
        "largest_tracked_files": largest,
        "rejected_artifacts": 0,
        "tracked_bytes": sum(size for size, _ in sizes),
        "tracked_file_count": len(tracked),
        "transcript_aggregate_bytes": transcript_size,
    }


def _submission_matrix(repo: Path) -> list[dict[str, object]]:
    matrix = [
        {"item": name, "present": (repo / relative).is_file(), "required": True}
        for name, relative in sorted(SUBMISSION_PATHS.items())
    ]
    if not all(bool(item["present"]) for item in matrix):
        raise AcceptanceError("required submission deliverable is missing")
    return matrix


def _base_payload(commit: str, commands: list[dict[str, object]]) -> dict[str, object]:
    return {
        "artifact_hygiene": {},
        "clone_mode": "local_git_clone_no_local_tracked_only",
        "commands": commands,
        "dependency_versions": {
            name: "unavailable" for name in ("duckdb", "pandas", "pip", "pytest", "ruff")
        },
        "documentation": {},
        "known_limitations": [
            "Dependencies are resolved from declared version ranges without a lock file.",
            "This run does not prove identical dependency resolution on every future platform.",
            "Credential pattern scanning is not a complete privacy audit.",
            "Fabric PySpark and ML runtimes are outside this local acceptance scope.",
        ],
        "lint": {},
        "phase_1": {},
        "phase_2": {},
        "phase_3": {},
        "python_version": "unavailable",
        "schema_version": 1,
        "source_integrity": {},
        "status": "FAILED",
        "submission_matrix": [],
        "tested_commit": commit,
        "tests": {},
    }


def run_acceptance(
    source_repo: Path,
    tested_commit: str,
    output_json: Path,
    python_interpreter: str,
    allow_network_install: bool,
) -> int:
    source_repo = source_repo.expanduser().resolve()
    validate_commit_object(source_repo, tested_commit)
    output_json = validate_output_path(output_json, source_repo)
    command_evidence = []
    for name in required_command_names():
        item: dict[str, object] = {"exit_status": -1, "logical_name": name}
        if name == "dependency_install":
            item["network_install"] = allow_network_install
        command_evidence.append(item)
    payload = _base_payload(tested_commit, command_evidence)

    try:
        with tempfile.TemporaryDirectory(prefix="lion-phase8-acceptance-") as directory:
            root = Path(directory)
            validate_temp_root(root, source_repo)
            clone = root / "repo"
            runtime = root / "runtime"
            venv = root / "venv"
            for path in (runtime, root / "home", root / "pip-cache", root / "xdg-cache"):
                path.mkdir()

            clone_result = subprocess.run(
                ("git", "clone", "--no-local", str(source_repo), str(clone)),
                check=False,
                capture_output=True,
                text=True,
            )
            if clone_result.returncode != 0:
                raise AcceptanceError("tracked-only local clone failed")
            _run_git(clone, "checkout", "--detach", tested_commit)
            if _run_git(clone, "rev-parse", "HEAD").stdout.strip() != tested_commit:
                raise AcceptanceError("clone HEAD does not match tested commit")
            if _run_git(clone, "status", "--porcelain").stdout.strip():
                raise AcceptanceError("initial clean clone working tree is not clean")

            env = os.environ.copy()
            for name in (
                "PIP_EXTRA_INDEX_URL",
                "PIP_FIND_LINKS",
                "PIP_INDEX_URL",
                "PIP_TRUSTED_HOST",
                "PYTHONHOME",
                "PYTHONPATH",
                "VIRTUAL_ENV",
            ):
                env.pop(name, None)
            env.update(
                {
                    "HOME": str(root / "home"),
                    "PIP_CACHE_DIR": str(root / "pip-cache"),
                    "PIP_CONFIG_FILE": os.devnull,
                    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                    "PIP_NO_INPUT": "1",
                    "PYTHONNOUSERSITE": "1",
                    "TMPDIR": str(runtime),
                    "XDG_CACHE_HOME": str(root / "xdg-cache"),
                }
            )

            venv_result = subprocess.run(
                (python_interpreter, "-m", "venv", str(venv)),
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            if venv_result.returncode != 0:
                raise AcceptanceError("fresh virtual environment creation failed")

            specs = acceptance_command_matrix(clone, venv, runtime, allow_network_install)
            results: dict[str, CommandResult] = {}
            for index, spec in enumerate(specs):
                result = _execute(spec, env)
                results[spec.logical_name] = result
                item = result.evidence()
                if spec.logical_name == "dependency_install":
                    item["network_install"] = allow_network_install
                command_evidence[index] = item

            if _run_git(clone, "rev-parse", "HEAD").stdout.strip() != tested_commit:
                raise AcceptanceError("clone HEAD changed during acceptance")

            python_version, dependency_versions = _resolved_versions(venv / "bin" / "python", env)
            payload["python_version"] = python_version
            payload["dependency_versions"] = dependency_versions

            source_count = results["source_integrity"].stdout.count(": OK")
            if source_count != 19:
                raise AcceptanceError("source integrity did not report 19 verified files")
            payload["source_integrity"] = {"files_checked": source_count, "violations": 0}
            payload["lint"] = {"passed": True}

            pytest_match = PYTEST_PASSED_RE.search(results["tests"].stdout)
            if not pytest_match:
                raise AcceptanceError("unable to parse pytest passed count")
            payload["tests"] = {
                "passed": True,
                "passed_count": int(pytest_match.group("count")),
                "rollback_coverage": "covered_by_full_suite",
            }
            payload["documentation"] = {
                "final_acceptance_validator": "covered_by_full_suite",
                "final_documentation_validator": "covered_by_full_suite",
                "passed": True,
            }

            phase_1_dir = runtime / "phase_1_evidence"
            phase_1_checksum = _verify_evidence_bundle(
                phase_1_dir,
                PHASE_1_SHA256,
                PHASE_1_EVIDENCE_FILES,
                include_file_names=True,
            )
            detector_count = len(_load_json(phase_1_dir / "issue_summary.json")["issues"])
            if detector_count != 47:
                raise AcceptanceError("Phase 1 detector count mismatch")
            payload["phase_1"] = {
                "canonical_bundle_sha256": phase_1_checksum,
                "detector_count": detector_count,
                "fresh_profile": True,
            }

            phase_2_dir = runtime / "phase_2_evidence"
            phase_2_checksum = _verify_evidence_bundle(
                phase_2_dir,
                PHASE_2_SHA256,
                PHASE_2_EVIDENCE_FILES,
                include_file_names=False,
            )
            phase_2_model = _load_json(phase_2_dir / "model_summary.json")
            phase_2_validation = _load_json(phase_2_dir / "validation_summary.json")
            check_count, violations = _validation_counts(phase_2_validation)
            member_summary = phase_2_model["member_summary"]
            phase_2_actual = {
                "canonical_bundle_sha256": phase_2_checksum,
                "check_count": check_count,
                "current_members": int(member_summary["current_versions"]),
                "fact_rows": _table_count(phase_2_model, "curated.fact_order"),
                "fresh_database": True,
                "known_member_versions": int(member_summary["member_versions"]),
                "violations": violations,
            }
            expected_phase_2 = {
                "check_count": 32,
                "current_members": 7_972,
                "fact_rows": 99_612,
                "known_member_versions": 8_745,
                "violations": 0,
            }
            if any(phase_2_actual[key] != value for key, value in expected_phase_2.items()):
                raise AcceptanceError("Phase 2 clean rebuild metrics mismatch")
            payload["phase_2"] = phase_2_actual

            phase_3_checksum = _phase_3_checksum(results["phase_3_acceptance"].stdout)
            phase_3_final = _load_json(clone / "docs/evidence/phase_03/final_summary.json")
            phase_3_validation = _load_json(
                clone / "docs/evidence/phase_03/validation_summary.json"
            )
            phase_3_checks, phase_3_violations = _validation_counts(phase_3_validation)
            phase_3_actual = {
                "base_through_day_3": True,
                "canonical_bundle_sha256": phase_3_checksum,
                "canonical_evidence_byte_identical": True,
                "check_count": phase_3_checks,
                "fact_rows": int(phase_3_final["fact_reconciliation"]["fact_rows"]),
                "file_registry": True,
                "full_sequence_replay": True,
                "metrics_source": "committed_bundle_verified_equal_to_clean_runs",
                "quarantined_orders": int(
                    phase_3_final["quarantine_reconciliation"]["summary"][
                        "quarantined_order_entities"
                    ]
                ),
                "rollback_coverage": "covered_by_full_suite",
                "single_file_replay": True,
                "violations": phase_3_violations,
            }
            expected_phase_3 = {
                "check_count": 41,
                "fact_rows": 109_888,
                "quarantined_orders": 2_172,
                "violations": 0,
            }
            if any(phase_3_actual[key] != value for key, value in expected_phase_3.items()):
                raise AcceptanceError("Phase 3 clean acceptance metrics mismatch")
            payload["phase_3"] = phase_3_actual

            payload["artifact_hygiene"] = _tracked_hygiene(clone)
            payload["submission_matrix"] = _submission_matrix(clone)
            payload["status"] = "PASSED"
    except (AcceptanceError, OSError, ValueError, json.JSONDecodeError) as exc:
        output_json.write_bytes(canonical_json(payload))
        print(f"final_acceptance=FAILED: {exc}", file=sys.stderr)
        return 1

    output_json.write_bytes(canonical_json(payload))
    print("final_acceptance=PASSED")
    print(f"tested_commit={tested_commit}")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--tested-commit", required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--allow-network-install", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validate_full_commit_sha(args.tested_commit)
        return run_acceptance(
            args.source_repo,
            args.tested_commit,
            args.output_json,
            args.python,
            args.allow_network_install,
        )
    except (AcceptanceError, OSError, ValueError) as exc:
        print(f"final_acceptance=FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
