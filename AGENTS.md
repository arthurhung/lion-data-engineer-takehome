# AGENTS.md — Codex 協作規範

## 1. 文件目的

本 repo 為雄獅資訊資料工程師 Take-home 作業。Codex 是開發協作工具，但所有設計決策、資料品質結論、測試結果與文件內容，最終都由應試者本人負責。

本作業需展現：

- 星型模型與 SCD Type 2；
- 可增量、冪等、可重跑的 ETL；
- 以實際資料與查詢為依據的資料品質分析；
- 對 AI 產出 PySpark 程式的批判性審查；
- Microsoft Fabric 架構判斷；
- ML 特徵管線的資料洩漏診斷；
- 成熟且可追溯的 AI 協作方式。

## 2. 需求優先順序

若文件內容衝突，依下列順序處理：

1. 原始考題文件。
2. `LionDEExam/candidate_package/README.md` 與題目附檔。
3. `SPEC.md`。
4. 本文件 `AGENTS.md`。
5. 既有程式與註解。

不得自行改寫或縮減考題要求。遇到會影響結果的模糊需求，先列出假設與選項，交由應試者確認。

## 3. 原始題目檔案保護

`LionDEExam/candidate_package/` 內所有內容均為唯讀原始輸入，包括所有 CSV、`buggy_pipeline.py`、Module D／E／F 附檔與題目 README。

禁止清洗、重新格式化、重新命名、覆寫或在原始資料夾內產生輸出。程式放在 `src/`，SQL 放在 `sql/`，測試放在 `tests/`，文件放在 `docs/`，產出放在 `output/`。

若發現原始檔案遭修改，立即停止並回報。

## 4. 分階段工作方式

一次只能執行 `SPEC.md` 中的一個 Phase。

修改前必須：

1. 完整閱讀該 Phase 的需求與相關檔案。
2. 執行 `git status`，保留使用者既有修改。
3. 說明本階段目標、預計修改檔案、驗證命令與假設。
4. 列出需要應試者親自判斷的事項。

實作期間必須：

- 先分析、後修改；
- 維持小範圍且可 review 的變更；
- 未經同意不得擴大 Phase 範圍；
- 區分 raw、accepted、normalized、quarantined 與 rejected 資料；
- 所有選擇與排序都必須 deterministic；
- 程式與測試同步完成；
- 只記錄實際執行過的命令及結果。

每個 Phase 完成後必須回報：

1. 已涵蓋的考題要求；
2. 新增或修改的檔案；
3. 實際執行的命令；
4. 測試與驗證結果；
5. 由命令產生的筆數、金額或 checksum；
6. 假設、限制與未完成事項；
7. 需要人工確認的內容；
8. 是否進行 commit、push、branch 或 PR 操作。

不得自動開始下一個 Phase。

## 5. 證據與誠信規則

禁止捏造或猜測資料筆數、異常筆數、checksum、金額總計、執行時間、效能倍數、測試結果、指令輸出、Git commit、push 或 CI 狀態。

每個數字都必須可追溯到實際執行的程式、SQL、測試或 evidence 檔案。尚未執行的內容必須明確標示為「預期」、「提案」或「假設」。

未實際執行測試，不得宣稱測試通過。若環境限制導致無法執行，需說明限制及未驗證範圍。

## 6. 資料探索與品質規則

題目刻意放入必須親自檢視資料才能發現的問題，不得只依賴 schema inference 或一次性的 AI profiling。

每個資料品質問題必須包含：

- 問題 ID 與描述；
- 影響 row 數，必要時補充 business key 數；
- 可重現的 SQL 或程式；
- 具代表性的安全 sample；
- 對業務與分析結果的影響；
- 處理方式：接受、正規化、修補、去重、隔離或拒絕；
- 選擇理由與取捨；
- 處理後驗證。

不得為了讓測試通過而直接刪除異常資料。若業務語意不明，優先保留 raw，並採 quarantine 或 quality flag，清楚說明限制。

所有 tie-breaker 必須明確且可重現。禁止使用無排序保證的 `drop_duplicates`、任意 aggregation 或檔案系統順序決定勝出資料。

## 7. 建模與 ETL 規則

### 7.1 星型模型

必須建立 `fact_order`、使用 SCD Type 2 的 `dim_member`、`dim_product` 與 `dim_date`。

建表前先寫明 grain。分析維度使用 surrogate key，同時保留來源 business key 供 lineage 使用。Fact 必須依文件定義的 as-of 規則，關聯到正確的維度版本。

### 7.2 SCD Type 2

`dim_member` 必須保留歷史，不得直接覆蓋舊版本。需明確定義並測試：

- tracked 與 non-tracked attributes；
- business key 與 surrogate key；
- `valid_from` 與 exclusive `valid_to`；
- `is_current`；
- 同會員同日重複或衝突快照；
- null-safe change detection；
- 版本期間不得重疊；
- 每位會員最多一筆 current row；
- 重跑不得新增重複版本。

### 7.3 增量處理

依題目順序先處理 `orders_base`，再處理 day1、day2、day3。保存來源檔名、batch 順序、source row 與 row hash 等 lineage。

同一檔案重跑不得產生重複 fact、重複 SCD2 版本或不同 aggregate。去重與 upsert 必須依文件化的 business timestamp 與 deterministic tie-breaker。

