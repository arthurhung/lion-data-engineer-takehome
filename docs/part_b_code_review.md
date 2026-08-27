# Part B｜AI PySpark 訂單管線 Code Review

## Executive summary

結論：**NO_DEPLOY**。這份管線不能證明「保留最新訂單狀態、SCD Type 2、幣別正確、冪等」等
核心宣稱；相反地，原始碼存在任意捨棄訂單事件、覆寫會員歷史、member join fan-out、inner join
靜默遺失資料及重跑 append 重複等風險。這些問題會直接影響訂單筆數、營收及會員歷史，不能只靠
語法檢查或目前的筆數訊息放行。部署前必須先完成本文列出的 blocking fixes，並通過最後一節的
correctness、idempotency、SCD2、money、failure-recovery 與規模測試。

## Review scope

- 審查標的：`LionDEExam/candidate_package/buggy_pipeline.py`，共 179 行。
- 方法：static review；未執行 PySpark、Delta Lake 或 Microsoft Fabric。
- Source SHA-256：`618f9c2a537bc1244fc44f2103eacd5e45c6a36e33ee94f99c499ae6a8e913ff`。
- Part A 文件只用來確認題目語意，例如訂單狀態以 `updated_at` 區分、會員有多個快照、
  `coupon_discount` 是 TWD；不把 Part A curated 結果當成這份 buggy pipeline 的執行結果。
- Severity：`CRITICAL` 表示可能破壞主要資料或核心grain，必須阻擋部署；`HIGH` 表示會造成
  correctness、資料遺失或不可安全營運，亦屬部署阻擋；`MEDIUM` 表示應追蹤但不單獨阻擋部署。

## Findings summary

| ID | Severity | Blocking | Finding |
|---|---|---|---|
| `PB-001` | CRITICAL | Yes | 訂單事件在判斷新舊前已被任意捨棄 |
| `PB-002` | CRITICAL | Yes | `dim_member`不是SCD Type 2，且overwrite會破壞歷史 |
| `PB-003` | CRITICAL | Yes | Fact關聯raw快照造成fan-out，inner product join又會丟單 |
| `PB-004` | CRITICAL | Yes | Fact使用append，重跑與狀態更新都不冪等 |
| `PB-005` | HIGH | Yes | FX inner join與Double計算會遺失訂單或產生不可靠金額 |
| `PB-006` | HIGH | Yes | 無explicit schema且以filter靜默丟棄品質問題 |
| `PB-007` | HIGH | Yes | Python UDF與全表`collect()`無法安全擴展 |
| `PB-008` | HIGH | Yes | 寫入缺乏原子性、audit與有效驗證，仍無條件宣告成功 |

## PB-001 — 訂單事件在判斷新舊前已被任意捨棄（CRITICAL）

位置：第 27–29、41–50 行。

### 問題是什麼

管線只讀當日incremental檔，沒有把事件與既有訂單狀態放在同一個upsert集合。接著先以
`dropDuplicates(["order_id"])` 將每個訂單任意保留一列；Spark沒有被要求依業務時間排序，因此
被保留的payload沒有確定性。去重後每個`order_id`已只剩一列，後面的window不再能選latest；而且
window使用`order_created_at`，不是題目用來區分狀態新舊的`updated_at`。這同時破壞correctness、
determinism及增量狀態合併。

### 業務影響

同一訂單在增量檔出現多個狀態事件時，可能任意留下舊狀態或新狀態；相同輸入在不同partition
layout下也沒有winner保證。只處理當日檔又未與既有狀態merge，無法產生「截至本批次每個訂單
一筆最新狀態」的fact。不能據此宣稱某個實際winner或影響筆數。

### 修正方式

保留全部raw事件與lineage，先完成typed normalization，再以`order_id`分組並依`updated_at`
選唯一最大值。相同`order_id + updated_at`若payload不同，應隔離整個business key或依權威sequence
處理，不能用檔案順序任選。最後將本批candidate與既有fact以`order_id`做deterministic MERGE；
older late event保留供audit，但不得使fact倒退。

