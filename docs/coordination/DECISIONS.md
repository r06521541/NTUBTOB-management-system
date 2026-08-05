# 專案決策紀錄

## DEC-001：接受 TASK-001 結案

- 日期：2026-08-04
- 決策者：Owner
- 狀態：accepted
- 決策：Owner 接受 TASK-001 的 Work 驗收結論，任務正式結案。
- 驗收證據：完整 unittest 17/17 通過，四項部署契約 mutation checks 均能捕捉回歸。
- 已知限制：尚未以可用的 Python 3.10 runtime 實跑，也未執行 Black、Docker build、Cloud Build 或線上整合驗證。
- 不包含的授權：此決策不批准 stage、commit、push、PR、部署、Secret 操作或真實 LINE/Discord 通知。
- 後續事項：是否建立 Python 3.10 CI 尚未決定；若要執行，應另立任務並定義 CI 平台與觸發條件。

## DEC-002：建立最小 Python 3.10 CI

- 日期：2026-08-04
- 決策者：Owner
- 狀態：approved
- 決策：建立 GitHub Actions workflow，以 Python 3.10 自動執行目前的 `game_broadcast_service` 完整 unittest suite。
- 範圍：只建立測試 CI；使用 repository read-only 權限，不使用 Secrets，不包含部署、發布、GCP 或真實外部服務。
- 觸發：pull request、push 到 main，以及手動 `workflow_dispatch`。
- 安全要求：官方 actions pin 到完整 commit SHA，不使用 `pull_request_target` 或 write permissions。
- 不包含的授權：不批准 commit、push、啟用/修改 repository Actions settings、branch protection、部署或 Secret 操作。
- 實作任務：`TASK-002`。

## DEC-003：接受 TASK-002 結案並建立 commit

- 日期：2026-08-04
- 決策者：Owner
- 狀態：accepted
- 決策：Owner 接受 TASK-002 的 Work 驗收結論，任務正式結案，並授權將 TASK-002 workflow 與協作文件建立為 commit。
- 驗收證據：本機 unittest 17/17 通過；workflow 安全與規格靜態檢查通過；官方 action release commit SHA 已查證。
- 已知限制：尚無 GitHub workflow parser 與 Python 3.10 hosted runner 的實跑證據；第一次 push 並建立 PR 後仍需確認線上 CI。
- 不包含的授權：不批准 push、PR、merge、部署、Secret 操作、正式 LINE/Discord 通知或其他雲端資源變更。

## DEC-004：採用 Draft PR 一次授權流程

- 日期：2026-08-04
- 決策者：Owner
- 狀態：accepted
- 問題：原流程需要 Owner 分別處理或批准 commit、push、建立 PR、CI 查驗及合併後證據更新，造成多次人工交接，也容易在 merge 後才補驗收文件。
- 決策：一般任務可在 Owner 批准任務時，同時批准該任務的「PR 工作包」，讓 Codex 與 Work 依序完成 branch、commit、push、Draft PR、CI 查驗及同一 PR 內的驗收文件更新。
- 必要紀錄：每個任務是否取得 PR 工作包授權，必須明確寫入任務文件或本決策紀錄；未記錄即視為未授權。
- 最終控制：Work 驗收及最終 CI 成功後，仍須交回 Owner 決定是否 merge。
- 永久排除：PR 工作包不包含 merge、直接寫入 default branch、部署、release、Secret、GitHub repository/organization 設定、正式通知、不可逆資料操作或重大架構變更。
- 流程文件：`docs/coordination/COLLABORATION.md` 版本 1.1，第十四節。

## DEC-005：notify cron 與 game broadcast 共用 LINE 官方帳號

- 日期：2026-08-04
- 決策者：Owner
- 狀態：confirmed
- 決策：`notify_cronjob_service` 與 `game_broadcast_service` 使用同一個 LINE 官方帳號發送訊息。
- TASK-003 影響：notify cron 的 repository deployment config 可沿用既有 `CHANNEL_ACCESS_TOKEN` Secret Manager 名稱與 version 1 binding，不建立新的 Secret。
- 限制：此決策不證明 GCP Secret version、內容或 IAM 正確，也不授權讀取、修改或輪替 Secret。

