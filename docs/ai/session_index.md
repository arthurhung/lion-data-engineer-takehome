# AI Session Index

本索引用於將各 Phase 的 AI 協作紀錄連回任務、驗證證據與人工決策。Task ID 只能協助追蹤，
不能取代題目要求的完整 transcript。完整 transcript 應由應試者從 Codex 匯出後放入
`docs/ai/transcripts/`，提交前須移除 secret 與無關個資。

| Phase | 日期 | 工具 / session | 任務摘要 | Transcript | Implementation commit | 狀態 |
|---:|---|---|---|---|---|---|
| 0 | 2026-08-25 | Codex task `01a0385e-5109-7862-8ac0-a55fbe2e2553`，標題「執行 Phase 0 Repo 初始化」 | 唯讀盤點、需求對照、骨架、setup/lint/smoke test | [`transcripts/phase_00_bootstrap.jsonl`](transcripts/phase_00_bootstrap.jsonl) | `68e77762` | Completed |
| 1 | 2026-08-26 | Codex current task；task ID 待 session 匯出時補入 | Profiling、typed contract、DuckDB detectors、canonical evidence、quality report 與 tests | 尚未建立；完整 session 結束後由應試者匯出 | 未 commit | implementation_complete_acceptance_pending |

## 每次更新規則

1. 一個 Phase 至少建立一筆可追溯 session。
2. Transcript 保留 user prompt、AI 回覆、tool command 與實際輸出；不可只存摘要冒充完整紀錄。
3. AI 建議、實際驗證證據與應試者最終決策分開記錄。
4. 只有 transcript 中實際發生的錯誤或不足才能列入協作報告。
5. 提交前檢查檔案可開啟、索引路徑有效，並完成 secret / 個資清理。