### Verification test

以同一`order_id`建立多個不同狀態與`updated_at`，打亂input order及partition後重跑，winner必須
相同；另測same-timestamp conflicting payload會進quarantine，而不是任選一筆。

## PB-002 — `dim_member`不是SCD Type 2，且overwrite會破壞歷史（CRITICAL）

位置：第 86–118 行。

### 問題是什麼

實作只從每位會員選一筆latest snapshot，且相同`extract_date`沒有deterministic tie/conflict策略；
change detection又把來源與整張dim依`member_id`相連，沒有先限制current row，`!=`也不是null-safe。
inner join使新會員不會進`changed`。輸出只有`member_id`、姓名、等級、城市與`valid_from`，沒有
surrogate key、exclusive `valid_to`或`is_current`，也沒有關閉舊版本再插入新版本。最後以
`mode("overwrite")`搭配廣泛的`member_id IS NOT NULL` predicate寫回；對正常非null會員範圍會
依Delta overwrite／replace predicate語意可能大範圍取代既有資料，而不是保存歷史版本；實際
constraint與transaction行為仍須在目標runtime版本確認。

### 業務影響

會員舊等級與城市可能被刪除，歷史訂單無法回答「下單當時的會員屬性」。未變更會員或新會員
也可能不在寫回結果中；既有dim若已有多版，join還可能把一個snapshot展開成多列changed rows。
這不是SCD2，且一旦覆寫後無法由該table追溯被移除的歷史。

### 修正方式

先建立可靠、每個`member_id + extract_date`唯一的snapshot staging；same-day conflict應隔離。
只與`is_current=true`版本比較，使用null-safe equality檢測tracked attributes。對changed member在
同一個受控transaction中把舊版`valid_to`關閉、`is_current=false`，再以deterministic surrogate key
插入新版；new member直接插入，unchanged member不改動。定義`valid_from` inclusive、`valid_to`
exclusive，並保留snapshot lineage。

### Verification test

覆蓋new、unchanged、tracked change、null transition、same-day identical duplicate及conflict；驗證
期間不重疊、每位會員最多一筆current、舊版仍存在，且相同snapshot重跑不新增版本。

## PB-003 — Fact關聯raw快照造成fan-out，inner product join又會丟單（CRITICAL）

位置：第 124–144、172–173 行。

### 問題是什麼

#### A. Raw member snapshot join

`update_dim_member()`回傳的`dim_member`存入區域變數，下一行卻把原始`members` DataFrame傳給
`build_fact()`。題目明示同一會員可能有多筆不同`extract_date`快照，因此只用`member_id` left join
是many-to-many風險，且沒有依訂單日期做SCD2 as-of條件。

#### B. Product inner join

產品使用raw master並做inner join；找不到`product_id`的訂單會直接消失。Fact選出的仍是natural
keys與dimension attributes，沒有product surrogate key或清楚的Unknown／quarantine策略。

### 業務影響

#### A. Raw member snapshot join

一張訂單可能因會員多個snapshot被複製多列，`amount_twd`與`net_amount_twd`在下游加總時會被
放大；也可能套用下單後才出現的會員等級。

#### B. Product inner join

缺少產品reference的訂單會因inner join被靜默移除，造成訂單數與營收漏計。

### 修正方式

#### A. Raw member snapshot join

Fact必須關聯完成的`dim_member`，而不是raw snapshots。以order business date滿足
`valid_from <= order_date < valid_to`取得唯一`member_sk`；找不到有效版本時依明確Unknown／
quarantine政策處理。

#### B. Product inner join

使用唯一`product_id`的`dim_product`取得`product_sk`。reference缺失時採Unknown key加quality flag，
或隔離並報告，不能以inner join靜默刪除。兩種join都要加入前後grain reconciliation，證明每個
accepted `order_id`仍恰好一列。

### Verification test

#### A. Raw member snapshot join

