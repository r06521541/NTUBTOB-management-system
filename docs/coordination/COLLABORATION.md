# Work–Codex 協作流程

版本：3.0

適用於本 repository 的規劃、實作、驗收、Git 整合與各環境基礎建設／production 操作。本文件是唯一協作規範；背景改善文件不構成
第二套規則。

## 1. 核心宗旨

> 對話用來釐清，repository 用來同步，Git 用來證明，HANDOFF 用來交棒；證據服務決策，不讓流程成為交付。

新 session 應只靠 active authority、實際 repository 與 Git 接棒，不依賴舊對話或 archive。

## 2. 角色、claim 與派工

- Owner：決定產品規則、優先序、重大取捨與 Owner-reserved 外部操作。
- Main Work：唯一全域協調核心；建立 task／claim、整合跨領域契約、驗收 diff、維護 authority、建立 final PR。
- Domain Work：在登記的具名領域內規劃、派工與 targeted review；跨端 API、auth、schema、shared model、通知、
  production、Secret、cloud、正式資料或 release 必須升級 Main。
- Codex writer：依 task 實作、自評、自測與交棒；不得成為自己 implementation 的唯一正式 acceptor。
- Advisor／reviewer：read-only；只對具名證據提出 `ACCEPT` 或 `REQUEST_CHANGES`。

每個 session 同時只持有一個 role。`main-work` 全域唯一；Domain lane 同時只可有一位 current actor；每個 work package
只有一位 writer。未獲有效 claim 者一律為 `advisor/read-only`。輪替先撤回舊 actor，記錄 full HEAD、dirty state、
已完成／剩餘事項，再遞增 lease。相同 `claim_id`／`lease_version` 的重送不得重複 ACK、開工或消耗驗證。

### Mandatory assignment packet

Main／Domain 每次派工只引用一次下列通用 packet，不在 task 反覆複製回報規則：

```text
task=<TASK-xxx>
branch=<exact branch>
base=<full SHA>
head=<full SHA>
actor_id=<exact session actor>
role=<main-work|domain-work:<domain>|codex-writer|advisor>
claim_id=<stable id>
lease_version=<positive integer>
scope=<bounded outcome>
owned_paths=<exact paths or globs>
write=<allowed|read-only>
report_to=<exact canonical agent path or Codex thread id>
stop_conditions=<bounded list>
```

Task 是 packet 權威；訊息只負責喚醒與傳送。接收者必須：

1. 立即回覆 `received/executing`，並核對 packet、HANDOFF、branch、HEAD 與 dirty state。
2. 工作持續時每 10–15 分鐘主動 heartbeat；blocker 或 stop condition 立即回報。
3. 完成時主動通知 Main，不可只停在自己的 session。Final packet 包含 task、branch、commit full SHA（未 commit 則
   current full HEAD 與 exact dirty paths）、tests、findings、remaining limits、external mutations。
4. Claim 缺失、actor／lease／owned paths 不符或 next actor 不符時維持 read-only 並通知 Main。

Main派工時不得要求接收者自行猜測recipient或thread id；packet直接提供canonical agent path或exact Codex thread id，
接收者在ACK、heartbeat與completion皆原樣回報。只要delegated agent／sibling task仍在執行，Main不得先結束自己的active
turn並假設completion會自動喚醒；必須以bounded `wait_agent`／`wait_threads`持續追蹤，遇Owner新輸入可中斷等待，處理後
仍須恢復追蹤。Main實際收到並處理completion packet後，delegated work才算完成交棒。

Domain Work 完成正式 task 後交回 Main；Main 只回 `changes_requested`、`accepted` 或 `next_task_assigned`。未收到
`next_task_assigned` 前不得自行開始下一個正式 implementation task。

## 3. 唯一真實來源與閱讀順序

| 資訊 | 唯一來源 |
| --- | --- |
| 當前任務、狀態與下一 actor | `HANDOFF.yaml` |
| 系統現在能力、外部 gate、active lanes | `PROJECT_STATE.md` |
| 長期產品、架構、授權與安全決策 | `DECISIONS.md` |
| 任務 scope、claim、invariant、acceptance | `tasks/TASK-xxx.md` |
| Writer delta 與直接證據 | `reports/` 中該 task 的既有 report |
| Main／Domain 驗收 | `reviews/` 中該 task 的既有 review |
| 已完成群組的索引 | `archive/<phase>/PHASE_*_CLOSEOUT.md` |