## DEC-006：批准 TASK-003 與 PR 工作包

- 日期：2026-08-04
- 決策者：Owner
- 狀態：approved
- 決策：批准 `TASK-003` 的範圍、驗收條件與 DEC-004 定義的 PR 工作包。
- 已授權：任務 branch、任務範圍內 commit、push、建立或更新 Draft PR、唯讀 CI 查驗，以及在同一 PR 更新驗收文件。
- 未授權：merge、直接寫入 default branch、部署、Secret 讀取或修改、憑證輪替、正式通知、不可逆資料操作或重大架構變更。
- 憑證輪替：仍為獨立待決事項，不阻擋 repository-only TASK-003。

## DEC-007：接受並合併 TASK-003

- 日期：2026-08-04
- 決策者：Owner
- 狀態：accepted
- 決策：Owner 接受 TASK-003 的 Work 驗收結論，授權將 PR #26 標記 ready 並 merge。
- 結果：PR #26 已以 merge commit `9b812f5c476d804b434e484ea7f4e8bfd299bfa4` 合併。
- Merge 標題：`security(notify-cron): keep LINE credentials out of images`。
- 驗收證據：最終 Actions run `30917468698` 成功；Python 3.10.20 下 game broadcast 17/17、notify cron 4/4 通過。
- 不包含的授權：未批准部署、Secret 操作、憑證輪替、正式通知或不可逆資料操作。

## DEC-008：採用描述性 commit 與 PR 標題

- 日期：2026-08-04
- 決策者：Owner
- 狀態：accepted
- 問題：以 `TASK-xxx`、handoff 或 update files 為標題，離開協作文件後無法理解 commit 的實際目的。
- 決策：commit、PR 與 merge commit 標題必須描述受影響元件及主要行為／結果；優先採用 `<type>(<scope>): <outcome>`。
- TASK 編號：只放在 commit body/footer 或 PR 說明中作為追溯資訊，不得取代描述性標題。
- 執行規則：Codex 建立 commit 前自行檢查，Work 驗收 commit/PR 時再次檢查；不合規時應在 merge 前改寫或補正。
- 流程文件：`AGENTS.md` 與 `docs/coordination/COLLABORATION.md` 版本 1.2，第十五節。

## DEC-009：批准賽程隊伍篩選修正與 PR 工作包

- 日期：2026-08-04
- 決策者：Owner
- 狀態：approved
- 決策：批准 TASK-004，修正 `update_game_schedule` 在日期篩選時丟失隊伍條件的錯誤，並新增純函式測試與 Python 3.10 CI coverage。
- 行為邊界：維持隊名完全相等、起訖時間皆包含、保留輸入順序；不新增隊名 alias 或正規化。
- PR 工作包：批准 branch、描述性 commits、push、Draft PR、CI 查驗及同一 PR 驗收文件更新。
- 未授權：merge、部署、Secret、正式通知、production data、不可逆操作或重大架構變更。
- 任務文件：`docs/coordination/tasks/TASK-004.md`。

## DEC-010：接受並合併 TASK-004

- 日期：2026-08-04
- 決策者：Owner
- 狀態：`accepted`
- 決策：Owner 接受 TASK-004 的 Work 驗收結論，授權將 PR #28 標記 ready 並 merge。
- 結果：PR #28 已以 merge commit `c70ce63d3b91fc0d224c86a1b8f3aba085f5979c` 合併。
- Merge 標題：`fix(schedule): preserve team filter when selecting games`。
- 驗收證據：最終 Actions run `30920092830` 成功；Python 3.10.20 下 game broadcast 17/17、notify cron 4/4、schedule filter 5/5 通過。
- 不包含的授權：未批准部署、Secret 操作、正式 LINE／Discord 通知、production data 操作或不可逆變更。

## DEC-011：精簡任務協作 commits

