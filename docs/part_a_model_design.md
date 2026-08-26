# Part A 星型模型與 SCD Type 2（Phase 2；Phase 3 延伸）

## 狀態與範圍

狀態：`implementation_complete_acceptance_pending`。本階段只使用 `orders_base.csv`、
`members.csv`、`products.csv` 與 `fx_rates.csv`；沒有載入或轉換三個 incremental order files。
本文件與 [`evidence/phase_02/`](evidence/phase_02/) 記錄 clean base build，不能解讀為 Phase 3
incremental idempotency proof。

SQL 是唯一 authoritative transformation：`schema.sql`、`staging.sql`、`quality_gates.sql`、
`dimensions.sql`、`fact_order.sql`、`validation.sql`。Python 只負責 transaction、allowlisted path
binding、SQL 執行順序、validation result 與 deterministic evidence 輸出。

## 分層、grain 與 key

Runtime database 預設位於 `output/warehouse/phase_02.duckdb`，不納入 Git。

| Table | Grain | Primary / unique key | 責任 |
|---|---|---|---|
| `raw.order_event` | base CSV 每個 physical row 一筆 | `source_row_uid` | 原始文字與 ingestion lineage |
| `raw.member_snapshot` | member CSV 每個 physical row 一筆 | `source_row_uid` | 原始生日 sentinel 亦完整保存 |
| `raw.product` | product CSV 每個 physical row 一筆 | `source_row_uid` | 原始產品主檔 |
| `raw.fx_rate` | FX CSV 每個 physical row 一筆 | `source_row_uid` | 原始 dated FX |
| `staging.order_event` | 每個 raw order row 一筆 | `source_row_uid` | typed、timezone/currency normalization、event identity、exact money |
| `staging.member_snapshot` | 每個 raw member row 一筆 | `source_row_uid` | canonical birthday、snapshot/version hash、dedup/conflict metadata |
| `staging.product` | 每個 raw product row 一筆 | `source_row_uid` | typed Type 1 candidate |
| `staging.fx_rate` | 每個 raw FX row 一筆 | `source_row_uid` | typed `DECIMAL(24,8)` rate |
| `quality.issue_hit` | source row × rule | `(source_row_uid, rule_id)` | 保留 overlapping rule hits |
| `quality.entity_rule` | entity × rule | `(entity_type, business_key, rule_id)` | rule-level entity count |
| `quality.entity_disposition` | entity 一筆 | `(entity_type, business_key)` | 單一 final disposition，避免重複 gating |
| `quality.quarantine_row` | quarantined source row 一筆 | `source_row_uid` | 同 row 命中多 rule 仍只保存一次 |
| `curated.dim_date` | calendar date 一筆 | `date_sk`；`calendar_date` unique | role-playing date dimension |
| `curated.dim_product` | accepted product 一筆 | `product_sk`；`product_id` unique | Type 1 product，另含 Unknown Product |
| `curated.dim_member` | member SCD2 version 一筆 | `member_sk`；`(member_id, valid_from)` unique | level/city history，另含 Unknown Member |
| `curated.dim_member_lineage` | member version × accepted source row | `(member_sk, source_row_uid)` | 包含 identical snapshot duplicate lineage |
| `curated.fact_order` | accepted `order_id` 一筆 | `order_id` | base 中唯一最大 `updated_at` 的有效狀態 |

Raw 與 staging 的每筆 row 都保存 `source_file`、1-based `source_row_number`、`batch_order`、
`row_hash`、`source_row_uid`、`ingested_at`。`source_row_number` 只供 lineage；不作 business winner。
`ingested_at` 不參與 row hash、curated checksum 或 committed evidence。

## Surrogate key

Known keys 使用 namespace-versioned SHA-256 前 15 hex digits 轉成正 60-bit `BIGINT`：

```text
product_sk = hash("dim_product|v1|" + product_id)
member_sk  = hash("dim_member|v1|" + member_id + "|" + valid_from)
```

