from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "LionDEExam/candidate_package/module_F/churn_training_pipeline.py"
ORDERS = ROOT / "LionDEExam/candidate_package/dataset/orders_base.csv"
REPORT = ROOT / "docs/module_f_diagnosis.md"
README = ROOT / "README.md"

SOURCE_SHA256 = "5bdea2ba2cad82936189afdddbbf385f8fc7a612839e466622bacfe24f599c23"
SEVERITIES = {
    "MF-001": "CRITICAL",
    "MF-002": "CRITICAL",
    "MF-003": "CRITICAL",
    "MF-004": "HIGH",
    "MF-005": "HIGH",
    "MF-006": "HIGH",
    "MF-007": "HIGH",
    "MF-008": "HIGH",
    "MF-009": "MEDIUM",
    "MF-010": "MEDIUM",
    "MF-011": "LOW",
}
REQUIRED_SECTIONS = {
    "Executive summary",
    "Scope、source checksum及static-review限制",
    "原始pipeline與資料流",
    "Root-cause findings",
    "Leakage causal chain",
    "Corrected point-in-time feature design",
    "Temporal evaluation及rolling backtest",
    "防再犯機制及production monitoring",
    "`NO_DEPLOY`結論及blocking fixes",
    "為什麼選擇Module F，而不選Module D／E",
    "AI-assisted與candidate-owned decisions",
    "References及validation appendix",
}
REQUIRED_FINDING_FIELDS = (
    "Severity",
    "Category",
    "Source location",
    "問題是什麼",
    "Leakage／failure mechanism",
    "為何離線可能看似準確",
    "為何線上會失效或無法重建",
    "具體業務／模型影響",
    "修正方式",
    "Verification test",
    "Causal confidence",
    "Deployment blocker",
)


def read_report() -> str:
    assert REPORT.is_file(), "正式 Module F Markdown 不存在"
    return REPORT.read_text(encoding="utf-8")


def finding_blocks(text: str) -> dict[str, str]:
    pattern = re.compile(
        r"^### (MF-\d{3})\s+—.*?\n(.*?)(?=^### MF-\d{3}\s+—|^## )",
        re.MULTILINE | re.DOTALL,
    )
    matches = pattern.findall(text)
    ids = [finding_id for finding_id, _ in matches]
    assert len(ids) == len(set(ids)), "finding ID 必須唯一"
    return dict(matches)


def test_source_is_fixed_and_report_has_required_sections() -> None:
    source_bytes = SOURCE.read_bytes()
    assert hashlib.sha256(source_bytes).hexdigest() == SOURCE_SHA256
    assert len(source_bytes.decode("utf-8").splitlines()) == 101

    text = read_report()
    headings = set(re.findall(r"^## (.+)$", text, re.MULTILINE))
    assert REQUIRED_SECTIONS <= headings
    assert "static review" in text
    assert "原始模型未執行" in text
    assert "未安裝 scikit-learn" in text
    assert "NO_DEPLOY" in text


def test_findings_have_fixed_contract_and_valid_source_lines() -> None:
    text = read_report()
    blocks = finding_blocks(text)
    assert set(blocks) == set(SEVERITIES)

    blockers: dict[str, str] = {}
    for finding_id, expected_severity in SEVERITIES.items():
        block = blocks[finding_id]
        for field in REQUIRED_FINDING_FIELDS:
            assert f"**{field}：**" in block, f"{finding_id} 缺少 {field}"
        severity = re.search(r"\*\*Severity：\*\* `([^`]+)`", block)
        assert severity and severity.group(1) == expected_severity

        source = re.search(r"\*\*Source location：\*\* ([^\n]+)", block)
        assert source
        line_numbers = [int(value) for value in re.findall(r"\d+", source.group(1))]
        assert line_numbers and all(1 <= value <= 101 for value in line_numbers)

        blocker = re.search(r"\*\*Deployment blocker：\*\* (Yes|No)", block)
        assert blocker
        blockers[finding_id] = blocker.group(1)

    assert blockers["MF-011"] == "No"
    assert all(blockers[finding_id] == "Yes" for finding_id in SEVERITIES if finding_id != "MF-011")
    no_deploy = text.split("## `NO_DEPLOY`結論及blocking fixes", maxsplit=1)[1]
    for finding_id, status in blockers.items():
        if status == "Yes":
            assert finding_id in no_deploy


