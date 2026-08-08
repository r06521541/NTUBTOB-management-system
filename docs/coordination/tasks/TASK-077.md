# TASK-077：建立 Phase C 跨服務 freeze gate 與受控啟用工具

## 任務目標

補上 TASK-076 明確要求、但 repository 尚未具備的可驗證 attendance／notification freeze。讓 Web Portal、LINE
webhook 與 notify cron 在 production Phase C 旗標依序切換期間，能先進入一致的 fail-closed freeze 狀態，阻止出席、
身分與排程通知副作用；三個服務全部到達同一 Phase C 狀態後才解除 freeze。

同時建立 repository-only rollout controller／preflight，將合法轉換、精確目標、觀察與rollback順序編碼並離線測試。
本任務只實作、測試及建立後續操作包，不部署、不修改 production flags、不暫停 Scheduler、不呼叫 production。

## Owner 已批准範圍

- Owner 已於 2026-08-08 指示本Work session繼續 Phase C 正式分階段部署與啟用主線。
- 本任務是正式啟用前不可省略的 repository-only safety prerequisite；可依standing Git authorization完成Codex
  實作、Work驗收、唯一ready PR、最小充分CI及squash merge。
- 本批准不包含任何production deployment、runtime env mutation、traffic mutation、Scheduler pause／resume、
  production endpoint invoke、DB DDL／DML、Secret／IAM修改或真實LINE／Discord通知。

## Base 與既存狀態

- Base commit：`43eb67c`
- Branch：`codex/phase-c-activation-freeze`
- TASK-076已由PR #77 merge為`43eb67c`，hosted final gate全部通過；schema已是0004，但三個production runtime的
  Phase C flags仍保持off，且本輪尚未部署。
- Work已將TASK-076 merge closeout併入`PROJECT_STATE.md`未提交變更；Codex必須保留並與本task交付合併。

## 已確認風險

- Repository現有rollout preflight會拒絕任一單服務／雙服務Phase C mixed vector，但沒有共同freeze runtime flag。
- 三個獨立服務的env／revision無法原子更新；若在正常流量下依序開啟，可能出現Portal、Webhook、notify使用不同資料模型。
- LINE webhook是出席寫入面；notify cron的`POST /run-game-attendance-count`會讀DB並發Discord管理通知；Web Portal
  Phase C callback與identity maintenance可能建立／修改identity資料。
- 僅靠人工告知隊員「不要操作」不可驗證，也不能作為production safety boundary。

## 設計要求

### 1. 共用 exact freeze state

- 在shared runtime建立單一明確環境變數，例如`PORTAL_DATA_ROLLOUT_FREEZE_ENABLED`；名稱若調整須在report說明理由。
- 只有exact字串`true`為freeze；missing、empty、大小寫或其他值皆為off。Demo mode不得因正式freeze flag連DB。
- 提供純函式runtime state與測試，不在import時讀DB、呼叫網路或固定現在時間。
- 三個service的`.env_example.yaml`都明確default `false`。
- Rollout state machine至少區分：legacy/unfrozen、legacy/frozen、mixed/frozen、phase_c/frozen、phase_c/unfrozen、
  maintenance/frozen、maintenance/unfrozen；任何mixed/unfrozen一律unsafe。

### 2. LINE webhook freeze boundary

- Freeze時只阻擋attendance reply postback mutation；一般文字、help與唯讀attendance query不得無故全面停用。
- Gate必須在query parsing、principal/member lookup、Game lookup、attendance write、audit及Discord late-reply notification前。
- 使用者應收到固定、簡短的「系統切換中，請稍後再試」LINE reply；不得包含旗標、例外、ID或內部狀態。
- 同一event仍遵守現有LINE signature與reply-token流程；不得另做push／broadcast。
- 測試證明freeze路徑零DB、零Discord、零attendance write，且legacy與Phase C兩條writer都被阻擋。

### 3. Notify cron freeze boundary

- Freeze時`POST /run-game-attendance-count`在任何DB／attendance analyzer／Discord前短路。
- 回應應避免Cloud Scheduler造成重試／告警風暴；採固定成功no-op response並提供不含資料的明確classification。
- `GET /healthz`仍維持無副作用；其他非attendance業務route不得被不必要地凍結。
- 測試證明freeze request零DB、零LINE／Discord、零analyzer及零時間相依副作用。

### 4. Web Portal freeze boundary

- Freeze時既有已登入使用者的唯讀頁面可繼續運作，只阻擋可能建立／修改Phase C identity／qualification／audit的流程。
- 至少阻擋LINE callback在Phase C路徑建立pending／linked identity，以及所有identity maintenance POST。
- Gate順序不得降低OAuth state、session、admin、CSRF或authorization驗證；但須在DB write及Discord通知前。
- Freeze回應為固定503或安全等待頁；不得把production flow fallback到legacy identity mutation。
- Demo mode仍完全離線且可瀏覽；freeze flag不能形成demo auth bypass。