### 7.4 幣別與金額

不得默認缺少匯率的資料為 rate `1.0`。必須說明：

- 匯率使用日期；
- `rate_to_twd` 方向；
- TWD 處理方式；
- 未支援幣別策略；
- decimal precision 與 rounding 時點；
- coupon discount 是否已是 TWD；
- gross/net amount 公式；
- 無效或可疑金額處理方式。

金融金額優先使用精確 decimal，不得無說明地以 binary floating-point 作為權威結果。

## 8. 測試與驗收規則

測試必須覆蓋高風險需求，不可只有 happy path。至少包含：

- deterministic 最新訂單選擇；
- 重複與衝突事件；
- SCD2 變更判定與有效期間；
- 每位會員最多一筆 current version；
- SCD2 期間不重疊；
- fact 與維度 referential integrity，或明確的 unknown/quarantine 策略；
- FX 換算、rounding 及未支援幣別；
- base 或 incremental 同檔重跑；
- 全部 increment 重跑；
- fact row count、order key、金額及 SCD2 checksum 穩定；
- quarantine 與 quality report 筆數符合預期。

必須提供能從乾淨輸出目錄執行的 end-to-end acceptance command。

不得為取得綠燈而降低測試標準或直接更改 expected result；先找出差異原因。

## 9. Part B 程式碼審查規則

`LionDEExam/candidate_package/buggy_pipeline.py` 僅供唯讀審查，不得原地重寫。

每項 finding 必須包含程式位置、問題類型、技術原因、具體業務影響、severity、修正方式及驗證測試。

審查範圍需包含 correctness、data loss、idempotency、SCD2、schema/type、join、currency、performance、scalability、observability 與 deployment safety。最後必須做出 deploy/no-deploy 結論並列出 blocking fixes。

## 10. Part C 架構規則

Microsoft Fabric 功能可能更新，需使用當下官方文件，並標示 GA、Preview、假設與尚未驗證功能。

架構必須同時支援每日批次 BI、分鐘級訂單 dashboard，以及受治理的 Text-to-SQL/RAG。

需包含 Mermaid 架構圖、元件職責、失敗與 replay 流程、安全邊界、observability，以及至少兩項有判斷依據的 trade-off。不得只列 Fabric 產品名稱。

AI 問數需具體定義 semantic metadata、權威指標、synonym、example query、權限、audit log、evaluation dataset、query safeguard 與 result verification。

文件中要標明哪些內容由 AI 協助，哪些是應試者的經驗判斷。

## 11. 進階模組規則

除非應試者正式修改 `SPEC.md`，進階模組選擇 Module F。

Module F 必須區分 target leakage、future information leakage、preprocessing leakage、random split 造成的 temporal leakage、training-serving skew、point-in-time feature 錯誤與 evaluation design 問題。

每個問題都要解釋為何使 offline AUC 虛高、如何驗證、如何修正成 point-in-time-correct feature，以及如何透過 CI/CD 與 production monitoring 防止再犯。不得修改題目提供的 Module F 程式。

## 12. 文件規範

面向 reviewer 使用繁體中文。程式 identifier 與必要技術名詞保留英文。

根目錄 `README.md` 必須讓 reviewer 在 30 分鐘內完成重現，並包含解法摘要、架構與資料流、環境需求、安裝與執行命令、輸出位置、測試方式、冪等證明、已知限制及文件索引。

避免沒有證據的「production-ready」、「已修正所有問題」或「資料品質已保證」等宣稱。

## 13. AI 協作紀錄

考題要求完整 AI 協作紀錄與一頁報告。

每個 Phase 必須：

- 保存完整 transcript 至 `docs/ai/transcripts/`，或提供可追溯的匯出索引；
- 記錄關鍵 prompt、AI 建議、應試者驗證、修正及最後決策；
- 只有實際發生時才能記錄 AI 錯誤；
- 不得為了報告而捏造 AI 失誤；
- 將 AI 建議與實際執行證據分開；
- 繳交前移除 secret 與無關個人資訊。

`docs/ai/collaboration_report.md` 需在一頁內摘要任務拆解、代表 prompt、AI 的實際不足與修正，以及刻意保留由人類負責的決策。

## 14. Git 與安全規則

除非使用者明確要求，禁止 commit、push、建立或合併 branch/PR、amend、rebase、squash、force push 或 destructive Git command。

執行 commit 前必須顯示 `git status`、相關 diff、驗證結果與建議 commit message。Commit 必須小而明確，並對應 `SPEC.md` Phase。

不得 commit secret、virtual environment、cache、生成資料庫、大型暫存輸出或與本題無關的 Codex history。

## 15. 完成定義

單一 Phase 只有在下列條件全部成立時才算完成：

- 必要交付物存在；
- 相關測試與驗證實際通過，或清楚揭露限制；
- evidence 與文件數字一致；
- 原始題目檔案未被修改；
- 未決事項已列出；
- 應試者已完成 review；
- 該 Phase 的 AI 協作紀錄已保存。

整份作業只有在乾淨環境或全新輸出目錄可重現文件結果，且 `SPEC.md` checklist 全數完成後，才能宣告完成。
