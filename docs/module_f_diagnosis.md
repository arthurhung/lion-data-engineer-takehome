# Module F｜訂單取消預測特徵管線診斷

## Executive summary

**狀態：`implementation_complete_acceptance_pending`。部署結論：`NO_DEPLOY`。**

原始管線的主要問題不是 Logistic Regression 本身，而是 label、特徵與評估資料的時間邊界被破壞。
程式先用每一列目前的 `order_status` 建立 label，再用包含該列、未來列及 test labels 的完整資料計算
三組取消率，之後以完整資料 fit scaler，最後才 random split。這使 offline test features 已帶有 outcome
訊號，且不能在訂單建立時用相同語意重建，是 offline AUC 虛高的直接且可信主因。

本報告建議把問題重新定義為「在訂單建立、必要建立時欄位已可取得時，預測一個 logical order
之後是否最終取消」，採 point-in-time features、成熟 label、chronological split、rolling backtest、
time-aware target encoding 與 train-only preprocessing。原始碼與題目敘述沒有 production log，故本報告
不把上述問題宣稱為線上 AUC 約 0.55 的唯一原因，也不捏造修正後指標。

## Scope、source checksum及static-review限制

- 審查標的：`LionDEExam/candidate_package/module_F/churn_training_pipeline.py`。
- SHA-256：`5bdea2ba2cad82936189afdddbbf385f8fc7a612839e466622bacfe24f599c23`。
- 檔案大小／行數：4,074 bytes／101 lines；Git tracked，且受 source manifest 保護。
- 方法：static review，加上對 allowlisted `orders_base.csv` 的唯讀 profiling。
- **原始模型未執行**，未安裝 scikit-learn，沒有模型 artifact 或本次 AUC。
- 原始碼能證明 feature computation 與 split 順序；「因此可能解釋線上落差」是因果推論，仍需
  production-like replay、serving logs 與成熟 labels 驗證。
- Prediction timestamp、label maturity、release threshold 等業務契約依本次 candidate-owned 決策提出；
  最終線上決策時點及成熟期限仍須 business／ML owner 確認。

唯讀 profiling 的描述性結果如下。原始資料有 100,040 個 physical rows、100,000 個 distinct orders，
其中 40 個 orders 有多列；physical rows 中 14,248 列為 `cancelled`。僅為比較 grain，依 parsed
`updated_at` 描述性選出每個 order 的 latest state 後有 14,241 個 cancelled orders；這不是已確認的
業務 label winner。member-product 有 95,891 個 singleton groups／rows，其 encoding 必然直接等於
自己的 label；product 有 120 個 singleton groups／rows，亦直接暴露自己的 label，兩者不得相加。
Currency 分布為 TWD 66,690、NTD 200、USD 22,128、JPY 11,022；另有 300 列 negative coupon。
目前 `days_to_departure` 為 6～119 天，沒有負值；目前三個 `dropna` 欄位 parse-loss 為 0，因此相關
finding 是未來批次的 silent-loss 風險，不是聲稱本次已遺失資料。

## 原始pipeline與資料流

```text
orders_base physical rows
  -> parse amount / created timestamp / departure date，dropna            (24–32)
  -> 以當前 physical-row status 建立 label                              (30–31)
  -> 用完整含 label 資料計算 member / member-product / product 統計       (35–54)
  -> 計算 order-level numeric features                                   (56–65)
  -> 全欄位 fillna(0)，用完整資料 fit StandardScaler                      (69–80)
  -> random row split                                                     (81)
  -> fit model，只以同一受污染資料的 train/test AUC 評估                 (83–94)
```

題目是**訂單取消預測**，不是 customer churn。程式檔名雖含 `churn`，樣本與 outcome 都應以 logical
order 定義。原始說明宣告會使用 `members.csv`，但 `load_orders()` 實際只讀 orders base。

## Root-cause findings

### MF-001 — Full-data target encoding洩漏label