建立同會員兩個SCD2版本及跨界訂單，驗證每單只連到當時版本；比較join前後row count、distinct
order及money totals，任何fan-out都必須使測試失敗。

#### B. Product inner join

建立missing product案例，驗證依政策落Unknown或quarantine；join前後distinct order必須可
reconcile，任何未解釋的silent drop都必須使測試失敗。

## PB-004 — Fact使用append，重跑與狀態更新都不冪等（CRITICAL）

位置：第 151–155 行。

### 問題是什麼

`write_fact()`無條件以Delta append寫入，沒有business key MERGE、partition replace、source ledger
或已處理檔案檢查。`order_date` partitioning只決定檔案布局，不提供`order_id`唯一性，也不會更新
先前狀態。

### 業務影響

同一incremental檔重跑會再次append同一批fact，訂單筆數與金額可能重複；舊訂單狀態更新也會
新增另一列，而不是取代截至目前的狀態。這直接違反題目要求的冪等性。

### 修正方式

建立source-file registry，固定logical filename、SHA-256、schema及batch順序；同檔同hash成功重送
應skip，同名不同hash應hard fail。Curated fact以`order_id`做Delta MERGE／等價transactional upsert，
並以唯一業務時間規則決定update。raw append、quality、dimension、fact及batch reconciliation應在
同一原子批次完成。

### Verification test

同一檔連續執行兩次，再重送完整batch sequence；比較fact row count、distinct order、order-key
checksum及gross/net checksum必須完全相同，且每個成功logical batch只有一份reconciliation。

## PB-005 — FX inner join與Double計算會遺失訂單或產生不可靠金額（HIGH）

位置：第 53、64–80、140–141 行。

### 問題是什麼

#### A. FX join correctness

`order_date`由raw timestamp前10字元截取，沒有先解析timezone與business date；非canonical格式可能
無法對上`rate_date`。FX以`currency + date`做inner join，任何缺rate、unsupported currency或需要
alias normalization的訂單都會消失；也沒有驗證FX key唯一，重複rate可能反向fan-out。程式沒有
明確處理TWD／NTD、FX方向及missing-rate政策。

#### B. Financial precision

金額透過Python UDF先轉成`float`，再輸出binary floating-point `DoubleType`，沒有Decimal precision
與rounding contract；`coupon_discount`依題目已是TWD，程式雖未再做FX換算，但直接從未定型別的
來源欄位相減，仍依賴implicit cast且沒有明確scale。

### 業務影響

#### A. FX join correctness

缺匯率或幣別表示不一致的訂單會被inner join靜默移除；重複FX key可能複製訂單。

#### B. Financial precision

即使join成功，Double rounding也可能讓財務加總與逐筆金額不穩定；discount的implicit cast或scale
不一致則可能使net amount錯誤。這是精度風險，不宣稱目前資料已產生某個實際金額差異。

### 修正方式

#### A. FX join correctness

先把timestamp正規化為明確timezone，再推導業務日期。保留original currency，依核准contract處理
alias；TWD明確使用Decimal rate 1，非TWD必須取得唯一dated rate。先left join並把missing／duplicate
FX隔離，不能fallback或drop；文件化`rate_to_twd`乘法方向。

#### B. Financial precision

用Spark原生Decimal expression計算exact gross/net，最後在明確時點round至報表scale。保留
`coupon_discount`為TWD，不再次換匯，並明確cast至核准的Decimal precision／scale。

### Verification test

#### A. FX join correctness

涵蓋TWD、alias、USD／JPY dated rate、unsupported currency、missing／duplicate FX及timezone邊界；
驗證沒有未解釋的join row loss或fan-out。

#### B. Financial precision

以精確Decimal expected values覆蓋coupon與`1.005` rounding案例，比對gross/net與aggregate checksum；
測試也要證明coupon沒有再次乘FX rate。

## PB-006 — 無explicit schema且以filter靜默丟棄品質問題（HIGH）

位置：第 27–32、53–56 行。

### 問題是什麼

