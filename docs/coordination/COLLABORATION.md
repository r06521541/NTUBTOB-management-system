# Work–Codex 協作流程

版本：2.2

適用範圍：本 repository 的產品規劃、實作、驗收、Git 整合與 production 操作。

多 agent 節流的改善理由、試行方式與輕量指標見 `docs/planning/MULTI_AGENT_WORKFLOW_IMPROVEMENT.md`；該文件
提供背景但不構成第二套規則，本文件仍是唯一協作規範來源。

## 1. 核心宗旨

> 對話用來釐清，repository 用來同步，Git 用來證明，HANDOFF 用來交棒；證據服務決策，不讓流程本身成為交付。

本流程追求：提早發現設計錯誤、最小充分測試、一個成果一次整合、production 可停可證明，以及讓新 session
不必閱讀全部歷史。

## 2. 角色與權限

### Owner

- 決定產品規則、優先序與重大技術取捨。
- 批准 production deployment、production DB DDL／DML、不可逆資料操作、Secret／IAM／Scheduler／cloud resource
  變更及真實 LINE／Discord 通知。
- 對精確 production 目標、影響範圍與 rollback boundary 作最終決策。

### Work

- 盤點 repository、Git、測試與必要的唯讀外部事實。
- 區分已確認事實、推論與待確認事項。
- 與 Owner 收斂需求，建立 task、風險與驗收邊界。
- 驗收實際 diff／commit／測試，不只接受文字摘要。
- 維護現行狀態、決策與 handoff；一般不負責主要程式實作。

### Codex

- 依 task 實作、測試、自我驗收、commit、push、report 與 handoff。
- 保持 diff 聚焦，不修改 Work／Owner 的既有變更。
- 主動回報 blocker，不以 workaround 降低 auth、data、Secret 或 deployment boundary。

### Session role claim 與問責

角色是綁定可辨認 session 的責任 lease，不是模型或暱稱；每個 session 同時只持有 `owner`、全域唯一 `main-work`、具名
`domain-work:<domain>`、work-package-specific `codex-writer` 或 `advisor` 之一。未獲 Main Work 派任時預設 `advisor/read-only`。
派工 role claim 固定明列 `actor_id`（穩定 thread ID）、role、task/scope、owned paths、write、report target 與 stop conditions；
正式交棒另帶 from/to role、full HEAD 與 dirty state。角色不從 session title、模型或前一 task 推定。
Domain Work 固定給同一 session 跨同領域 task 問責，負責 writer、批次 findings、領域接受建議、heartbeat、交回與風險升級；
writer 每 package 唯一且不得自審，Main／Domain 不寫審查標的，advisor 永遠 read-only。切換前先撤回、記錄 final state 再派任；L1 可省 Domain，不可假造自寫自審。

### 多領域 Work 與次決策核心

專案可為 Flutter、Web、data 等邊界清楚的領域設置 `Domain Work`。Main Work 仍是全專案總控；Domain Work 是該領域
的次決策核心，不是第二套全域治理來源。

Domain Work 數量不預設上限。每新增一個 Domain Work，Main Work 必須先登記其領域名稱、worktree／branch、可自主
決策範圍、禁止觸碰範圍、上游契約與交回節點；Domain Work 之間不直接建立互相矛盾的正式契約，所有跨領域依賴與
衝突均匯入 Main Work，由 Main Work 作唯一核心協調與整合節點。

- Owner 決定產品方向、優先序與重大取捨；Main Work 管理全域 TASK 編號、跨領域契約、依賴順序、協作文件、final PR／merge／deployment 與最終驗收。
- Domain Work 可在已核准規格與 task 內，自主與 Owner 收斂領域需求、決定低風險內部設計、拆解候選 work
  packages、指揮領域 Codex、要求 task 內補正並驗收領域測試。
- Domain Work 可使用獨立 worktree／branch 並行；不得與其他 Work 同時修改同一檔案，也不得自行占用全域
  `TASK-xxx`／`DEC-xxx` 編號。候選工作先使用穩定名稱，由 Main Work 配號及檢查 delivery group。
- 純領域內 UI、元件、routing、fake repository／fixture、測試與不改契約的重構，不需逐步向 Main Work 請示。
- 涉及跨端 API、authentication、authorization、schema、shared model、通知語意、production、Secret、IAM、cloud
  resource、正式資料或 release boundary 時，Domain Work 必須先升級給 Main Work；需要 Owner 權限者再由 Main Work
  交 Owner 決定。
