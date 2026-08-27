# AI 協作報告

> Phase 7狀態：`implementation_complete_acceptance_pending`；本Phase transcript待應試者人工匯出與closeout。

## 1. 協作方式

我把作業拆成Phase 0～7，每一Phase依序進行planning、人工gate、implementation、validation、commit與
transcript closeout，並明確禁止Codex自行跨Phase擴張。代表prompt包括「同一檔重跑不得改變
analytical state；同名不同SHA必須hard fail」，以及「不要只列Fabric元件，需對workload與trade-off
提出判斷」。AI負責提出profiling候選、SQL／Python實作、測試與文件草稿；business policy、severity、
trade-off、acceptance及最後答案由我核准並負責。完整task與transcript見
[session index](session_index.md)。

## 2. AI協助範圍

| 範圍 | AI協助 | 人工責任 |
|---|---|---|
| Part A | profiling候選、SQL／Python、tests、deterministic evidence | quality treatment、SCD2／FX／money與acceptance |
| Part B | finding inventory、影響、修法與verification候選 | severity、措辭、blocking順序及`NO_DEPLOY` |
| Part C | Fabric元件、trade-off候選、Mermaid及官方claim mapping | workload選型、authority、權限fallback及限制 |
| Module F | leakage因果鏈、point-in-time修正與防再犯測試 | prediction contract、severity、選擇理由及`NO_DEPLOY` |
| 文件 | 索引、驗證命令、checksum與traceability整理 | reviewer敘事、誠信界線與最終review |

## 3. AI的實際不足與人工修正

1. Phase 1起初把parse-valid的`1900-01-01`生日sentinel混入identity-change判斷；Phase 2設計review由人工
   發現日期範圍與語意不合理，遂暫停下一Phase，重新profiling並以sentinel、唯一非sentinel及真正
   identity ambiguity分流，透過detector tests與新canonical checksum閉合。
2. Phase 3初版對successful registry的different-SHA有防護，但failed／stale attempt尚未進registry時仍
   可能放行。Final review以failure／recovery情境識別缺口，補成三種狀態皆hard fail，加入回歸測試並
   重新執行rerun與clean-DB evidence。
3. Part B草稿曾以較強的Delta overwrite語氣描述未在目標runtime驗證的行為，PB-007也先列MEDIUM。
   人工逐行對照原碼後將前者改成版本中立的「可能大範圍取代」，並因全表`collect()`位於append後、
   具有無界driver memory與partial-run風險，將PB-007調為HIGH blocker；manifest與validator同步核對。
4. Part C未採AI候選的Direct Lake on SQL預設。人工依官方文件區分兩種Direct Lake模式後，改為先POC
   Direct Lake on OneLake、以Import fallback，並把OBO與Azure AI Search保留為tenant待驗證項目。

後續回歸測試也曾抓到Phase 4／5 validator仍斷言舊lifecycle；修正只更新current closeout assertion，
保留immutable implementation snapshot。

## 4. Candidate-owned decisions

我核准Part A採cumulative order-level quarantine，late event保留lineage但不得使fact倒退；missing
reference、dated FX、TWD／NTD、unsupported currency、Exact Decimal與rounding policy亦由我確認。
我決定Part B的severity、blocking順序及`NO_DEPLOY`；Part C採Bronze／Silver Lakehouse＋Gold
Warehouse、Eventstream＋Eventhouse、caller-aware權限與least-privilege fallback；Module F則由我核准
logical-order prediction contract、temporal evaluation、severity、`NO_DEPLOY`及選擇Module F而非D／E
的理由。這些決策由AI協助檢查與文件化，不表示全部技術內容均由我逐字手寫。

## 5. 防止捏造與限制

每階段以source SHA-256 pinning、SQL reconciliation、Exact Decimal、deterministic clean DB evidence、
tests、replay／rollback checks及人工diff review區分「AI建議」與「已執行證據」；Fabric claim另以官方
來源查證，完成後才匯出transcript並closeout。AI仍可能提出不精確的policy、severity或產品claim；
validator只能保護格式、checksum及一致性，不能取代人工技術審查。本作業未執行PySpark／Fabric
deployment，也未執行原始或修正版ML模型。Raw transcript可能包含本機filesystem path與工具metadata；
各closeout的credential pattern scan已通過，但不宣稱完全去識別化。最終答案、取捨與提交責任由我承擔。
