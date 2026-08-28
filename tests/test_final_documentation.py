from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
AI_REPORT = ROOT / "docs/ai/collaboration_report.md"
SESSION_INDEX = ROOT / "docs/ai/session_index.md"
PART_C = ROOT / "docs/part_c_fabric_architecture.md"
MAKEFILE = ROOT / "Makefile"
PHASE_7_TRANSCRIPT = (
    ROOT / "docs/ai/transcripts/phase_07_reviewer_ai_collaboration.jsonl"
)
PHASE_8_TRANSCRIPT = (
    ROOT / "docs/ai/transcripts/phase_08_clean_room_final_acceptance.jsonl"
)
PHASE_8_EVIDENCE = ROOT / "docs/evidence/phase_08/final_acceptance.json"
PHASE_8_REPORT = ROOT / "docs/final_acceptance.md"
PHASE_8_TESTED_COMMIT = "7b75354fd4f4c51a24485c771412200d8dc57e4a"
PHASE_8_EVIDENCE_COMMIT = "b6b5ccbeabf8e580b33d907820a933c2dc588ca4"
PHASE_8_CLARIFICATION_COMMIT = "da87484f01f1c51a443b97245c4efc71e1e1a53e"
PHASE_8_EVIDENCE_SHA256 = (
    "13da90163628e9f7627a33799e259ddc9a82736a025cc0d4bfaac46ac7b34ab7"
)
PHASE_8_CLOSEOUT = "6c0d0ba0f5a9645930bc8703003e6a4963153e29"
PHASE_8_CLOSEOUT_SUBJECT = "docs: record Phase 8 AI collaboration evidence"
PHASE_8_METADATA_PIN = "this final metadata pin commit; Git history is authoritative"

PHASE_7_METADATA = (
    "01a044f1-b53c-7171-9573-f874f78cdcc3",
    "docs/ai/transcripts/phase_07_reviewer_ai_collaboration.jsonl",
    612,
    5_492_105,
    "00970a65298bd7c52d6ebfbc56d38bd3223713cd47f5b362a4472471e502c26b",
    "1886317fdb8c5e30257610e9d0ad5c4faf87b85e",
)

PHASE_7_CLOSEOUT = "515af728f64e9430dba7784fb9fa5627b98e316b"
PHASE_7_CLOSEOUT_SUBJECT = "docs: record Phase 7 AI collaboration evidence"

PHASE_8_METADATA = (
    "01a0458a-b830-7a03-a8be-f5acbe34a07c",
    "docs/ai/transcripts/phase_08_clean_room_final_acceptance.jsonl",
    1_178,
    4_299_586,
    "ffd93e2195baa3257bc06f9228da5a05ffa657fce14588663844c98bcfd9a18d",
)

REQUIRED_PATHS = (
    "docs/part_a_model_design.md",
    "docs/part_a_quality_report.md",
    "docs/part_a_rerun_evidence.md",
    "docs/part_b_code_review.md",
    "docs/part_c_fabric_architecture.md",
    "docs/module_f_diagnosis.md",
    "docs/ai/collaboration_report.md",
    "docs/ai/session_index.md",
    "docs/evidence/phase_02/evidence_manifest.json",
    "docs/evidence/phase_03/evidence_manifest.json",
    "docs/evidence/phase_04/review_manifest.json",
    "docs/final_acceptance.md",
    "docs/evidence/phase_08/final_acceptance.json",
)

