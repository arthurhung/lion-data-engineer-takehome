# SPEC.md — 雄獅資料工程師 Take-home 實作規格

## 1. 文件狀態

- 狀態：規劃基準版
- 建議 repo 名稱：`lion-data-engineer-takehome`
- 繳交方式：除非考試方另有要求，使用 private GitHub repo 連結
- 文件語言：繁體中文；程式與必要技術名詞保留英文
- 進階模組：Module F — 特徵管線除錯

本文件將原始考題轉成可執行的 Phase、交付物與驗收條件，但不取代原始考題。若內容衝突，以原始考題為準，並修正本文件。

## 2. 專案目標

建立一套可在本機重現的資料工程解法，完成：

1. 建立題目要求的星型模型。
2. 使用 SCD Type 2 保存會員歷史。
3. 依序處理 base 與三個 incremental 檔案。
4. 以實際重跑證據證明 idempotency。
5. 找出、量化、解釋並處理資料品質問題。
6. 批判性審查題目提供的 AI PySpark 管線。
7. 設計支援批次 BI、準即時 dashboard 與 AI 問數的 Microsoft Fabric 架構。
8. 診斷 churn feature pipeline。
9. 完整記錄 AI 如何被使用、驗證、修正與限制。

## 3. 非目標

- 不需實際部署 Microsoft Fabric 或其他 cloud resource。
- 不修改原始考題檔案。
- 不同時實作 D、E、F 三個模組。
- 不建置 production orchestration platform 或 UI。
- 不為了得到乾淨結果而隱藏異常資料。
- 不宣稱未實際執行的 benchmark、測試或品質結果。

## 4. 建議技術基準

- Python：CLI 與 orchestration。
- DuckDB：本機 SQL transformation 與 warehouse table。
- pandas：CSV ingestion、資料檢視與報告輔助。
- pytest：自動化測試。
- ruff：lint 與格式檢查。
- Markdown：所有報告。
- Mermaid：Part C 架構圖。

Dependency 維持最小化，並在 `pyproject.toml` 設定版本範圍。Reviewer 不需 cloud account，即可重現主要結果。

若變更技術選擇，需說明原因及對重現流程的影響。

## 5. 建議目錄

```text
lion-data-engineer-takehome/
├── AGENTS.md
├── SPEC.md
├── README.md
├── pyproject.toml
├── Makefile
├── LionDEExam/
│   ├── 01_考題卷_資料工程師TakeHome.docx
│   └── candidate_package/          # 唯讀原始題目資料包
├── src/
│   └── lion_de_exam/
│       ├── cli.py
│       ├── config.py
│       ├── ingestion.py
│       ├── quality.py
│       ├── dimensions.py
│       ├── fact_order.py
│       ├── reconciliation.py
│       └── reporting.py
├── sql/
│   ├── schema.sql
│   ├── staging.sql
│   ├── quality_checks.sql
│   ├── dimensions.sql
│   ├── fact_order.sql
│   └── validation.sql
├── tests/
│   ├── test_quality.py
│   ├── test_scd2.py
│   ├── test_incremental.py
│   └── test_idempotency.py
├── docs/
│   ├── part_a_model_design.md
│   ├── part_a_quality_report.md
│   ├── part_a_rerun_evidence.md
│   ├── part_b_code_review.md
│   ├── part_c_fabric_architecture.md
│   ├── module_f_diagnosis.md
│   └── ai/
│       ├── collaboration_report.md
│       ├── session_index.md
│       └── transcripts/
└── output/                          # 生成檔，通常不 commit
```

實作時可微調 module，但每個交付物的責任與位置必須清楚。

## 6. 共通設計原則

### 6.1 分層與 lineage

- Raw：題目原始檔，永久不修改。
- Staging：完成型別轉換，加入 source file、batch order、source row number、ingested_at 與 deterministic row hash。
- Quality/Quarantine：保留無效或語意不明資料及 rule ID。
- Curated：產出 dim 與 fact。
- Evidence：保存 quality result、reconciliation 與 rerun checksum。

每筆 curated 或 quarantined 資料都應能追溯至來源。

### 6.2 Determinism

所有 winner selection 都必須使用明確且穩定的排序。除非來源 contract 明確定義，否則檔案順序不可單獨作為 tie-breaker。

### 6.3 Idempotency

同一輸入重跑後，analytical state 必須完全一致。證明不得只比較 row count，至少需比較：

- fact row count；
- distinct order count；
- deterministic order-key checksum；
- gross TWD amount checksum；
- net TWD amount checksum；
- dim_member row count；
- current member count；
- member-version checksum；
- 各 quality rule 的 quarantine count。

### 6.4 資料品質處理類型