- 日期：2026-08-04
- 決策者：Owner
- 狀態：`accepted`
- 決策：保留 Codex report、Work review、PROJECT_STATE 與 HANDOFF 等正式證據，但不再為每次狀態文字或角色交棒機械式建立 commit。
- 原則：每個任務原則上只有功能 commit、Codex 完工 commit、Work 驗收 commit 三類；實質且可獨立理解的修改仍可合理拆分。
- Merge 後結案：若只有 merge commit、時間與 PR 狀態等新事實，不另開純 closeout PR，併入下一個任務的規劃 commit；安全事件或重大風險不得延後。
- 流程文件：`docs/coordination/COLLABORATION.md` 版本 1.3，第十六節。

## DEC-012：批准 TASK-005 與 PR 工作包

- 日期：2026-08-04
- 決策者：Owner
- 狀態：`completed`
- 決策：批准 TASK-005，將 game broadcast 的邀請與取消時間視窗改為每次 request 取得一次 Asia/Taipei snapshot，避免長壽命 instance 沿用 module import 時間。
- 產品規則：保留既有 `today_begin + 11 days` 查詢上限；本任務不改變邀請提前範圍。
- PR 工作包：批准 branch、描述性 commits、push、Draft PR、CI 查驗及同一 PR 驗收文件更新。
- 未授權：merge、部署、Secret、正式 LINE／Discord 通知、production data、不可逆操作或重大架構變更。
- 任務文件：`docs/coordination/tasks/TASK-005.md`。

## DEC-013：接受並合併 TASK-005

- 日期：2026-08-04
- 決策者：Owner
- 狀態：`accepted`
- 決策：Owner 接受 TASK-005 的 Work 驗收結論，授權將 PR #29 標記 ready 並 merge。
- 結果：PR #29 已以 merge commit `086d663831cf49ddaa5f8413edd8508d1f6bf596` 合併。
- Merge 標題：`fix(game-broadcast): compute announcement windows per request`。
- 驗收證據：最終 Actions run `30922220358` 成功；Python 3.10.20 下 game broadcast 24/24、notify cron 4/4、schedule 5/5 通過。
- 不包含的授權：未批准部署、Secret、正式 LINE／Discord 通知、production data 或不可逆操作。

## DEC-014：採納 Production Deployment Runbook

- 日期：2026-08-04
- 決策者：Owner
- 狀態：`accepted`
- 決策：接受 `docs/operations/DEPLOYMENT_RUNBOOK.md` 作為未來 production deployment 的標準流程。
- 授權邊界：本決策只採納文件、部署前檢查、批准閘門、停止條件、驗證與 rollback 原則；不授權任何一次實際部署或雲端操作。
- 持續限制：每次 production deployment 仍須由 Owner 針對 target、commit、影響與 rollback 另行明確批准。
- Web Portal：在 LINE Login／session Secret 與 build context 邊界修正前維持禁止部署。
- 未授權：gcloud mutation、Cloud Build、Cloud Run／Functions deployment、Secret／IAM／Scheduler 操作、正式通知及 production data 操作。

## DEC-015：批准並完成 Game Broadcast Production Deployment

- 日期：2026-08-04
- 決策者：Owner
- 狀態：`completed`
- 核准：將 commit `086d663831cf49ddaa5f8413edd8508d1f6bf596` 部署至 production `game-broadcast-service`，並在定義失敗條件下允許 traffic rollback 至 `game-broadcast-service-00029-vmc`。
- 執行結果：Cloud Build `80b086fc-f0c1-4f6b-a4e6-3acb456a1d6b` 成功；revision `game-broadcast-service-00030-pgg` ready／healthy 並承接 100% traffic。
- 安全結果：service 維持 private，runtime identity 與 Secret references 未退化，temporary env 已清理，未觸發 rollback。
- 未包含／未執行：人工 endpoint invocation、Secret/IAM/Scheduler 修改、其他服務部署、正式資料操作或人工通知 smoke test。

