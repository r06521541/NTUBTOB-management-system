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

## DEC-042：部署 Web Portal runtime Secret rollout

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`approved_and_completed`
- 決策：Owner 批准依 TASK-027 將 commit `cdb67bf007ec67d882c6e974143a4d527f1528cd` 部署至 production `web-portal`，綁定既定 runtime Secret references 與 Owner 已設定的管理者 allowlist，並執行兩個無副作用 HTTP GET 驗證。
- 結果：Cloud Build `7f155fb7-2288-416a-83a7-d77a95eee7e9` 成功；revision `web-portal-00027-fwf` Ready 且承接 100% traffic；`GET /` 為 200、`GET /demo/` 為 404；未觸發 rollback。
- 限制：未讀取 Secret payload 或管理者 ID 值，未測 LINE callback、production DB/admin routes，未發通知，也未修改 IAM、Scheduler、schema 或 production data。

## DEC-043：建立 Web Portal 跨平台安全部署工具

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`approved`
- 決策：Owner 批准建立 TASK-028 並交棒 Codex，將 TASK-027 暴露的 Windows make/sh 缺口、build context、PowerShell substitutions、長時間輪詢與 temporary env cleanup 風險做成 fail-closed Python 3.10 deployment wrapper。
- 授權：可修改 tools、離線 tests 與文件並建立描述性 local commit。
- 安全邊界：不得執行 `--execute`、不得呼叫 cloud/HTTP/Secret/DB/notification、不得部署或 rollback，也不得 push、建立 PR 或 merge。

## DEC-044：批准 TASK-028 Push 與 PR 工作包

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`approved`
- 決策：Owner 接受 Work 驗收建議，批准將 `codex/web-portal-safe-deployment-wrapper` push 至 `origin` 並建立描述性 Draft PR，允許唯讀查驗 GitHub Python 3.10 CI 與依結果更新同一 PR 的驗收文件。
- 安全邊界：不包含 merge、production deployment、wrapper `--execute`、Secret/IAM/Scheduler/DB/schema/data 修改、production HTTP 或 LINE/Discord 通知。

## DEC-045：批准跨瀏覽器 LINE Login State 修正

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`approved`
- 現象：Owner 在一般網頁瀏覽器進行 LINE Login 時看到 `Invalid state parameter`，LINE 內建瀏覽器則可使用受保護頁面。
- 決策：建立 TASK-029，使用具期限與簽章的 self-contained OAuth state，讓 callback 不依賴起始瀏覽器 session cookie，同時保持 fail-closed state validation 與站內 return-path 限制。
- 授權：TASK-028／PR #38 已完成 squash merge；Owner 批准 TASK-029 本機實作、離線測試與描述性 commit並正式交棒 Codex。
- 安全邊界：本決策不批准 production 登入、logs、真實 LINE API、Secret／LINE Console 修改、部署、DB/schema/data 操作、push、PR 或 merge。

## DEC-046：Squash merge Web Portal 安全部署工具

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`accepted`
- 決策：Owner 批准將 PR #38 標記 ready 並以 Squash merge 合併，維持 default branch 每個 TASK 一個描述性 commit的精簡規則。
- 結果：PR #38 已合併為 `196c2087a1bfdf816f16aafc267c7008aa376f41`，標題為 `feat(web-portal): add cross-platform safe deployment wrapper`；最終 Python 3.10.20 CI run `31028391679`／job `92382569298` 成功。
- 安全邊界：merge 未執行 wrapper `--execute`、production deployment／HTTP、Secret／IAM／Scheduler／DB／schema／data 操作或通知。

## DEC-047：優先診斷 LINE callback 回到原瀏覽器

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`approved`
- 背景：TASK-029 證明 transferable signed state 會降低 login-CSRF／transaction-binding 邊界；安全補正後，不同 cookie store callback 會 fail closed。
- 決策：Owner 選擇先診斷並優先讓 LINE callback 回到登入發起的 external browser，不先建 two-phase shared transaction，也不接受 signed bearer login。
- 授權：Codex 可查 repository、離線測試與 LINE 官方公開文件；只有能證明維持 session binding 的 repository-only 修正才可實作並建立本機 commit。
- 安全邊界：不批准 production logs/login/API、LINE Developers Console 修改、Secret、DB/schema/data、部署、push、PR 或 merge。