- **Severity：** `CRITICAL`
- **Category：** target leakage
- **Source location：** lines 30–31, 35–54, 75–81
- **問題是什麼：** `member_cancel_rate`、`member_product_cancel_rate`、`product_cancel_rate` 都由包含
  train/test 全部 labels 的同一 DataFrame 計算，然後才切分資料。
- **Leakage／failure mechanism：** 每列自己的 label、test labels，以及在該列 prediction time 之後才
  成熟的 labels 都會改變 encoding。95,891 個 member-product singleton rows 與 120 個 product singleton
  rows 的 encoding 直接等於自己的 label；兩組可能重疊，不合併計數。
- **為何離線可能看似準確：** 模型可從取消率特徵讀到 target 本身或高度濃縮的 target 訊號。
- **為何線上會失效或無法重建：** 新訂單的最終 label 尚不存在，也沒有包含未來與 test labels 的
  full-data mapping，線上 feature 語意必然不同。
- **具體業務／模型影響：** 取消風險排名可能主要反映 outcome 回填，而非可提前採取行動的訊號，造成
  客服資源或提醒優惠錯配。
- **修正方式：** training rows 使用 time-aware expanding history 或 temporal OOF encoding，每列排除
  自己且只納入 cutoff 前已成熟 outcome；validation/test 使用先前 training period 的 frozen mapping，
  配合 smoothing、minimum support 與 hierarchical/global fallback。
- **Verification test：** 改動 test-period labels 不得改變 train features；逐列重算證明 encoding 不含
  自己的 label；future-shift sentinel 不得影響較早 encoding。
- **Causal confidence：** Certain（原始碼直接證明）；對線上約 0.55 的貢獻幅度需 runtime 驗證。
- **Deployment blocker：** Yes。

### MF-002 — Future-information／point-in-time leakage

- **Severity：** `CRITICAL`
- **Category：** future-information leakage / point-in-time correctness
- **Source location：** lines 24–25, 35–54
- **問題是什麼：** 管線沒有 prediction timestamp、observation window 或 outcome availability time；
  `member_order_cnt` 與三組取消統計直接使用整份 base。
- **Leakage／failure mechanism：** 較晚訂單、較晚狀態與較晚成熟結果會回流到較早樣本的特徵，形成
  time travel；即使排除當列 label，仍可能使用未來資訊。
- **為何離線可能看似準確：** 後見之明的行為量與結果統計能區分已知 outcome。
- **為何線上會失效或無法重建：** 訂單建立當下只能查到 cutoff 前已存在且可用的資料，不能查詢未來
  訂單或未成熟 outcome。
- **具體業務／模型影響：** 上線風險分數的分布及排序會與訓練時不同，既有 intervention capacity
  planning 與 threshold 失去依據。
- **修正方式：** 每筆 sample 明列 `prediction_ts`、feature event time、outcome available time；所有
  point-in-time join 均要求兩種時間不晚於 cutoff，並保存 source max event time 與 lineage。
- **Verification test：** 修改 cutoff 後的事件或 label 不得改變較早 features；assert 每個 feature 的
  source event/availability timestamp `<= prediction_ts`。
- **Causal confidence：** Certain（原始碼直接證明缺少時間過濾）。
- **Deployment blocker：** Yes。

### MF-003 — Sample grain與label maturity錯誤

- **Severity：** `CRITICAL`
- **Category：** label contract / sample grain
- **Source location：** lines 24–32, 97–100
- **問題是什麼：** 每個 physical row 都成為樣本，label 是該列當前 status，而不是 prediction 後已成熟
  的 logical-order 最終取消結果。base 有 100,040 rows、100,000 orders 與 40 個 multi-row orders。
- **Leakage／failure mechanism：** 同 order 可能重複進入資料集；中間狀態可能被當成 negative，且一個
  order 的不同事件可能落入不同 partition。這既污染 label，也破壞獨立樣本假設。