## DEC-016：批准並完成 Notify Cron Production Deployment

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`completed`
- 核准：部署 commit `086d663831cf49ddaa5f8413edd8508d1f6bf596` 至 production `notify-cronjob-service`；接受 emergency rollback 至 `00009-k8z` 會短期恢復舊 credential boundary。
- 結果：Cloud Build `20152b06-02be-44d0-b50c-b92fc95877e7` 成功；revision `00010-z2x` ready／healthy並承接 100% traffic。
- 安全結果：service 維持 private，LINE token version 1 已作 runtime Secret reference，temporary env 已清理，未 rollback。
- 未包含／未執行：人工 endpoint invocation、credential rotation、Secret/IAM/Scheduler 修改、其他服務、production data 或人工通知 smoke test。

## DEC-017：批准並完成 Update Schedule Production Deployment

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`completed`
- 核准：將 commit `086d663831cf49ddaa5f8413edd8508d1f6bf596` 部署至 production `update-game-schedule`，接受既有 Scheduler 自然觸發可能造成的 production DB writes，並在定義失敗條件下允許以 Cloud Functions v2 API 回復 source generation `1741711972938401`。
- 結果：Cloud Build `7d26952d-f9d3-4a40-a941-26db20630636` 成功；revision `update-game-schedule-00028-bij` ACTIVE／ready。
- 安全結果：function 與 underlying service 維持 private，runtime、entry point、runtime identity、Secret reference與 Scheduler contract未退化，未觸發 rollback。
- 未包含／未執行：人工 function invocation、Scheduler/IAM/Secret 修改、手動 production data 修復、其他服務部署或 application log讀取。

## DEC-018：接受 Web Portal Local Demo並批准下一個Health Check任務

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`accepted`
- TASK-012：Owner完成local視覺驗收並接受mobile-first Web Portal demo MVP，授權建立描述性commit；不授權production deployment。
- TASK-013：批准為`game-broadcast-service`與`notify-cronjob-service`建立無副作用health checks，並批准標準PR工作包。
- TASK-013安全邊界：不得部署、人工呼叫production service、發送通知、讀寫production data、操作Secret/IAM/Scheduler或擴張至其他服務。

## DEC-019：接受並合併Health Checks，批准建立Game Broadcast部署工作包

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`accepted`
- TASK-013：Owner授權將PR #30標記ready並merge；merge commit為`974433168b86e5638adce779ed8eccced0542094`。
- TASK-014：Owner同意先建立`game-broadcast-service` health check production deployment工作包及唯讀preflight。
- 授權邊界：尚未批准實際build、deploy、production endpoint invocation、rollback、其他服務、通知、production data、Secret/IAM/Scheduler操作；執行需另行exact deployment批准。

## DEC-020：批准Game Broadcast Health部署並依條件Rollback

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`completed_with_rollback`
- 核准：將commit `974433168b86e5638adce779ed8eccced0542094`部署至production `game-broadcast-service`，執行control-plane驗證及唯一一次authenticated `GET /healthz`；符合trigger時允許100% traffic切回`game-broadcast-service-00030-pgg`。
- 結果：Cloud Build `fe74ab5d-7fa8-4ff1-8220-fa914b569f63`成功，revision `game-broadcast-service-00031-s65` Ready；但唯一一次health request回傳HTTP 404，因此依批准條件rollback。
- Rollback後狀態：`game-broadcast-service-00030-pgg` Ready並承接100% traffic；service維持private，Scheduler未變。
- 未執行：business routes人工invoke、application log讀取、其他服務部署、Secret／IAM／Scheduler修改或production data操作。
- 後續：404根因尚未確認；任何新production request、traffic mutation或deploy仍需Owner另行批准。

## DEC-021：建立Game Broadcast Health 404診斷工作包

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`approved`
- 決策：Owner要求建立TASK-015，以唯讀優先方式診斷TASK-014的production health 404。
- 規劃原則：先核對build／image provenance與Cloud Run metadata，再以production digest image做本機斷網驗證；必要時只讀取該次404的極窄request log metadata。
- 執行授權：Owner批准TASK-015第10節，包括GCP metadata／provenance、以digest唯讀下載image、本機`network none`驗證及極窄Cloud Run request log metadata查詢。
- 授權邊界：不批准production request、application stdout/stderr或payload讀取、部署、traffic／revision／IAM／Secret／Scheduler／network修改、production data或通知操作。
- 執行結果：TASK-015確認build source與deployed image均含正確health route；精確時間窗沒有對應Cloud Run request log，404已定位在frontend／container之前。現有授權不足以再區分URL入口與VPC Service Controls，已停止並交回Owner。
- 後續授權與結果：Owner批准唯讀子任務查詢同一精確時間窗及服務的Cloud Audit `HttpIngress` policy metadata；結果為0筆，未發現可記錄的policy denial證據，未擴大logs或重送production request。