四個CSV reader只設定header，未提供schema、parse policy或fail-fast contract，因此欄位以字串讀入；
後續比較、排序、substring及減法依賴implicit cast。`amount > 0`直接filter，沒有區分parse failure、
null、負值、退款或其他業務語意，也沒有raw retention、quality flag或quarantine。來源header、欄位
domain與檔案identity同樣未驗證。

### 業務影響

字串排序或環境中的cast設定可能改變結果；不合法金額可能觸發job failure，也可能被filter靜默
移除。資料團隊無法回答哪些source rows未進fact、為何被排除，亦無法安全replay或調查上游問題。

### 修正方式

為每個來源定義explicit schema與accepted raw formats，raw層保留原字串及source lineage，再派生
typed staging欄位。parse、domain與business-rule failure分開記錄；無權威修補規則的異常進
quarantine，不能只為得到乾淨fact而刪除。入口先驗header/schema與file hash，失敗回傳non-zero。

### Verification test

注入bad numeric、null、negative、malformed timestamp、unexpected status及schema drift；驗證每筆
raw row都能reconcile到accepted、flagged或quarantined狀態，且沒有silent drop。

## PB-007 — Python UDF與全表`collect()`無法安全擴展（HIGH）

位置：第 67–72、79、157–162 行。

### 問題是什麼

逐列Python UDF做簡單乘法，失去Spark原生expression的code generation及較佳執行計畫；寫入後又
把整張歷史fact `collect()`到driver，只為以Python dictionary計數。資料量隨每日append增長，
驗證成本與driver memory使用會持續上升。

### 業務影響

大批次可能因driver記憶體不足而失敗，或在fact已寫入後才失敗，形成不完整run；UDF序列化成本
也會延長批次時間。因`collect()`讀取的是持續累積的整張fact而非有界batch summary，driver memory
需求沒有固定上限；它又位於fact append之後，所以此處失敗會留下已寫入但run未完成的狀態。這是
production部署阻擋，而不只是後續效能優化。

### 修正方式

以Spark原生Decimal column expression換算金額；驗證使用distributed aggregation，只收集小型
summary。對輸入partition、small reference broadcast與Delta layout先用execution plan及代表性資料
量測，再決定優化，不宣稱未量測倍數。

### Verification test

以代表性規模執行並記錄plan、shuffle、driver peak memory及runtime；測試禁止對完整fact呼叫
`collect()`，且驗證summary row數有固定上限。效能測試不得放寬correctness checksum。

## PB-008 — 寫入缺乏原子性、audit與有效驗證，仍無條件宣告成功（HIGH）

位置：第 19、25–33、151–175 行。

### 問題是什麼

路徑與batch命名硬編碼，`batch_date`沒有allowlist或嚴格順序；沒有source ledger、run ID、row-level
lineage、quarantine metrics或失敗恢復狀態。會員overwrite先發生，fact append後發生，兩者沒有共同
transaction或可證明的checkpoint；任一步失敗都可能留下半套狀態。所謂驗證只是在寫入後collect
全表並印row counts，沒有檢查order uniqueness、money、SCD2、referential integrity或replay。
最後仍無條件印出「資料品質已確保」。

### 業務影響

若dimension成功但fact失敗，或fact已append後validation／driver失敗，重試可能在不一致狀態上再次
寫入。維運人員沒有可靠證據判斷哪個source已commit、是否應retry，也可能把錯誤資料當作成功批次
提供給BI與AI應用。

### 修正方式

將設定外部化並驗證batch contract；建立attempt、source registry及reconciliation audit。使用可恢復
的orchestration，讓raw、quality、dimensions與fact具原子commit邊界或明確checkpoint／compensation。
成功前執行hard gates：source-to-staging reconciliation、fact grain、dimension RI、SCD2 overlap／
single-current、money recomputation、quarantine count及rerun checksum；任一失敗不得發布或印成功。

### Verification test