- **為何離線可能看似準確：** 重複或高度相似事件可跨 split，當前狀態也可能比 prediction point 更接近
  最終結果。
- **為何線上會失效或無法重建：** 建立訂單時尚未知道之後的狀態序列；未成熟訂單不能可靠標成未取消。
- **具體業務／模型影響：** 模型可能對「目前尚未取消」而非「最終不取消」學習，低估 delayed
  cancellation，導致錯過應介入訂單。
- **修正方式：** deterministic 收斂為每個 logical order 一個 sample；prediction point 採 canonical
  `order_created_at` 候選，label 只從 prediction 後的 outcome window 取得，未達 maturity 者排除而非
  填 0。最終 maturity 期限由 business owner 確認，不捏造固定天數。
- **Verification test：** sample key 唯一；同 order 不跨 partitions；未成熟 orders 不進 supervised
  evaluation；label lineage 必須落在 prediction 後且在 maturity cutoff 前。
- **Causal confidence：** Grain mismatch 為 Certain；最終 label winner／maturity rule 待業務確認。
- **Deployment blocker：** Yes。

### MF-004 — Random temporal／entity split

- **Severity：** `HIGH`
- **Category：** temporal leakage / evaluation split
- **Source location：** line 81
- **問題是什麼：** `train_test_split` 對 rows 做 random split，沒有 chronological boundary、same-order
  isolation 或 future holdout。
- **Leakage／failure mechanism：** 同時期資料及相同 member/product/order 的相關資訊可能跨 partition；
  test 並非部署後的 future unseen period。
- **為何離線可能看似準確：** train/test 分布與 entity 高度相似，且與 upstream full-data features 疊加。
- **為何線上會失效或無法重建：** 正式 serving 面對之後發生的訂單與 distribution shift，而不是隨機抽出
  的同時期 rows。
- **具體業務／模型影響：** release decision 無法代表下一期訂單，可能讓 seasonal、channel 或 product
  mix 變化後的模型錯誤通過。
- **修正方式：** chronological train/validation/test 加 rolling backtest；同 logical order 強制隔離。
  不強制完全隔離 member/product，因 serving 會預測既有 entity，但另報 unseen cold-start slices。
- **Verification test：** partition 時間單調且無 overlap／反轉；同 order partition count 必須為 1；
  separately report seen/unseen member/product performance。
- **Causal confidence：** Certain（split 行為由原始碼直接證明）。
- **Deployment blocker：** Yes。

### MF-005 — Split前fit scaler造成preprocessing leakage

- **Severity：** `HIGH`
- **Category：** preprocessing leakage
- **Source location：** lines 75–81
- **問題是什麼：** `StandardScaler.fit_transform(X)` 在 train/test split 前執行。
- **Leakage／failure mechanism：** test period 的 mean 與 variance 進入 training transformation。
- **為何離線可能看似準確：** preprocessing 已提前知道 holdout distribution，降低真正 future shift。
- **為何線上會失效或無法重建：** serving 只能使用已發布的 training scaler；不應以未來流量重算。
- **具體業務／模型影響：** release evaluation 對 amount、quantity 等分布變化過度樂觀，threshold 及
  calibration 可能失準。
- **修正方式：** 先依時間切分，再把 imputer、encoder、scaler、model 封裝為同一 versioned pipeline；
  fit-based transformer 僅 fit training partition。
- **Verification test：** 驗證 scaler 的 row IDs、mean、scale 僅由 train 重算；修改 validation/test
  features 不得改變 fitted scaler state。
- **Causal confidence：** Certain。
- **Deployment blocker：** Yes。

### MF-006 — Evaluation contract不完整

- **Severity：** `HIGH`
- **Category：** evaluation design
- **Source location：** lines 81, 86–94
- **問題是什麼：** 只有單次 random split 的 train/test ROC-AUC 與係數，沒有 rolling backtest、
  calibration、threshold、class/decision cost、segment 或 uncertainty 評估。