- Owner 與 Domain Work 可連續互動到一個完整段落；新決定若改變已核准 task 的範圍、契約或驗收條件，必須先同步
  Main Work，不得從討論完成推定為已授權跨領域實作、PR 或部署。

Domain Work 完成正式 task 後必須交回 Main Work，至少提供 branch、完整 commit SHA、dirty state、完成／未完成範圍、
驗證結果、外部副作用聲明與建議下一工作包。Main Work 回覆狀態只有：`changes_requested`、`accepted` 或
`next_task_assigned`；在收到 `next_task_assigned` 前，Domain Work 可繼續規劃與處理原 task review，但不得自行開始下一個
正式 implementation task。

## 3. 唯一真實來源

| 資訊 | 唯一來源 |
| --- | --- |
| 當前任務、狀態與下一位角色 | `HANDOFF.yaml` |
| 系統現在能力、風險與優先序 | `PROJECT_STATE.md` |
| Owner 核准且仍有效的長期決策 | `DECISIONS.md` |
| 任務需求、範圍與驗收條件 | `tasks/TASK-xxx.md` |
| Codex 最終實作與測試證據 | `reports/TASK-xxx-CODEX.md` |
| Work 最終驗收結論 | `reviews/TASK-xxx-WORK.md` |
| 已完成階段的摘要與歷史索引 | `archive/<phase>/PHASE_*_CLOSEOUT.md` |

歷史 task／report／review／decision 只證明當時發生的事，不授權現在的操作。封存資料預設不讀，只有調查歷史
決策、事故、migration 或 rollback 時才查閱。

## 4. 啟動閱讀順序

每次開始依序閱讀：

1. `AGENTS.md`。
2. 本文件。
3. `HANDOFF.yaml`。
4. `PROJECT_STATE.md`。
5. 當前 task 與直接相關 report／review。
6. 目標程式碼、相鄰測試與必要 runbook。
7. Windows／本機操作時閱讀 `docs/development/AGENT_ENVIRONMENT.md`。

不要掃讀 archive，也不要因 roadmap 出現某功能就擴張 active task。

## 5. TASK、Push 與 PR

三者不是一對一：

- TASK：工作、決策與驗收單位。
- Push：保存 checkpoint 與跨 session 交棒；不代表已整合、CI 完成或可部署。
- PR：整合進 `main` 的 delivery unit。

新 task 應標記：

```text
task_type: planning | work_package | delivery
delivery_group: <stable-name> | none
requires_independent_pr: true | false
```

Task 同時列出風險等級與 verification budget。Domain review 只有在 task 明列獨立 domain risk 時才加入；小型
presentation task 不因模板自動增加 reviewer。預算是節流而非省略安全驗證；新增高風險 diff 時只重置受影響部分。

- `planning`：唯讀盤點、產品規則或設計；通常不單獨 commit／PR。
- `work_package`：大型成果的一段；可 commit／push 到共同 release branch。
- `delivery`：可獨立整合、部署、rollback 或成為後續穩定基準；建立 final PR。
- 同一 `delivery_group` 原則上只有一個 ready PR 與一次 final hosted CI。
- 小型獨立 bug 或安全修正可以一個 TASK 對一個 PR。

## 6. 任務流程

### A. Work 收斂需求

Work 先確認：使用者價值、範圍、非目標、已知事實、風險、依賴、最小充分測試、是否涉及 production 或 Owner
決策。尚未收斂的願景先寫 planning note，不急著建立 implementation task。

### B. 實作前五行 checkpoint

高風險、跨模組或 database work package 修改前，Codex 回報：

1. 理解的目標。
2. 預計修改的核心檔案。
3. 關鍵 invariant／安全邊界。
4. 預計執行的最小充分測試。
5. 歧義或 blocker。

Work 應在此時攔截錯誤設計。沒有 Owner 決策點時，Codex 可直接繼續，不增加儀式性等待。
平行任務的第 2 行必須包含 owned paths；Main Work 在派工前確認 writer scope 沒有交集。

### C. Codex 實作與自我驗收

交回前必須：

- 檢查完整 diff 並逐條對照 task。
- 覆蓋重要成功、失敗、重試、併發與 rollback 路徑。
- 執行最小充分測試、`git diff --check`、`git status --short`。
- 確認 branch、base、HEAD，且未納入他人既有變更。
- 更新同一份 Codex report；同一 task 不新增 correction report。
- 建立描述性 commit、push，將 `HANDOFF.yaml` 交回 `ready_for_review / work`。