## DEC-048：採用 Production 受控 LINE Login Smoke Test 路線

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`approved_for_planning`
- 決策：TASK-029 經 PR #39 squash merge後，Owner選擇部署至既有Web Portal hostname，再由本人從原external browser進行一次真實LINE Login，以驗證 `disable_auto_login=true` 是否保持browser session continuity。
- 執行邊界：本決策批准建立TASK-030工作包，不等於production deployment授權。真正執行仍須批准exact commit、target、rollback、真實LINE API與production唯讀Member查詢；不包含Secret／IAM／LINE Console／schema／data修改或通知。

## DEC-049：修正 Windows gcloud Executable Resolution

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`approved`
- 決策：Owner批准TASK-031與完整PR工作包，修正deployment wrapper在Windows找到`gcloud.cmd`卻硬編碼執行`gcloud`的缺口，並要求離線regression tests與Python 3.10 CI。
- 安全邊界：不批准wrapper `--execute`、production deployment／rollback、真實gcloud／HTTP／LINE／DB呼叫、Secret／IAM／LINE Console／schema／data修改或通知；merge仍由Owner另行決定。

## DEC-050：以 Cookie Versioning處理既有Session遷移

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`approved`
- 證據：Owner在一般瀏覽器遇到Invalid state，但無痕視窗與清除該網站cookie後均可正常登入；production已依TASK-030 rollback至`web-portal-00027-fwf`。
- 決策：建立TASK-032，以專用版本化cookie名稱、明確production安全屬性及fail-closed重試UI處理stale/collision狀態，不建立跨瀏覽器transaction store或database schema。
- 安全邊界：批准本機實作、測試與描述性commit；不包含push／PR／merge、production deployment、LINE／DB／HTTP呼叫、Secret／IAM／LINE Console／schema／data修改或通知。

## DEC-051：部署驗證須等待Cloud Run Control-plane收斂

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`approved`
- 證據：TASK-032部署的`web-portal-00030-jmg`稍後顯示完整Ready／digest／runtime contract，但wrapper在HTTP前判定失敗並rollback；批准範圍內的request metadata為0筆。證據支持但不證明eventual-consistency race。
- 決策：建立TASK-033，以bounded polling等待new revision與traffic收斂，並加入不含敏感資訊的失敗stage分類；timeout或明確drift仍rollback。
- 安全邊界：批准本機工具／測試／文件修改與描述性commit；不包含push／PR／merge、wrapper execute、gcloud／HTTP／logs、production deployment／rollback、Secret／IAM／DB／schema／LINE或通知。

## DEC-052：Pinned Traffic須在Revision驗證後顯式Promotion

- 日期：2026-08-06
- 決策者：Owner
- 狀態：`approved`
- 證據：TASK-033部署建立Ready的`web-portal-00031-zvr`，但service traffic全程維持明確pin住的`web-portal-00027-fwf=100%`；現有wrapper沒有new-revision promotion command。
- 決策：建立TASK-034，將流程拆為new revision contract convergence、exact traffic promotion、traffic convergence、IAM／HTTP；任一步失敗仍回復exact rollback revision。
- 授權：Owner批准TASK-034與PR工作包。
- 安全邊界：不包含merge、production deployment／traffic mutation、wrapper execute、gcloud／HTTP／logs、Secret／IAM／DB／schema／LINE或通知；production須merge後另以exact commit批准。

## DEC-053：下一優先任務為Web Portal名單隱私邊界