TRANSCRIPTS = {
    "0": (
        "01a0385e-5109-7862-8ac0-a55fbe2e2553",
        "docs/ai/transcripts/phase_00_bootstrap.jsonl",
        404,
        5_246_779,
        "cf2ec64d1fdc48cc0947c9e342d43acadd0ed5d1d9f29b82f3848e4b987c7682",
        "68e77762f7daba44d7456ce0956b654cd5d2b49d",
        "db9b17b1fd59af7b9fe9ed5fb69b8b83955fb806",
    ),
    "1": (
        "01a03a9f-8a8c-7113-bcc4-496ca58fb87c",
        "docs/ai/transcripts/phase_01_profiling_quality_contract.jsonl",
        707,
        2_917_584,
        "99d305962bbfbdd28e6cb2d480f2545705c22d35d50a57a840df4d10e9ca10fb",
        "05ace53e8728af804c7a41e4e6274b723cfb95fc",
        "3a4eadaa884daf20ce11dc801f25543835e60055",
    ),
    "1 correction": (
        "01a03c1a-bf2f-7922-a666-f24a26bc44dd",
        "docs/ai/transcripts/phase_01_birth_date_sentinel_correction.jsonl",
        576,
        1_991_551,
        "383ec90513bb6cd710f346de5a20de1e50043ca748718dc0d68463acd5ea4dfa",
        "5c66c4cb25bee529f9f12002599bba39ac87d94a",
        "d7dabdb490c40b5ddba886f1325f66a4585a19cc",
    ),
    "2": (
        "01a03c01-720a-7cf1-afbe-47df73a79464",
        "docs/ai/transcripts/phase_02_star_schema_scd2.jsonl",
        848,
        6_872_171,
        "d8f09de47470d8fbd0ace821d11353e4f9dd7d00311db53699218b06efe23c2e",
        "ae0a08652c103e2469b2f648de237dc194d542d7",
        "a94d603708f1c1fa367fc078c1bc1166d99e1f52",
    ),
    "3": (
        "01a03d4f-f0d1-77e3-a0e0-d1014f8e425c",
        "docs/ai/transcripts/phase_03_incremental_processing.jsonl",
        1_291,
        8_075_904,
        "02cd5876f033835f6ffae565772fbb76f882ffdad8f199550c37dfd54f4921f6",
        "3522c85cd6c51a003234c3521908c6f153406817",
        "63a8357a0610c3a510bf33f99b8ef1dc4bf50fb5",
    ),
    "4 / Part B": (
        "01a040b8-6202-7211-9588-56d053a5eb2d",
        "docs/ai/transcripts/phase_04_part_b_code_review.jsonl",
        491,
        3_169_132,
        "dcd364541cda862273e28342dda3c4cc53156d328c9766466f83b49fb11e337d",
        "e9dfe44e3e9987acb896960bb296b52c6a66d520",
        "d58affe74ee04049f0da29ba321cb2c9313598f5",
    ),
    "5 / Part C": (
        "01a04266-4304-7132-98b2-2d24e5231d0d",
        "docs/ai/transcripts/phase_05_part_c_fabric_architecture.jsonl",
        703,
        6_200_032,
        "63980ef6610efe0c54d736d4cebc1649b2f3886007c96664caa74f021c06dca1",
        "3596e02c0dd801a8b20aa8c1a27dd9a73199dfcc",
        "be17266ed19f04c8b86ed666c35784e1ec101cd0",
    ),
    "6 / Module F": (
        "01a042b2-1034-7cb0-8027-6fcc5415a4fa",
        "docs/ai/transcripts/phase_06_module_f.jsonl",
        747,
        2_157_237,
        "d6ac71ced5640a196ececcb74fadab7248ba1552834bd204f754edf8d93f4760",
        "9ad55f2822048fd9dbd343eb38a535e06ad78628",
        "0fbb4267f3a87f13be9df327635bf17271dde029",
    ),
}

