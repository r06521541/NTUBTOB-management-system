\# Work–Codex 協作流程



版本：1.3

制定者：專案負責人

適用範圍：本 repository 內所有由 ChatGPT Work 與 Codex 參與的規劃、實作、審查與交接工作



\---



\## 一、目的



本流程用於確保專案負責人、Work 與 Codex 對以下事項維持一致理解：



\* 專案目前狀態

\* 當前工作目標

\* 已確認的產品與技術決策

\* Codex 實際完成的修改

\* 測試與驗收結果

\* 下一位應接手工作的角色



Work 與 Codex 不依賴彼此的對話歷史進行同步。



所有重要需求、決策、進度、實作結果與驗收結論，皆應保存於 repository、Git 與本流程指定的協作文件中。



\---



\## 二、角色與權責



\### 1. 專案負責人 Owner



專案負責人擁有最終決策權，負責：



\* 決定產品方向與優先順序

\* 解釋實際球隊與校友會運作規則

\* 批准重大架構變更

\* 批准資料庫不可逆操作

\* 批准正式部署

\* 批准真實 LINE 通知或廣播

\* 決定是否接受、合併或退回 Codex 成果



Work 與 Codex 不得取代專案負責人做出上述決定。



\### 2. Work



Work 擔任專案總控、產品顧問、系統分析師與技術驗收者，負責：



\* 與專案負責人討論需求與策略

\* 直接查閱 repository、Git 與專案文件

\* 區分已確認事實、合理推論與待確認假設

\* 將需求整理為可交付 Codex 的任務規格

\* 維護專案狀態與正式決策文件

\* 在 Codex 完成工作後，檢查實際 diff、commit 與測試

\* 提出接受、退回或補正建議



Work 原則上不負責主要程式實作，也不得與 Codex 同時修改相同的程式檔案。



\### 3. Codex



Codex 擔任實作與測試者，負責：



\* 閱讀任務規格與相關程式碼

\* 提出實作方案與風險

\* 修改程式碼、測試、migration 與必要設定

\* 執行指定的 build、test、lint 與檢查

\* 將工作結果留下可驗證的 diff 或 commit

\* 撰寫 Codex 任務報告

\* 根據 Work 的驗收意見進行修正



Codex不得自行改變產品需求、擴張任務範圍或決定重大架構方向。



\---



\## 三、共同真實來源



Work 與 Codex 必須以以下內容作為共同真實來源：



1\. repository 當前內容

2\. Git branch、commit、status 與 diff

3\. `AGENTS.md`

4\. 本文件 `docs/coordination/COLLABORATION.md`

5\. 當前任務文件

6\. Codex 實作報告

7\. Work 驗收報告

8\. `docs/coordination/HANDOFF.yaml`



任何只存在於 Work 或 Codex 對話、但未寫入 repository 的重要資訊，不視為已完成正式交接。



\---



\## 四、協作文件結構



```text

docs/coordination/

├─ COLLABORATION.md

├─ HANDOFF.yaml

├─ PROJECT\_STATE.md

├─ DECISIONS.md

├─ tasks/

│  └─ TASK-xxx.md

├─ reports/

│  └─ TASK-xxx-CODEX.md

└─ reviews/

&#x20;  └─ TASK-xxx-WORK.md

```



各文件用途如下：



\### `COLLABORATION.md`



本協作流程。Work 與 Codex 每次開始新任務或新 session 時，都必須先閱讀。



\### `HANDOFF.yaml`



目前接力狀態的唯一真實來源，用於說明：



\* 當前任務

\* 任務狀態

\* 下一位負責角色

\* 任務開始與目前 commit

\* 最後更新者及時間



\### `PROJECT\_STATE.md`



由 Work 維護，記錄整體專案狀態、已完成工作、進行中工作、主要風險與下一步。



\### `DECISIONS.md`



記錄經專案負責人確認的重要產品或技術決策。



\### `tasks/TASK-xxx.md`



由 Work 根據與專案負責人的討論建立，定義任務目標、範圍、非目標、驗收條件、測試需求及安全限制。



\### `reports/TASK-xxx-CODEX.md`



由 Codex 維護，記錄實際修改、測試、commit、假設、風險與未完成事項。



\### `reviews/TASK-xxx-WORK.md`



由 Work 維護，記錄驗收結果、阻擋問題、必要修改及接受建議。



