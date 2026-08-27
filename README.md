# 雄獅資訊資料工程師 Take-home

本 repository 提供可在本機重現的資料工程解法。正式答案以 reviewer 文件為入口，實際數字以
`docs/evidence/` 的 deterministic evidence 為準；原始題目與資料包位於 `LionDEExam/`，共 19 檔，
全程視為唯讀輸入。

## Completion summary 與 lifecycle authority

| 範圍 | Current lifecycle | 主要結論 |
|---|---|---|
| Part A 星型模型、品質、增量與冪等 | `Completed` | DuckDB／SQL 實作、SCD Type 2、Decimal money、quarantine與rerun evidence已閉合 |
| Part B AI PySpark code review | `Completed` | 8 findings；部署結論為 `NO_DEPLOY` |
| Part C Microsoft Fabric架構 | `Completed` | architecture design已完成；未部署Fabric tenant |
| Module F 特徵管線診斷 | `Completed` | 11 findings；部署結論為 `NO_DEPLOY` |
| Module D／E | 不適用 | 原題要求D／E／F三選一，本作業選擇Module F，並非交付缺漏 |
| Phase 0～6 AI evidence | `Completed` | 8份實際transcript已匯出、核對並索引 |
| Phase 7 reviewer／AI文件 | `implementation_complete_acceptance_pending` | 本輪implementation完成後，transcript仍待應試者人工匯出與closeout |
| Phase 8 clean-room | 尚未開始 | 保留給乾淨環境／全新output的最終重現 |

Current lifecycle authority是本README與
[`docs/ai/session_index.md`](docs/ai/session_index.md)。Part A／B／C／Module F正式文件、
machine-readable evidence及transcript內的`implementation_complete_acceptance_pending`，記錄的是各
Phase「implementation完成、transcript closeout尚未發生」的implementation-time snapshot，不是目前repo狀態。
例如Module F正式文件曾記錄「Module F transcript待應試者人工匯出」；目前Phase 6 transcript已完成
closeout。`NO_DEPLOY`是Part B與Module F的技術結論，與其作業階段`Completed`不衝突。
`Completed`只代表該Phase交付與AI evidence已閉合，不代表PySpark、Fabric或ML production deployment
已完成。

## Reviewer quick path

建議依下列順序閱讀，正式報告不在README重複展開：

1. 本頁的completion summary、重現命令與限制。
2. Part A的[模型設計](docs/part_a_model_design.md)、[品質報告](docs/part_a_quality_report.md)與
   [rerun evidence](docs/part_a_rerun_evidence.md)。
3. Part B的[AI PySpark code review](docs/part_b_code_review.md)與`NO_DEPLOY`結論。
4. Part C的[Fabric架構、workload及trade-offs](docs/part_c_fabric_architecture.md)。
5. Module F的[leakage診斷與point-in-time修正設計](docs/module_f_diagnosis.md)。
6. [一頁AI協作報告](docs/ai/collaboration_report.md)與[session index](docs/ai/session_index.md)。
7. 依下一節執行本機驗證。

## 環境與驗證入口

環境需求為Python 3.11以上。首次使用：

```bash
make setup
```

Reviewer建議先執行下列現有Make targets：

```bash
make source-integrity
make lint
make test
make phase3-acceptance
```

`make source-integrity`驗證19份原始檔；`make test`執行完整pytest；`make phase3-acceptance`會使用
全新暫存DB重建兩次並核對canonical evidence。Runtime DuckDB、cache與一般output不納入Git。

### Phase 1 profiling

```bash
make profile
make profile OUTPUT_DIR=/tmp/lion-profile-run1 EVIDENCE_DIR=/tmp/lion-profile-run1
```

Phase 1保留observed facts與當時proposed treatments；實際套用的SCD2、fact、duplicate、sentinel、FX
與money政策見Phase 2／3正式文件及evidence。Phase 1 current canonical checksum為
`5cd9bf274d171f7007c4b160addb6fe281f3be1da13939b35c52ecf14a1d9ee8`。

### Phase 2 base warehouse

Build command會拒絕覆寫既有DB，請使用不存在的路徑：

```bash
make build-base OUTPUT_DB=/tmp/lion-phase2.duckdb \
  PHASE2_EVIDENCE_DIR=/tmp/lion-phase2-evidence
make validate-base OUTPUT_DB=/tmp/lion-phase2.duckdb \
  PHASE2_EVIDENCE_DIR=/tmp/lion-phase2-evidence
```

Phase 2只讀`orders_base.csv`、members、products與FX；不讀三個incremental order files。

### Phase 3 incremental warehouse與rerun

```bash
make build PHASE3_OUTPUT_DB=/tmp/lion-phase3.duckdb \
  PHASE3_EVIDENCE_DIR=/tmp/lion-phase3-evidence
make rerun-proof PHASE3_OUTPUT_DB=/tmp/lion-phase3.duckdb \
  PHASE3_EVIDENCE_DIR=/tmp/lion-phase3-evidence
```