PINNED_SHA256 = {
    "docs/evidence/phase_04/review_manifest.json": (
        "2446b8c14245e431147e27ea2b3c4cc61411744187cf44dab5f3a3ae3dda79b9"
    ),
    "docs/part_c_fabric_architecture.md": (
        "0b5def8a604969ab155d0b090d03774a87308c1ef0bdbf84e7e775cfd8618915"
    ),
    "tests/test_part_c_architecture.py": (
        "c06d07b071df8bf5ade8d555db6b516208c075773f5d3bbf6b8b2217f7d7bd3b"
    ),
    "docs/module_f_diagnosis.md": (
        "6ddb7a7389d4a477383a5266cbdb07cae7d96c01693d1bbbfa5bcc820818218a"
    ),
    "tests/test_module_f_diagnosis.py": (
        "8bb9a2f86d25bacd32317e11c92ca4b052cbd005ea4db3922d6027dda06029bd"
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _phase_row(index: str, text: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(f"| {index} |"))


def test_required_deliverables_and_reviewer_index_exist() -> None:
    readme = README.read_text(encoding="utf-8")
    for relative in REQUIRED_PATHS:
        assert (ROOT / relative).exists(), relative
    for relative in REQUIRED_PATHS[:8]:
        assert relative in readme, relative
    assert "D／E／F三選一" in readme
    assert "Module D／E" in readme
    assert "並非交付缺漏" in readme


def test_current_lifecycle_and_historical_snapshot_are_unambiguous() -> None:
    readme = README.read_text(encoding="utf-8")
    index = SESSION_INDEX.read_text(encoding="utf-8")
    for phase in ("Part A", "Part B", "Part C", "Module F", "Phase 0～6 AI evidence"):
        row = next(line for line in readme.splitlines() if f"| {phase}" in line)
        assert "`Completed`" in row
    assert "Phase 7 reviewer／AI文件 | `Completed`" in readme
    assert "Phase 7 transcript已匯出、驗證並索引" in readme
    assert "Phase 8 clean-room | `Completed`" in readme
    assert "formal clean-room已`PASSED`" in readme
    assert "Phase 8 transcript已匯出、驗證並索引" in readme
    assert PHASE_8_TESTED_COMMIT in readme
    assert PHASE_8_EVIDENCE_SHA256 in readme
    assert "implementation-time snapshot" in readme
    assert "不是目前repo狀態" in readme
    assert "`NO_DEPLOY`是Part B與Module F的技術結論" in readme
    assert "不代表PySpark、Fabric或ML production deployment" in readme
    for phase in TRANSCRIPTS:
        row = _phase_row(phase, index)
        assert row.rstrip().endswith("| Completed |") or phase == "1"
    phase_7_row = _phase_row("7", index)
    assert phase_7_row.rstrip().endswith("| Completed |")
    assert "pending manual export" not in phase_7_row
    assert PHASE_7_CLOSEOUT in phase_7_row
    phase_8_row = _phase_row("8", index)
    assert phase_8_row.rstrip().endswith("| Completed |")
    assert "pending" not in phase_8_row.lower()
    assert PHASE_8_TESTED_COMMIT in phase_8_row
    assert PHASE_8_EVIDENCE_COMMIT in phase_8_row
    assert PHASE_8_CLARIFICATION_COMMIT in phase_8_row
    assert PHASE_8_EVIDENCE_SHA256 in phase_8_row
    assert PHASE_8_CLOSEOUT in phase_8_row
    assert PHASE_8_METADATA_PIN in phase_8_row
    assert PHASE_8_REPORT.exists()
    assert PHASE_8_EVIDENCE.exists()


def test_session_index_matches_transcript_files_and_git_history() -> None:
    index = SESSION_INDEX.read_text(encoding="utf-8")
    for phase, metadata in TRANSCRIPTS.items():
        task_id, relative, records, byte_size, digest, implementation, closeout = metadata
        path = ROOT / relative
        row = _phase_row(phase, index)
        assert task_id in row
        assert relative.removeprefix("docs/ai/") in row
        assert len(path.read_bytes().splitlines()) == records
        assert path.stat().st_size == byte_size
        assert _sha256(path) == digest
        assert f"{records:,}" in row
        assert f"{byte_size:,}" in row
        assert digest in row
        assert implementation in row
        assert closeout in row
        for commit in (implementation, closeout):
            result = subprocess.run(
                ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, commit

    phase_7_row = _phase_row("7", index)
    task_id, relative, records, byte_size, digest, implementation = PHASE_7_METADATA

    assert PHASE_7_TRANSCRIPT.exists()
    assert PHASE_7_TRANSCRIPT.stat().st_size > 0
    assert len(PHASE_7_TRANSCRIPT.read_bytes().splitlines()) == records
    assert PHASE_7_TRANSCRIPT.stat().st_size == byte_size
    assert _sha256(PHASE_7_TRANSCRIPT) == digest

    first_record = json.loads(
        next(
            line
            for line in PHASE_7_TRANSCRIPT.open(encoding="utf-8")
            if line.strip()
        )
    )
    assert first_record["type"] == "session_meta"
    assert first_record["payload"]["id"] == task_id
    assert first_record["payload"]["session_id"] == task_id

    assert task_id in phase_7_row
    assert relative.removeprefix("docs/ai/") in phase_7_row
    assert f"{records:,}" in phase_7_row
    assert f"{byte_size:,}" in phase_7_row
    assert digest in phase_7_row
    assert implementation in phase_7_row
    assert PHASE_7_CLOSEOUT in phase_7_row
    assert "pending manual export" not in phase_7_row

    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relative],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert tracked.returncode == 0, relative

    commit = subprocess.run(
        ["git", "cat-file", "-e", f"{implementation}^{{commit}}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert commit.returncode == 0, implementation

    closeout = subprocess.run(
        ["git", "cat-file", "-e", f"{PHASE_7_CLOSEOUT}^{{commit}}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert closeout.returncode == 0, PHASE_7_CLOSEOUT
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", PHASE_7_CLOSEOUT, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert ancestor.returncode == 0, PHASE_7_CLOSEOUT
    subject = subprocess.run(
        ["git", "show", "-s", "--format=%s", PHASE_7_CLOSEOUT],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert subject == PHASE_7_CLOSEOUT_SUBJECT

    phase_8_row = _phase_row("8", index)
    task_id, relative, records, byte_size, digest = PHASE_8_METADATA
    assert PHASE_8_TRANSCRIPT.exists()
    assert PHASE_8_TRANSCRIPT.stat().st_size > 0
    assert len(PHASE_8_TRANSCRIPT.read_bytes().splitlines()) == records
    assert PHASE_8_TRANSCRIPT.stat().st_size == byte_size
    assert _sha256(PHASE_8_TRANSCRIPT) == digest

    first_record = json.loads(
        next(line for line in PHASE_8_TRANSCRIPT.open(encoding="utf-8") if line.strip())
    )
    assert first_record["type"] == "session_meta"
    assert first_record["payload"]["id"] == task_id
    assert first_record["payload"]["session_id"] == task_id
    for value in (
        task_id,
        relative.removeprefix("docs/ai/"),
        f"{records:,}",
        f"{byte_size:,}",
        digest,
        PHASE_8_TESTED_COMMIT,
        PHASE_8_EVIDENCE_COMMIT,
        PHASE_8_CLARIFICATION_COMMIT,
        PHASE_8_CLOSEOUT,
        PHASE_8_METADATA_PIN,
    ):
        assert value in phase_8_row

    visible = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relative],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert visible.returncode == 0

    closeout = subprocess.run(
        ["git", "cat-file", "-e", f"{PHASE_8_CLOSEOUT}^{{commit}}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert closeout.returncode == 0
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", PHASE_8_CLOSEOUT, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert ancestor.returncode == 0
    subject = subprocess.run(
        ["git", "show", "-s", "--format=%s", PHASE_8_CLOSEOUT],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert subject == PHASE_8_CLOSEOUT_SUBJECT


def test_canonical_and_document_checksums_are_pinned() -> None:
    phase2 = json.loads((ROOT / "docs/evidence/phase_02/evidence_manifest.json").read_text())
    phase3 = json.loads((ROOT / "docs/evidence/phase_03/evidence_manifest.json").read_text())
    assert phase2["canonical_bundle_sha256"] == (
        "2d9cf41622428233c7b83d3de7aa0df860912ba457c72be22f3b26758cdd2c1e"
    )
    assert phase3["canonical_bundle_sha256"] == (
        "530804916123aacc3fe4aa4c4c9646cc9fdc35b306af6799b06fb23de052720d"
    )
    readme = README.read_text(encoding="utf-8")
    for relative, digest in PINNED_SHA256.items():
        assert _sha256(ROOT / relative) == digest
        assert digest in readme


def test_reviewer_documents_do_not_contain_user_specific_path() -> None:
    reviewer_docs = (README, AI_REPORT, SESSION_INDEX) + tuple(
        ROOT / path for path in REQUIRED_PATHS[:6]
    )
    for path in reviewer_docs:
        assert "/Users/arthur/" not in path.read_text(encoding="utf-8"), path


def test_readme_make_targets_exist() -> None:
    readme = README.read_text(encoding="utf-8")
    makefile = MAKEFILE.read_text(encoding="utf-8")
    declared = set(re.findall(r"^([A-Za-z0-9_-]+):(?:\s|$)", makefile, flags=re.M))
    used = set(re.findall(r"(?m)^make\s+([A-Za-z0-9_-]+)", readme))
    assert used
    assert used <= declared


def test_internal_markdown_file_links_resolve() -> None:
    markdown_files = (README, AI_REPORT, SESSION_INDEX) + tuple(
        ROOT / path for path in REQUIRED_PATHS[:6]
    )
    missing: list[str] = []
    for markdown in markdown_files:
        text = markdown.read_text(encoding="utf-8")
        for raw_target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
            target = raw_target.strip().removeprefix("<").removesuffix(">")
            target = re.split(r"[?#]", target, maxsplit=1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = (markdown.parent / target).resolve()
            if not resolved.exists():
                missing.append(f"{markdown.relative_to(ROOT)} -> {raw_target}")
    assert not missing


def test_part_c_mermaid_fences_are_balanced() -> None:
    text = PART_C.read_text(encoding="utf-8")
    blocks = re.findall(r"```mermaid\n.*?\n```", text, flags=re.S)
    assert len(blocks) == 2
    assert text.count("```mermaid") == 2


def test_ai_report_is_concise_traceable_and_does_not_copy_transcript_blocks() -> None:
    report = AI_REPORT.read_text(encoding="utf-8")
    for heading in (
        "## 1. 協作方式",
        "## 2. AI協助範圍",
        "## 3. AI的實際不足與人工修正",
        "## 4. Candidate-owned decisions",
        "## 5. 防止捏造與限制",
    ):
        assert heading in report
    for phrase in (
        "1900-01-01",
        "failed／stale",
        "PB-007",
        "Direct Lake on SQL",
        "source SHA-256",
        "Exact Decimal",
        "不宣稱完全去識別化",
        "最終答案、取捨與提交責任由我承擔",
    ):
        assert phrase.lower() in report.lower()
    chinese_characters = re.findall(r"[\u3400-\u9fff]", report)
    assert 500 <= len(chinese_characters) <= 1_500
    assert "```" not in report
    assert not re.search(r".{800}", report)
