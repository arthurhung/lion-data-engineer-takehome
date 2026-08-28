# Phase 8 clean-room acceptance

## 驗收結論與範圍

Phase 8B正式clean-room acceptance結果為`PASSED`。本次驗收固定測試commit
`7b75354fd4f4c51a24485c771412200d8dc57e4a`，以local `git clone --no-local`建立只含tracked files的
clone，再於fresh virtual environment執行九個logical commands。Machine-readable原始結果見
[`evidence/phase_08/final_acceptance.json`](evidence/phase_08/final_acceptance.json)，檔案SHA-256為
`13da90163628e9f7627a33799e259ddc9a82736a025cc0d4bfaac46ac7b34ab7`。

這個結果證明指定commit在本次fresh環境及實際resolved dependencies下通過驗收；不代表所有未來平台、
package index狀態或外部runtime都會得到相同結果。Phase 8整體lifecycle仍為
`implementation_complete_acceptance_pending`，因本task的transcript尚待人工匯出、核對與metadata
closeout；clean-room通過不等於AI evidence已閉合。

## 執行環境與驗證結果

- Python 3.12.3；pip 24.0、DuckDB 1.5.5、pandas 2.3.3、pytest 9.1.1、ruff 0.16.5。
- 九個logical commands均exit 0：dependency install、source integrity、lint、tests、Phase 1 profile、
  Phase 2 build、Phase 2 validate、Phase 3 acceptance及final git clean。
- Source integrity核對19檔、0 violations；lint通過；fresh full suite為93 passed，rollback coverage由
  full suite涵蓋。
- Phase 1以fresh profile執行47個detectors；canonical bundle SHA-256為
  `5cd9bf274d171f7007c4b160addb6fe281f3be1da13939b35c52ecf14a1d9ee8`。
- Phase 2使用fresh database完成32項checks、0 violations；fact 99,612 rows、known member versions
  8,745、current members 7,972；canonical bundle SHA-256為
  `2d9cf41622428233c7b83d3de7aa0df860912ba457c72be22f3b26758cdd2c1e`。
- Phase 3依`base → day1 → day2 → day3`完成41項checks、0 violations；fact 109,888 rows、
  quarantined orders 2,172。File registry、single-file replay、full-sequence replay均通過，committed
  canonical evidence與clean runs byte-identical；canonical bundle SHA-256為
  `530804916123aacc3fe4aa4c4c9646cc9fdc35b306af6799b06fb23de052720d`。

上述byte-identical結論只適用於Phase 3 canonical evidence，不宣稱兩次runtime DuckDB database file
逐byte相同。

## Submission readiness與邊界

Submission matrix共25個required items，全部存在。作業依三選一規則選擇Module F，因此Module D／E不
適用而非缺件。Artifact hygiene共檢查101個tracked files、58,943,598 bytes；rejected artifacts為0，
credential pattern matches為0。Pattern scan不是完整privacy audit，raw transcripts仍需人工檢查實際
分享範圍。

已知限制如下：dependencies由version ranges解析且沒有lock file，未證明未來所有平台都會得到相同
resolution；credential pattern scan不等於完整privacy audit；Fabric、PySpark與ML runtime不在本機
clean-room acceptance範圍。

提交前仍需由應試者完成人工review、Phase 8 transcript匯出與closeout、最終metadata pin，以及依實際
繳交管道處理repository access、表單或email。此文件只記錄已實際執行並驗證的結果，不宣告Phase 8
`Completed`。