在dimension更新後、fact寫入前及fact寫入後注入failure，驗證rollback或安全resume且不重複資料；
另讓每個hard gate故意失敗，確認run狀態為FAILED、下游不發布，audit能指出source與failure reason。

## 整體部署結論

### 1. 這段程式碼目前可以部署嗎？

不可以。結論為 **NO_DEPLOY**。

### 2. 為什麼？

PB-001、PB-002、PB-003及PB-004已足以否定核心correctness：訂單latest state不是deterministic，
會員歷史會被破壞，fact join可能放大或遺失訂單，重跑則可能重複append。PB-005與PB-006使金額及
資料品質不可控；PB-007與PB-008進一步顯示此管線無法在production規模安全執行、失敗或replay。
目前的print訊息不是測試證據，也不能抵銷上述blocking defects。

### 3. 部署前必須完成哪些blocking fixes？

八項finding都是blocking：`PB-006 → PB-001 → PB-005 → PB-002 → PB-003 → PB-004 → PB-008 →
PB-007`。即使先不考慮PB-007的規模風險，PB-001～006及PB-008仍已充分支持`NO_DEPLOY`。

### 4. Blocking fixes的修復順序是什麼？

以下是修復依賴順序，不是依severity或ID排序：先建立可靠的typed／quality邊界，才能穩定判斷event
與金額；接著建立正確SCD2及dimension joins，才能安全寫fact；最後完成冪等publish、原子控制、
validation與規模gate。

1. `PB-006`：加入explicit schema、raw lineage、quality disposition及quarantine。
2. `PB-001`：建立以`updated_at`為核心的deterministic event selection及existing-state merge。
3. `PB-005`：完成dated FX、currency、Decimal及rounding contract。
4. `PB-002`：停止破壞性overwrite，完成真正SCD2與歷史／current invariants。
5. `PB-003`：改用surrogate key與as-of dimension join，消除fan-out及silent reference drop。
6. `PB-004`：以source registry及transactional fact upsert保證冪等。
7. `PB-008`：建立原子commit／recovery、audit與hard validation gates。
8. `PB-007`：移除Python UDF與全表collect，完成代表性規模驗證。

### 5. 修正後必須通過哪些驗證？

- Deterministic latest-state：input reorder／repartition後結果不變；tie與conflict依政策處理。
- Idempotency：單檔與完整batch sequence重跑後，order keys、row count及money checksum不變。
- SCD2：null-safe change、exclusive periods、no overlap、single current、same-day conflict及重跑。
- Join／RI：每個accepted order維持一列；dimension as-of正確；missing reference依政策處理。
- Money：dated FX、TWD／alias、unsupported／missing FX、Decimal precision、coupon及rounding。
- Quality：raw rows全部reconcile至accepted、flagged或quarantined，無silent drop。
- Failure recovery：各寫入邊界注入failure後能rollback或safe resume，且不發布partial state。
- Scalability：不collect完整fact；distributed plan在代表性資料量通過資源與runtime gate。

### 6. 哪些行為仍需在Fabric／PySpark runtime確認？

本次未執行PySpark、Delta或Fabric，因此修正後仍須在目標runtime確認：CSV malformed／implicit cast
在實際Spark ANSI設定下的failure mode、Delta `replaceWhere`與MERGE在使用版本的constraint／
transaction語意、跨table publish的orchestration邊界、physical plan／broadcast策略，以及代表性
資料量下的shuffle、driver memory與runtime。這些runtime確認不改變目前由原始碼即可成立的
`NO_DEPLOY`結論。

## Supporting evidence與AI協作狀態

Machine-readable source pinning、finding severity、blocking順序及coverage對照位於
`docs/evidence/phase_04/review_manifest.json`；它只是一致性證據，不取代本報告。對應validator只
檢查source與文件結構，不能取代人工技術審查。本次Phase 4 transcript尚待應試者從Codex人工匯出、
檢查完整性並移除secret／無關個資；在該closeout完成前，本階段狀態為
`implementation_complete_acceptance_pending`。