- **Leakage／failure mechanism：** 這不是新的 label leakage root cause；它讓前述 contamination 不易被
  發現，也讓單一受污染 AUC 被誤當 release evidence。
- **為何離線可能看似準確：** 單一 aggregate ROC-AUC 可掩蓋時間、cold-start 與 segment 失效。
- **為何線上會失效或無法重建：** production decision 需要固定 threshold、capacity/cost 與 delayed
  labels；原流程沒有對應 contract。
- **具體業務／模型影響：** 即使排序指標尚可，也可能在客服可處理量下產生過多 false positives，或在
  高價／特定通路漏掉高成本 cancellation。
- **修正方式：** rolling temporal folds；同時報 ROC-AUC、PR-AUC、calibration、threshold precision/
  recall、cost metric 與 member/product/channel/currency slices，門檻由 owner 核准。
- **Verification test：** 固定 dataset/config 可重現所有 fold；release gate 需逐項檢查候選 thresholds
  與 slices，任一 blocking metric 未達標即 fail。
- **Causal confidence：** Certain for contract gap；實際 metric 結果需 runtime 驗證。
- **Deployment blocker：** Yes。

### MF-007 — Training-serving skew與artifact lifecycle缺失

- **Severity：** `HIGH`
- **Category：** training-serving skew / reproducibility
- **Source location：** lines 35–66, 69–94
- **問題是什麼：** feature builder 需要含 label 的完整 DataFrame，且 mapping、scaler、schema、model
  沒有組成可發布、可追溯的 artifact。
- **Leakage／failure mechanism：** offline 使用 batch-only、outcome-dependent 計算；serving 無法用同一
  implementation 和資料可用性重建。
- **為何離線可能看似準確：** offline 能自由存取完整資料並即時計算 mapping。
- **為何線上會失效或無法重建：** serving 缺少 frozen mapping、preprocessor version、feature cutoff
  與 fallback contract。
- **具體業務／模型影響：** 同一訂單可在 batch 與 API 得到不同分數；事故時無法辨識使用哪個 mapping、
  dataset 或 scaler，也無法安全 rollback。
- **修正方式：** 單一 versioned feature contract；封裝 preprocessing＋model；registry 保存 dataset、
  mapping、schema、code、config、lineage 與 rollback target。
- **Verification test：** golden orders 在 offline/serving 得到相同 features／score；artifact save-load
  round trip 一致；任一 prediction 可追溯所有版本。
- **Causal confidence：** High；實際 serving implementation 未提供，差異幅度待 production-like 測試。
- **Deployment blocker：** Yes。

### MF-008 — Mixed-currency money feature

- **Severity：** `HIGH`
- **Category：** feature correctness / currency
- **Source location：** lines 25–26, 60, 62–65
- **問題是什麼：** `amount` 是原幣金額，但 TWD、NTD、USD、JPY 直接進同一 numeric feature；coupon
  已是 TWD。實際分布分別為 66,690、200、22,128、11,022 rows。
- **Leakage／failure mechanism：** 這不是直接 label leakage；不同幣別共用 scale 造成 feature 語意錯誤，
  並可能放大 offline/serving FX 處理差異。
- **為何離線可能看似準確：** currency mix 可能成為資料期間或產品的 proxy，模型可利用偶然相關。
- **為何線上會失效或無法重建：** currency/product mix 或 FX 變動後，相同 numeric amount 不代表相同
  價值；若 serving 換匯策略不同更會 skew。
- **具體業務／模型影響：** 高價值訂單排序可能因幣別而顛倒，使 intervention ROI 與 segment 分析失真。
- **修正方式：** 依 prediction time 可取得的 event/business date FX 轉為 TWD，明定 rate direction、
  missing FX 與 rounding；NTD alias 規則化，coupon 保持 TWD且不得再次換匯，保留原幣與 lineage。
- **Verification test：** 等值多幣訂單轉換一致；missing/duplicate FX hard fail 或 quarantine；coupon 不被
  再換匯；offline/serving 使用同一 FX snapshot/version。
