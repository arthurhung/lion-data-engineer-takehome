# Part A 資料 Profiling 與 Data Quality Contract（Phase 1）

## 狀態、範圍與 evidence

本文件只記錄 Phase 1 observed facts、expected conditions、control checks、candidate data-quality
issues 與 proposed treatment。狀態為 `implementation_complete_acceptance_pending`；尚未建立 SCD2、
dimension、fact、warehouse database 或 incremental merge。

Correction note：Phase 2 model-design review 發現 Phase 1 將 parse-valid sentinel date
`1900-01-01` 誤判成 identity change；經 repo 內 DuckDB detector 重新 profiling 後，已修正 semantic
rule。birth-date 與 duplicate correction policy 已由應試者核准，本次 implementation 仍待人工驗收。

DuckDB 可執行的 [`sql/quality_checks.sql`](../sql/quality_checks.sql) 是 detector 與 supporting
analysis 的唯一權威實作。Python 只負責載入 raw text、執行 SQL、固定排序與 canonical evidence
輸出。Reviewer evidence：

- [`source_profile.json`](evidence/phase_01/source_profile.json)
- [`source_contract.json`](evidence/phase_01/source_contract.json)
- [`issue_summary.json`](evidence/phase_01/issue_summary.json)
- [`analysis_summary.json`](evidence/phase_01/analysis_summary.json)
- [`treatment_matrix.json`](evidence/phase_01/treatment_matrix.json)
- [`representative_samples.json`](evidence/phase_01/representative_samples.json)
- [`evidence_manifest.json`](evidence/phase_01/evidence_manifest.json)

Canonical bundle SHA-256：
`5cd9bf274d171f7007c4b160addb6fe281f3be1da13939b35c52ecf14a1d9ee8`。

```bash
make profile
make profile OUTPUT_DIR=/tmp/lion-profile-run1 EVIDENCE_DIR=/tmp/lion-profile-run1
```

所有 row count 都是 data rows，不含 CSV header。不同 detector 可能重疊，禁止相加成「總異常列數」。

## Finding 分類摘要

| 指標 | 實際結果 |
|---|---:|
| 執行 detector 總數 | 47 |
| non-zero detector 結果數 | 14 |
| candidate `DATA_QUALITY_ISSUE` 數 | 11 |
| non-zero `EXPECTED_CONDITION` 數 | 3 |
| zero-result `CONTROL_CHECK` 數 | 33 |

`ORD-002`、`ORD-022` 與 `MEM-010` 是題目或歷史模型預期情境，不列為資料品質錯誤：

- `ORD-002`：同一 order 多筆狀態事件。
- `ORD-022`：incremental batch 更新既有 order。
- `MEM-010`：合法的 level/city 歷史變化，是 Phase 2 候選 tracked attributes 來源。

## Detector 執行結果

| Issue ID | Rows | Business keys | Finding type | Severity | Proposed disposition |
|---|---:|---:|---|---|---|
| `FX-001` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `FX-002` | 0 | 0 | CONTROL_CHECK | CRITICAL | QUARANTINE |
| `FX-003` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `FX-004` | 0 | 0 | CONTROL_CHECK | WARNING | QUARANTINE |
| `MEM-001` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `MEM-002` | 60 | 30 | DATA_QUALITY_ISSUE | ERROR | QUARANTINE |
| `MEM-003` | 60 | 30 | DATA_QUALITY_ISSUE | CRITICAL | QUARANTINE |
| `MEM-004` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `MEM-005` | 0 | 0 | CONTROL_CHECK | WARNING | NORMALIZE |
| `MEM-006` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `MEM-007` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `MEM-008` | 0 | 0 | CONTROL_CHECK | INFO | ACCEPT |
| `MEM-009` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `MEM-010` | 804 | 803 | EXPECTED_CONDITION | INFO | ACCEPT |
| `MEM-011` | 81 | 80 | DATA_QUALITY_ISSUE | WARNING | NORMALIZE |
| `ORD-001` | 0 | 0 | CONTROL_CHECK | WARNING | NORMALIZE |
| `ORD-002` | 3,799 | 1,889 | EXPECTED_CONDITION | INFO | ACCEPT |
| `ORD-003` | 0 | 0 | CONTROL_CHECK | CRITICAL | QUARANTINE |
| `ORD-004` | 3,613 | 1,796 | DATA_QUALITY_ISSUE | ERROR | QUARANTINE |
| `ORD-005` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `ORD-006` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `ORD-007` | 0 | 0 | CONTROL_CHECK | WARNING | NORMALIZE |
| `ORD-008` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `ORD-009` | 200 | 200 | DATA_QUALITY_ISSUE | WARNING | NORMALIZE |
| `ORD-010` | 50 | 50 | DATA_QUALITY_ISSUE | ERROR | QUARANTINE |
| `ORD-011` | 300 | 300 | DATA_QUALITY_ISSUE | ERROR | QUARANTINE |
| `ORD-012` | 3,001 | 3,001 | DATA_QUALITY_ISSUE | WARNING | NORMALIZE |
| `ORD-013` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `ORD-014` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `ORD-015` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `ORD-016` | 120 | 120 | DATA_QUALITY_ISSUE | ERROR | ACCEPT |
| `ORD-017` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `ORD-018` | 368 | 366 | DATA_QUALITY_ISSUE | WARNING | ACCEPT |
| `ORD-019` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `ORD-020` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `ORD-021` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `ORD-022` | 1,893 | 1,873 | EXPECTED_CONDITION | INFO | ACCEPT |
| `ORD-023` | 40 | 40 | DATA_QUALITY_ISSUE | WARNING | QUARANTINE |
| `ORD-024` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `PROD-001` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `PROD-002` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `PROD-003` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `PROD-004` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `PROD-005` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `PROD-006` | 0 | 0 | CONTROL_CHECK | INFO | ACCEPT |
| `SRC-001` | 0 | 0 | CONTROL_CHECK | ERROR | QUARANTINE |
| `SRC-002` | 0 | 0 | CONTROL_CHECK | WARNING | NORMALIZE |