Unknown Member 與 Unknown Product 固定為 0。Validation hard-fail known key 0、hash collision 與同 key
對應多個 natural identities。新增未來 member version只產生新 seed，不改變既有 SK。Tracked-state
`version_hash` 保存完整 64-character SHA-256，seed 明列 schema version、欄位名稱、null marker、
`member_level` 與 `city`。

## Member SCD2 與生日 correction

Tracked attributes 是 `member_level`、`city`。`member_name`、canonical `birth_date`、
`register_date` 是 identity-guarded non-tracked attributes。

來源語意採：2026-04-30 initial full snapshot；2026-05-31、2026-06-30 change snapshots。Change
snapshot 未出現某會員不表示刪除。Tracked state相同不開新版本；變更時才建立版本。

- `valid_from` inclusive；`valid_to` exclusive。
- 同日 order 使用當日新版本。
- Current sentinel 是 `9999-12-31`，不放入 `dim_date`。
- 同 member/date identical payload canonical deduplicate，全部 raw lineage仍保留。
- 同 member/date conflicting payload全組 quarantine；前一版本在 conflict date結束，下一可靠
  snapshot才重新開始。Gap 期間 fact 使用 Unknown Member。
- 接受版本不得重疊；每會員最多一筆 current。

Birthday policy：raw `1900-01-01` 保留，canonical value為 `NULL` 並設
`birth_date_sentinel=true`。只有 sentinel 時另設 `birth_date_unknown=true`，會員仍可進維度。
Sentinel 加唯一 non-sentinel date時，依已核准 data-pattern assumption 將唯一真實日期 restate 到所有
versions，不形成 business-state version；本次有 19 members。只有兩個以上 distinct non-sentinel
dates 才 quarantine 整個 member；本次為 0。

實際結果：8,000 source members中，30 個同日 conflict snapshot keys（60 rows）形成 uncertainty
gaps。`dim_member` 有 8,745 known versions、7,972 represented/current members，加一筆 Unknown
Member。28 個 conflict members沒有任何可靠版本；另 2 個在後續 change snapshot重新開始。
337 facts、30 個 source member IDs 因 as-of gap 關聯 Unknown Member。

完整 row bridge 是：8,991 raw snapshot rows − 60 conflict raw rows = 8,931 accepted lineage
rows；其中8,745 rows開立 known SCD2 versions，另186個 unchanged snapshots只連到既有版本，
不重複開版。30個 conflict snapshot entities代表30個不同 `member_id + extract_date`；每個 entity
各有兩個衝突 physical rows，所以60 rows全組不進 accepted lineage。Unknown Member facts再分成：
28個從未有可靠版本的 source member IDs共323 facts，以及2個日後重新開始版本、但 order落在
uncertainty gap內的 IDs共14 facts。兩者合計337 facts／30 source member IDs。

## Order selection 與 quality gating

Fact grain是每個通過 entity gate 的 `order_id` 一筆，取 canonical events中唯一最大
`updated_at`。Exact duplicate使用完整 canonical event identity deduplicate；所有 raw rows、duplicate
count與 lineage仍保留，不 quarantine order。相同 `order_id + updated_at` 但 payload不同、latest tie
或 canonical invariant conflict時 quarantine整個 order，不用 file order、source row或 row hash挑 winner。

本次 base 有 100,040 event rows、100,000 orders、40 個 multi-event orders。實際 exact duplicate
extra rows、same-timestamp conflicts、canonical invariant conflicts與latest ties均為 0；100,040
canonical events依唯一最大 `updated_at` 收斂成 latest-state candidates。

Raw/canonical invariant bridge由 pipeline SQL重算：40個 multi-event orders中，8個在 raw文字層
看似 invariant conflict；逐欄比較只有 `order_created_at` 是8，`member_id`、`product_id`、
`channel`、`quantity`、`currency`、`amount`、`coupon_discount`、`departure_date`均為0。這8組包含
8列 explicit offset對照、5列 UTC `Z`與3列 `YYYY/MM/DD HH:MM:SS` naive Asia/Taipei表示。
轉成 canonical `TIMESTAMPTZ`後，九個 invariant欄位的 semantic conflict counts全為0，因此
`ORD-004`也是0。

