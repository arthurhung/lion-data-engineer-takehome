from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT = PROJECT_ROOT / "docs" / "part_b_code_review.md"
MANIFEST = PROJECT_ROOT / "docs" / "evidence" / "phase_04" / "review_manifest.json"
README = PROJECT_ROOT / "README.md"
SESSION_INDEX = PROJECT_ROOT / "docs" / "ai" / "session_index.md"
TRANSCRIPT = PROJECT_ROOT / "docs" / "ai" / "transcripts" / "phase_04_part_b_code_review.jsonl"
SOURCE_MANIFEST = PROJECT_ROOT / "docs" / "source_manifest.sha256"
MANIFEST_SHA256 = "2446b8c14245e431147e27ea2b3c4cc61411744187cf44dab5f3a3ae3dda79b9"
REQUIRED_COVERAGE = {
    "correctness",
    "currency",
    "data_loss",
    "deployment_safety",
    "idempotency",
    "join",
    "observability",
    "performance",
    "scalability",
    "scd2",
    "schema_type",
}
REQUIRED_FINDING_SECTIONS = (
    "### 問題是什麼",
    "### 業務影響",
    "### 修正方式",
    "### Verification test",
)


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_markdown(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("`", ""))


def test_source_checksum_line_count_and_original_manifest_are_pinned() -> None:
    manifest = _manifest()
    source = manifest["source"]
    source_path = PROJECT_ROOT / source["path"]
    assert source_path.is_file()
    assert _sha256(source_path) == source["sha256"]
    assert len(source_path.read_text(encoding="utf-8").splitlines()) == source["line_count"]
    assert f"{source['sha256']}  {source['path']}" in SOURCE_MANIFEST.read_text(encoding="utf-8")
    assert manifest["review_method"] == "static_review_only_no_pyspark_or_fabric_execution"
    assert _sha256(MANIFEST) == MANIFEST_SHA256
    # Historical implementation-evidence snapshot; Phase 4 lifecycle later closed as Completed.
    assert manifest["status"] == "implementation_complete_acceptance_pending"


def test_finding_ids_severity_lines_and_coverage_are_consistent() -> None:
    manifest = _manifest()
    findings = manifest["findings"]
    ids = [finding["finding_id"] for finding in findings]
    assert len(findings) == 8
    assert [finding["severity"] for finding in findings].count("CRITICAL") == 4
    assert [finding["severity"] for finding in findings].count("HIGH") == 4
    assert ids == [f"PB-{number:03d}" for number in range(1, len(findings) + 1)]
    assert len(ids) == len(set(ids))
    assert {finding["severity"] for finding in findings} <= {"CRITICAL", "HIGH", "MEDIUM"}
    for finding in findings:
        assert 1 <= finding["line_start"] <= finding["line_end"] <= manifest["source"]["line_count"]
        assert finding["categories"]
        assert finding["blocking"] is True

    coverage = manifest["coverage"]
    assert set(coverage) == REQUIRED_COVERAGE
    assert all(set(finding_ids) <= set(ids) and finding_ids for finding_ids in coverage.values())
    for category, finding_ids in coverage.items():
        for finding_id in finding_ids:
            finding = next(item for item in findings if item["finding_id"] == finding_id)
            assert category in finding["categories"]


def test_markdown_is_primary_and_each_finding_has_required_sections() -> None:
    manifest = _manifest()
    report = REPORT.read_text(encoding="utf-8")
    assert manifest["primary_deliverable"] == "docs/part_b_code_review.md"
    assert report.index("## Executive summary") < report.index("## PB-001")

    matches = list(
        re.finditer(
            r"^## (PB-\d{3}) — (.+)[（(](CRITICAL|HIGH|MEDIUM)[）)]$", report, re.M
        )
    )
    assert [match.group(1) for match in matches] == [
        finding["finding_id"] for finding in manifest["findings"]
    ]
    assert [_normalized_markdown(match.group(2)) for match in matches] == [
        _normalized_markdown(finding["title"]) for finding in manifest["findings"]
    ]
    assert [match.group(3) for match in matches] == [
        finding["severity"] for finding in manifest["findings"]
    ]
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else report.index(
            "## 整體部署結論"
        )
        section = report[match.start() : end]
        assert "位置：" in section
        assert all(section.count(heading) == 1 for heading in REQUIRED_FINDING_SECTIONS)

    for finding_id in ("PB-003", "PB-005"):
        start = report.index(f"## {finding_id}")
        next_id = f"PB-{int(finding_id[-3:]) + 1:03d}"
        section = report[start : report.index(f"## {next_id}")]
        for heading in REQUIRED_FINDING_SECTIONS:
            subsection = section[section.index(heading) :]
            next_heading_positions = [
                subsection.find(candidate)
                for candidate in REQUIRED_FINDING_SECTIONS
                if subsection.find(candidate) > 0
            ]
            if next_heading_positions:
                subsection = subsection[: min(next_heading_positions)]
            assert "#### A." in subsection
            assert "#### B." in subsection

    summary = report[report.index("## Findings summary") : report.index("## PB-001")]
    for finding in manifest["findings"]:
        row = next(line for line in summary.splitlines() if f"`{finding['finding_id']}`" in line)
        assert finding["severity"] in row
        assert "Yes" in row
        assert _normalized_markdown(finding["title"]) in _normalized_markdown(row)


def test_blocking_order_and_deployment_conclusion_match_report() -> None:
    manifest = _manifest()
    report = REPORT.read_text(encoding="utf-8")
    ids = {finding["finding_id"] for finding in manifest["findings"]}
    blocking = manifest["blocking_fixes"]
    assert len(blocking) == len(set(blocking))
    assert set(blocking) == ids
    assert manifest["deployment_conclusion"] == "NO_DEPLOY"
    assert "### 1. 這段程式碼目前可以部署嗎？" in report
    assert "### 2. 為什麼？" in report
    assert "### 3. 部署前必須完成哪些blocking fixes？" in report
    assert "### 4. Blocking fixes的修復順序是什麼？" in report
    assert "### 5. 修正後必須通過哪些驗證？" in report
    assert "### 6. 哪些行為仍需在Fabric／PySpark runtime確認？" in report
    conclusion = report[report.index("## 整體部署結論") :]
    assert "**NO_DEPLOY**" in conclusion
    positions = [conclusion.index(f"`{finding_id}`") for finding_id in blocking]
    assert positions == sorted(positions)


def test_phase_4_closeout_lifecycle_and_transcript_linkage_are_complete() -> None:
    readme = README.read_text(encoding="utf-8")
    session_index = SESSION_INDEX.read_text(encoding="utf-8")
    assert "docs/part_b_code_review.md" in readme
    part_b_row = next(
        line for line in readme.splitlines() if "Part B AI PySpark code review" in line
    )
    assert "Completed" in part_b_row

    phase_4_row = next(
        line for line in session_index.splitlines() if line.startswith("| 4 / Part B |")
    )
    assert "transcripts/phase_04_part_b_code_review.jsonl" in phase_4_row
    assert phase_4_row.rstrip().endswith("| Completed |")

    assert REPORT.is_file()
    assert MANIFEST.is_file()
    assert TRANSCRIPT.is_file()
    assert TRANSCRIPT.stat().st_size > 0
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(TRANSCRIPT.relative_to(PROJECT_ROOT))],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert tracked.returncode == 0