## `ORD-004` invariant candidate 欄位拆解

同一 order ID 的非狀態欄位衝突不能在缺少 correction event type 或權威 sequence 時以 latest
row 覆蓋。整體 `ORD-004` 是 3,613 event rows、1,796 order IDs。欄位別 evidence 如下；各欄位
最多三筆 sample 與完整 source-file distribution 保存在 `analysis_summary.json`。

| Field | Orders | Event rows | Base | Day1 | Day2 | Day3 |
|---|---:|---:|---:|---:|---:|---:|
| `member_id` | 1,788 | 3,597 | 1,789 | 603 | 602 | 603 |
| `product_id` | 1,783 | 3,587 | 1,784 | 600 | 601 | 602 |
| `channel` | 1,350 | 2,716 | 1,351 | 448 | 442 | 475 |
| `quantity` | 1,350 | 2,718 | 1,351 | 455 | 453 | 459 |
| `currency` | 883 | 1,778 | 884 | 293 | 293 | 308 |
| `amount` | 1,788 | 3,597 | 1,789 | 603 | 602 | 603 |
| `coupon_discount` | 1,691 | 3,403 | 1,692 | 576 | 570 | 565 |
| `order_created_at` | 1,796 | 3,613 | 1,805 | 603 | 602 | 603 |
| `departure_date` | 1,773 | 3,567 | 1,774 | 600 | 596 | 597 |

Proposed decision：`QUARANTINE` 整個衝突 order business key，保留所有 raw events；不使用
source row、檔案順序或 row hash 宣稱任一 payload 具有業務正確性。

## Birth-date sentinel correction：`MEM-009` 與 `MEM-011`

| Field | Members | Snapshot rows | 實際結論 |
|---|---:|---:|---|
| `member_name` | 0 | 0 | 本次沒有姓名變更 |
| `birth_date` | 19 | 38 | raw change；19 members 均為 sentinel 與唯一非 sentinel 並存 |
| `register_date` | 0 | 0 | 本次沒有註冊日變更 |

`birth_date` 值不進 deterministic samples。`MEM-011` sample 只保留 `member_id`、`extract_date`、
`birth_date_sentinel`、non-sentinel distinct count、source file 與 source row number；不輸出姓名或
實際生日。

| Semantic metric | 實際結果 |
|---|---:|
| `1900-01-01` rows / members | 81 / 80 |
| Extract date `2026-04-30` / `2026-05-31` / `2026-06-30` | 76 / 2 / 3 rows |
| 只有 sentinel、沒有 non-sentinel 的 members | 61 |
| Sentinel 與唯一 non-sentinel 並存的 members | 19 |
| 兩個以上不同 non-sentinel birth dates 的 members | 0 |
| Non-sentinel observed min / max | `1960-01-03` / `2003-10-17` |