每個 rule 需選擇：

- `ACCEPT`：資料有效，直接接受；
- `NORMALIZE`：保留 raw value，轉成一致表示；
- `REPAIR`：有權威規則可推導修正；
- `QUARANTINE`：不進 curated，但保留供調查；
- `REJECT`：明確無效且不處理；
- `WARN`：保留資料並加上 quality flag。

所有處理策略在 Phase 1 完成 sample review 前均為提案，不得提前寫死。

## 7. 分析模型初始提案

以下為初始方向，仍需在 Phase 1 依資料驗證，並於 Phase 2 完成正式文件。

### 7.1 `fact_order`

建議 grain：每個來源 `order_id` 一筆，表示截至目前 batch 的最新有效狀態。

歷史 order event 保留在 staging 供 lineage 使用。若 profiling 發現同一 `order_id` 實際代表不同 business entity，而非單純狀態更新，不得直接合併，需使用 quarantine 或另外定義 identity policy。

建議欄位：

- order business key；
- member surrogate key；
- product surrogate key；
- order date key 與 departure date key；
- channel、latest status、quantity；
- original currency 與 original amount；
- FX rate 與 FX date；
- gross TWD amount；
- coupon discount TWD；
- net TWD amount；
- source `updated_at`；
- source file、batch 與 quality status。

### 7.2 `dim_member`

必須使用 SCD Type 2。建議欄位：

- member surrogate key；
- `member_id` business key；
- member name、level、city、birth date、register date；
- `valid_from`；
- exclusive `valid_to`；
- `is_current`；
- source extract date；
- deterministic version hash。

tracked attributes、同日衝突、null change 及 fact as-of semantics，必須在 Phase 2 明確決定並測試。

### 7.3 `dim_product`

因產品資料只有一份 master snapshot，且考題未要求產品歷史，初步採 Type 1。保留來源 product key 並產生 surrogate key。找不到產品的訂單需有 unknown 或 quarantine 策略。

### 7.4 `dim_date`

建立連續日期範圍，涵蓋所有需要分析的 order、update、departure、FX、member extract、register 與 validity 日期。文件中說明 date key 格式與 calendar attributes。

### 7.5 幣別與金額語意

Phase 1 需驗證並正式決定：

- 建議以 `order_created_at` 的 business date 作為 FX date；
- `rate_to_twd` 是否為 original amount 乘以 rate；
- decimal precision 與 rounding 時點；
- original amount 與 currency 必須保留；
- coupon discount 依題目描述視為 TWD；
- TWD、alias currency、missing rate、negative value 與 extreme value 策略。

未支援幣別禁止默認 rate `1.0`。

## 8. 執行階段

## Phase 0 — Repo 初始化與需求對照

### 範圍

- 匯入並保護原始題目；
- 建立工具與目錄骨架；
- 建立 `AGENTS.md`、`SPEC.md`、README 骨架與 AI log template；
- 只做輕量 file/schema inventory，不做正式清洗結論。

### 交付物

- repo skeleton；
- `pyproject.toml`、`.gitignore`、`Makefile`；
- requirement checklist；
- AI transcript/index template；
- source inventory。

### 驗收條件

- 原始檔案內容完全不變；
- setup command 可執行；
- test 與 lint entry point 存在；
- 每項考題要求都對應到 Phase 與交付物；
- 尚未實作正式 Part A、B、C、F 答案。

## Phase 1 — 資料 Profiling 與品質 Contract

### 範圍

- profile Part A 所有資料集；
- 人工抽樣異常資料；
- 定義 typed source contract；
- 實作可重複執行的 quality check；
- 提出並由應試者確認處理策略。

### 必查項目

- duplicate row 與 duplicate business key；
- order 狀態更新與 deterministic latest selection；
- 同一 order 的 invariant attributes 衝突；
- timestamp 格式、timezone、時間先後與 parse failure；
- status、channel、quantity、currency、amount、discount domain；
- FX key 唯一性、coverage、日期與 rate；
- missing member/product reference；
- member snapshot key 與同日衝突；
- SCD2 attribute change、null transition 與可疑 identity change；
- product key 與 domain；
- 金額及 referential reconciliation。

### 交付物

- profiling command；
- machine-readable quality result；
- `sql/quality_checks.sql` 或等價檢核；
- 經人工 review 的 treatment matrix；
- 初版 `docs/part_a_quality_report.md`。

### 驗收條件

- 每個 issue 都有實際 count 與 detector；
- 已人工檢視 representative samples；
- 沒有異常被靜默刪除；
- 文件區分 observed fact 與 assumption；
- quality rule 有自動化測試。

## Phase 2 — 星型模型與 SCD Type 2

### 範圍

