# TASK-082：Phase C production activation

## 目標

把已合併的 Phase C application bridge 安全部署至 Web Portal、LINE webhook 與 notify cron，先建立三服務 feature-off baseline，再透過共同 freeze gate 分階段啟用 Phase C。任何 production mutation 都必須使用本任務產生的精確工作包並取得 Owner 明確批准。

## 基準與前置事實

- Reviewed／merged source：`0e79763115ff5549a8fdf045eb48f48012ea5469`。
- TASK-081 PR #80 的 hosted Python 3.10 final gate 已全部通過。
- Production schema 已是 `0004_phase_c_identity_lifecycle`；本任務不執行 migration、DDL、DML、downgrade 或資料修復。
- 三個 rollout units：`web-portal`、`line-webhook-handler`、`notify-cronjob-service`。
- `game-broadcast-service` 不是 Phase C direct caller，不在本任務部署範圍。
- 起始假設是三服務 Phase C／freeze 皆為 `false`、Web Portal maintenance 為 `false`；必須以 fresh metadata 證明，不能只依賴本機 env 檔案。

## 階段 A：唯讀 production inventory 與精確工作包

取得 Owner 對唯讀 inventory 的批准後，Work 可使用已設定的 `gcloud.cmd`，只讀取下列非機密 metadata：

1. active account 與 project guard；project 必須精確為 `ntubtob-schedule-405614`，否則停止。
2. Cloud Run Web Portal／notify 的 latest created、latest ready、100% traffic revision、image digest、readiness、ingress，以及是否存在 `allUsers`／`allAuthenticatedUsers` binding。
3. LINE Gen2 function 的 state、build source bucket/object/generation、runtime、ingress，以及是否存在公開 invoker binding。
4. 三服務只讀取三個 Phase C 相關 flag 的名稱與值；不得列出完整 environment payload。
5. Secret 僅讀取 binding name／version，禁止讀取 payload、latest value 或完整 runtime config。
6. 相關 Scheduler job 的 name、state、schedule、timezone、target service/path；不得 invoke、pause、resume 或修改。
7. 重新計算 merged source 的 shared artifact fingerprint，並用 all-off vector 執行 offline preflight/controller。

Inventory 輸出必須去識別化，不記錄 token、DB URL、Member／Person／identity 資料、完整 IAM member、完整 service response 或其他 env values。任何缺漏、漂移、非 exact boolean、非單一 100% traffic 或未知 rollback identity皆 fail closed。

## 階段 B1：feature-off baseline deployment

只在 Owner 批准精確 work package 後執行：

1. 以 merged source及重建後已驗證的 shared artifact部署 Web Portal、LINE webhook、notify cron；三服務的 Phase C／freeze 均保持 `false`，maintenance 保持 `false`。
2. Cloud Run candidate在 Ready、digest、source、runtime contract與IAM邊界驗證前不得承接 normal traffic。
3. LINE Gen2 deployment 前必須鎖定 immutable source rollback triple；失敗時依既有 Gen2 rollback runbook恢復該 source。
4. 每一單元完成後只做無副作用驗證：Web Portal首頁與demo 404、notify authenticated `GET /healthz`、LINE僅檢查metadata／logs，不人工送 webhook event。
5. 每單元觀察15分鐘；三單元 feature-off baseline共同觀察30分鐘。若時間不足，允許保持 feature-off並於稍後繼續，不得跳過觀察直接 activation。

## 階段 B2：coordinated activation

必須在 feature-off baseline通過後、同一份 Owner批准邊界內按 controller唯一順序執行：

1. Freeze on：Web Portal → LINE webhook → notify cron。
2. Phase C on（全程 frozen）：Web Portal → notify cron → LINE webhook。
3. Freeze off：Web Portal → LINE webhook → notify cron。
4. All-on／maintenance-off共同觀察30分鐘。

每次 mutation 前後均重新讀取該單元 exact flag、revision/source、readiness與traffic，並重新跑 controller next-step。任一 mixed-unfrozen、revision drift、非 exact boolean、IAM drift、startup error、unexpected DB／attendance／identity／notification side effect均立即停止。

## Scheduler 與自然流量策略

- 在 inventory 得到 schedule 後，activation window應避開會發送通知的排程；若無法避開，必須另取得 Owner 對精確 Scheduler pause／resume 的批准。
- Freeze使 attendance count job成為成功 no-op，但不代表批准人工 invoke。
- LINE webhook freeze期間，真實使用者若送出 attendance postback，會收到固定「系統切換中」回覆；本任務不人工觸發、不廣播。
- Web Portal freeze期間，受控登入 callback／identity／attendance／admin writes回覆503；read-only頁面仍可使用。

## Rollback

第一層為 flags rollback：重新進入全 frozen，依 LINE webhook → notify cron → Web Portal 關閉 Phase C，再依 controller反向解除 freeze。Schema 0004與已寫入的資料／audit保留。

第二層為 deployment rollback：在 all-off已確認後，Cloud Run回切精確 feature-off revision；LINE Gen2回復鎖定的 immutable source triple。任何 traffic／source mutation均包含在 Owner工作包批准內才可執行。

## 明確非目標

- 不啟用 `WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED`。
- 不執行 production DB寫入、migration、修復、清理或備份還原。
- 不人工 invoke Scheduler、webhook、attendance、identity或通知 endpoint。
- 不修改 Secret、IAM、Scheduler、schema或其他服務。
- 不發送人工 LINE／Discord訊息。

## 驗收與停止條件

- 每一步皆有 exact before／after metadata、controller判定與 rollback target。
- 所有服務最後為 Phase C `true`、freeze `false`、maintenance `false`，且不存在 mixed-unfrozen狀態。
- 觀察期間無新增 startup/import error、5xx異常、principal resolution failure、attendance projection drift、duplicate audit或通知錯誤。
- 無法證明以上任一項時停止並保持最近一個已驗證安全狀態。

## Owner 批准點

1. 先批准階段 A 的 production唯讀 inventory；此批准不包含 build、deploy、flag／traffic／source、Scheduler、IAM、Secret或DB mutation。
2. Work填妥 exact work package後，Owner再一次批准 B1、B2及條件式 rollback的精確範圍。