\---



\## 五、HANDOFF 接力規則



`docs/coordination/HANDOFF.yaml` 是「現在輪到誰」的唯一真實來源。



建議格式：



```yaml

active\_task: TASK-001

status: ready\_for\_codex

next\_actor: codex



base\_commit: abc1234

head\_commit: null



updated\_by: work

updated\_at: 2026-08-04T01:18:00+08:00



note: >

&#x20; 任務規格已完成，等待 Codex 接手。

```



`next\_actor` 可使用以下值：



\* `work`

\* `codex`

\* `owner`



主要狀態包括：



\* `planning`

\* `awaiting\_owner\_decision`

\* `ready\_for\_codex`

\* `in\_progress`

\* `ready\_for\_review`

\* `changes\_requested`

\* `awaiting\_owner\_approval`

\* `completed`

\* `blocked`



Work 與 Codex只有在 `next\_actor` 符合自身角色時，才能修改任務相關內容。



如果不是自己的回合，應停止工作並回報目前應由哪位角色接手。



\---



\## 六、標準工作流程



\### 階段一：需求討論與任務建立



1\. 專案負責人向 Work 提出需求、問題或目標。

2\. Work 查看 repository 現況，確認需求是否與現有系統一致。

3\. Work 與專案負責人釐清產品規則、範圍及取捨。

4\. 重要決策經專案負責人確認後，寫入 `DECISIONS.md`。

5\. Work 建立 `tasks/TASK-xxx.md`。

6\. Work 更新 `HANDOFF.yaml`：



```yaml

status: ready\_for\_codex

next\_actor: codex

```



\### 階段二：Codex 接手實作



1\. Codex 先閱讀：



&#x20;  \* `AGENTS.md`

&#x20;  \* `COLLABORATION.md`

&#x20;  \* `HANDOFF.yaml`

&#x20;  \* 當前任務文件

&#x20;  \* 相關決策與專案狀態

2\. Codex確認：



&#x20;  \* `next\_actor` 是 `codex`

&#x20;  \* `base\_commit` 與目前 repository 相符

&#x20;  \* 工作目錄狀態可安全開始

3\. Codex 執行任務，不得自行擴張範圍。

4\. Codex 執行指定測試。

5\. Codex 將結果寫入 `reports/TASK-xxx-CODEX.md`。

6\. Codex留下可驗證的 diff 或 commit。

7\. Codex 更新 `HANDOFF.yaml`：



```yaml

status: ready\_for\_review

next\_actor: work

```



\### 階段三：Work 驗收



1\. Work 讀取 `HANDOFF.yaml` 與 Codex report。

2\. Work 檢查實際：



&#x20;  \* branch

&#x20;  \* HEAD

&#x20;  \* `git status`

&#x20;  \* `git diff`

&#x20;  \* commit

&#x20;  \* 測試結果

3\. Work 不得只根據 Codex 的文字摘要判斷是否完成。

4\. Work 將驗收結果寫入 `reviews/TASK-xxx-WORK.md`。



若未通過：



```yaml

status: changes\_requested

next\_actor: codex

```



若通過：



```yaml

status: awaiting\_owner\_approval

next\_actor: owner

```



\### 階段四：專案負責人裁決



專案負責人根據 Work 的驗收結果決定：



\* 接受並結案

\* 要求補充驗證

\* 要求 Codex 修正

\* 暫緩合併

\* 批准或拒絕部署



正式結案後：



```yaml

status: completed

next\_actor: owner

```



Work同步更新 `PROJECT\_STATE.md`。



\---



\## 七、任務規格最低要求



每份 `TASK-xxx.md` 至少必須包含：



\* 任務目標

\* 背景與現況

\* 工作範圍

\* 明確非目標

\* 驗收條件

\* 必要測試

\* 安全限制

\* 相關檔案或模組

\* 已知風險

\* 需要專案負責人決策的事項

\* `base\_commit`



需求仍存在重大歧義時，不應直接進入 Codex 實作階段。



\---



\## 八、Codex 報告最低要求



每份 `TASK-xxx-CODEX.md` 至少必須包含：



\* 任務狀態

\* base commit

\* head commit

\* 實際修改內容

\* 修改檔案清單

\* 執行過的命令

\* 測試項目及結果

