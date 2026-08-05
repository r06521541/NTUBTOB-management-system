# TASK-021 Work Review

日期：2026-08-05
結論：`accepted`
Branch：`codex/protect-web-portal-member-matching`
Codex驗收HEAD：`6d53b2ce4c8795d50ab5a6178b62ef937efb5af6`
Implementation commit：`1f0813e00ac22464d099aa136bc3a63b6d002e19`
Draft PR：[#35](https://github.com/r06521541/NTUBTOB-management-system/pull/35)

## 實際查驗

- Working tree乾淨；PR #35為open／draft／mergeable，remote head與本機一致。
- Implementation diff限於Web Portal管理authorization／CSRF、template、離線tests、非機密env example、README及CI；未修改schema、shared library、Cloud Build、Docker或deployment設定。
- 三個管理route共用`admin_required`，先確認LINE session與`member_id` allowlist，再進入任何管理ORM query。
- 兩個POST在authorization後、業務form欄位與ORM前執行CSRF驗證。
- 既有demo isolation透過`before_request`先回404；既有demo tests全數通過。

## 驗收條件

- Allowlist只接受不重複、逗號分隔的ASCII正整數；unset、blank、empty item、mixed-invalid、zero、negative與duplicate均整體fail closed。
- 未登入的三個route皆redirect至既有登入流程，且不查詢管理資料。
- 已登入但非管理者、缺失或invalid config皆回403且零ORM／Discord副作用。
- 管理GET只允許合法管理者查詢，並建立／重用不可預測session CSRF token。
- Match與ignore均會提交同一hidden CSRF token；missing／blank／wrong token回400且零管理副作用。
- 合法match只更新指定配對、保留既有成功Discord通知與redirect；合法ignore只更新ignored狀態並redirect。
- LINE callback成功登入後新增最小`member_id`，未移除既有session內容或登入流程。
- CI維持`contents: read`與pinned actions，未新增runtime dependency。

## Work重跑證據

使用workspace bundled CPython 3.12.13離線執行：

- Web Portal：19/19通過。
- LINE webhook ingress：10/10通過。
- Game broadcast：28/28通過。
- Notify cronjob：9/9通過。
- Update schedule：5/5通過。
- Scheduled deployment wrapper：11/11通過。
- `python -m compileall -q apps/web_portal`：通過。
- `git diff --check c022d51`：通過。

GitHub-hosted Python 3.10 Codex-head run `30988778233`／job `92249675723`：`SUCCESS`。Work驗收commit push後仍須等待其最終CI成功才交Owner merge決策。

## Blocking問題

無。

## 殘餘風險與未驗證

- Production尚未設定或查驗`WEB_PORTAL_ADMIN_MEMBER_IDS`；若直接部署且未設定，會依設計安全鎖住所有管理者。
- 未向真實LINE Login或production Web Portal送request，線上session與runtime env行為尚未驗證。
- 既有session仍保存完整`member`物件；safe redirect、session lifetime、logout與session全面重構是明確非目標。
- 本任務沒有處理Web Portal build context／Secret boundary；依既有runbook仍不得部署Web Portal。
- Member ID allowlist是暫時性授權模型；若未來需要多人角色管理或稽核，應另立schema-compatible任務。

## 安全邊界

未部署、未呼叫production、未連production DB、未發送LINE／Discord、未讀取Secret，亦未操作IAM、Scheduler、schema、ready或merge。

## 結論與下一步

`accepted`。等待Work驗收commit的Python 3.10 CI成功後，交由Owner決定是否將PR #35標記ready並merge。Merge不代表Web Portal deployment或allowlist設定授權。