### 5. Rollout transition controller

- 擴充既有`tools/phase_c_rollout_preflight.py`或建立聚焦controller，輸入目前與目標的三服務Phase C／freeze／maintenance
  非機密旗標，輸出合法transition及下一步；不得直接執行gcloud。
- 合法主路徑固定為：
  1. all Phase C off / all freeze off；
  2. 逐服務freeze on，Phase C仍all off；
  3. all freeze on；
  4. freeze期間依runbook逐服務Phase C on；
  5. all Phase C on / all freeze on / maintenance off；
  6. 逐服務freeze off，只有在all Phase C on後才可解除；
  7. 穩定觀察後，maintenance可另案啟用。
- Rollback反向執行；任何mixed Phase C加任一服務unfrozen必須fail closed。
- Controller須要求完整三服務集合、exact布林值與expected source commit／artifact fingerprint；缺漏、未知service或
  ambiguous current state皆停止。
- CLI只做validate／plan／JSON或human-readable輸出，不讀真實`.env.yaml`、不執行shell／gcloud、不顯示secret。

### 6. Runtime／deployment metadata readiness

- 更新三服務README、TASK-076 rollout runbook與offline preflight，納入freeze flag及合法transition。
- 查驗deploy wrappers如何保存未列出的env keys，避免後續deploy feature-off artifact時意外刪除freeze／Phase C flag；
  若現有wrapper無法安全表達，加入dry-run／contract support，但本task不得實際deploy。
- 定義TASK-078 feature-off deployment及TASK-079 activation所需exact evidence：commit、三artifact fingerprints、三個
  current／rollback revisions、flag vectors、Scheduler jobs、觀察者、freeze確認與停止條件。

## 必要測試

- Shared runtime exact flag、demo與所有state／transition truth tables。
- Webhook freeze：legacy／Phase C attendance reply都零DB／Discord/write，固定使用者回覆；其他事件不被誤擋。
- Notify freeze：attendance-count no-op且零依賴；health與非attendance route維持契約。
- Portal freeze：callback／maintenance writes被擋，OAuth／admin／CSRF順序不退化，唯讀與demo維持。
- Controller：合法forward／rollback sequence、每種mixed-unfrozen負例、缺service、未知值、stale commit／artifact及
  output redaction。
- Deployment wrapper若修改，執行完整dry-run／contract tests，證明沒有cloud mutation。
- 重建／安裝shared library，更新Web Portal、Webhook、notify三份exact sdist並跑三個服務受影響完整suites。
- Python 3.10 compile/import、Black、isort、`git diff --check`、`git status --short`。
- 所有DB、LINE、Discord、GCP、GitHub與production網路邊界mock；不得讀真實env或secret。

## 非目標與禁止事項

- 不部署、不執行Cloud Build、不建立revision、不切traffic、不修改production env。
- 不pause／resume／修改Scheduler，不人工invokeWebhook、cron或Portal production route。
- 不連production Supabase，不執行DDL／DML／migration／backfill／cleanup。
- 不修改Secret、IAM、public/private boundary或發送真實LINE／Discord通知。
- 不開啟`PORTAL_DATA_PHASE_C_ENABLED`或`WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED`。
- 不新增schema 0005、不擴張角色／活動功能、不進行無關重構。

## 交付與協作流程

1. Work建立本task與`ready_for_codex / codex` handoff，透過固定跨session交給「Codex－實作」。
2. Codex實作、完整本機驗證、描述性commit、push、report及`ready_for_review / work`，預設不先建立PR。
3. Codex完成、中斷、疑義或blocking finding必須跨session通知Work；Work退回時同步HANDOFF並直接通知Codex。
4. Work查驗實際diff與高價值freeze反例；通過後建立唯一ready PR。
5. 這是shared runtime／跨服務安全邊界變更，CI應跑三個直接受影響服務與deployment tools；沒有schema／migration／
  model／SQL變更時，不應僅因Phase C名稱啟動PostgreSQL matrix。若classifier過度分類，應修正分類contract。
6. Required CI成功後依standing authorization squash merge；不另建純closeout PR。

## 完成定義

- 三個服務可在Phase C切換前由同一exact flag進入可驗證freeze，且受控副作用確實為零。
- Mixed Phase C只有在all-services frozen時才被controller接受為transition；mixed/unfrozen永遠被拒絕。
- Forward與rollback plan可離線重現，無shell／cloud mutation能力且不洩漏secret。
- TASK-078／079所需部署與activation證據、Owner批准點及停止條件完整。
- Work驗收、唯一ready PR及最小充分hosted Python 3.10 CI成功並squash merge。