\* 未執行或無法執行的測試

\* 仍存在的假設

\* 風險與阻礙

\* 是否有未提交修改

\* 是否涉及 migration、環境變數或部署設定

\* 是否需要專案負責人決策



\---



\## 九、Work 驗收最低要求



每份 `TASK-xxx-WORK.md` 至少必須包含：



\* 驗收的 branch 與 commit

\* repository 是否乾淨

\* 驗收條件逐項結果

\* 測試證據

\* 回歸風險

\* Blocking 問題

\* 非阻擋建議

\* 驗收結論：



&#x20; \* `accepted`

&#x20; \* `changes\_requested`

&#x20; \* `blocked`

\* 下一位角色



\---



\## 十、安全限制



除非專案負責人明確批准，Work 與 Codex 均不得：



\* 部署至 production

\* 發送真實 LINE broadcast 或大量通知

\* 顯示、複製或提交 Secret

\* 修改正式 Secret Manager 值

\* 刪除正式資料

\* 執行不可逆 migration

\* 強制推送 Git 歷史

\* 合併至正式分支

\* 進行任務規格外的大型重構



發現憑證、個資、安全漏洞或正式環境風險時，應立即停止相關操作並回報。



\---



\## 十一、同時工作限制



Work 與 Codex 原則上採取輪流接手，不得同時修改相同檔案。



如果 Codex正在修改程式：



\* Work 可以閱讀與討論。

\* Work 不應同時修改相同程式檔。

\* Work 應等待 Codex 進入 `ready\_for\_review` 後再正式驗收。



未來需要平行工作時，必須使用獨立 branch 或 Git worktree，並明確指定檔案與責任範圍。



\---



\## 十二、每個新 session 的必要開場



任何新的 Work 或 Codex session 在開始工作前，都必須先閱讀：



1\. `AGENTS.md`

2\. `docs/coordination/COLLABORATION.md`

3\. `docs/coordination/HANDOFF.yaml`

4\. 當前任務相關文件



未完成上述閱讀，不得開始修改 repository。



\---



\## 十三、核心原則



本專案採用以下原則：



> 對話用來討論，repository 用來同步，Git 用來證明，HANDOFF 用來交棒，專案負責人負責最終決策。



\---



\## 十四、Draft PR 一次授權流程



為減少 Owner 在 commit、push、建立 PR、查看 CI 與補驗收證據之間反覆交接，本專案採用以下標準流程。



\### 1. PR 工作包授權



Owner 可在批准任務時，一次授權該任務的「PR 工作包」。授權內容限於：



\* 建立或切換該任務的 branch

\* 建立任務範圍內的 commit

\* push 該任務 branch

\* 建立或更新 Draft PR

\* 唯讀監看與查驗 CI、PR checks 及 job logs

\* 依查驗結果更新 Codex report、Work review、`PROJECT_STATE.md` 與 `HANDOFF.yaml`

\* 將上述驗收文件 commit 並 push 到同一個 Draft PR



Owner 的授權必須記錄在任務文件或 `DECISIONS.md`。沒有明確記錄時，仍視為未授權 commit、push 或建立 PR。



\### 2. 標準執行順序



1\. Work 完成任務規格，Owner 同時批准任務與 PR 工作包。

2\. Codex 依任務規格實作、測試、commit、push，並建立或更新 Draft PR。

3\. Codex 將 report 與 handoff 更新為 `ready_for_review / work`。

4\. Work 查驗實際 diff、commit、PR、CI、Python/runtime 版本與測試 log。

5\. 若需修正，Work 交回 `changes_requested / codex`，Codex 在同一個 Draft PR 補正。

6\. 若通過，Work 將 review 與證據更新 commit/push 到同一個 Draft PR，等待最終 CI 成功。

7\. Work 更新 handoff 為 `awaiting_owner_approval / owner`，Owner 最後決定是否 merge。

8\. merge 後由 Work 做唯讀確認；若沒有新事實需要補寫，不再建立純 closeout PR。



\### 3. 永遠不包含於 PR 工作包的授權



即使 Owner 已批准 PR 工作包，仍不得自行執行：



\* merge PR 或直接寫入受保護/default branch

\* production deployment、release 或 package publish

\* 建立、讀取、顯示、修改、輪替或刪除 Secret

\* 修改 GitHub repository/organization Actions settings、branch protection、environment 或 credentials