- 狀態：`approved`
- 日期：2026-08-06
- 背景：production `/game-roster/<game_id>` 可在未登入時查詢並顯示已回覆與未回覆成員姓名；完整角色與 capability 規則仍未核准。
- 提案：TASK-035 先建立最小會員 authentication boundary，匿名 request 在任何 roster／attendance 查詢前 fail closed；已登入且已配對 Member 暫時維持既有隊內內容。
- 延後決策：普通隊員能否看未回覆者姓名、幹部／管理者更細權限，以及正式 RBAC schema 均另案決定。
- 授權：Owner 批准 TASK-035 與 PR 工作包；可實作、測試、commit、push、建立 Draft PR 與查看 CI。
- 安全邊界：repository-only；不包含 deployment、production／DB 存取、schema／migration、Secret／IAM、LINE／Discord 通知或其他服務修改。

## DEC-054：TASK-035合併並完成Roster Privacy Rollout

- 狀態：`approved_and_executed`
- 日期：2026-08-06
- 已完成：Owner批准PR #44 ready與squash merge；main commit為`5952e0b6d075ee2ba05c3b50057cc8108fc8e8cf`。
- 提案：建立TASK-036，以現有fail-closed wrapper部署exact merge commit，並新增一次不跟隨redirect的匿名roster 302 smoke check。
- Rollback原則：執行前重新唯讀確認當下Ready且承接100% traffic的exact revision；不得直接沿用歷史revision假設。
- 核准：Owner批准TASK-036文件內的exact commit deployment、限定唯讀／HTTP驗證與條件式rollback範圍。
- 結果：`5952e0b`部署為`web-portal-00033-kzq`，Ready且承接100% traffic；首頁200、demo 404、匿名roster同站登入302；未觸發rollback。
- 安全邊界：未修改Secret／IAM／DB／schema／data／LINE，未部署其他服務，未跟隨LINE Login redirect。

## DEC-055：最小化Web Portal Signed Cookie Session

- 狀態：`approved_for_local_implementation`
- 日期：2026-08-06
- 背景：LINE callback將完整Member dataclass與未使用的LINE display name放入Flask signed-but-not-encrypted cookie session；attendance直接依賴該Member snapshot。
- 決策：建立TASK-037，只保存`user_id`與`member_id`，平順清除既有legacy fields，並在attendance request-time取得fresh Member。
- 相容性：不得全域清空session；須保留合法identity、OAuth transaction、CSRF、return path及demo資料，Member不存在時fail closed且不loop。
- 授權：Owner要求直接交棒Codex；批准repository-only實作、測試、文件與本機commit。
- 後續授權：Work驗收通過後，Owner批准TASK-037 PR工作包，可push、建立Draft PR並查驗hosted Python 3.10 CI。
- 安全邊界：仍未批准merge、deployment、production／DB存取、schema／migration、Secret／IAM或通知。

## DEC-056：TASK-037合併並批准LINE Auto-login安全Fallback

- 狀態：`approved_for_local_implementation`
- 日期：2026-08-06
- 已完成：TASK-037經hosted Python 3.10 CI驗證，PR #45 squash merge為`4b9ddd483a197d00a41403858efd36ff964e6e10`；尚未部署。
- 問題：TASK-029對所有authorization request固定加入`disable_auto_login=true`，因此LINE in-app browser原可用的auto-login也被停用。
- 提案：TASK-038讓normal login不帶該參數；只有state continuity失敗頁的明確browser fallback以全新nonce/state加入`disable_auto_login=true`。
- 安全原則：保留signed state、session nonce compare與safe return path；不做User-Agent sniffing、不重用失敗code/state、不建立跨browser bearer state。
- 授權：Owner批准TASK-038 repository-only實作、離線測試與本機commit，並交棒Codex。
- 後續授權：Owner在Codex完成後授權Work驗收及後續完整鏈；驗收與hosted CI通過可直接push、建立PR、squash merge並部署exact merge commit至production Web Portal，含既有wrapper checks與條件式rollback。
- 安全邊界：真實LINE登入仍由Owner後續人工驗證；不允許LINE Console、Secret、IAM、DB、schema、data、其他服務或通知操作。
- 結果：PR #46 hosted Python 3.10 CI成功並merge為`d1ebefa`；production `web-portal-00034-7lm` Ready且承接100% traffic，normal login contract確認不含`disable_auto_login`，未觸發rollback。