- 建立 warehouse schema；
- 建立 `dim_date`、`dim_product`、SCD2 `dim_member`；
- 以 base 建立初始 `fact_order`；
- 文件化 grain、key、as-of rule 與 monetary semantics。

### 交付物

- schema 與 transformation code；
- model diagram 或清楚的關聯說明；
- `docs/part_a_model_design.md`；
- SCD2 與 referential integrity tests。

### 驗收條件

- table grain 與 key 已文件化；
- member version 不重疊；
- 每位會員最多一筆 current version；
- fact 能關聯正確有效版本或明確 unknown policy；
- product/date 關聯可 reconciliation；
- 金額符合已定義 precision 與 FX rule。

## Phase 3 — 增量、冪等與可重跑 ETL

### 範圍

- 依序處理 base、day1、day2、day3；
- 實作 deterministic order-state upsert；
- 防止 duplicate ingestion 與 duplicate SCD2 version；
- 產生 batch audit、reconciliation 與 rerun evidence。

### 交付物

- incremental pipeline CLI；
- batch/source ledger 或等價機制；
- reconciliation output；
- idempotency tests；
- `docs/part_a_rerun_evidence.md`。

### 驗收條件

- clean run 依指定順序成功；
- 每個 incremental 檔重跑後 curated state 不變；
- 整段流程重跑後 curated state 不變；
- row、key、amount、SCD2、quarantine checksum 相同；
- late、duplicate、conflicting、invalid record 符合文件策略；
- README 提供精確重現命令。

## Phase 4 — Part B AI PySpark Code Review

### 範圍

對 `LionDEExam/candidate_package/buggy_pipeline.py` 做 static review，不需執行。

### 交付物

- `docs/part_b_code_review.md`。

### 每項 Finding 格式

- ID 與 severity；
- 程式位置或行為；
- 問題與原因；
- 具體業務影響；
- 修正方式；
- 驗證測試。

### 驗收條件

- 涵蓋 correctness、data loss、idempotency、SCD2、schema/type、currency、join、performance、scalability、observability；
- 業務影響具體；
- 有 deploy/no-deploy 結論；
- blocking fixes 已排序；
- 未修改題目程式。

## Phase 5 — Part C Microsoft Fabric 架構

### 範圍

設計同時支援每日批次 Power BI、分鐘級訂單 dashboard，以及受治理的 Text-to-SQL/RAG。

### 交付物

- 含 Mermaid 圖的 `docs/part_c_fabric_architecture.md`。

### 必要內容

- ingestion、storage、transformation、serving、semantic、AI、governance、observability 職責；
- batch 與 real-time path；
- replay 與 failure handling；
- 至少兩項 trade-off；
- semantic metadata 與 authoritative metric；
- permission、RLS/CLS、audit、query safeguard 與 PII boundary；
- golden questions、expected query/result 與 regression gate；
- AI-assisted 與 candidate-owned 判斷標示；
- 最新 Microsoft 官方文件 citation。

### 驗收條件

- 同時滿足三種 workload；
- trade-off 有明確 workload reasoning；
- Text-to-SQL 配套具體到可建置的 asset 與 control；
- Preview 或不確定功能已標示。

## Phase 6 — Module F 特徵管線除錯

### 選擇理由

Module F 與資料工程師負責的 point-in-time correctness、可重現特徵管線、資料驗證及 ML lifecycle reliability 高度相關。相較 Module D，它不依賴特定硬體 benchmark；相較 Module E，它不依賴外部 LLM judge 的不確定結果。

最終繳交時，應試者必須用自己的語氣改寫為 3–5 句。

### 範圍

- 靜態閱讀 churn pipeline；
- 找出導致 offline AUC 虛高的機制；
- 設計 verification experiment；
- 提出 point-in-time-correct feature 與 evaluation；
- 設計防再犯機制。

### 交付物

- `docs/module_f_diagnosis.md`。

### 驗收條件

- 每個問題都說明 leakage mechanism 與 online impact；
- verification method 可證實或推翻診斷；
- 修正 pseudocode 只使用 prediction time 可取得資訊；
- preprocessing 只 fit training data；
- evaluation 尊重 time/entity boundary；
- offline/online parity 與 monitoring 已說明；
- CI/CD 包含 point-in-time test、data contract、feature lineage、leakage check 與 deployment gate。

## Phase 7 — AI 協作與 Reviewer 文件

### 範圍

- 整理完整 AI transcript；
- 完成一頁 AI 協作報告；
- 完成 reviewer-oriented README；
- 對齊文件數字與 evidence。

### 交付物

- `docs/ai/transcripts/` 或完整匯出索引；
- `docs/ai/session_index.md`；
- 一頁 `docs/ai/collaboration_report.md`；
- 最終 `README.md`。