- **Causal confidence：** Certain for mixed units；對 AUC 落差的實際貢獻需 runtime 驗證。
- **Deployment blocker：** Yes（只要保留 money feature）。

### MF-009 — Missing／invalid value與schema contract

- **Severity：** `MEDIUM`
- **Category：** data quality / schema
- **Source location：** lines 24–29, 60, 75
- **問題是什麼：** parse error 會成為 null後被 `dropna` 靜默刪除；其他 features 以 `fillna(0)` 將 unknown
  當真實零，且缺少 schema/domain gate。現有 base 的三個 drop 欄位 parse-loss 為 0，但有 300 列
  negative coupon。
- **Leakage／failure mechanism：** 不是已證明的 AUC leakage；未來批次可在無告警下改變樣本母體，或
  讓 invalid/unknown 和合法零值不可區分。
- **為何離線可能看似準確：** 訓練資料的錯誤列可被靜默排除，形成比 serving 流量更乾淨的樣本。
- **為何線上會失效或無法重建：** serving 必須即時處理 parse failure、missing 與 invalid domain，不能
  假定全部為零或直接不評分。
- **具體業務／模型影響：** 特定來源或通路可能被系統性排除，negative coupon 也可能形成無業務語意的
  分數，卻沒有 audit trail。
- **修正方式：** versioned schema/domain contract、missing indicators、欄位別 imputation；invalid rows
  hard fail、quarantine 或明確 abstain，不靜默刪除。
- **Verification test：** schema drift 必須 hard fail/quarantine；missing 與 zero fixture 產生不同表示；
  input/output/quarantine counts 可 reconciliation。
- **Causal confidence：** Certain for code risk；目前 drop-loss 為 0，未宣稱已發生該資料損失。
- **Deployment blocker：** Yes，直到策略與 gate 完成。

### MF-010 — Timestamp／timezone semantics

- **Severity：** `MEDIUM`
- **Category：** temporal feature correctness
- **Source location：** lines 27–29, 57–59
- **問題是什麼：** created timestamp 解析為 UTC instant，但 naive departure date 直接 localize 為 UTC，
  沒有 business timezone 或 date-only contract。目前 `days_to_departure` 為 6～119，未觀察到負值。
- **Leakage／failure mechanism：** 不是直接 label leakage；錯誤 timezone/date semantics 可產生 off-by-one、
  invalid days，並讓 offline 與 serving 使用不同 cutoff。
- **為何離線可能看似準確：** 固定 base 期間內的格式規律可能掩蓋 timezone 問題。
- **為何線上會失效或無法重建：** 新來源、offset 或日界線資料會按不同方式解讀，改變 feature 與
  temporal partition。
- **具體業務／模型影響：** 出發迫近程度與 intervention urgency 可能分錯層，邊界訂單也可能落入錯誤
  training/evaluation period。
- **修正方式：** 明定 canonical instant、Asia/Taipei business date候選、date-only departure semantics，
  保存 raw/canonical values；negative/invalid days quarantine、flag 或 abstain 由 owner 決定。
- **Verification test：** offset-equivalent timestamps 產生相同結果；跨日邊界及 negative fixture 遵守
  contract；partition cutoff 使用 canonical time。
- **Causal confidence：** High for contract gap；目前沒有 negative days。
- **Deployment blocker：** Yes（只要保留此 feature／時間切分）。

### MF-011 — 宣告的member source未使用

- **Severity：** `LOW`
- **Category：** source contract / maintainability
- **Source location：** lines 10, 24–25
- **問題是什麼：** module docstring 宣告 `members.csv`，但程式只讀 `orders_base.csv`。
- **Leakage／failure mechanism：** 這不是 label leakage；是 source contract 與 implementation 不一致。
- **為何離線可能看似準確：** 目前模型根本未使用 member master，因此其 AUC 不能證明會員屬性有效。
- **為何線上會失效或無法重建：** 若 serving 或後續版本自行加入 current member profile，可能與訓練
  定義不同，甚至把未來會員屬性帶回過去。
