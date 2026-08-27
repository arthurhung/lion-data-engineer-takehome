# 雄獅資訊資料工程師 Take-home

本 repository 用於建立可在本機重現的資料工程解法。Phase 0～3 已完成；Phase 3 incremental
warehouse、batch registry、replay proof、deterministic evidence 與 AI evidence closeout 皆已完成。
Part B正式審查報告與 Phase 4 AI evidence closeout 均已完成，狀態為 `Completed`。
Part C Fabric 架構設計與 Phase 5 AI evidence closeout 均已完成，狀態為 `Completed`。Phase 6
Module F 的 Static review／修正設計已完成實作，狀態為
`implementation_complete_acceptance_pending`；正式 deployment 結論為 `NO_DEPLOY`。

> 文件狀態修正：Phase 0 transcript 已存在並完成索引，因此移除舊版「等待 transcript 匯出」文字；
> 此修正不是 Phase 1 功能。

## 原始輸入

原始考題實際位於 `LionDEExam/`，資料包位於
`LionDEExam/candidate_package/`。原始題目範圍為資料包 18 檔加上正式考題 Word 1 檔，
合計 19 檔；這些檔案視為唯讀輸入，不在其中產生任何輸出。
詳細清單、CSV schema、row count 與 SHA-256 manifest 見
[`docs/source_inventory.md`](docs/source_inventory.md)。

## Phase 0 快速驗證

環境需求：Python 3.11 以上。

```bash
make setup
make source-integrity
make lint
make test
```

`make setup` 建立本機 `.venv/`，並安裝 DuckDB、pandas、pytest 與 ruff。

## Phase 1 Profiling

```bash
make profile
make profile OUTPUT_DIR=/tmp/lion-profile-run1 EVIDENCE_DIR=/tmp/lion-profile-run1
```

預設 runtime output 位於 `output/quality/`；小型、deterministic、去識別化 reviewer evidence 位於
`docs/evidence/phase_01/`。完整結果與待人工決策見
[`docs/part_a_quality_report.md`](docs/part_a_quality_report.md)。所有 treatment 仍是 proposed，
Phase 1 detector仍是 profiling authority；Phase 2 treatment application另見 model design。

目前 canonical evidence checksum 為
`5cd9bf274d171f7007c4b160addb6fe281f3be1da13939b35c52ecf14a1d9ee8`；其中 birth-date 與
exact/conflicting duplicate correction policy 已由應試者核准，其餘 treatment 仍待後續人工決策。

## Phase 2 Base Warehouse

請使用不存在的新 DB path；build command會拒絕覆寫既有 warehouse：

```bash
make build-base OUTPUT_DB=/tmp/lion-phase2.duckdb \
  PHASE2_EVIDENCE_DIR=/tmp/lion-phase2-evidence
make validate-base OUTPUT_DB=/tmp/lion-phase2.duckdb \
  PHASE2_EVIDENCE_DIR=/tmp/lion-phase2-evidence
```

SQL 是 authoritative transformation，Python只負責transaction、allowlisted path binding、執行順序、
validation與evidence輸出。Phase 2只載入 `orders_base.csv`、members、products與FX；不讀三個
incremental order files。實際模型、grain、SCD2、quality gating與money結果見
[`docs/part_a_model_design.md`](docs/part_a_model_design.md)。Phase 2 canonical evidence checksum為
`2d9cf41622428233c7b83d3de7aa0df860912ba457c72be22f3b26758cdd2c1e`。

## Phase 3 Incremental Warehouse

從不存在的新 DB path 依 `base → day1 → day2 → day3` 建置：

```bash
make build PHASE3_OUTPUT_DB=/tmp/lion-phase3.duckdb \
  PHASE3_EVIDENCE_DIR=/tmp/lion-phase3-evidence
make rerun-proof PHASE3_OUTPUT_DB=/tmp/lion-phase3.duckdb \
  PHASE3_EVIDENCE_DIR=/tmp/lion-phase3-evidence
```

同 logical filename、相同 SHA-256 的成功檔案回傳 `SKIPPED_ALREADY_APPLIED`；若successful
registry或既有failed／interrupted attempt曾觀察到不同SHA-256則hard fail。只有未登錄的新檔才接受
strict next-batch檢查。Raw append、cumulative staging／
quality、dimension、fact 與成功 reconciliation 在同一 transaction；audit attempt 狀態在該
transaction 外保存。

完整 clean acceptance 會建立兩個全新 DB、各自重跑 increments，並逐檔比較 canonical evidence：

```bash
make phase3-acceptance
```

詳細 batch counts、money totals、checksums、late/conflict 策略與限制見
[`docs/part_a_rerun_evidence.md`](docs/part_a_rerun_evidence.md)。小型 deterministic evidence 位於
[`docs/evidence/phase_03/`](docs/evidence/phase_03/)；DuckDB 與 runtime output 不納入 Git。

## Phase 5 Part C Fabric Architecture

正式答案與兩張內嵌 Mermaid 圖見
[`docs/part_c_fabric_architecture.md`](docs/part_c_fabric_architecture.md)。此文件是 proposed
architecture，不是 Fabric deployment evidence；輕量 validator 只檢查文件結構與必要 coverage：

```bash
.venv/bin/python -m pytest tests/test_part_c_architecture.py
```

目前狀態為 `Completed`；Phase 5 transcript 已完成人工匯出、驗證與索引。

## Phase 6 Module F 訂單取消預測特徵管線診斷