\* 正式 LINE/Discord 通知、broadcast 或其他對真實使用者的外部副作用

\* 正式資料刪除、不可逆 migration 或其他不可逆資料操作

\* Owner 未批准的重大架構變更或任務範圍擴張



上述操作仍須 Owner 逐項明確批准。PR 工作包授權可由 Owner 隨時撤回；發現 secret、資料安全、權限退化或重大非預期 diff 時，Work 與 Codex 必須停止並交回 Owner。



\---



\## 十五、Commit 與 PR 標題規範



Commit 與 PR 標題必須讓未閱讀 TASK 文件的人也能理解實際變更，不得以流程編號取代行為描述。



\### 1. 標題格式



優先使用：



```text

<type>(<scope>): <outcome>

```



scope 不需要時可省略為 `<type>: <outcome>`。建議使用既有 repository 語言，以簡潔英文描述可觀察的行為或結果。



常用 type：



\* `feat`：新增使用者功能

\* `fix`：修正錯誤行為

\* `security`：強化安全邊界

\* `test`：新增或改善測試保護

\* `ci`：修改自動化驗證

\* `docs`：修改文件或正式紀錄

\* `refactor`：不改行為的結構調整

\* `chore`：必要但不屬於上述類型的維護工作



\### 2. 標題內容要求



\* 使用具體 scope，例如 `notify-cron`、`web-portal`、`coordination` 或 `ci`。

\* 描述改變後的行為或成果，不只描述「做了更新」。

\* 建議控制在約 72 個字元，必要時將背景、測試與 TASK 編號放入 body。

\* 一個 commit 應只有一個主要目的；內容差異過大時拆分 commits。

\* PR title 同樣使用描述性 outcome；merge commit subject 優先沿用描述性的 PR title。



\### 3. TASK 編號使用方式



TASK 編號用於追溯，不得成為標題的主要內容。應放在 commit body/footer，例如：



```text

Refs TASK-003

```



允許：



```text

security(notify-cron): keep LINE credentials out of images
docs(coordination): record notify cron security review
ci(python): run notify cron deployment contracts

```



不允許：



```text

docs: hand off TASK-003
docs: update TASK-003
fix: task changes
chore: update files

```



建立 commit 前，作者與驗收者都應確認：只看標題是否能判斷受影響元件與主要結果。若不能，必須先改寫標題。


\---


\## 十六、任務 Commit 精簡規則


協作文件仍是正式證據，但不得因每次狀態更新或角色交棒而機械式建立新 commit。每個任務原則上控制為以下三類 commit：


1\. 功能 commit：包含實際程式、設定、測試與必要 CI 變更；若存在可獨立理解、可獨立回復的多項修改，可合理拆分。

2\. Codex 完工 commit：一次納入最終 Codex report、測試／CI 證據與 `ready_for_review / work` handoff。

3\. Work 驗收 commit：一次納入 Work review、`PROJECT_STATE.md` 與 `awaiting_owner_approval / owner` handoff。


執行原則：


\* Codex 應盡量等實作與當次 CI 證據完整後，再一次提交 report 與 handoff；不得只為補時間、改狀態文字或再次表示「已交棒」建立額外 commit。

\* Work 應將驗收結論、最終證據、專案狀態與 handoff 合併為一個驗收 commit。

\* `changes_requested` 後的實質修正可新增 commit；純文字往返應併入下一個有意義的實作或驗收 commit。

\* 不得為符合數量而把互不相關的功能硬塞進同一 commit；可理解性、可驗證性與可安全回復仍優先於 commit 數量。

\* Merge commit 由 GitHub 依 Owner 授權建立，標題沿用描述性的 PR title，不計入上述三類工作 commit。

\* Merge 後若只有 merge commit、時間與 PR 狀態等結案新事實，Work 做唯讀確認即可，不另開純 closeout PR。這些結案紀錄應在下一個任務的規劃 commit 中，與新 task、決策或專案狀態一起提交。

\* 若 merge 後發現安全事件、錯誤合併、重要風險或會影響下一步的重大新事實，不得延後；應立即交回 Owner，必要時另立修正或 closeout 任務。


此規則的目的，是保留可稽核的協作證據，同時避免 Git history 被無實質內容的流程 commit 淹沒。


