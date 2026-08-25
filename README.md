# 雄獅資訊資料工程師 Take-home

本 repository 用於建立可在本機重現的資料工程解法。目前 Phase 0 的實作與自動驗證已完成，
但仍等待完整 transcript 匯出與應試者最終人工驗收；尚未開始 Part A、Part B、Part C 或
Module F 的正式答案。

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
| Part A 星型模型與 `dim_member` SCD Type 2 | 2 | schema、transformation、model design、tests | 僅完成路由 |
| Part A base 與三個 increment、冪等重跑 | 3 | ETL CLI、batch audit、rerun evidence | 僅完成路由 |
| Part A 資料品質檢核報告 | 1–3 | detectors、treatment matrix、quality report | 僅完成來源盤點 |
| Part B AI PySpark code review | 4 | `docs/part_b_code_review.md` | 未作答 |
| Part C Microsoft Fabric 架構與取捨 | 5 | `docs/part_c_fabric_architecture.md` | 未作答 |
| 進階模組三選一與 3–5 句選擇理由 | 6 | `docs/module_f_diagnosis.md` | 依規格選 Module F，未作答 |
| 完整 AI transcript 與一頁報告 | 全階段、7 | `docs/ai/` | 建立索引與模板 |
| Reviewer 30 分鐘內可重現 | 7–8 | 最終 README、clean-room evidence | Phase 0 只提供 setup/lint/test |

原始考題與 `SPEC.md` 沒有發現縮減需求的實質衝突。實際資料包比規格建議路徑多一層
`LionDEExam/`；後續程式若引用來源，應使用設定值處理，不應搬移或修改原始檔案。

## 後續命令（尚未實作）

`make profile`、`make build`、`make rerun-proof` 與 `make cleanroom` 將在對應 Phase
完成後才加入。現階段不應將其視為可用介面或已驗證結果。

## 已知限制與人工決策

- Phase 0 inventory 只記錄檔名、欄位、row count、大小與少量格式觀察，不代表資料品質結論。
- 資料清洗、SCD2、fact grain、增量 tie-breaker、幣別與金額策略須由後續 Phase 依證據提出，並由應試者確認。
- Module F 的最終選擇理由必須由應試者以自己的語氣確認。
- AI 協作紀錄的匯出完整性與去識別化需在提交前由應試者確認。
- Phase 0 完整 transcript 尚未匯出；應保存為 `docs/ai/transcripts/phase_00_bootstrap.md`。

## 文件索引

- [`SPEC.md`](SPEC.md)：Phase、交付物與驗收條件。
- [`AGENTS.md`](AGENTS.md)：協作、證據、原始資料保護與 Git 規則。
- [`docs/source_inventory.md`](docs/source_inventory.md)：Phase 0 原始來源盤點。
- [`docs/ai/session_index.md`](docs/ai/session_index.md)：AI session 索引。
- [`docs/ai/collaboration_report.md`](docs/ai/collaboration_report.md)：一頁 AI 協作報告模板。