開始依序讀 `AGENTS.md`、本文件、`HANDOFF.yaml`、`PROJECT_STATE.md`、active task 與直接 report/review、目標
code/tests/runbook、Windows 時的 `AGENT_ENVIRONMENT.md`。Archive 預設不讀；只有具名歷史決策、事故、migration 或
rollback 調查才讀。歷史文件只證明當時事實，不授權今天的操作。

## 4. TASK、Push、PR 與 Flutter incubator

- TASK 是工作／決策單位；push 是 checkpoint；PR 是整合 delivery unit，三者不必一對一。
- Task 標記 `planning`、`work_package` 或 `delivery`，並有 stable `delivery_group`、風險與 verification budget。
- 同一 delivery group 原則上一個 ready PR、一次 final hosted CI；純 coordination 不單獨建 PR。
- Final PR 由 Main 在完整 delivery unit 上建立；required CI 綠且無 blocker 才依 standing authorization merge。
- 描述性 commit 使用 `<type>(<scope>): <outcome>`；TASK 編號放 body/footer。

Flutter 產品孵化只涵蓋 task 明列之 UI、routing、local state、fixture 與 prototype model。具名共同 branch 可累積 focused
evidence checkpoint；接近部署／release candidate 才建立唯一 final PR。Auth、安全、後端契約、shared boundary、正式
資料、Secret、schema、真實通知、deployment、signing 或 store 一律退出豁免並升級 L2／L3。

## 5. 任務流程與驗收

Work 先收斂價值、scope、non-goals、事實、風險、依賴、測試與 Owner gate。高風險／跨模組／database writer 修改前
回報五行 checkpoint：目標、owned paths、invariant、最小測試、blocker／Owner 決策點；無決策點可直接繼續。

Writer 交回前必須：

- 逐條對照 task 與完整 diff，保留他人 dirty changes。
- 覆蓋重要成功、失敗、重試、併發、rollback 與權限／資料邊界。
- 執行最小充分測試、格式檢查、`git diff --check`、`git status --short`。
- 核對 branch、base、full HEAD、未追蹤檔案與外部副作用。
- 更新同一份 report，不新增 correction／completion 變體。

安全／架構初審先於昂貴 matrix、Flutter build、Emulator 或 hosted CI。Main 驗收實際 diff 與 immutable evidence；一次列完
同風險層 findings。低風險最多一輪 correction，中風險最多兩輪；同一 runtime blocker只允許一次唯讀 layer split 與
一次 source correction，再次出現即 inconclusive／quarantine，不以 retry 或新 reason code 無限延長。

## 6. HANDOFF singleton

`HANDOFF.yaml` 只表示當前 task 與下一 actor，task claim 與 Domain registry 分別由 active task 與 `PROJECT_STATE.md`
承載。跨 session handoff 只傳 base/head、dirty paths、behavior delta、exact tests、limits 與 next action。

有 active task 時，`task` 指向它；`report`／`review` 是 exact path 或 `pending`。沒有 active task 時必須同時滿足：

```yaml
active_task: null
status: completed
next_actor: owner
task: null
report: null
review: null
```

不得保留 stale task/report/review，也不得以 sidebar、對話或跨 session 訊息改寫 singleton authority。常用 status：
`planning`、`ready_for_writer`、`in_progress`、`ready_for_review`、`changes_requested`、`awaiting_owner_approval`、
`completed`、`blocked`。Next actor 不屬於自己時保持 read-only。

## 7. Git 與外部授權邊界

Owner standing authorization 允許 task 內 branch、commit、push、PR、CI 查驗、ready、修正、squash merge、同步 main 與
branch cleanup；前提是 diff 已驗收、CI 成功且無 blocker／scope expansion。不得直接 commit default branch。

此授權不包含 production、production DB、Secret payload、IAM／Scheduler／cloud resource、真實通知、provider／store、
release signing、付費／公開權限、不可逆刪除或重大產品／架構變更。這些仍需 exact Owner gate。

IOS-TF-01例外僅依DEC-109／TASK-198生效：Owner已授權既有資產簽署、隔離staging與僅本人TestFlight。
Main保留exact preflight與單次operation證據，但包內SHA／confirmed-zero correction不重複要求Owner批准。
下列wrapper／review／清理／uncertain reconcile規則仍保留；named stops與USD20上限不因standing approval豁免。