三種 count 的定義刻意分開：raw birth-date change 是 19 members／38 snapshots；將 sentinel
normalize 為 `NULL` 後的 sentinel-to-known correction/restatement 候選仍是 19／38；真正的
canonical identity ambiguity（兩個以上 distinct non-sentinel dates）是 0／0。因此 `MEM-009`
保留為 zero-result `CONTROL_CHECK`，證明已檢查；`MEM-011` 是 81 rows／80 members 的
`DATA_QUALITY_ISSUE`。兩者與其他 detectors 可能在 raw row 層級重疊，不得相加成總異常量。

核准 treatment：raw `1900-01-01` 保留，canonical `birth_date=NULL`，並設定
`birth_date_sentinel=true`。只有 sentinel 的 member 不 quarantine，設定 `birth_date_unknown=true`；
sentinel 加唯一 non-sentinel 是 correction/restatement assumption，不產生 business-state version；
兩個以上不同 non-sentinel dates 才整個 member `QUARANTINE`，不得任選 winner。

Typed source contract 亦明確分離兩層：raw parse contract 接受 `1900-01-01` 為合法 `DATE` 字串；
semantic contract 將它定義為本來源的 unknown/sentinel。Canonical `birth_date` nullable，raw value
持續保留，quality flags 為 `birth_date_sentinel` 與 `birth_date_unknown`；只有兩個以上 distinct
non-sentinel dates 才觸發 identity ambiguity。

另外，`MEM-002`／`MEM-003` 的同 member、同 extract date 衝突為 60 rows、30 members；整組
`QUARANTINE`，保留所有 raw snapshots，不依 row hash 或檔案順序選 winner。

## Exact duplicate 與 conflicting duplicate policy

`ORD-001` 完全相同 event row 本次為 0，維持 zero-result control。核准 policy 是保留全部 raw
rows 與 lineage；canonical staging 依完整 canonical event identity／row hash deduplicate，保留
`duplicate_count`，不因 exact duplicate 隔離整個 order。`ORD-003` 同一 `order_id + updated_at`
但 payload 不同本次亦為 0；此情境仍整個 order business key `QUARANTINE`，不得用 source row、
file order 或 row hash 選 winner。兩者不可混為同一 duplicate 類型。

## `ORD-012` timestamp 欄位拆解與 normalization contract

| Field | Orders | Event rows | Observed noncanonical format |
|---|---:|---:|---|
| `order_created_at` | 3,001 | 3,001 | `YYYY/MM/DD HH:MM:SS` |
| `updated_at` | 0 | 0 | 無 |

Typed source contract 明確區分：

- accepted raw formats：帶 offset ISO 8601，以及只限本來源的 `YYYY/MM/DD HH:MM:SS`；
- canonical typed format：`TIMESTAMPTZ`；
- normalization assumption：依台灣業務情境及同資料集 `updated_at +08:00` 證據，將該 naive
  format 指定為 `Asia/Taipei`；
- 保留 raw value，並設定 `timezone_assumed=true`；
- 不把其他任意無 timezone timestamp 通用地默認為 Asia/Taipei。

因此 `ORD-012` 是 proposed `NORMALIZE`，不是直接 quarantine。`departure_date` 已由獨立的
`ORD-024` control check 驗證，結果為 0。

## Status transition pair analysis

事件先依 `updated_at`、`batch_order`、`source_row_number` 做 deterministic profiling 排序。資料中
沒有相同 `order_id + updated_at` payload conflict 或 latest tie；tie-breaker 只保證重現，不表示業務
winner。完整 observed pairs：

| Transition | Events | Orders |
|---|---:|---:|
| `cancelled → cancelled` | 121 | 120 |
| `cancelled → completed` | 122 | 122 |
| `cancelled → paid` | 4 | 4 |
| `completed → cancelled` | 238 | 238 |
| `completed → completed` | 265 | 262 |
| `completed → created` | 1 | 1 |
| `completed → paid` | 3 | 3 |
| `created → cancelled` | 146 | 146 |
| `created → completed` | 147 | 147 |
| `created → created` | 22 | 22 |
| `paid → cancelled` | 407 | 407 |
| `paid → completed` | 402 | 402 |
| `paid → paid` | 32 | 32 |

共 1,910 observed transitions。`ORD-018` 不再使用線性 rank；它只將從 `completed`／`cancelled`
這類「候選 terminal-looking」狀態轉到不同狀態的 368 events、366 orders 列為待 review 集合。
這不是正式 invalid-state 判定。Disposition 改為 proposed `ACCEPT`，等待上游正式 state machine。