## DEC-022：批准排程服務Startup安全修正與PR工作包

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`approved`
- 決策：Owner同意由唯讀子任務查audit log，主線同時繼續盤點其他安全修正。
- 盤點結果：兩個scheduled services在app import時建立`LineBotAnnouncementHelper`並查DB；notify package的`__init__.py`另有import-time `announce('Hi')`真實通知風險。
- TASK-016：已建立最小lazy initialization與import side-effect移除規格。
- PR工作包：Owner批准branch、描述性commits、push、Draft PR、CI查驗及同一PR內的報告／驗收文件更新；merge仍需Owner最終批准。
- 授權邊界：不批准部署、production request、production DB、真實通知、shared_lib／schema／Secret／IAM／Scheduler／deployment config修改或其他服務擴張。

## DEC-023：接受並合併排程服務Startup安全修正

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`accepted`
- 決策：Owner接受TASK-016的Work驗收結論，授權將PR #32標記ready並merge。
- 結果：PR #32已以merge commit `b14dcad3d1261772c8dc00898ba1caca114ce941`合併。
- Merge標題：`fix(scheduled-services): defer startup notification side effects`。
- 驗收證據：合併前最終Actions run `30975939328`、job `92209817045`成功；Python 3.10.20下game broadcast 27/27、notify cron 8/8、schedule 5/5通過。
- 安全邊界：未部署、未呼叫production、未連production DB、未發送通知，亦未操作shared_lib、schema、Secret、IAM、Scheduler或deployment config。
- 後續：若要讓production使用本修正，必須另立deployment任務，確認目標服務、commit、驗證與rollback後再取得Owner精確批准。

## DEC-024：批准Notify Cron Startup安全修正Production Deployment

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`completed`
- 核准：將exact commit `b14dcad3d1261772c8dc00898ba1caca114ce941`部署至production `notify-cronjob-service`，依runbook執行build、deploy及唯讀control-plane驗證。
- Scheduler：批准部署後既有Scheduler依原排程自然呼叫新revision，接受其可能讀取production DB並發送既有正式LINE通知。
- Rollback：符合TASK-017失敗條件時，批准將100% traffic切回`notify-cronjob-service-00010-z2x`。
- 未批准：人工invoke、Secret／IAM／Scheduler修改、credential輪替、其他服務部署或人工production data操作。
- 結果：Cloud Build `3d751cb3-6b47-4de5-9568-e25425ef63c5`成功；revision `notify-cronjob-service-00011-jpj` Ready／healthy並承接100% traffic，digest為`sha256:8f7d551c41bb6e911d1a2cbc8a22c2b0911ea98650c6e27d613b4c5e6057c596`。
- 安全結果：service維持private，runtime identity與Secret references未退化，temporary env已清理；未人工invoke、未修改Scheduler／Secret／IAM，未觸發rollback。

## DEC-025：批准Game Broadcast Startup安全修正Production Deployment

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`completed`
- 核准：將exact commit `b14dcad3d1261772c8dc00898ba1caca114ce941`部署至production `game-broadcast-service`，依TASK-018與runbook執行build、deploy及唯讀control-plane驗證。
- Scheduler：接受既有Scheduler自然呼叫新revision，並可能讀取production DB、發送既有LINE／Discord通知或寫入announcement timestamps。
- Rollback：符合TASK-018失敗條件時，批准將100% traffic切回`game-broadcast-service-00030-pgg`。
- 未批准：人工invoke任何health或business route、Secret／IAM／Scheduler修改、credential輪替、其他服務部署或人工production data操作。
- 結果：Cloud Build `b4081955-261f-4e41-a160-c31376e3b1ff`成功；精確digest建立revision `game-broadcast-service-00033-mdp`，Ready／healthy並承接100% traffic。
- 安全結果：service維持private，runtime identity、Secret references及Scheduler未退化；未人工invoke、未觸發rollback。
- 工具鏈發現：固定`:tag1`使原deploy step未建立新revision，Work以同一build的精確digest及顯式traffic完成核准部署；後續應改用immutable image reference並建立跨平台wrapper。