### 驗收條件

- 每個 Phase 都有完整 AI record；
- 報告包含實際 prompt；
- AI 不足與修正可由 transcript 證明；
- human-owned decision 標示正確；
- 已移除 secret 與無關個資；
- README 能在 30 分鐘內完成重現。

## Phase 8 — Clean-room 最終驗收

### 範圍

- 從乾淨環境或全新 output directory 重現；
- 執行 lint、tests、ETL、quality report 與 rerun proof；
- 檢查文件、Git diff 與繳交 checklist。

### 驗收條件

- setup command 成功；
- required tests 全數通過；
- clean ETL 與 rerun 成功；
- 文件筆數與 checksum 符合 evidence；
- 原始題目未修改；
- 未 commit generated DB、cache、secret 或無關檔案；
- 所有文件內容一致；
- 應試者能親自解釋每項決策。

## 9. 考題需求對照

| 考題要求 | 主要交付物 | Phase | 驗證方式 |
|---|---|---:|---|
| `fact_order` | pipeline、schema、模型文件 | 2–3 | grain、key、reconciliation、rerun tests |
| `dim_member` SCD2 | dimension code 與 tests | 2–3 | version、current row、overlap、rerun tests |
| `dim_product` | dimension code 與 tests | 2 | uniqueness、referential checks |
| `dim_date` | dimension code 與 tests | 2 | continuous range、key checks |
| Grain、幣別與 key 說明 | `part_a_model_design.md` | 2 | 文件與實作交叉檢查 |
| Base 與三個 increment | ETL CLI | 3 | clean end-to-end run |
| 冪等證明 | `part_a_rerun_evidence.md` | 3 | before/after checksums |
| Increment 狀況策略 | quality 與 rerun 文件 | 1–3 | treatment matrix、tests |
| 完整品質報告 | `part_a_quality_report.md` | 1–3 | count、detector、decision、post-check |
| Part B review | `part_b_code_review.md` | 4 | finding checklist、deploy decision |
| Part C 圖與職責 | `part_c_fabric_architecture.md` | 5 | architecture review |
| 至少兩項 trade-off | Part C 文件 | 5 | decision rationale review |
| Text-to-SQL/RAG 配套 | Part C 文件 | 5 | semantic/security/evaluation checklist |
| AI 與本人判斷標示 | Part C 文件 | 5 | explicit label |
| 進階模組 | `module_f_diagnosis.md` | 6 | Module F acceptance gate |
| 模組選擇說明 | Module F 前言 | 6 | 本人語氣 3–5 句 |
| 完整 AI transcript | `docs/ai/transcripts/` | 全階段 | session index completeness |
| 一頁 AI 報告 | `collaboration_report.md` | 7 | prompt/error/human decision checklist |
| 30 分鐘重現 | README | 7–8 | clean-room run |

## 10. 預期命令介面

最終命令可在實作時調整，但應收斂為類似：

```bash
make setup
make profile
make build
make test
make lint
make rerun-proof
make cleanroom
```

命令需文件化，盡量 non-interactive，失敗時回傳 non-zero exit code。

## 11. 最終繳交 Checklist

- [ ] 原始題目檔案保持不變。
- [ ] Part A 程式與 warehouse model 已完成。
- [ ] Grain、key、SCD2 與幣別決策已文件化。
- [ ] Base 與三個 incremental 檔案皆已處理。
- [ ] 同檔與全流程重跑皆有冪等證明。
- [ ] 品質報告包含所有已發現問題、筆數、detector、decision 與理由。
- [ ] Part B 包含業務影響、修正方式與 deploy conclusion。
- [ ] Part C 包含清楚架構圖與至少兩項 trade-off。
- [ ] Text-to-SQL/RAG 的 semantic、security、evaluation 配套具體。
- [ ] Module F 診斷、修正設計與防再犯機制完成。
- [ ] Module 選擇理由已由本人改寫為 3–5 句。
- [ ] 完整 AI 協作紀錄已整理。
- [ ] 一頁 AI 協作報告已完成。
- [ ] README 可於 30 分鐘內重現。
- [ ] Clean-room acceptance 有實際 evidence。
- [ ] Repo 無 secret、cache、virtual environment 或不必要生成檔。
- [ ] 繳交前已確認 private repo reviewer access。

## 12. 變更管理

若 grain、SCD2 semantics、資料異常處理、金額公式、module 選擇或架構有重大修改，必須同步更新：

1. 本規格；
2. 相關 tests；
3. 受影響文件；
4. AI collaboration notes 與決策原因。

在 acceptance gate 與 AI record 均完成前，不得將 Phase 標示為完成。