Raw textual difference是來源字串不同；canonical semantic difference則是 normalization後的
instant或其他 typed invariant值真正不同。Raw字串與每筆 lineage全部保留。Timezone
normalization不是選任意 winner；`Z`、對應的 `+08:00`、以及依既定政策解讀為 Asia/Taipei的
naive值若代表同一 instant，就不形成 conflict。只有 canonical instant或其他 invariant payload
真正不同時，才由 `ORD-004` quarantine整個 order。故8→0是語意等價正規化，不是靜默刪除。

Order quarantine rules實際為：50 orders `ORD-010`、300 orders `ORD-011`、40 orders
`ORD-023`。Rule sets有重疊：1 order同時命中 `ORD-010/011`，另1 order同時命中
`ORD-011/023`；因此是388個 distinct quarantined orders，不是390。結果為99,612 facts。

保留但加 flag：NTD normalization、timezone assumption、status-transition warning、missing product與
missing member as-of。本次 facts包含120個 Unknown Product、337個 Unknown Member、200個 NTD
normalizations、2,988個timezone assumptions；base latest state沒有 status warning。

`timezone_assumed` 的 source-event → entity gate → latest fact bridge如下：3,001 flagged source rows
對應3,001 orders；其中2,989 rows/orders通過 entity gate，12 rows/orders因獨立規則 quarantine
（`ORD-010` 1、`ORD-011` 11，兩組之間沒有 overlap）。通過 gate的2,989 orders都有 fact，但其中
1個 multi-event order的 flagged event不是唯一最大 `updated_at`；最後選中的等價事件已有明確
offset，因此 fact-level flag為false。其餘2,988筆 selected fact source events保留
`timezone_assumed=true`。因此3,001→2,988的差額13是「12 quarantine + 1 accepted但非latest」，
不是用減法猜成13筆 quarantine。`ORD-012`本身是 `NORMALIZE`／accepted flag，不是 quarantine rule。

Missing Product使用 `product_sk=0`，並設 `missing_product=true`、
`price_check_not_evaluable=true`；不能因 reference缺失宣稱價格正常。Missing/uncertain member as-of
使用 `member_sk=0`，保留 source `member_id`。

## Quality entity 與 quarantine reconciliation

`quality.entity_disposition` 的117,395 entities由各自明列的 grain相加：

| entity type | grain | ACCEPT | ACCEPT_WITH_FLAGS | QUARANTINE | total |
|---|---|---:|---:|---:|---:|
| order | `order_id` | 96,310 | 3,302 | 388 | 100,000 |
| member_snapshot | `member_id + extract_date` | 8,931 | 0 | 30 | 8,961 |
| member | `member_id` | 7,920 | 80 | 0 | 8,000 |
| product | `product_id` | 300 | 0 | 0 | 300 |
| fx_rate | `rate_date + currency` | 134 | 0 | 0 | 134 |

所以SQL實際公式為 `100,000 + 8,961 + 8,000 + 300 + 134 = 117,395`。Member snapshot
entity用於隔離某會員某次 extract的衝突，member business-key entity則處理跨所有 snapshots的生日
identity語意；它們是兩層不同 gate，不是把同一 grain重複計數。

Quarantine在 entity與physical row兩層的 bridge為：388個 quarantined order entities對應388個
order source rows；30個 quarantined member snapshot entities對應60個 member source rows；member、
product、FX均為0。因此 `quality.quarantine_row = 388 + 60 = 448`。實際 quarantined orders中
multi-event order數為0；若未來出現，entity count仍是一個 order，但 physical rows會保留該 entity
的所有 source rows，兩者不保證相等。Order hard-rule links為390（3種 hard rules），其中2個
orders各有兩條 hard rules；member snapshot hard-rule links為30（1種 hard rule），無 overlap。

`quality.issue_hit` 的3,852是 source-row × rule links；`quality.entity_rule` 的3,821是
entity × rule links。差31來自：`MEM-003` 60 source links壓成30 snapshot-entity links（差30），
`MEM-011` 81 source links壓成80 member-entity links（差1），order rules均無 collapse。兩張表都
不能直接當作 distinct anomaly count；distinct entity由 `entity_disposition` grain判讀。