Writer 完成初版 diff 與 invariant self-review 後，先交 architecture／authorization／security boundary review；通過後
才執行 PostgreSQL matrix、Flutter build、Emulator 或 hosted CI 等昂貴驗證，避免錯誤設計先消耗完整 suite。

### D. Work 風險式驗收

Work 檢查 branch、commit、dirty state、實際 diff、核心 invariant、權限、資料一致性與 rollback；預設執行少量高價值 targeted tests，不機械重跑 Codex 的全部 suite。

- 接受：更新同一份 Work review。
- 補正：`changes_requested / codex`。Work 先完成同風險層的整體 review，再一次列完 findings、最小修正與必要
  regression，避免逐條回送。
- Codex 只處理 blocker；後續 review 只查 correction diff 與受影響的相鄰 invariant，不重做任務或重跑無關 matrix。
  只有 correction 引入新風險時才新增 finding。

Correction 預算：低風險最多一輪，中風險最多兩輪；runtime 同一 blocker 只允許一次唯讀 layer split 與一次 source correction。再次出現即標記 inconclusive／quarantine，另列低優先 follow-up，不得靠新增 retry、reason code 或 task 無限延長。超過兩個 correction PR、90 分鐘 active elapsed 或兩次相同 runtime variation 時，Main 必須重新判斷阻塞者是產品還是驗收工具。

### E. Final integration

到 delivery unit 完整時，由 Work 建立唯一 ready PR。Required CI 通過且無 blocker 後，依一般 Git 長期授權 squash
merge。純 handoff、run ID、時間戳或 merge metadata 不另建 commit／PR。

## 7. HANDOFF

`HANDOFF.yaml` 是現在輪到誰的唯一真實來源。

跨 session handoff 只傳 base/head、changed files、behavior delta、exact test results、remaining limits 與 next
actor/action。背景規則引用 authoritative path 與 section，不重貼全文；尚未進入權威文件的安全關鍵資訊仍須明列，
不得為求短而省略。

`next_actor` 使用 `owner`、`main-work`、`domain-work`、`codex-writer`、`advisor`；domain/session 另以 `actor_id`、scope、
owned paths、write、report target 與 stop conditions 綁定。Archive 的舊 `work`／`codex` 名稱不授權新工作。常用狀態：

- `planning`
- `ready_for_codex`
- `in_progress`
- `ready_for_review`
- `changes_requested`
- `awaiting_owner_approval`
- `completed`
- `blocked`

`next_actor` 不是自己的角色時，不修改任務檔案；先說明應由誰處理。純角色交棒不單獨 commit，併入下一個有
實質內容的 commit。沒有 active task 時使用 `active_task: null`、`status: completed`、`next_actor: owner`。

## 8. Git 與 GitHub 授權

Owner 已長期授權 Work／Codex在 task 範圍內自行建立 branch、commit、push、PR、查驗 CI、標記 ready、修正、
squash merge、同步 `main` 與清理 task branch。此授權跨 session 有效，不需每次重問。

前提：實際 diff 已驗收、required CI 成功、沒有 blocker 或範圍擴張。不得直接 commit／push default branch；commit
前必須確認目前 branch。Commit／PR 標題使用 `<type>(<scope>): <outcome>`，TASK 編號放 body/footer，不使用
「update files」「handoff TASK」等無法脫離上下文理解的標題。

上述授權不包含 production、Secret、IAM、Scheduler、通知或重大產品／架構變更。

### Staging fictional autonomy 與操作責任

Owner 已授權 Main Work 在已隔離、已核准 identity 與成本上限的 staging fictional environment 內，持續完成
build、candidate revision、health check、traffic promotion／rollback、fictional seed／repair／test mutation、Emulator／ADB
驗收及 task-specific cleanup。這些動作必須沿用既有 Secret reference、runtime identity、public boundary 與 fail-closed
operator；不得因 staging 授權推論 production、真實通知、Secret payload、額外付費資源或不可逆刪除也獲授權。

每個 runtime 指令或跨 session 派工應明列：

```text
operator=agent | owner
owner_gate=none | <exact sensitive action>
standing_authorization=<applicable decision/task>
stop_only_on=<remaining stop conditions>
report_to=main-work
```

- `operator=agent` 是一般預設。Agent 可自行完成 fictional UI 導覽、唯讀點擊、App 啟停、cold start、offline、截圖、
  低敏 staging mutation／reconcile／restore及可復原 rollback，不得為儀式性確認停給 Owner。
