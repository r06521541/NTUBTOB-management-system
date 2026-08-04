\# Work–Codex 協作流程



版本：1.0

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