上述 machine-readable bridge位於 `model_summary.json` 的 `order_invariant_bridge`、
`timezone_assumption_bridge`、`entity_disposition_bridge`、`quarantine_reconciliation`與
`member_scd2_bridge`，所有 arrays均以明確欄位／entity／rule順序輸出。

## Monetary semantics

```text
original_amount              DECIMAL(24,4)
coupon_discount_twd_source   DECIMAL(24,4)
rate_to_twd                  DECIMAL(24,8)
gross/net exact              DECIMAL(38,12)
gross_amount_twd             DECIMAL(28,2)
net_amount_twd               DECIMAL(28,2)

gross_exact = original_amount × rate_to_twd
net_exact   = gross_exact - coupon_discount_twd_source
```

`amount` 已包含 quantity，FX conversion不再乘 quantity。FX date是 normalized Asia/Taipei
order-created date。TWD／normalized NTD明確使用 `1.00000000`；USD／JPY必須取得唯一 dated
rate，沒有一般性 missing-rate fallback。Coupon已是 TWD。Gross/net各自由 exact intermediate
使用 DuckDB Decimal `round(..., 2)`；synthetic `1.005 → 1.01` 已實測。

本次99,612 facts的 gross exact合計為 `25,792,028,503.760350200000`，net exact為
`25,744,761,153.760350200000`；2-decimal gross/net合計分別為 `25,792,028,505.27` 與
`25,744,761,155.27`。這些是不同層級的實際 Decimal reconciliation，不以 float計算。

## Date dimension

Range由 Phase 2 accepted canonical dates推導：base order-created、updated、departure；FX rate；
member extract、register與non-sentinel birth date。Raw birth sentinel與SCD validity sentinel均排除，
也不讀 incremental files。實際連續範圍為 1960-01-03～2026-10-27，共24,405 rows；
`date_sk` 是 `YYYYMMDD` integer。Calendar attributes使用 Gregorian/ISO calendar，不建立缺乏
權威來源的 holiday flag。

## Validation、evidence 與限制

`validation.sql` 實際執行32項 checks，全部 violation count為0，涵蓋grain、SCD overlap/current、
SK collision、fact/date RI、Unknown cardinality、money recomputation、FX/currency leakage、date
continuity、quarantine uniqueness、raw/staging reconciliation、source allowlist、entity source-grain、
member accepted lineage、canonical conflict rule與selected-event timezone flag reconciliation。

兩個乾淨 DB 的 canonical evidence byte-for-byte相同：

```text
2d9cf41622428233c7b83d3de7aa0df860912ba457c72be22f3b26758cdd2c1e
```

這只證明 Phase 2 clean base rebuild stability。Incremental ingestion、batch ledger、upsert與完整
idempotency evidence均留待 Phase 3。

## Phase 3 incremental extension

Phase 3 不改變上述 grain、key、as-of、FX 或 Decimal contract。它以
`audit.source_file_registry` 固定 logical filename、batch order、SHA-256、schema hash、byte size
與 row count；`staging.order_event_lineage` 將每個 physical row 映射至 canonical event hash。
Exact duplicate 的 deterministic 最小 `source_row_uid` 只是 lineage representative，不是 business
winner。Fact仍以唯一最大 `updated_at` 選 latest state；canonical invariant conflict、latest tie或
其他歷史 hard rule會對整個 order採 cumulative quarantine，並刪除先前已存在的 fact。

實際來源沒有 member increment，所以 day1～day3 不產生不同會員版本：known versions皆為
8,745，current members皆為7,972，member version checksum皆為
`d6d050056c26ccf74cf2ba64b3113f332995cc10190df657ed23f7729bbf5356`。Synthetic test另外驗證
tracked change、non-tracked/unchanged snapshot、same-day conflict、exclusive validity、重跑、
single-current與non-overlap；這不是捏造actual member結果。完整Phase 3數字見
[`part_a_rerun_evidence.md`](part_a_rerun_evidence.md)。