## DEC-026：授權後續任務自行建立Local Commits

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`accepted`
- 決策：Owner持續授權Work／Codex在完成範圍內工作並通過必要驗證後，自行建立local commits，不必逐次請示。
- Commit要求：維持描述性標題、範圍聚焦、保留使用者既有變更，並在提交前執行任務所需測試與`git diff --check`。
- 不包含：push、建立或合併PR、production deployment、正式通知、Secret／IAM／Scheduler修改、不可逆資料操作或重大架構變更；這些仍依既有流程個別取得Owner授權。

## DEC-027：批准Immutable Deployment Wrapper與PR工作包

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`approved`
- 決策：Owner批准TASK-019，由Codex實作scheduled services immutable image references與Python 3.10跨平台deployment wrapper。
- PR工作包：允許建立／使用task branch、描述性commits、push、Draft PR、CI查驗，以及Work在同一PR更新report／review／PROJECT_STATE／HANDOFF。
- 安全邊界：不得執行wrapper `--execute` path、Cloud Build、deployment、traffic mutation、production存取、Secret／IAM／Scheduler修改、正式通知、production data操作或merge。

## DEC-028：接受並合併Immutable Deployment Wrapper

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`accepted`
- 決策：Owner接受TASK-019的Work第三輪驗收結論，授權將PR #33標記ready並merge。
- 結果：PR #33已以merge commit `b053fce6b60c58b5dca597f4e4962f63d016a44a`合併。
- Merge標題：`feat(deployment): make scheduled service rollouts commit-addressable`。
- 驗收證據：合併前最終Actions run `30983055468`、job `92231531057`成功；本機wrapper 11/11、game broadcast 28/28、notify cron 9/9、update schedule 5/5及preflight／compile／diff checks通過。
- 安全邊界：未執行wrapper `--execute`、Cloud Build、deployment、production存取、通知、production data、Secret／IAM／Scheduler操作。
- 後續：首次使用execute path仍須針對exact commit、target service與rollback revision另立deployment工作包並取得Owner批准。

## DEC-029：批准LINE Webhook Ingress安全修正與PR工作包

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`approved`
- 決策：Owner批准TASK-020，以共用、可測試的ingress boundary讓缺少／空白／無效LINE signature明確回HTTP 400，且不得由未受信任請求觸發Discord、LINE、DB、cache或其他外部副作用。
- 相容性：合法LINE webhook仍維持HTTP 200／`OK`與既有event handlers；unexpected application failure不得偽裝為成功。
- PR工作包：允許建立`codex/harden-line-webhook-ingress` branch、描述性commits、push、Draft PR、離線測試與Python 3.10 CI查驗，以及同一PR內的report／review／PROJECT_STATE／HANDOFF更新。
- 安全邊界：不批准ready／merge、Cloud Functions deployment、production webhook request、正式LINE／Discord通知、production DB、Secret／IAM／Scheduler、schema或其他雲端操作。

## DEC-030：接受並合併LINE Webhook Ingress安全修正

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`accepted`
- 決策：Owner接受TASK-020的Work驗收，授權將PR #34標記ready並merge。
- 結果：PR #34已以merge commit `c022d5185cf6126ffd228b0c95b815c80ee39606`合併。
- Merge標題：`fix(webhook): reject untrusted LINE ingress without side effects`。
- 最終證據：Work-head `2227016148b5fdb91a56ea9af3b0d53bfc37e10c`的Python 3.10 run `30985595920`／job `92239490734`成功；Work本機重跑webhook 10/10、game 28/28、notify 9/9、schedule 5/5、wrapper 11/11及compile／diff checks通過。
- 安全邊界：未部署Cloud Function、未呼叫production webhook、未發送通知，亦未操作production DB、Secret、IAM、Scheduler或schema。