正式答案見 [`docs/module_f_diagnosis.md`](docs/module_f_diagnosis.md)。內容是對題目原始程式的
Static review、唯讀資料 profiling、point-in-time corrected design、temporal evaluation 與防再犯
控制；未執行原始模型，也未宣稱修正版 pipeline 已實測。原始流程存在 full-data target encoding、
future-information leakage、錯誤 sample/label contract、random split 與 split 前 preprocessing 等
deployment blockers，因此結論為 `NO_DEPLOY`。

小型 validator 會從 allowlisted 原始 CSV 重算報告引用的 profiling 數字，並檢查 source checksum、
finding contract、文件狀態與選擇理由；它不取代 ML leakage experiment：

```bash
.venv/bin/python -m pytest tests/test_module_f_diagnosis.py
```

目前狀態為 `implementation_complete_acceptance_pending`。Module F transcript待應試者人工匯出；
Module D／E未作答，Phase 6 尚未標示為 `Completed`。

## 目錄責任

```text
src/lion_de_exam/          Python package
sql/                       後續 Phase 的可重現 SQL
tests/                     自動化測試
docs/                      reviewer 文件與來源盤點
docs/ai/transcripts/       AI 協作紀錄或匯出檔
output/                    可重建產出（預設不納入 Git）
LionDEExam/                唯讀原始考題與資料包
```

## 考題需求對照

| 原始考題要求 | `SPEC.md` Phase | 預定交付物 | Phase 0 狀態 |
|---|---:|---|---|
| Part A 星型模型與 `dim_member` SCD Type 2 | 2 | schema、transformation、model design、tests | 本機實作完成，待人工驗收 |
| Part A base 與三個 increment、冪等重跑 | 3 | ETL CLI、batch audit、rerun evidence | Completed（implementation + AI evidence closeout） |
| Part A 資料品質檢核報告 | 1–3 | detectors、treatment matrix、quality report | Phase 1 本機實作完成，待人工驗收 |
| Part B AI PySpark code review | 4 | `docs/part_b_code_review.md` | Completed |
| Part C Microsoft Fabric 架構與取捨 | 5 | `docs/part_c_fabric_architecture.md` | Completed |
| 進階模組三選一與 3–5 句選擇理由 | 6 | `docs/module_f_diagnosis.md` | Module F implementation完成，待人工acceptance／transcript |
| 完整 AI transcript 與一頁報告 | 全階段、7 | `docs/ai/` | 建立索引與模板 |
| Reviewer 30 分鐘內可重現 | 7–8 | 最終 README、clean-room evidence | Phase 0 只提供 setup/lint/test |

原始考題與 `SPEC.md` 沒有發現縮減需求的實質衝突。實際資料包比規格建議路徑多一層
`LionDEExam/`；後續程式若引用來源，應使用設定值處理，不應搬移或修改原始檔案。

## 已知限制與人工決策

- Phase 2 已套用核准的 SCD2、fact、duplicate、sentinel 與幣別／金額規則。
- Phase 3 採 correctness-first cumulative recomputation，適合本題資料量；未宣稱為大型 production
  partition-pruned 最佳化方案。Audit recovery只支援single writer，啟動時將殘留 `RUNNING`標成
  `INTERRUPTED`。
- 實際沒有 member incremental file；actual day1～day3 member checksum不變，incremental SCD2
  行為以synthetic fixture驗證，不代表實際會員增量結果。
- Module F 的四句選擇理由已由應試者在 Phase 6 planning gate 核准。
- AI 協作紀錄的匯出完整性與去識別化需在提交前由應試者確認。
- Phase 1 完整 transcript 已匯出並更新索引；提交前仍須由應試者確認匯出完整性與去識別化。

## 文件索引

- [`SPEC.md`](SPEC.md)：Phase、交付物與驗收條件。
- [`AGENTS.md`](AGENTS.md)：協作、證據、原始資料保護與 Git 規則。
- [`docs/source_inventory.md`](docs/source_inventory.md)：Phase 0 原始來源盤點。
- [`docs/part_a_quality_report.md`](docs/part_a_quality_report.md)：Phase 1 profiling、detector 與 proposed treatment。
- [`docs/evidence/phase_01/`](docs/evidence/phase_01/)：Phase 1 canonical machine-readable evidence。
- [`docs/part_a_model_design.md`](docs/part_a_model_design.md)：Phase 2 grain、SCD2、fact、money 與實際 reconciliation。
- [`docs/evidence/phase_02/`](docs/evidence/phase_02/)：Phase 2 deterministic base-build evidence。
- [`docs/part_a_rerun_evidence.md`](docs/part_a_rerun_evidence.md)：Phase 3 batch、lineage、replay 與 reconciliation。
- [`docs/evidence/phase_03/`](docs/evidence/phase_03/)：Phase 3 deterministic incremental evidence。
- [`docs/part_b_code_review.md`](docs/part_b_code_review.md)：Phase 4 Part B AI PySpark正式審查報告。
- [`docs/part_c_fabric_architecture.md`](docs/part_c_fabric_architecture.md)：Phase 5 Part C Fabric架構、workload、trade-off與可信AI問數設計。
- [`docs/module_f_diagnosis.md`](docs/module_f_diagnosis.md)：Phase 6 Module F訂單取消預測管線診斷、point-in-time修正設計與防再犯機制。
- [`docs/ai/session_index.md`](docs/ai/session_index.md)：AI session 索引。
- [`docs/ai/collaboration_report.md`](docs/ai/collaboration_report.md)：一頁 AI 協作報告模板。
