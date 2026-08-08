# TASK-081：Phase C 正式上線 release train

## 北極星目標

把已完成的 Phase C 資料模型與 application bridge，安全地帶到可供球隊正式使用的狀態：

- Person／多個登入 identity；
- Person status、qualification 與管理核可；
- Person-based attendance 與 display/formal name 呈現；
- 多服務一致、可凍結、可回退的 production activation。

本任務是一個大里程碑，但分成 **A. repository release readiness** 與 **B. Owner 一次性 production activation**。
Codex 只可執行 A；B 必須待 A 驗收、hosted CI、feature-off baseline 重新盤點及 Owner 對 exact operations 的明確批准。

## 現況與已確認事實

- production schema 已是 `0004_phase_c_identity_lifecycle`；不做 downgrade、DDL、backfill 或資料修復。
- Web Portal、LINE webhook 與 notify 是 Phase C direct callers；game broadcast 不是。
- 三服務的 runtime state machine 已是 exact flag、mixed-unfrozen fail-closed 的設計。Phase C 與 freeze 預設 off。
- notify 已於 TASK-080 部署 feature-off source；Web Portal 與 LINE webhook 已有 TASK-077 feature-off source evidence。
- 本次 notify 部署顯示 scheduled deployment wrapper 若本機等待被中斷，Cloud Build 仍可能繼續，但本機 post-check／temporary env cleanup
  需要人工接手。這是上線前必須補強的操作風險。

## A. Codex repository release readiness 範圍

### 1. Scheduled deployment 的中斷恢復安全性

- 將 scheduled-service deployment 修改為：Cloud Build／Cloud Run 新 revision 在所有 digest、Ready、private boundary、
  approved SHA 與 runtime contract 驗證前，不得自行承接 normal traffic。
- 支援受限的 resume／verify-only 流程：由非機密 build ID、service、approved full SHA、rollback revision 恢復；不得接受
  任意 shell、任意 revision、secret 或 env payload。
- 執行中斷、超時或 local process 結束後，後續 operator 必須能判定 build 未開始／進行中／成功未 promote／已 promote／未知，
  並依狀態明確停止、驗證或條件式 rollback。
- temporary `.env.yaml` 必須在本機正常失敗、KeyboardInterrupt／timeout-like exception、resume 與成功路徑安全清理；
  不讀取、列印、commit 或擴散內容。

### 2. 三服務 Phase C activation release controller

- 擴充既有 offline controller／preflight，產生可審查的 release manifest：三個 deployment unit 的 exact source commit、
  artifact/source fingerprint、candidate current／rollback revision、Phase C/freeze/maintenance vectors、Scheduler boundary、
  observation／stop criteria。
- manifest 與所有 CLI output 必須排除 Secret、env payload、token、DB URL、identity／member資料與完整 GCP response。
- 要求完整三服務集合，並讓 activation path 固定：all-off → all-frozen → all-on/frozen → all-on/unfrozen → observation；
  rollback 必須是反向且重新 freeze。任何 mixed-unfrozen、flag 缺漏／未知、revision/commit/fingerprint 漂移都 fail closed。
- controller 在 repository/local 階段僅能 validate/plan/render，不得自行呼叫 `gcloud`、HTTP、Scheduler、DB 或通知。

### 3. Feature-off／activation deployment contracts

- 查驗並補足 Web Portal、LINE webhook、notify 的 deployment settings／examples／tests，確保 Phase C、freeze 與
  maintenance flags 的 explicit false baseline 不會在 deploy 時消失；不讀真實 `.env.yaml`。
- 檢查 Web Portal wrapper、scheduled wrapper、LINE function deployment path 的 traffic/rollback/disruption boundary；
  對缺少的 static contract 補 test 或 fail-closed preflight，不做無關重寫。
- 為 production Stage B 生成一份精確 work package template，列出需在執行時唯讀重取的 revision、traffic、Secret binding
  name/version、flag metadata、IAM、Scheduler metadata、觀察者與停止權。不可填入猜測性 production 值。

### 4. 測試與交付

- 為 interrupted build、build polling、unknown/ambiguous state、resume mismatch、no-traffic promotion、cleanup、rollback、
  manifest redaction、mixed vector、flag/revision drift 建立離線 mock tests。
- 修改 shared runtime／Portal／webhook／notify 時，重建 shared artifact並跑直接 callers 的完整 suites；deployment tool變更跑完整 tools tests。
- 依變更範圍使用 change-aware CI；本任務若涉及 controller/deployment config而非 schema/model/SQL，不應無故要求 PostgreSQL matrix。
- Codex commit、push、report、handoff；Work 驗收並建立唯一 ready PR。Hosted CI 通過後可依 standing Git authorization merge。

## B. production activation gate（本輪不得執行）

只有 A 已驗收／merge後，Work 才能提出獨立的 Owner approval text。該 approval 必須同時鎖定：

1. exact merged commit、三個 feature-off revisions 與完整 rollback targets；
2. all three flags 在每一步的 exact values，並確認 private/public IAM boundary不退化；
3. 三服務 freeze開啟、Phase C依序開啟、freeze依序解除的每個 cloud mutation；
4. Scheduler 的自然排程／暫停策略、notification/attendance freeze 行為、命名操作員與觀察者；
5. 每步 15 分鐘、全量 30 分鐘觀察，及可立即 stop／rollback 的條件；
6. 不進行人工 attendance、identity、notification POST 或 production DB write，除非另有獨立且具體的測試批准。

## 明確非目標

- 不加入活動／旅遊／聚餐、Event schema、Google/Apple OAuth 或新的角色產品規則。
- 不改 schema `0004`、不做 backfill、RLS/grant/IAM/Secret/Scheduler資料變更。
- Codex 不得 build/deploy、讀真實 env／Secret、連 production、切 traffic、啟用 flags、呼叫 endpoint或發通知。
- 本任務完成不等於自動啟用 Phase C；B仍要 Owner final approval。

## 成功定義

- Phase C activation 有一條完整、可離線驗證、可中斷恢復、無 Secret輸出的 release path。
- scheduled deploy 不再因本機等待中斷而讓新 revision未經驗證自行承接 normal traffic。
- 三服務 explicit feature-off／freeze／activation contract均有 regression tests，所有不完整或mixed-unfrozen狀態都 fail closed。
- A經 Work／hosted CI驗收後，Owner只需要決定 activation window與最終精確 work package，而不用臨時補設計。

## Base 與協作

- Base commit：`d9213acea1708f051fc457753b3b941dbad305f6`
- Branch：`codex/phase-c-release-train`
- Owner已批准本任務的 repository/local實作與一般 Git流程；production B gate未批准。
- Codex完成、中斷或發現需要 Owner決策時，必須以跨 session通知 Work；Work的退回也以相同方式通知 Codex。
