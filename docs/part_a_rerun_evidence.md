# Part A Incremental Rerun Evidence（Phase 3）

## 執行契約

批次固定為 `base → day1 → day2 → day3`。每次先驗證 SHA-256、header/schema、byte size與row
count，再查 `audit.source_file_registry`：已成功的同名同hash檔案為
`SKIPPED_ALREADY_APPLIED`；同名不同hash在successful registry、failed或stale attempt狀態皆hard
fail；只有新檔才檢查strict next batch。Registry
每個logical file一筆，`audit.batch_reconciliation`每個成功batch一筆。Replay可新增
`audit.batch_attempt`，但attempt ID、timestamp與執行時間不進analytical checksum。

Raw append、staging、quality、quarantine、dimensions、fact與成功reconciliation在同一DuckDB
transaction。失敗rollback後才將attempt標成`FAILED`。目前是single-writer設計；新attempt會把殘留
`RUNNING`標為`INTERRUPTED`，不提供multi-writer lease或distributed recovery。

## Event identity、latest state與lineage

每個physical row保存source file、batch order、1-based source row、raw row hash與stable
`source_row_uid`。Canonical event hash包含normalized完整event payload；
`staging.order_event_lineage`讓每筆physical row映射到logical event。若有exact duplicate，最小
`source_row_uid`只作lineage representative，不能決定business state。

Fact grain仍是accepted `order_id`一筆。Winner先限制為canonical events，再取唯一最大
`updated_at`；canonical event hash只用於確定性排序／tie檢測，不用來替業務衝突選winner。Late
older event保留並標`INC-001 WARN`，但不使fact倒退。任何歷史event命中hard rule或canonical
invariant conflict，整個order cumulative quarantine；若Phase 2已有fact，incremental projection
會將它移除。

## 實際 batch reconciliation

以下數字由Phase 3 build實際產生；金額都是Decimal，exact為`DECIMAL(38,12)`，rounded為各筆
round至2位後加總。

| Batch | Raw rows / orders | Facts | Accept / flagged / quarantine | Gross exact / rounded | Net exact / rounded | Member versions / current | Quarantine rows |
|---|---:|---:|---:|---|---|---:|---:|
| base | 100,040 / 100,000 | 99,612 | 96,310 / 3,302 / 388 | 25,792,028,503.760350200000 / 25,792,028,505.27 | 25,744,761,153.760350200000 / 25,744,761,155.27 | 8,745 / 7,972 | 448 |
| day1 | 104,655 / 104,000 | 103,016 | 99,734 / 3,282 / 984 | 26,698,985,080.244930200000 / 26,698,985,081.70 | 26,650,122,530.244930200000 / 26,650,122,531.70 | 8,745 / 7,972 | 1,647 |
| day2 | 109,355 / 108,060 | 106,479 | 103,190 / 3,289 / 1,581 | 27,580,182,717.041740200000 / 27,580,182,718.46 | 27,529,704,417.041740200000 / 27,529,704,418.46 | 8,745 / 7,972 | 2,847 |
| day3 | 113,970 / 112,060 | 109,888 | 106,624 / 3,264 / 2,172 | 28,440,830,927.383050200000 / 28,440,830,928.91 | 28,388,704,477.383050200000 / 28,388,704,478.91 | 8,745 / 7,972 | 4,041 |

Actual inputs沒有exact duplicate，所以final physical rows與logical events皆為113,970；synthetic
cross-file fixture另驗證兩筆physical lineage收斂為一個logical event。Final quality有7,854筆
source-row×rule links、6,012筆entity×rule links、2,172個quarantined order entities及4,041筆
quarantine physical rows。`ORD-004`為1,788 orders／3,597 source-rule links；late `INC-001`為37
orders，其中25 accepted、12因invariant conflict quarantined。

## Checksums與重跑

| Batch | Fact order key | Fact money | Member version | Quarantine |
|---|---|---|---|---|
| base | `642008029063076b37b0d61b092afffcc90f5c4d3a8223c357b3b509260b6125` | `68932c6afc06f25b9b185d9421de2faa8020cc4807a11858891bcc4d8fadbe81` | `d6d050056c26ccf74cf2ba64b3113f332995cc10190df657ed23f7729bbf5356` | `af795e698a85de3b0bf41b44c740b7395b294edbefa6ba8d537ade0c2d5af52f` |
| day1 | `3c15248ba71e97a63566f4c035256baa0f32cfd0ddbab5ea56e742a7a0bffe0e` | `6fcf37709d0d80b271e05dfba44dbabbc21683509c572b61c0bc9d87ec01dacb` | 同上 | `2f4b84fbb847314dcc6219f17ee956745721fb98943a2da1d95cf94ddd99153b` |
| day2 | `a09851da1ca895c36daf6186f959cb8e1316ff6223be7eeac9da18bc8ce0a20e` | `6b76af77de0ac4b25bcaf9fd8769f508f6d9cfefc228477cc66967f2ad11e1d5` | 同上 | `29d40638d078ce9c3dac395dce351994fa17bee6a079baa346abf646a802c395` |
| day3 | `a4b4be02a4e56d04bd6e33aee66c370f423377df6ddc04171d64c2c394aeac07` | `afd6be3e0d060d9f23fe2a2068cae9791f023f351bf26107c9845f1ec4ffe479` | 同上 | `f6159ff8a91a2047aea2cd6b6f7c837714fc0f376ea5127cedc98c78832903b2` |

Day1、day2、day3逐檔重送均為`SKIPPED_ALREADY_APPLIED`；完整base→day3重送亦全部skip。
重送前、逐檔後及整段後analytical state checksum均為
`b8f0653ea882b031da570795a542dc2faa4c82a7e40770e625c6af283e64fbf3`。Skipped replay不新增raw、
logical event、quality/quarantine、fact、SCD2或第二份batch reconciliation。

Canonical evidence只含穩定分析狀態，不含absolute path、runtime timestamp、attempt ID或duration。
41個validation checks皆為0 violations。Canonical bundle checksum為
`530804916123aacc3fe4aa4c4c9646cc9fdc35b306af6799b06fb23de052720d`；兩個clean DB的
byte-for-byte identity由`make phase3-acceptance`驗證。Machine-readable內容見
[`evidence/phase_03/`](evidence/phase_03/)。

## 限制

Incremental quality採correctness-first cumulative recomputation，適合本題約11萬event規模；未做
大型production所需的partition pruning或分散式concurrency。實際沒有member incremental file，故
actual SCD2 checksum應保持Phase 2不變；member incremental語意僅由synthetic fixture證明。Missing
member/product、NTD、dated FX、unsupported currency、Decimal precision與rounding沿用Phase 2政策。
