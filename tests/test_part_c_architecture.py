from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT = PROJECT_ROOT / "docs" / "part_c_fabric_architecture.md"
README = PROJECT_ROOT / "README.md"

REQUIRED_HEADINGS = (
    "## Executive summary",
    "## Assumptions 與非目標",
    "## Fabric data platform architecture diagram",
    "## 三條 workload path",
    "## 元件與分層職責",
    "## Batch／stream reconciliation",
    "## 關鍵 trade-off",
    "## Text-to-SQL／RAG trusted query flow diagram",
    "### Text-to-SQL 配套",
    "### RAG 配套",
    "### Evaluation release gate",
    "## Security／governance／observability",
    "## AI協助與應試者本人判斷",
    "## 限制及待tenant驗證事項",
    "## 官方參考資料",
)


def _report() -> str:
    return REPORT.read_text(encoding="utf-8")


def _mermaid_blocks(report: str) -> list[str]:
    return re.findall(r"```mermaid\n(.*?)\n```", report, flags=re.S)


def _node_ids(block: str) -> list[str]:
    return re.findall(r"^\s{2,}([A-Z][A-Z0-9_]*)\[[^\n]+\]$", block, flags=re.M)


def _edge_ids(line: str) -> set[str]:
    without_labels = re.sub(r"\|[^|]*\|", "", line)
    parts = re.split(r"\s*(?:-->|-\.->)\s*", without_labels.strip())
    return {
        match.group(1)
        for part in parts
        if (match := re.match(r"([A-Z][A-Z0-9_]*)", part)) is not None
    }


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def test_primary_document_has_required_reviewer_sections_and_two_diagrams() -> None:
    report = _report()
    positions = [report.index(heading) for heading in REQUIRED_HEADINGS]
    assert positions == sorted(positions)
    assert len(_mermaid_blocks(report)) == 2
    assert "implementation_complete_acceptance_pending" in report


def test_mermaid_node_ids_are_unique_and_edges_reference_defined_nodes() -> None:
    for block in _mermaid_blocks(_report()):
        node_ids = _node_ids(block)
        assert node_ids
        assert len(node_ids) == len(set(node_ids))
        defined = set(node_ids)
        edge_ids: set[str] = set()
        for line in block.splitlines():
            if "-->" not in line and "-.->" not in line:
                continue
            edge_ids.update(_edge_ids(line))
        assert edge_ids <= defined


def test_three_workloads_and_reconciliation_are_explicit() -> None:
    report = _report()
    workload_section = report[
        report.index("## 三條 workload path") : report.index("## 元件與分層職責")
    ]
    for path in ("Daily BI", "Minute dashboard", "Trusted AI"):
        assert f"| {path} |" in workload_section
    for field in ("Source", "Freshness", "failure handling", "Ownership", "monitoring"):
        assert field.lower() in workload_section.lower()

    reconciliation = report[
        report.index("## Batch／stream reconciliation") : report.index("## 關鍵 trade-off")
    ]
    for term in (
        "event time",
        "processing time",
        "order count",
        "latest status",
        "gross",
        "net",
        "duplicate",
        "late",
        "quarantine",
        "correction",
        "PROVISIONAL",
        "FINAL",
    ):
        assert term.lower() in reconciliation.lower()


def test_two_required_tradeoffs_have_complete_decisions() -> None:
    report = _report()
    section = report[
        report.index("## 關鍵 trade-off") : report.index(
            "## Text-to-SQL／RAG trusted query flow diagram"
        )
    ]
    assert "Trade-off 1：Lakehouse vs Warehouse" in section
    assert "Trade-off 2：Eventstream vs micro-batch" in section
    for field in (
        "選項 A",
        "選項 B",
        "本題 decision／basis",
        "Benefits",
        "Costs／data duplication",
        "Switch condition",
    ):
        assert f"| {field} |" in section
    assert "Bronze／Silver Lakehouse＋Gold Warehouse" in section
    assert "Eventstream＋Eventhouse" in section


def test_ai_routes_controls_and_release_gate_are_separate_and_complete() -> None:
    report = _report()
    diagram = _mermaid_blocks(report)[1]
    for route in ("structured", "knowledge", "hybrid"):
        assert route in diagram

    for term in (
        "ai_serving",
        "table／column／join／metric allowlists",
        "synonym",
        "SCD2 as-of",
        "Parser／AST",
        "Single statement",
        "SELECT／CTE",
        "Timeout",
        "Row limit",
        "Date-range requirement",
        "Generated SQL",
        "Permission leakage",
        "Unsafe SQL escape",
        "Golden question set",
        "RAG groundedness",
        "Citation correctness",
    ):
        assert _normalized(term) in _normalized(report)
    assert _normalized("Permission leakage與 unsafe SQL escape 是 **0 容忍**") in _normalized(
        report
    )


def test_rag_permission_filter_citation_and_identity_limits_are_explicit() -> None:
    report = _report()
    for term in (
        "Azure AI Search 是候選外部相鄰服務",
        "department／principal ACL",
        "approved與current version",
        "不得先取回未授權全文再 post-filter",
        "source URI／version",
        "low confidence",
        "delegated／OBO",
        "least-privilege service principal",
        "不得使用共用高權限帳號",
    ):
        assert term.lower() in report.lower()


def test_candidate_ownership_and_fact_inference_assumption_labels_exist() -> None:
    report = _report()
    assert "| AI協助內容 | 應試者本人確認、修改或否決 |" in report
    for label in ("`Fact`", "`Inference`", "`Assumption`", "`Tenant validation required`"):
        assert report.count(label) >= 2
    assert "最終元件、trade-off、語意、權限與 release decision 均由應試者負責" in report


def test_official_references_are_allowlisted_and_no_deployment_claim_is_made() -> None:
    report = _report()
    urls = re.findall(r"\]\((https://[^)]+)\)", report)
    assert len(urls) >= 10
    allowed_hosts = {"learn.microsoft.com"}
    assert {urlparse(url).hostname for url in urls} <= allowed_hosts
    assert len(urls) == len(set(urls))

    prohibited_claims = (
        "已部署Fabric",
        "已建立Fabric tenant",
        "已執行Fabric pipeline",
        "已建立OneLake",
        "已實作Text-to-SQL",
    )
    assert not any(claim in report for claim in prohibited_claims)
    assert "並非\nFabric deployment evidence" in report


def test_readme_exposes_part_c_targeted_validation_and_pending_transcript() -> None:
    readme = README.read_text(encoding="utf-8")
    assert "docs/part_c_fabric_architecture.md" in readme
    assert ".venv/bin/python -m pytest tests/test_part_c_architecture.py" in readme
    assert "implementation_complete_acceptance_pending" in readme
    assert "Phase 5 transcript 待人工匯出" in readme
    part_c_row = next(line for line in readme.splitlines() if "Part C Microsoft Fabric" in line)
    assert "Completed" not in part_c_row