- **具體業務／模型影響：** reviewer／operator 可能錯認資料依賴，導致權限、freshness 與 incident
  analysis 漏掉真正來源。
- **修正方式：** 不使用則修正文檔；若加入會員屬性，必須依 prediction timestamp 做 SCD2 as-of lookup，
  定義 PII allowlist、freshness 與 unknown member fallback。
- **Verification test：** dependency manifest 與實際 reads 一致；member feature 的 source version 有效於
  prediction timestamp，current snapshot 不得 time travel。
- **Causal confidence：** Certain for mismatch；沒有證據顯示它直接造成 AUC 落差。
- **Deployment blocker：** No（除非發布設計依賴 member attributes）。

## Leakage causal chain

```text
由當前status建立label
→ 使用完整資料計算三組取消率
→ 自己的label、test labels及future labels進入feature
→ scaler又在完整資料上fit
→ 最後才random split
→ train/test同時帶有outcome訊號與entity/time重疊
→ offline AUC被高估
→ 線上沒有未來outcome、test labels或完整資料mapping
→ feature無法以相同語意重建
→ 線上效能顯著落差
```

前六步及線上無法重建相同 mapping 可由原始碼直接推導；「足以造成顯著落差」是合理因果推論。
沒有 production feature logs、prediction records 與成熟 labels，故不能宣稱這是線上約 0.55 的唯一原因，
也不能量化各 finding 對 AUC 的個別影響。

## Corrected point-in-time feature design

### Prediction、observation與label contract

- **Sample grain：** 一個 logical order 一筆。
- **Prediction point：** 訂單建立、必要建立時欄位已可取得；候選 timestamp 是 canonical
  `order_created_at`。最終是建立事件落地、transaction commit 或其他線上決策時點，仍由 business owner
  確認。
- **Observation window：** 只能讀取 `event_time < prediction_ts` 且 `outcome_available_at <=
  prediction_ts` 的歷史。窗口長度不在沒有證據時寫死，應依 seasonality、coverage 與 backtest 決定。
- **Label：** prediction 後 logical order 的最終取消結果。
- **Label window/maturity：** 訓練 cutoff 必須晚於 outcome maturity；期限目前未知，由取消政策、出發日、
  退款／狀態 SLA 與延遲事件分析確認。未成熟 order 排除，不得當 negative。

### 建議資料流

```text
raw immutable events + ingestion/event/availability timestamps
  -> deterministic logical-order resolution
  -> build eligible samples(prediction_ts, maturity_cutoff)
  -> point-in-time joins to mature history only
  -> chronological train / validation / test
  -> fit train-only encoders, imputer, scaler, model
  -> frozen transform on validation/test
  -> rolling backtests + cold-start/segment evaluation
  -> version and register dataset + mappings + preprocessing + model
```

短小 pseudocode（設計意圖，未在本題執行）：

```python
eligible_history = outcomes.where(
    (outcomes.event_time < sample.prediction_ts)
    & (outcomes.outcome_available_at <= sample.prediction_ts)
)
train_encoding = expanding_smoothed_mean(
    eligible_history, keys=["member_id", "product_id"], exclude_current_label=True
)
valid_features = frozen_train_mapping.transform(valid_rows, fallback="hierarchical_global")
pipeline.fit(train_features, train_labels)  # imputer/scaler/model只fit train
```

Target encoding 應優先使用 time-aware expanding history；若因計算成本使用 temporal OOF，各 fold 也只能
讀到 fold cutoff 前已成熟 outcome。Member-product support不足時依序 fallback 到 smoothed member、
product、global prior；unseen member/product 需產生明確 cold-start flag。Validation/test mapping 在該
evaluation period 開始前 freeze，不能以該 period label更新。