DEC-100 的隔離 fictional staging autonomy只允許 repository verifier與read-only preflight確認 exact target、identity、cost、
public boundary、rollback後的 task-scoped可復原操作。不得推論 production、真實資料、Secret payload或不可逆操作也獲授權；
結果不確定時先唯讀 reconcile，不重送 mutation。

## 8. Repository-owned Owner interaction wrapper

會收集敏感輸入或執行mutation的scripted／CLI／operator workflow，只能由已提交、已review且task明列的repository
wrapper承載。Task／HANDOFF可交給Owner一個exact、可見的手動browser／login／MFA／consent／Console動作而不使用
wrapper；完成後只回固定去識別化結果。Browser/chat state、臨時UI或off-repository helper都不能成為durable authority、
approval、target或evidence來源，也不得包裝mutation來繞過review。

Wrapper contract：

1. 先執行完全 read-only preflight，固定解析 exact target、action、count／scope、artifact、identity、rollback 與目前外部
   state；preflight與mutation不得合併成 Owner 看不到目標的單一步驟。
2. Prompt與error使用固定 ASCII-safe文字，不插入caller提供的 key/value、Secret或exception cause。敏感輸入必須 hidden
   input、不得 echo／log／clipboard／command line／environment；length-only feedback只顯示長度與固定分類，不顯示
   內容、prefix或hash。
3. Owner approval綁定 preflight產生的 exact one-shot action。Wrapper每次執行最多送出一次 mutation；輸入只存記憶體並在
   使用後清除，不產生重複 transcript、screenshot、temporary file或其他 off-repository evidence副本。
4. Retry只依固定分類：`pre_execution_rejected`可修正後重新 preflight；`confirmed_zero_mutation`需新 preflight與新 one-shot
   approval；`confirmed_success`不得重送；`uncertain`／中斷／timeout只准獨立 read-only reconcile，禁止 mutation retry。
5. Durable evidence只能是repository contract允許的單一 sanitized result，記錄artifact／target alias、固定結果類別與必要
   metadata；不得保存敏感輸入或把臨時 helper、聊天文字、瀏覽器狀態當 authority。

每個 runtime packet另列 `operator=agent|owner`、`owner_gate`、`standing_authorization`、`stop_only_on`、`report_to`。
Agent處理一般唯讀與已核准可復原 sandbox操作；Owner只處理登入／MFA／consent、Secret payload、signing／store、production、
真實通知、付費／公開權限與不可逆刪除。

### 8.1 重要基礎建設的可靠性與診斷驗收

按控制能力與失敗影響分級：持有credential、控制簽署／發布／CI/CD、可寫外部狀態／付費資源、執行migration／
recovery，或故障會阻斷交付的工具，即使只跑local／staging／internal testing，仍屬重要基礎建設。
涉及權限／Secret／發布等控制邊界採L3；一般無副作用工具依實際風險分級，不一律要求production批准。

- 首次建立或更換交付鏈，先取得最小、平台原生／官方支援路徑的成功基準與清理證據，再擴充自動控制層。
  記錄來源、工具／環境、目標與實際完成層級；沒有真實簽署／上傳基準時不能以mock或未簽署build替代。
  手動觸發同一壞掉wrapper不算獨立基準。可重用未變更的exact evidence，不要求每次小修再跑完整live流程。
- 新增自訂gate先說明它防止的具體失敗、為何平台機制不足、如何正反向測試、退出／替代方式與維護者。
  Baseline準備前先完成必要安全檢查；不是為省流程而繞過review、公開secret或放寬key access。
- 新建／修改重要操作入口，必須把診斷列為acceptance：區分本機驗證、transport、provider拒絕及程式錯誤；
  保留原始原因與獨立cleanup結果、當時stage/check、已知副作用／未知範圍、固定next action。
  已知cause／effect不得被上層default覆寫；未解決不能回NONE。未知原因需明示缺證據處與唯讀處置，不暗示重試。
- 保存的是白名單結構化診斷，不是raw exception／完整response／secret／雜湊secret。每個邊界在丟棄原文前分類；
  可用固定check名稱或match布林保留差異，不必公開實際敏感值。寫入／close失敗也須保留可安全回報的原始原因。
- 至少一組protocol-shaped假回應／假日誌穿越真實adapter→state→recovery→final output；只mock最外部I/O。
  驗證等待／未知狀態、HTTP／transport失敗、部分mutation、主失敗＋cleanup失敗、legacy／損壞證據與不洩密。
  正向與失敗語意都須assert；一味assert STOP或沒有secret不足。新增回歸須先在舊實作失敗，再在修正後通過。
