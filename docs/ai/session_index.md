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

Phase 1 整體狀態：`Completed after sentinel correction`。

Phase 2 狀態：`Completed`。

Phase 2 transcript 驗證資訊：848 records、6,872,171 bytes、SHA-256
`d8f09de47470d8fbd0ace821d11353e4f9dd7d00311db53699218b06efe23c2e`。

## 每次更新規則

1. 一個 Phase 至少建立一筆可追溯 session。
2. Transcript 保留 user prompt、AI 回覆、tool command 與實際輸出；不可只存摘要冒充完整紀錄。
3. AI 建議、實際驗證證據與應試者最終決策分開記錄。
4. 只有 transcript 中實際發生的錯誤或不足才能列入協作報告。
5. 提交前檢查檔案可開啟、索引路徑有效，並完成 secret / 個資清理。
