# Phase 8 clean-room acceptance

## 驗收結論與範圍

Phase 8B正式clean-room acceptance結果為`PASSED`。兩個commit的角色如下：

- Tested infrastructure commit：`7b75354fd4f4c51a24485c771412200d8dc57e4a`。Clean-room實際checkout
  並驗收的是這個commit；以local `git clone --no-local`建立只含tracked files的clone，再於fresh
  virtual environment執行九個logical commands。
- Acceptance evidence commit：`b6b5ccbeabf8e580b33d907820a933c2dc588ca4`。這個commit保存正式JSON、
  Reviewer Markdown與post-evidence validators，不是clean-room tested commit。因此evidence JSON的
  `tested_commit`維持`7b75354fd4f4c51a24485c771412200d8dc57e4a`是刻意且正確的設計。

Machine-readable原始結果見
[`evidence/phase_08/final_acceptance.json`](evidence/phase_08/final_acceptance.json)，檔案SHA-256為
`13da90163628e9f7627a33799e259ddc9a82736a025cc0d4bfaac46ac7b34ab7`。

這個結果證明指定commit在本次fresh環境及實際resolved dependencies下通過驗收；不代表所有未來平台、
package index狀態或外部runtime都會得到相同結果。Phase 8整體lifecycle仍為
`implementation_complete_acceptance_pending`，因本task的transcript尚待人工匯出、核對與metadata
closeout；clean-room通過不等於AI evidence已閉合。

## 執行環境與驗證結果

- Python 3.12.3；pip 24.0、DuckDB 1.5.5、pandas 2.3.3、pytest 9.1.1、ruff 0.16.5。
- Network dependency installation：本次formal run由人工opt-in設為enabled；只依clone內的
  `pyproject.toml`安裝dependencies。Evidence記錄上述實際resolved versions；因沒有lock file，不宣稱
  未來仍會得到exact dependency resolution。
- 九個logical commands均exit 0：dependency install、source integrity、lint、tests、Phase 1 profile、
  Phase 2 build、Phase 2 validate、Phase 3 acceptance及final git clean。
- Source integrity核對19檔、0 violations；lint通過。`93 passed`是tested infrastructure commit在
  tracked-only clean clone與fresh venv中的full suite結果；不是evidence commit的suite count。
- `96 passed`是正式JSON、Reviewer Markdown與validators加入後，在acceptance evidence commit工作樹執行的
  post-evidence full suite結果；這不回寫或取代JSON中的clean-room `93 passed`。
- Phase 1以fresh profile執行47個detectors並產生7份canonical evidence files；canonical bundle
  SHA-256為
  `5cd9bf274d171f7007c4b160addb6fe281f3be1da13939b35c52ecf14a1d9ee8`。
- Phase 2使用fresh database完成32項checks、0 violations；fact 99,612 rows、known member versions
  8,745、current members 7,972；canonical bundle SHA-256為
  `2d9cf41622428233c7b83d3de7aa0df860912ba457c72be22f3b26758cdd2c1e`。
- Phase 3完成41項checks、0 violations；fact 109,888 rows、quarantined orders 2,172。單次
  `make phase3-acceptance`驗證`base → day1 → day2 → day3`、file registry、single replay、full replay、
  Phase 3 validations及兩次clean-run canonical evidence identity；canonical bundle SHA-256為
  `530804916123aacc3fe4aa4c4c9646cc9fdc35b306af6799b06fb23de052720d`。
- Transaction rollback、failed attempt behavior及stale attempt／different-SHA regression，則由clean-room
  full test suite對Phase 3 incremental behavior提供coverage；不宣稱`make phase3-acceptance`另行重跑
  這些rollback fixtures。

上述byte-identical結論只適用於Phase 3 canonical evidence，不宣稱兩次runtime DuckDB database file
逐byte相同。

## Submission readiness與邊界

Submission matrix共25個required items，全部存在。作業依三選一規則選擇Module F，因此Module D／E不
適用而非缺件。Artifact hygiene中的101個tracked files、58,943,598 tracked bytes、0 rejected
artifacts及0 credential matches，都是tested infrastructure commit的clean-room snapshot。Acceptance
evidence commit加入final JSON及Markdown後共有103個tracked files；103描述evidence commit的repo狀態，
不取代JSON保存的tested snapshot。Pattern scan不是完整privacy audit，raw transcripts仍需人工檢查
實際分享範圍。

已知限制如下：dependencies由version ranges解析且沒有lock file，未證明未來所有平台都會得到相同
resolution；credential pattern scan不等於完整privacy audit；Fabric、PySpark與ML runtime不在本機
clean-room acceptance範圍。

提交前仍需由應試者完成人工review、Phase 8 transcript匯出與closeout、最終metadata pin，以及依實際
繳交管道處理repository access、表單或email。此文件只記錄已實際執行並驗證的結果，不宣告Phase 8
`Completed`。
