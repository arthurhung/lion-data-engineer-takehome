# AI Session Index

本索引用於將各 Phase 的 AI 協作紀錄連回任務、驗證證據與人工決策。Task ID 只能協助追蹤，
不能取代題目要求的完整 transcript。完整 transcript 應由應試者從 Codex 匯出後放入
`docs/ai/transcripts/`，提交前須移除 secret 與無關個資。

| Phase | 日期 | 工具 / session | 任務摘要 | Transcript | Implementation commit | Canonical evidence checksum | 狀態 |
|---:|---|---|---|---|---|---|---|
| 0 | 2026-08-25 | Codex task `01a0385e-5109-7862-8ac0-a55fbe2e2553`，標題「執行 Phase 0 Repo 初始化」 | 唯讀盤點、需求對照、骨架、setup/lint/smoke test | [`transcripts/phase_00_bootstrap.jsonl`](transcripts/phase_00_bootstrap.jsonl) | `68e77762` | — | Completed |
| 1 | 2026-08-26 | Codex task `01a03a9f-8a8c-7113-bcc4-496ca58fb87c` | Profiling and quality contract | [`transcripts/phase_01_profiling_quality_contract.jsonl`](transcripts/phase_01_profiling_quality_contract.jsonl) | `05ace53e8728af804c7a41e4e6274b723cfb95fc` | `f326a97e6833d55071b2752581cae31fe5049d7b8efde016e8cfc5048843fa39`（superseded） | Completed（pre-correction） |
| 1 correction | 2026-08-26 | Codex task `01a03c1a-bf2f-7922-a666-f24a26bc44dd` | Phase 1 birth-date sentinel correction；原因：Phase 2 model-design review 發現 parse-valid sentinel 被誤判為 identity change | [`transcripts/phase_01_birth_date_sentinel_correction.jsonl`](transcripts/phase_01_birth_date_sentinel_correction.jsonl) | `5c66c4cb25bee529f9f12002599bba39ac87d94a` | `5cd9bf274d171f7007c4b160addb6fe281f3be1da13939b35c52ecf14a1d9ee8`（current） | Completed |
| 2 | 2026-08-26 | Codex task `01a03c01-720a-7cf1-afbe-47df73a79464` | Base star schema、SCD2、quality gates、reconciliation 與 final Git review | [`transcripts/phase_02_star_schema_scd2.jsonl`](transcripts/phase_02_star_schema_scd2.jsonl) | `ae0a08652c103e2469b2f648de237dc194d542d7` | `2d9cf41622428233c7b83d3de7aa0df860912ba457c72be22f3b26758cdd2c1e` | Completed |
| 3 | 2026-08-27 | Codex task `01a03d4f-f0d1-77e3-a0e0-d1014f8e425c` | Incremental ETL、registry、replay、reconciliation與acceptance | [`transcripts/phase_03_incremental_processing.jsonl`](transcripts/phase_03_incremental_processing.jsonl)；1,291 records；8,075,904 bytes；SHA-256 `02cd5876f033835f6ffae565772fbb76f882ffdad8f199550c37dfd54f4921f6` | `3522c85cd6c51a003234c3521908c6f153406817` | `530804916123aacc3fe4aa4c4c9646cc9fdc35b306af6799b06fb23de052720d` | Completed |
| 4 / Part B | 2026-08-27 | Codex task `01a040b8-6202-7211-9588-56d053a5eb2d` | AI PySpark code review；deployment decision：`NO_DEPLOY` | [`transcripts/phase_04_part_b_code_review.jsonl`](transcripts/phase_04_part_b_code_review.jsonl)；491 records；3,169,132 bytes；SHA-256 `dcd364541cda862273e28342dda3c4cc53156d328c9766466f83b49fb11e337d` | `e9dfe44e3e9987acb896960bb296b52c6a66d520` | Review manifest SHA-256 `2446b8c14245e431147e27ea2b3c4cc61411744187cf44dab5f3a3ae3dda79b9` | Completed |
| 5 / Part C | 2026-08-27 | Codex task `01a04266-4304-7132-98b2-2d24e5231d0d` | Microsoft Fabric 架構；Phase 4 validator fix `00741db586d7ec299139dc2f63af1a1baea62185` | [`transcripts/phase_05_part_c_fabric_architecture.jsonl`](transcripts/phase_05_part_c_fabric_architecture.jsonl)；703 records；6,200,032 bytes；SHA-256 `63980ef6610efe0c54d736d4cebc1649b2f3886007c96664caa74f021c06dca1` | `3596e02c0dd801a8b20aa8c1a27dd9a73199dfcc` | Part C SHA-256 `0b5def8a604969ab155d0b090d03774a87308c1ef0bdbf84e7e775cfd8618915`；validator SHA-256 `ceaf85de5bbd64e6be2a00f6a628674ca95d34a1a7f5e1879de580a90e41f068`；targeted 9 passed；full 48 passed；source integrity 19/19 OK | Completed |

Phase 1 整體狀態：`Completed after sentinel correction`。

Phase 2 狀態：`Completed`。

Phase 3 狀態：`Completed`。

Phase 4 狀態：`Completed`。Review manifest 保留 implementation evidence 產生時的 gate 狀態；
Phase 4 lifecycle 由本次 transcript closeout 正式完成。

Phase 5 狀態：`Completed`。

Phase 2 transcript 驗證資訊：848 records、6,872,171 bytes、SHA-256
`d8f09de47470d8fbd0ace821d11353e4f9dd7d00311db53699218b06efe23c2e`。

## 每次更新規則

1. 一個 Phase 至少建立一筆可追溯 session。
2. Transcript 保留 user prompt、AI 回覆、tool command 與實際輸出；不可只存摘要冒充完整紀錄。
3. AI 建議、實際驗證證據與應試者最終決策分開記錄。
4. 只有 transcript 中實際發生的錯誤或不足才能列入協作報告。
5. 提交前檢查檔案可開啟、索引路徑有效，並完成 secret / 個資清理。