Money feature 以 event/business date 可取得的有效 `rate_to_twd` 轉為 TWD，明定 FX direction、timezone、
missing-rate policy 與 rounding。`coupon_discount` 已是 TWD，不再次換匯。所有 feature 保存
`feature_timestamp`、source max event/availability time、mapping version 與 lineage。

## Temporal evaluation及rolling backtest

資料先依 label maturity 截出可評估母體，再建立 chronological train/validation/test；不捏造固定日期或
比例。每個 evaluation period 的 preprocessing 與 encoding 只 fit 先前 training period。Rolling folds
應模擬「截至當時訓練、預測下一期、等待 label 成熟後評估」的真實 lifecycle。

同 logical order 絕不能跨 partitions。Member/product 不強制完全隔離，因線上也會預測既有 entities；
但每個 fold 必須分別回報 seen、unseen member、unseen product、雙 unseen cold-start slices。另按 channel、
currency、product family 與風險／價值層級檢查，避免 aggregate metric 掩蓋局部失效。

Release metrics 不限於 ROC-AUC：至少包含 PR-AUC、calibration/Brier或等價指標、business-approved
threshold 下的 precision/recall、coverage 與 cost/benefit。Class imbalance 的處理、threshold、客服容量、
false-positive／false-negative cost 及最低 release 門檻均是 business／ML owner 待決事項；先在
validation 選擇，test 只做一次 final estimate。

## 防再犯機制及production monitoring

### CI與資料測試

1. 修改 test-period labels 不得改變 train features。
2. 修改未來事件不得改變較早 prediction-time features。
3. 每筆 training target encoding 不包含自己的 label。
4. Validation/test encoder 只使用過去 training period 的 frozen mapping。
5. Scaler及所有 fit-based transformer 只 fit training partition。
6. 同 logical order 不跨 train/validation/test。
7. Temporal boundaries 無 overlap、反轉或不成熟 labels。
8. Feature event/availability timestamps 不晚於 prediction cutoff。
9. Unseen member/product 使用明確 hierarchical/global fallback 與 flag。
10. Mixed currency 不直接進同一 amount scale；FX 與 coupon contract 可重現。
11. Negative/invalid `days_to_departure` 依明確策略處理。
12. Missing 不被無條件解讀為真實零。
13. 相同 input、config、code、seed 產生相同 dataset contract/checksum。
14. Schema drift hard fail 或進明確 quarantine，不靜默刪列。
15. Delayed labels 只在成熟後進 performance evaluation。
16. Offline與serving feature implementation 通過 golden-record parity。
17. Leakage sentinel／future-shift regression 必須保持較早 features 不變。
18. 任一 blocking validation 失敗，release gate 回傳 `NO_DEPLOY`。
19. Training feature來源最大可用時間早於對應 evaluation period。
20. Target-encoding mapping、preprocessor與model版本可由 prediction 追溯。

上述是修正後必須建立的測試設計；本 repo 的文件 validator 只驗證報告、來源與 profiling consistency，
**不宣稱上述 ML tests 或修正版 pipeline 已實測通過**。

### Artifact、release與rollback

不可只以 training job 成功或單一 AUC 允許發布。Release bundle 應包含 immutable training dataset
reference/checksum、feature schema、cutoff/maturity contract、encoder mappings、preprocessor、model、
code/config version、evaluation report、owner與approval。Registry 保存 promotion history 與上一個可回復
artifact；parity、data contract、leakage、temporal、quality 或 metric gate 任一失敗均禁止 deploy。

### Production monitoring

- Data：freshness、volume、schema、parse/quarantine、missing/invalid rate。
- Feature：unseen/fallback rate、feature age、range、currency mix、training-serving parity、feature drift。
- Prediction：score/decision drift、coverage、abstention、channel/product/member slices。
- Delayed performance：labels 成熟後計算 ROC-AUC、PR-AUC、calibration、threshold metrics、segment
  performance 與 business outcome；不可用未成熟 negative 提前計算。