## DEC-031：批准Web Portal成員配對保護與PR工作包

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`approved`
- 決策：Owner批准TASK-021，以既有LINE登入、`WEB_PORTAL_ADMIN_MEMBER_IDS` Member ID allowlist及session CSRF保護Web Portal成員配對管理頁與兩個資料修改端點。
- Fail-closed規則：allowlist未設定、空白或任一格式錯誤時全部拒絕；未登入者不得讀取管理資料，非管理者回403，CSRF失敗回400且不得產生DB／Discord副作用。
- PR工作包：允許建立`codex/protect-web-portal-member-matching` branch、描述性commits、push、Draft PR、離線測試與Python 3.10 CI查驗，以及同一PR內的report／review／PROJECT_STATE／HANDOFF更新。
- 安全邊界：不批准ready／merge、Web Portal deployment、production request、正式LINE／Discord通知、production DB、Secret／IAM／Scheduler、schema或其他雲端操作。

## DEC-032：接受並合併Web Portal成員配對保護

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`accepted`
- 決策：Owner接受TASK-021的Work驗收，授權將PR #35標記ready並merge。
- 結果：PR #35已以merge commit `a7f801b44e07d1d8518b9f8675e99b4743a98e00`合併。
- Merge標題：`fix(web-portal): protect member matching administration`。
- 最終證據：Work-head `e51d2c07a9ffeedaaf0dfaf6c980b7519521ce28`的Python 3.10 run `30989020840`／job `92250460562`成功；Work本機重跑82項tests及compile／diff checks通過。
- 安全邊界：未部署Web Portal、未設定production allowlist、未呼叫production或操作Secret／IAM／Scheduler／schema。

## DEC-033：批准Web Portal Build與Secret邊界修正及PR工作包

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`approved`
- 決策：Owner批准建立TASK-022後直接交棒Codex，修正Web Portal完整env進入build／image、runtime Secret binding不足與固定`:tag1`問題。
- Secret策略：DB password、LINE Login channel secret與Flask session key只由Cloud Run runtime Secret references注入；repository未知的正式Secret resource名稱必須以必填參數提供，不得猜測、硬編碼或讀取Secret。
- PR工作包：允許建立`codex/harden-web-portal-build-boundary` branch、描述性commits、push、Draft PR、離線deployment contract tests與Python 3.10 CI，以及同一PR內的report／review／PROJECT_STATE／HANDOFF更新。
- 安全邊界：不批准ready／merge、Docker／Cloud Build實跑、deployment、production request、正式通知、production DB、Secret／IAM／Scheduler、schema或其他雲端操作。

## DEC-034：接受並合併Web Portal Build與Secret邊界修正

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`accepted`
- 決策：Owner接受TASK-022第二輪Work驗收，授權將PR #36標記ready並merge。
- 結果：PR #36已以merge commit `f7471da1fed20f6477a16d125a6347692e3e732d`合併。
- Merge標題：`security(web-portal): keep runtime secrets out of images`。
- 最終證據：Work-head `1dd9e30e47d513afe9e41a767278385eff8eed06`的Python 3.10 run `30992839053`／job `92262772115`成功；Linux實跑Web Portal 27/27與其餘70項tests通過。
- 安全邊界：未執行Docker／Cloud Build、Web Portal部署、Secret／IAM查詢、production request或production DB／schema操作。

## DEC-035：批准Web Portal Production Readiness唯讀盤點

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`approved_and_completed`
- 決策：Owner批准TASK-023第4節的production唯讀GCP與Secret metadata查詢，不包含Secret value、部署或任何mutation。
- 結果：Cloud Run current revision、traffic、digest、public boundary、runtime identity、env key分類、Secret resource names與narrow IAM metadata已完成查驗；readiness結果記錄於`docs/operations/deployments/WEB_PORTAL_READINESS_2026-08-05.md`。
- 阻擋：無法唯一辨識TASK-022要求的LINE Login channel secret與Flask session key Secret resources，故未產生可直接執行的deployment批准文字。
- 安全邊界：未讀取Secret／plain env values，未呼叫production URL，未執行build、deploy、traffic或任何Cloud Run／IAM／Secret／DB修改。