## Amount semantic distribution 與 `ORD-023`

候選公式與前提：

```text
amount_twd = DECIMAL(amount) × DECIMAL(rate_to_twd)
```

- `amount` 是原幣別的訂單列總金額；FX 換算不得再乘 quantity。
- FX date 使用 normalize 後 `order_created_at` 的 Asia/Taipei business date。
- raw `TWD` 與來源限定 alias `NTD` 使用精確 rate 1；保留 raw currency，canonical currency 為 TWD。
- USD/JPY 必須依日期取得 rate，禁止 `COALESCE(missing_rate, 1)`。
- `coupon_discount` 依題目定義已是 TWD。

113,970 筆 order events 中排除 50 筆 negative amount，以及 120 筆 missing product reference，
因此實際納入 semantic distribution 的母體為 113,800 rows、111,892 orders：

| Comparison | Min | p01 | Median/p50 | p99 | Max | Outside 0.5–2 rows/orders |
|---|---:|---:|---:|---:|---:|---:|
| `amount_twd / base_price_twd` | 0.83783549 | 0.86594407 | 2.49846026 | 4.93238901 | 4749.07860462 | 74,592 / 73,745 |
| `amount_twd / (base_price_twd × quantity)` | 0.83783549 | 0.85277161 | 1.04953901 | 1.24681058 | 1235.46039604 | 40 / 40 |

第二個 ratio 的 median 約 1.05，第一個約 2.50，支持「amount 已含 quantity 的 order-line total」候選
語意。這是 profiling inference，不是 Phase 2 ETL 實作。

`ORD-023` 使用 `amount_twd / (base_price_twd × quantity)`，threshold 是 `< 0.5` 或 `> 2.0`，
實際 40 rows、40 orders。選擇此門檻是因為 central distribution 的 p01 約 0.853、p99 約 1.247，
0.5–2.0 明顯更寬，足以保守容納一般價格差異。`base_price_twd` 只是 reference price，不宣稱每筆
交易必須等於牌價。Outlier 仍 proposed `QUARANTINE`。

## 其他人工 treatment 決策

- `ORD-009`：200 個 `NTD` rows proposed `NORMALIZE` 為 canonical `TWD`，保留 raw currency；只有
  TWD／NTD 明確處理可用 rate 1。
- `MEM-010`：level/city 變化 `ACCEPT`，作為 Phase 2 候選 SCD2 tracked attributes；本階段不建 SCD2。
- `ORD-016`：120 個 missing product reference 保留 raw order；Phase 2 候選 Unknown Product SK 加
  quality flag。本階段不建立 Unknown Product，也不刪除 order。
- `ORD-010`：50 個 negative amount `QUARANTINE`；題目沒有 refund status，不推測為退款。
- `ORD-011`：300 個 coupon discount `-1` `QUARANTINE`；不 repair 成 0 或 NULL。
- FX direction：原幣金額乘 `rate_to_twd` 得 TWD；FX business date 使用 normalized Asia/Taipei
  `order_created_at` date。

所有 disposition 仍是 proposed Phase 2 candidates；Phase 1 沒有將 treatment 套用到資料。

## Phase 3 applied incremental quality semantics

Phase 3 依已核准政策對全部累積 order events重新計算quality。Detector發生在event/source-row
層；`quality.entity_disposition` 將hard rule提升為整個 `order_id` 的cumulative disposition；
`quality.quarantine_row` 再保留該business key全部physical rows及其rule lineage。沒有權威
correction contract，因此後續正常event不能解除 `ORD-004`、`ORD-010`、`ORD-011`、
`ORD-023`等歷史hard quarantine。

`ORD-021` 不以filename字串推測日期，而使用batch metadata contract：base允許
2026-05-01～06-30，day1延伸至07-01，day2延伸至07-02，day3延伸至07-03。Phase 2 base-only
builder仍只讀四個base/reference檔，既有32 checks與canonical evidence不變。

最終累積資料有1,788個canonical invariant-conflict orders，全部quarantine；其3,597筆
source-rule links與所有physical lineage均保留。37個late-arriving orders標記 `INC-001 WARN`：
25個invariant一致者仍可curate，且舊event不會使唯一最大 `updated_at` fact倒退；12個同時命中
invariant conflict者依order-level policy quarantine。各批與最終reconciliation見
[`part_a_rerun_evidence.md`](part_a_rerun_evidence.md)。