- Operations：artifact/version、deployment、rollback、access、PII、audit log 與 incident lineage。

Alert threshold、rollback、retraining cadence 不能由本題資料臆造，需依正式流量、成本與 error budget 由
business／ML owner核准。這些屬 production hardening；但 feature freshness、parity、mature-label
performance 與 rollback capability 是部署前必要控制。

## `NO_DEPLOY`結論及blocking fixes

**目前訓練流程不可部署，結論為 `NO_DEPLOY`。** 排序後的 blocking fixes：

1. 先定義 logical-order sample、prediction timestamp、final label 與 maturity contract（MF-003）。
2. 移除 full-data／future target encoding，落實 point-in-time joins（MF-001、MF-002）。
3. 改為 chronological split、same-order isolation 與 rolling backtest（MF-004、MF-006）。
4. 將所有 preprocessing 改為 train-only，封裝可重現 artifact並做 serving parity（MF-005、MF-007）。
5. 完成 currency、schema/missing、timezone contracts 與 release data-quality gate（MF-008、MF-009、
   MF-010）。
6. 通過前節20項防洩漏／parity／reproducibility tests及核准後的 release metrics，再考慮部署。

MF-011 本身不是 blocker；若正式設計使用 member attributes，才需先完成 SCD2 as-of與PII contract。
即使修正完成，實際效能、calibration、capacity threshold、production latency與 drift sensitivity仍需在
production-like data及成熟 outcomes 上驗證。

## 為什麼選擇Module F，而不選Module D／E

我選擇Module F，因為point-in-time correctness、可重現特徵管線與資料品質控制，直接連結資料工程師對可信資料產品的責任。這個題目也符合我以資料工程為核心，並結合過去ML lifecycle與工作流可靠性經驗的職涯定位。Module D的效能工程很有價值，但相較之下，本次以特徵資料正確性、資料時序與可追溯性更能呈現我的核心能力。Module E的AI評分守門同樣重要，但LLM judge與rubric設計並不是我這次最希望作為主軸呈現的專長。

以上四句為應試者在 planning gate 核准的本人陳述；Module D／E 未在本作業中作答或實作。

## AI-assisted與candidate-owned decisions

AI 協助逐行審查、root-cause 合併、唯讀 profiling、finding 結構、候選修法與 verification test 整理；
AI 建議不等於執行證據。應試者明確核准 Module F 選擇、訂單取消問題定義、logical-order grain、建立時
prediction point候選、成熟 label原則、chronological/rolling evaluation、same-order isolation、
target-encoding策略、currency contract、`NO_DEPLOY`結論、severity、blocking順序及四句個人選擇理由。

仍由 business／ML owner 決定：最終線上 prediction event、observation window、label maturity期限、
rolling periods、class/cost policy、release thresholds、監控／rollback／retraining門檻。Phase 6 transcript
須由應試者事後人工匯出、檢查完整性與去識別化；本次不建立假 transcript。

## References及validation appendix

### Evidence classification

- **原始碼直接證明：** label建立位置、完整資料 aggregation、split前 scaling、random split、單一 AUC、
  members source未讀取。
- **唯讀資料證明：** 本報告列出的 base row/order/singleton/currency/coupon/day-range/parse-loss counts。
- **合理推論：** 上述機制會高估 offline evaluation且線上無法同義重建；不是對 AUC 下降幅度的量化。
- **需 runtime 確認：** 修正後所有 metrics、feature parity、latency、production drift及實際 business outcome。
- **Candidate-owned：** 問題／grain／prediction候選／切分／encoding／部署結論與個人選擇理由。

### 文件驗證

```bash
.venv/bin/python -m pytest tests/test_module_f_diagnosis.py
```

該 validator 會校驗 source checksum/line count、finding contract、選擇理由、README狀態，並從 allowlisted
CSV 唯讀重算本報告引用的 profiling數字。它不是模型執行、修正版 leakage experiment 或 deployment
approval。