- `operator=owner` 只用於輸入帳密、掃碼、登入／consent、Secret payload、付費／公開權限、release signing／store、
  production、真實通知與不可逆刪除等人類保留動作。交回時必須說明唯一動作、原因與完成後的安全回報文字。
- Domain Work 收到派工後立即回 `received/executing`；執行超過一個可見工作段落時主動 heartbeat。完成、阻塞或需要
  Owner 動作時必須主動敲 Main Work，不可只停在自己的 session 等待。
- Main Work 可撤銷不必要的 Owner gate；撤銷時須縮限 exact action、次數、資料分類與停止條件。外部結果不確定時，
  仍先唯讀 reconcile，不以 autonomy 作為盲目重送理由。

## 9. CI 與測試成本

依實際變更選最小充分測試：

| 變更 | Required evidence |
| --- | --- |
| 一般純文件 | 快速文件 gate；不跑 PostgreSQL／應用 suites |
| 單一服務 | 該服務受影響 suite |
| shared library | 所有直接 callers |
| schema／migration／model／受控 SQL／DB verifier | PostgreSQL 15／16 matrix 與 portal-data gates |
| auth／authorization／webhook signature／deployment tooling／workflow | 對應完整安全 suite |

驗收分三級：

- L1 小型 UI／presentation：Main review、focused tests、format/analyze、hosted full；不要求 Domain、local full 或 runtime。
- L2 state／auth／cache／offline／idempotency：writer affected-full、named Domain targeted review、Main risk review、hosted CI；runtime 僅在 task 明列時使用一個原子 smoke，不使用完整 acceptance orchestration。
- L3 API／schema／deploy／Secret／production：architecture/security review、受影響 full matrix、hosted CI、exact target／artifact、Owner gate 與 post-check／rollback。

證據採分層產生：L2／L3 Codex writer 跑 affected complete suite；L1 writer 跑 focused tests 與 analyze，由 hosted CI 提供唯一 full suite。Domain reviewer 只跑 task 明列之專屬風險的 targeted tests；Main Work抽查關鍵 regression 與整合邊界；hosted CI 作 final gate。相關 diff 未變時，不同角色不得無理由重跑 PostgreSQL matrix、Flutter build／Emulator 或同一 suite；重跑時必須記錄新增風險或證據需求。

Evidence reuse key 至少包含 exact full HEAD、exact command／suite、runtime／database matrix 與直接相關 artifact
fingerprint。只有相關 diff、dependency 與 environment contract 均未變才可沿用。相同 SHA 因 runner、network 或
platform infrastructure transient failure 的重試不算新的產品驗證輪，但須記錄 infra 原因；source、config、lockfile
或 artifact 改變時只重置受影響的 budget slice。

只有本機無法取得必要平台證據時，才提前建立 Draft PR。Final PR head 未再變更且 required CI 成功時，不為補 run
ID 或 merge 時間再觸發 CI。

## 10. Production 流程

Merge 不等於部署或資料操作。Production 固定分為：

1. 唯讀 discovery／inventory。
2. 將精確 target、count、commit／digest、影響與 rollback 交給 Owner。
3. Owner 明確批准。
4. 單次 mutation／deployment。
5. 立即 post-check。

輸出不確定、網路中斷或工具被取消時，不得直接重跑 mutation；先查外部狀態或使用獨立唯讀 recovery diagnostic。
批准鎖定 material artifact／target，不因純 coordination commit 失效；artifact、checksum、validator、runbook順序或安全
邊界改變時必須重新驗收與批准。

## 11. 文件生命週期

- 同一 TASK 原則上只有一份 task、一份 report、一份 review。
- L1 delivery 可使用 task、PR evidence 與 HANDOFF 完成；沒有新外部證據或 review finding 時，不強制另建 report／review。
- Task 只放需求、scope、invariants、acceptance；report 只記相對 task 的完成 delta 與新證據；review 只記 findings、
  判定與未完成事項；HANDOFF 只放狀態、SHA、下一步與真正 blocker。同一內容不得在這些文件平行維護。
- 多輪修正更新原檔，不建立 completion／correction／recovery review 變體；不同 production operation 確有獨立安全
  邊界時才例外。