### 正式歷史與 PR branch 精簡上限

為兼顧可追溯性與可讀性，協作證據應以「最終文件狀態、PR timeline 與 CI records」保存，不應把每次角色交棒都轉成獨立 Git commit。

1. `main`／default branch 原則上一個 TASK 只保留一個描述性 commit；任務 PR 優先使用 **Squash merge**。
2. PR branch 原則上維持兩個主要 commits，最多三個有意義 commits：
   - 實作 commit：程式、測試與必要產品／操作文件。
   - 驗收 commit：Codex report、Work review、`PROJECT_STATE.md`、`HANDOFF.yaml` 與最終驗證證據。
   - 只有確實可獨立理解、測試與回復的修正，才增加第三個 commit。
3. 任務規格若在前一任務結案後立即建立，應盡量與前一任務的必要結案文件合併為同一個規劃 commit；不得只為切換 TASK 編號建立 commit。
4. 下列內容不得單獨形成 commit，應併入下一個有實質內容的實作或驗收 commit：
   - `ready_for_codex`、`ready_for_review`、`awaiting_owner_approval` 等單純 handoff 狀態；
   - 單純更新時間戳、角色或「已閱讀／已交棒」文字；
   - Owner 對 push／PR 的授權紀錄；授權可先保留於對話與 PR timeline，並在下一次實質文件更新時一併寫回 repository；
   - 只有 CI run／job ID、PR ready 狀態或 merge 時間等外部證據，且結果未改變驗收結論時。
5. Codex 應在實作與本機驗證穩定後再提交，report 與 handoff 優先併入實作 commit；若實作 commit 已完成，才使用一次 completion commit，禁止逐次補狀態 commit。
6. Work 應將完整驗收結論、專案狀態與 handoff 合併為單一驗收 commit；Owner 批准 push／PR 後，不再為授權本身建立額外 commit。
7. PR CI 成功且沒有改變程式或驗收結論時，以 GitHub check／PR comment 作為證據，不必新增 Git commit。若 CI 失敗導致修正，修正與更新後證據應合併為一個具實質內容的 commit。
8. Squash merge 不會取消稽核能力：最終 TASK、report、review、decision、PR discussion 與 GitHub Actions records 共同構成完整證據；branch 上的細碎流程 commits 不需要進入 `main`。

例外情況包括安全事件、錯誤部署、資料風險、需要立即告知下一位角色的 blocking finding，或可獨立回復的緊急修正。此時可立即建立描述性 commit，不受上述數量目標限制，但必須在 commit body 說明例外原因。

---

## 十七、一般 Git 工作流程長期授權

Owner已授權Work與Codex在任務範圍內，於實際diff驗收、required CI成功且無blocking finding後，自行完成branch、
commit、push、PR、ready、squash merge、同步main及清理task branch，不需逐次請示。此授權不得用來擴張task範圍，
也不包含production deployment、production database migration／DDL／DML、不可逆資料操作、Secret／IAM／
Scheduler／cloud resource變更、真實LINE／Discord通知或重大架構／產品規則變更；上述事項仍需Owner另行明確批准。

### 跨 session 效力與 PR 角色

1. 本節及當前 task／decision 中記錄的 standing authorization，就是 Owner 的明確授權；它以 repository 作為
   跨 session 的持久交接，不要求 Owner 在每個 Codex 對話再次輸入相同批准。只有 Owner 後續撤回、task 明確
   排除，或 `HANDOFF.yaml` 顯示尚未授權時才停止。
2. Codex 原則上負責完成實作、測試、commit、push，並建立或更新同一 task branch 的 Draft PR；完成後更新
   report 與 handoff 為 `ready_for_review / work`。不得僅因「目前對話沒有重複授權文字」而停在 Draft PR 前。
3. Work 負責查驗實際 diff、commit、hosted CI 與 PR；有 blocking finding 時交回 Codex。驗收通過後由 Work 將
   PR 標記 ready，並在 required CI 成功後依長期授權 squash merge。若 Codex 無法建立 PR，Work 可代為建立，
   但這是 fallback，不是固定要求。
4. Standing authorization 只涵蓋 task 範圍內的一般 Git／GitHub 流程。Production database、deployment、Secret、
   IAM、Scheduler、通知及其他本節已排除的外部副作用，仍不得因 PR 權限而推定已獲批准。