def test_module_selection_reason_is_four_sentences_and_mentions_all_modules() -> None:
    text = read_report()
    section = text.split("## 為什麼選擇Module F，而不選Module D／E", maxsplit=1)[1]
    section = section.split("## AI-assisted與candidate-owned decisions", maxsplit=1)[0]
    paragraph = next(line for line in section.splitlines() if line.startswith("我選擇Module F"))
    sentences = [sentence for sentence in re.split(r"[。！？]", paragraph) if sentence.strip()]
    assert len(sentences) == 4
    assert all(f"Module {name}" in paragraph for name in ("F", "D", "E"))


def test_profile_numbers_are_recomputed_from_allowlisted_source() -> None:
    text = read_report()
    df = pd.read_csv(ORDERS, dtype=str)
    amount = pd.to_numeric(df["amount"], errors="coerce")
    created = pd.to_datetime(df["order_created_at"], format="mixed", errors="coerce", utc=True)
    departure = pd.to_datetime(df["departure_date"], errors="coerce", utc=True)
    keep = amount.notna() & created.notna() & departure.notna()
    kept = df.loc[keep].copy()
    kept["label"] = kept["order_status"].eq("cancelled").astype(int)
    kept["updated_ts"] = pd.to_datetime(
        kept["updated_at"], format="mixed", errors="coerce", utc=True
    )
    latest = (
        kept.sort_values(["order_id", "updated_ts"], kind="mergesort")
        .groupby("order_id", as_index=False)
        .tail(1)
    )
    member_product_sizes = kept.groupby(["member_id", "product_id"], dropna=False).size()
    product_sizes = kept.groupby("product_id", dropna=False).size()
    currency = kept["currency"].value_counts(dropna=False).to_dict()
    coupon = pd.to_numeric(kept["coupon_discount"], errors="coerce")
    days = (departure[keep] - created[keep]).dt.days

    expected_phrases = {
        f"{len(df):,} 個 physical rows",
        f"{df['order_id'].nunique(dropna=False):,} 個 distinct orders",
        f"{int((df.groupby('order_id', dropna=False).size() > 1).sum()):,} 個 orders 有多列",
        f"{int(df['order_status'].eq('cancelled').sum()):,} 列為 `cancelled`",
        f"{int(latest['order_status'].eq('cancelled').sum()):,} 個 cancelled orders",
        f"{int((member_product_sizes == 1).sum()):,} 個 singleton groups／rows",
        f"product 有 {int((product_sizes == 1).sum()):,} 個 singleton groups／rows",
        (
            f"TWD {currency['TWD']:,}、NTD {currency['NTD']:,}、"
            f"USD {currency['USD']:,}、JPY {currency['JPY']:,}"
        ),
        f"{int((coupon < 0).sum()):,} 列 negative coupon",
        f"`days_to_departure` 為 {int(days.min())}～{int(days.max())} 天",
        f"parse-loss 為 {int((~keep).sum())}",
    }
    missing = expected_phrases - {phrase for phrase in expected_phrases if phrase in text}
    assert not missing, f"報告 profiling 數字與原始 CSV 不一致或遺漏：{sorted(missing)}"


def test_readme_exposes_phase6_status_and_validation() -> None:
    text = README.read_text(encoding="utf-8")
    assert "docs/module_f_diagnosis.md" in text
    assert "implementation_complete_acceptance_pending" in text
    assert "tests/test_module_f_diagnosis.py" in text
    assert "NO_DEPLOY" in text
    assert "Static review" in text
    assert "Module F transcript待應試者人工匯出" in text
    assert "Module D／E未作答" in text