- `PROJECT_STATE.md` 只寫現在式，不累積逐任務流水帳。
- `DECISIONS.md` 只放仍有效的規範；完整歷史移入 archive。
- 階段完成後，task／report／review 移入 `archive/<phase>/`，以一份 closeout 作入口。
- 純 coordination 文件預設併入 delivery PR；只有必須立即生效的安全、授權或操作邊界才可獨立文件 PR。
- Merge 後到下一個實質 coordination update 前，Git／PR merge SHA 可作短期 completed 事實來源；不得為只補 run ID、
  merge時間或 singleton狀態另開PR。下一個實質 delivery 必須先收斂過期 PROJECT_STATE／HANDOFF。
- `AGENTS.md` 與本文件由 Work 維護；Codex 只有 active task 明確要求時才修改全域規範。

### 文件預算

- `COLLABORATION.md` 目標不超過 350 行；新規則優先改寫既有章節，禁止只在尾端持續追加版本。
- `PROJECT_STATE.md` 目標不超過 200 行，只寫現在式；新增狀態時同步移除或封存過期內容。
- `DECISIONS.md` 不設 active decision 數量上限；由 Work 依重複、衝突、可讀性與生命週期適時整併，被取代或只剩
  歷史價值的內容移入 history。
- `tasks/`、`reports/`、`reviews/` 只保留 active delivery group 與尚未封存工作；完成一個 Phase 或累積約 10 個
  tasks 時，由 Work 執行一次封存。
- Final PR 前，Work 檢查上述預算、重複 report／review、過期 HANDOFF 與 archive 誤讀風險。超標先整理，不把
  新一輪膨脹合併進 `main`。
- 文件預算是維護警戒線，不是強迫刪除必要安全資訊的硬上限。若 agent 判斷無法在預算內完整表達需求、決策、
  風險或操作邊界，必須停止擴寫並向 Owner 說明：超標原因、不可刪內容及建議拆分／封存方式；不得自行犧牲必要
  資訊，也不得默默突破預算。

### 決策生命週期

1. 只有會跨 task 規範未來產品、架構、授權或安全行為的 Owner 決定，才建立 DEC。單次 task 核准、PR、CI、部署
   或操作結果留在 task／review／closeout／operations evidence，不為每次同意建立 DEC。
2. 新 DEC 使用唯一連續的 `DEC-xxx` 編號，直接加入現行 `DECISIONS.md`，標記狀態、生效日、來源與
   `supersedes`；不得先只寫入 archive，再期待 agent 推論目前效力。
3. 只有文字澄清、引用補充或不改語意的維護，更新原 active DEC 並記錄修訂日期，不建立新編號。
4. 產品規則、授權或安全語意實質改變時，建立新 DEC；新項列出 `supersedes`，舊項原文移入 append-only history。
5. 多項 active decisions 開始重複或分散描述同一政策時，由 Work 建立一項新的整併 DEC，明列所有被取代編號，
   再封存舊項；不得只刪除或悄悄改變語意。
6. 已完成且只剩歷史價值，或已由 phase closeout／`PROJECT_STATE.md`完整承接的決策，移入 history；編號永不
   重用或重編。
7. 封存與整併以 phase closeout、重大階段開始前、發現重複／衝突或閱讀困難時批次進行；不設數量門檻，也不必
   每新增一項就建立 archive commit。
8. Archive 原文不回寫成今天的規則；現行 register 是唯一可直接規範未來行為的 decision source。

## 12. 衝突與停止條件

衝突優先序：

1. Owner 最新明確指示。
2. Active task 中有理由、範圍與結束條件的安全例外。
3. `HANDOFF.yaml` 當前狀態。
4. 現行 `DECISIONS.md`、本文件與 `AGENTS.md`。
5. 歷史 decision／task／report／review。

遇到下列情況必須停止並交回 Owner：未批准的 production mutation、Secret payload、真實通知、不可逆資料操作、重大
架構／產品規則改變、目標不明的 destructive action、無法判定的外部 mutation 結果，或安全邊界必須被放寬才能繼續。

## 13. Session 交接

新 session 不依賴舊對話。結束前確保 `PROJECT_STATE.md`、`DECISIONS.md` 與 `HANDOFF.yaml` 足以回答：系統現在
如何運作、什麼尚未完成、輪到誰、下一步需要哪個決策。若沒有 active task，不要預先建立大量 task；先與 Owner
選定下一個 delivery group。

新任務優先使用乾淨 session，只讀 active task、HANDOFF、PROJECT_STATE、active decisions 與直接相關 code/tests；
archive 按需讀。厚重 session 留作歷史顧問，不承擔日常實作或完整驗收；inactive agent 不反覆喚醒。Main Work
維護唯一全域協調與 singleton HANDOFF，Domain Work 只回報自己的 lane delta。