處理順序固定為`base → day1 → day2 → day3`。同logical filename與相同SHA-256的成功檔案回傳
`SKIPPED_ALREADY_APPLIED`；successful、failed或interrupted attempt觀察到同名不同SHA-256均hard
fail。詳細batch counts、money、quarantine、SCD2與rerun checksum見正式rerun evidence。

## Evidence pinning

| Evidence | SHA-256 |
|---|---|
| Phase 2 canonical bundle | `2d9cf41622428233c7b83d3de7aa0df860912ba457c72be22f3b26758cdd2c1e` |
| Phase 3 canonical bundle | `530804916123aacc3fe4aa4c4c9646cc9fdc35b306af6799b06fb23de052720d` |
| Phase 4 review manifest | `2446b8c14245e431147e27ea2b3c4cc61411744187cf44dab5f3a3ae3dda79b9` |
| Part C architecture | `0b5def8a604969ab155d0b090d03774a87308c1ef0bdbf84e7e775cfd8618915` |
| Current Phase 5 validator | `c06d07b071df8bf5ade8d555db6b516208c075773f5d3bbf6b8b2217f7d7bd3b` |
| Module F diagnosis | `6ddb7a7389d4a477383a5266cbdb07cae7d96c01693d1bbbfa5bcc820818218a` |
| Module F validator | `8bb9a2f86d25bacd32317e11c92ca4b052cbd005ea4db3922d6027dda06029bd` |

Machine-readable evidence位於`docs/evidence/phase_01/`、`phase_02/`、`phase_03/`及`phase_04/`。
上述pinning用來偵測文件整合造成的非預期變更，不取代SQL reconciliation、tests或人工review。

## Phase 5 Part C Fabric Architecture

正式答案含兩張Mermaid圖、Daily BI、分鐘級dashboard、Text-to-SQL／RAG／hybrid、權限與evaluation
設計。此文件是proposed architecture，不是Fabric deployment evidence：

```bash
.venv/bin/python -m pytest tests/test_part_c_architecture.py
```

目前狀態為 `Completed`；Phase 5 transcript 已完成人工匯出、驗證與索引。

## Phase 6 Module F

正式答案是對題目原始程式的Static review、唯讀profiling、point-in-time corrected design、temporal
evaluation與防再犯控制；原始與修正版模型均未執行：

```bash
.venv/bin/python -m pytest tests/test_module_f_diagnosis.py
```

Module F current lifecycle為`Completed`，技術結論為`NO_DEPLOY`。Module D／E未作答是因原題要求
D／E／F三選一；四句選擇理由見Module F正式文件。

## 已知限制與submission boundary

- Part A incremental projection採correctness-first cumulative recomputation，適合本題資料量；未宣稱為
  大型production partition-pruned最佳化。
- Incremental audit是single-writer；殘留`RUNNING`會轉為`INTERRUPTED`，不提供distributed lease。
- Actual source沒有member incremental file；actual day1～day3 SCD2 checksum不變，incremental member
  change主要由synthetic fixture驗證。
- Part B沒有執行PySpark、Delta或Fabric runtime；static findings仍需在目標runtime驗證修法。
- Part C沒有部署Fabric tenant，capacity、security propagation、latency與cost仍需POC。
- Module F沒有執行原始或修正版模型，沒有本次AUC或production-like leakage experiment。
- Module D／E依三選一規則未作答；不是遺漏必交項目。
- Phase 8 clean-room尚未開始，本README不宣稱已完成最終clean-room acceptance。
- Raw AI transcripts是完整開發session export，可能包含本機filesystem path及工具metadata。各closeout的
  credential pattern scan已通過，但不宣稱transcript已完全去識別化。
- 原題若採private Git submission，保留raw transcript可維持audit fidelity；此repo不應因此被宣稱適合
  直接公開。若未來改為public repo，應另做獨立privacy review，本Phase不執行該公開化流程。

## 文件索引

- [`SPEC.md`](SPEC.md)：Phase、交付物與驗收條件。
- [`AGENTS.md`](AGENTS.md)：協作、證據、資料保護與Git規則。
- [`docs/source_inventory.md`](docs/source_inventory.md)：原始來源盤點。
- [`docs/part_a_model_design.md`](docs/part_a_model_design.md)：grain、SCD2、fact、money及reconciliation。
- [`docs/part_a_quality_report.md`](docs/part_a_quality_report.md)：profiling、detectors及treatment contract。
- [`docs/part_a_rerun_evidence.md`](docs/part_a_rerun_evidence.md)：batch、lineage、replay及checksums。
- [`docs/part_b_code_review.md`](docs/part_b_code_review.md)：Part B正式審查。
- [`docs/part_c_fabric_architecture.md`](docs/part_c_fabric_architecture.md)：Part C正式架構設計。
- [`docs/module_f_diagnosis.md`](docs/module_f_diagnosis.md)：Module F正式診斷。
- [`docs/ai/collaboration_report.md`](docs/ai/collaboration_report.md)：一頁AI協作報告。
- [`docs/ai/session_index.md`](docs/ai/session_index.md)：task、transcript、commit及checksum索引。