- Main與獨立reviewer檢查完整失敗鏈及實際未驗證層，不以測試數量／文件齊備替代；CI應執行直接回歸套件。
  同blocker的試誤上限依第5節／active authority，換task、SHA、操作者或reason code不重置次數；兩輪無新證據
  即停止live試誤、比較標準路徑／縮小流程，不能用Owner再次輸入代替實驗設計。
- 每次Owner操作前在原task五行checkpoint補上假說、可觀察成功／失敗、回復／清理與剩餘Owner動作。
  Standing authorization內的普通修正不新增批准儀式；新credential custody／服務商／成本等實質變更才升級。

實作指引與教訓索引見 `../development/INFRASTRUCTURE_RELIABILITY.md`；不建立另一套授權規範。

## 9. CI 與證據成本

| 變更 | 最小充分 evidence |
| --- | --- |
| 純文件／archive | quick docs gate |
| 單一服務 | affected suite |
| shared library | 所有直接 callers |
| schema／migration／model／受控 SQL | PostgreSQL 15／16與portal-data gates |
| auth／authorization／workflow／deployment tooling | 對應完整安全 suite |

- L1 presentation：focused tests、format/analyze、Main review、hosted full；不機械增加 Domain/local full/runtime。
- L2 state/auth/cache/idempotency：writer affected-full、具名 targeted review、Main risk review、hosted CI。
- L3 API/schema/deploy/Secret/production：architecture/security review、affected matrix、exact target/artifact、Owner gate、
  post-check與rollback。

Evidence reuse key包含 full HEAD、exact command/suite、runtime/database matrix與artifact fingerprint。相關 diff、dependency與
environment contract均未變才可重用。Platform transient可在相同 SHA 記錄原因後重試；source/config/lockfile/artifact改變
只重置受影響 slice。只有本機缺必要平台證據才提前 Draft PR，不為補 run ID／timestamp重跑 CI。

## 10. Production 流程

Merge不等於部署。Production固定為：read-only discovery → 將 exact target/count/commit或digest/impact/rollback交 Owner →
Owner exact approval → 一次 mutation/deployment → immediate post-check。取消、網路中斷或輸出不明時禁止重送；先做
獨立 read-only recovery diagnostic。Artifact、checksum、validator、runbook順序或安全邊界變更會使舊批准失效。

## 11. 文件與決策生命週期

- 同一 TASK 原則上一份 task、一份 report、一份 review；L1無新外部證據／finding時可不另建 report/review。
- Task只放scope/invariants/acceptance；report只放delta/evidence；review只放finding/verdict/limits；HANDOFF只放singleton。
- `PROJECT_STATE.md`只寫現行能力、外部 gate與active lanes，不累積逐 task流水帳。
- `DECISIONS.md`只放仍規範未來的決策；不改語意的澄清更新原 DEC，實質改變才建立連續新 DEC並標示 supersedes。
- 完成群組原文不改，整組移入`archive/<phase>/`，只新增一份closeout索引；archive永不授權現在操作。
- Active `tasks/`、`reports/`、`reviews/`只保留 active或外部仍待完成群組；模糊狀態不封存。
- `COLLABORATION.md`不超過350行；`PROJECT_STATE.md`不超過200行。預算不足時停止並向Owner說明，不犧牲安全語意。

純 coordination預設併入實質 delivery PR；只有必須立即生效的安全／授權／操作邊界才可獨立 PR。Merge SHA可在下一次
實質 coordination update前作短期完成證據；不得只為run ID、時間或singleton另建 PR。

## 12. 衝突、停止與 session 交接

優先序：Owner最新明確指示 → active task具理由／範圍／終止條件的安全例外 → `HANDOFF.yaml` → 現行
`DECISIONS.md`／本文件／`AGENTS.md` → archive歷史。

遇到未批准production mutation、Secret payload、真實通知、不可逆資料操作、重大產品／架構改變、不明destructive target、
無法判定的外部 mutation結果，或必須放寬安全邊界才能繼續時立即停止交回Owner。

結束前讓`PROJECT_STATE.md`、`DECISIONS.md`、`HANDOFF.yaml`回答：現在如何運作、尚缺什麼、輪到誰、下一步需何決策。
新 task優先使用乾淨session；厚重session只作歷史顧問。Main維護全域singleton與跨lane整合，Domain只交回自己的delta。