## DEC-036：批准離線Web Portal Team Operations Demo

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`approved`
- 決策：Owner批准建立TASK-024並交由Codex長時間離線實作，將既有demo深化為球隊賽事作戰中心。
- 產品範圍：Dashboard營運摘要、賽程月曆／篩選／ICS、出席細節、Game Day、交通與裝備分工、個人設定及幹部工作台prototype。
- 實作授權：可修改`apps/web_portal` demo程式／templates／static／tests與必要文件，並依既有授權建立描述性local commits。
- 安全邊界：不批准push／PR、部署、Secret／IAM、production request／DB、LINE／Discord或其他外部呼叫、schema／shared_lib修改或正式通知。

## DEC-037：接受Team Operations Demo並批准多元活動Demo

- 日期：2026-08-05
- 決策者：Owner
- 狀態：`accepted_and_approved`
- 決策：Owner接受TASK-024本機成果，不要求push；並批准Codex依Work整理的願景實作TASK-025多元活動與複合行程Demo，細節先採安全合理假設、後續再調整。
- 產品方向：幹部prototype可建立聚餐、旅遊／移地活動、友誼賽／OB賽；Event可包含多個Activities與三場以上比賽，並區分聯盟匯入／手動比賽及Event／Activity兩層出席。
- 實作授權：可修改Web Portal demo程式、templates、static、tests、README與必要協作文件，並建立描述性local commits。
- 安全邊界：不批准push／PR、部署、Secret／IAM、production／Supabase DB、schema／migration、shared_lib、crawler／LINE／外部API或正式通知。

## DEC-038：接受多元活動與複合行程Demo

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`accepted`
- 決策：Owner接受TASK-025及其mobile officer navigation補正。
- 成果：Local demo支援Event／Activity、幹部builder、聯盟／手動比賽來源、草稿／發布／取消、兩層出席與手機幹部入口；Work最終重跑45項tests通過，2項既有Windows platform skips。
- 限制：尚未完成Python 3.10與browser automation視覺證據；正式RBAC、API、schema、同步／去重與通知均未實作。
- 安全邊界：未push、建立PR、部署、操作Secret／IAM、連線production／Supabase DB、修改schema或呼叫外部服務。

## DEC-039：批准Web Portal Prototype Push與PR

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`approved_and_executed`
- 決策：Owner在接受TASK-025後批准push與建立PR，不包含merge或deployment。
- 結果：Branch `codex/prototype-web-portal-team-events`已push並建立ready PR #37；Python 3.10 run `31021863646`／job `92360319877`成功。
- 安全邊界：未merge、部署、操作production／Secret／IAM／DB／schema或發送通知。

## DEC-040：合併Web Portal Team Operations與Composite Events Prototype

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`accepted`
- 決策：Owner授權merge PR #37。
- 結果：PR #37以merge commit `cdb67bf007ec67d882c6e974143a4d527f1528cd`合併，標題為`feat(web-portal): prototype team operations and composite events`。
- 最終CI：Python 3.10 run `31022009347`／job `92360824095`成功。
- 安全邊界：merge不代表Web Portal deployment、Secret／IAM、production DB／request或通知授權。

## DEC-041：批准並完成Web Portal Runtime Secrets Bootstrap

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`approved_and_completed`
- 決策：Owner批准TASK-026依文件第5節建立兩個exact Secret resources及各一個version；LINE Login Channel Secret由Owner透過hidden terminal prompt輸入，session key由secure RNG產生。
- 結果：`web-portal-line-login-channel-secret:1`與`web-portal-session-secret-key:1`均為enabled；runtime service account既有`roles/secretmanager.secretAccessor`已確認。
- 安全證據：未執行Secret payload access／readback，值未寫入command argument、檔案、Git或對話；一次性腳本已移除。
- 安全邊界：未修改IAM／Cloud Run、未部署、未呼叫production、未連DB、未發通知，也未delete／disable／destroy任何Secret。