## DEC-057：以明確登入選擇取代跨平台自動跳轉假設

- 狀態：`approved_for_local_implementation`
- 日期：2026-08-06
- Production觀察：LINE in-app auto-login與desktop QR登入成功；Owner的iOS Safari難以喚起LINE App，Android browser尚未驗證。
- 決策：建立TASK-039，移除`redirect_page.html`的meta auto-redirect，提供normal LINE登入與`mode=browser`fallback兩個明確、mobile-first入口。
- 安全原則：保留signed state、fresh nonce、safe return path與TASK-038 fallback；不使用UA sniffing、`line://`或自動OS判斷。
- 授權：Owner批准repository-only實作、測試、文件與本機commit，並直接交棒Codex。
- 後續授權：Codex完成後，Owner授權Work驗收並執行至deployment；hosted CI與PR通過可直接squash merge並部署exact merge commit，含既有wrapper checks、登入選擇頁無副作用HTTP contract與條件式rollback。
- 安全邊界：不點擊或跟隨LINE登入連結，不執行真實LINE／DB驗證，不修改Secret／IAM／schema／data／LINE Console或通知。
- 結果：PR #47 hosted Python 3.10 CI成功並merge為`7082afd`；production `web-portal-00035-mcl` Ready且承接100% traffic，登入選擇頁契約通過，未觸發rollback。

## DEC-058：先建立無Schema的角色權限基礎

- 狀態：`approved_for_local_implementation`
- 日期：2026-08-06
- 背景：Web Portal 已具備登入會員與runtime管理員allowlist，但普通隊員、幹部、系統管理者的能力仍分散在decorator、route與Demo判斷；未來活動管理需要可測試且fail-closed的權限邊界。
- 決策：建立TASK-041，集中角色與capability判斷並盤點既有routes。Production第一階段只把有效登入會員辨識為普通隊員，把既有`WEB_PORTAL_ADMIN_MEMBER_IDS`辨識為系統管理者；幹部capability先定義與測試，但在沒有正式角色來源前不得於production自動授予任何人。
- 產品方向：普通隊員管理自己的出席；幹部以上未來可管理活動；只有系統管理者可做Member配對與角色指派。其餘資料可見性與通知核准規則仍待Owner逐項決定。
- 授權：Owner批准建立TASK-041、整理文件資產並交棒Codex；可做repository-only實作、離線測試、必要文件與描述性本機commit。
- 安全邊界：不包含schema／migration、production DB、角色管理UI、真正活動CRUD、Secret／IAM／LINE Console、通知、push／PR／merge或deployment。

## DEC-059：以正式帳號頁與安全登出落地角色政策

- 狀態：`approved_for_local_implementation`
- 日期：2026-08-06
- 背景：TASK-041已建立並通過集中role/capability policy，但production尚無使用者可見的帳號頁、角色標示或全域登出；管理員配對入口仍需知道固定URL。
- 決策：建立TASK-042，新增member-only帳號頁、一般隊員／系統管理者角色標示、capability-aware管理入口，以及POST-only且CSRF保護的完整session登出；並為既有attendance／roster加入最小一致的mobile navigation。
- 相容性：Member資料須依session中的`member_id` request-time查詢，不放入cookie；production仍不得產生officer或提供角色指派。公開首頁／賽程與LINE Login流程保持不變。
- 授權：Owner批准建立TASK-042並直接交棒Codex；可做repository-only實作、離線測試、文件與描述性本機commit。
- 安全邊界：不包含schema／migration、新env、Google／Apple OAuth、production／DB操作、Secret／IAM／LINE Console、通知、push／PR／merge或deployment。TASK-041與TASK-042預計待驗收後合併為同一PR與Web Portal部署批次，仍須Owner另行批准。

## DEC-060：Web Portal採隊徽深藍與中性灰品牌系統

- 狀態：`approved_for_local_implementation`
- 日期：2026-08-06
- 背景：現有正式Portal、登入頁與Demo大量使用綠色作為品牌主色，與隊徽的深藍識別不一致；各CSS也各自定義相近色彩。
- 決策：TASK-043以隊徽深藍為主色、中性灰為介面基底，使用少量暖金／沙色作非語意強調；綠色只保留LINE官方按鈕與成功狀態，紅色只保留警示、取消、拒絕及破壞性操作。
- 實作原則：建立共用design tokens並漸進套用正式Portal、登入／恢復頁及Demo；不改route、資料、auth或產品規則，不引入大型前端framework。
- 驗收：需涵蓋約375px手機與桌面視覺、無橫向捲動、focus與文字對比、既有功能與離線測試。
- 安全邊界：repository-only；不包含push／PR／merge／deployment、production／DB、schema、Secret／IAM、LINE Console或通知。

## DEC-061：合併並部署角色帳號與品牌介面批次

- 狀態：`approved_and_executed`
- 日期：2026-08-06
- 授權：Owner一次批准TASK-041至TASK-043的PR、merge與production Web Portal deployment。
- 結果：PR #49的Python 3.10 CI成功，squash merge commit為`9deb7e11311d5ccdb4131cb3b13a318a6bceca60`；部署建立`web-portal-00037-lhx`並承接100% traffic，首頁200、Demo 404，未觸發rollback。
- 邊界：未修改Secret／IAM／Scheduler／schema／data、未人工觸發LINE或部署其他服務。

## DEC-062：優先診斷LINE登入後目的地遺失

- 狀態：`approved_for_local_implementation`
- 日期：2026-08-06
- Production觀察：Owner在LINE App內從`/attendance`開始normal LINE登入，成功後落到`/`；匿名redirect與登入選擇頁仍可確認保留`next=/attendance`。
- 決策：TASK-044先建立protected-route至callback的完整離線契約、集中安全目的地規則，能重現則修根因；無法重現則只加入固定分類且不含OAuth／個資的安全診斷，不做猜測性redirect hack。
- 優先順序：原過時webhook cache invalidation任務順延為TASK-045。
- 授權：Owner要求執行；批准repository-only實作、離線測試與描述性本機commit並交棒Codex。
- 安全邊界：不包含production logs/request URL讀取、push／PR／merge／deployment、production DB、LINE Console／Secret、schema、IAM、通知或其他服務。

## DEC-063：暫停登入目的地調查並移除過時cache呼叫

- 狀態：`approved_for_local_implementation`
- 日期：2026-08-06
- TASK-044狀態：安全診斷已部署，Owner重現仍落到首頁；Owner決定暫停此題，後續再查，不宣稱已修復。
- 決策：建立TASK-045，移除LINE webhook在attendance reply後對不存在Web Portal cache endpoint的同步、無timeout HTTP呼叫；先以離線測試證明reply行為與attendance fresh-read契約。
- 架構原則：不建立替代cache invalidation endpoint或跨服務呼叫；Web Portal attendance維持request-time查詢。
- 授權：Owner要求建立並交棒；批准repository-only實作、shared library rebuild、離線測試與描述性本機commit。
- 安全邊界：不包含push／PR／merge／deployment、production DB／logs、LINE／Discord通知、schema、Secret／IAM／Scheduler、LINE Console或其他服務重構。

## DEC-064：先量測attendance延遲再選cache或cold-start策略

- 狀態：`approved_for_local_implementation`
- 日期：2026-08-06
- 背景：Owner回想cache原始動機為首次取得資料約10秒；現行repository顯示Web Portal attendance request直接查DB而不呼叫Cloud Function，但尚無分段延遲證據。
- 決策：TASK-046只加入無個資、固定欄位、best-effort的attendance stage timings，區分Member／首次DB連線、games query、attendance analysis、render與total。
- 決策順序：先量測；cold start才評估minimum instances／startup CPU，DB connection才調pooling，query慢才看plan/index，只有優化後讀取壓力仍高才評估共享Redis短TTL。
- 授權：Owner同意依建議執行；批准repository-only實作、離線測試與描述性本機commit並交棒Codex。
- 安全邊界：不包含cloud config、pooling/query/schema、Redis/cache、production log/DB、load test、push／PR／merge／deployment或通知。
