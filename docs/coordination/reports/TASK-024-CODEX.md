# TASK-024 Codex Report

狀態：`ready_for_review`
執行者：Codex
task 起始 commit：`8ee73f660aad8edf7145a8510ebd7cb923c01227`
初版實作 commit：`1572d1b`
補正實作 commit：`637d9b9`

## Work review 補正

- `demo_operations.games[game_id]` 現在分別保存交通、裝備與 checklist；跨兩場測試證明狀態不互相污染。
- 交通流程涵蓋自行前往、需要接送及可提供 1–4 席，僅接受兩個虛構集合點；各模式的欄位組合、CSRF 與畸形輸入均 fail closed。
- 三類通知偏好可透過 POST 切換並保存於 session，未知 key／值及錯誤 CSRF 不改狀態，reset 回復預設。
- 賽程新增 server-rendered 時間軸／月曆及 all／home／away 篩選，所有 query value 具 allowlist。
- 出席新增僅觀賽與預計抵達時間，所有欄位保存後回填；invalid status 以有效 CSRF 測試拒絕。
- Dashboard 的回覆、交通與裝備待辦由 session helper 導出，跨賽事頁、Game Day 與 Dashboard 的完整操作測試證明同步更新。

## 完成內容

- Dashboard 新增回覆截止、人力與守位缺口、公告及 Game Day 快速入口。
- 賽程新增出席狀態篩選與空狀態；賽事詳情新增準時／晚到／早退、守位偏好及 80 字備註。
- 新增單場 `.ics` 匯出，使用 Asia/Taipei、CRLF、內容 escaping 及下載 headers，不呼叫 Calendar API。
- 新增 Game Day 中心：集合資訊、建議打序、守位、賽前檢查、裝備認領及共乘選擇。
- 新增個人球季摘要、Demo reset，以及唯讀幹部工作台（人力／核可／裝備缺口及通知預覽）。
- 所有可變狀態只保存為 Flask session 中的 JSON-compatible primitive data；POST 具 demo 專用 CSRF，game／status／arrival／position／item ID 皆以 allowlist 驗證。
- 新頁面沿用既有 Flask/Jinja 與本地 CSS，mobile bottom navigation 擴為四欄；未引入 framework 或新 dependency。

## 驗證

工作區隔離 runtime 為 Python 3.12.13；本機 `python` 不在 PATH，`py -3.10` 指向失效的 Windows Store 安裝，因此仍無本機 Python 3.10 實跑證據。

```text
python-runtime -m unittest discover -s apps/web_portal/tests -v
33 tests: OK，2 skipped（本機缺 make/sh，既有 deployment executable coverage）

python-runtime -m compileall -q apps/web_portal
passed

git diff --check
passed
```

新增測試涵蓋 demo gate、主要頁面、狀態篩選、完整回覆 allowlist、CSRF、`.ics` headers／timezone／CRLF、未知賽事、Game Day session 操作、reset、無 model／HTTP 呼叫及 responsive CSS contract。既有 LINE route、admin security 與 deployment contract tests 亦通過。

## Prototype 與風險

- 打序、守位、人力警示、共乘、裝備、通知預覽、核可數字與球季統計皆為虛構產品原型，不寫 DB、不跨裝置同步。
- 共乘導航刻意 disabled；未呼叫 maps、LINE、weather、calendar、DB 或其他外部服務。
- 未進行瀏覽器視覺實測；375px 由既有 viewport、無固定最小寬度、四欄 bottom nav 及單欄 media contracts 驗證，仍待 Work／Owner 主觀瀏覽。
- 沒有修改 `app.py`、production routes、shared_lib、schema、deployment、Secret、IAM 或其他服務；沒有 deploy、push 或 PR。
- TASK-023 的 production Secret blockers 不受本任務影響，這個 demo commit 不應據此部署。

## 變更檔案

- `apps/web_portal/README.md`
- `apps/web_portal/demo_data.py`
- `apps/web_portal/demo_portal.py`
- `apps/web_portal/static/operations.css`
- `apps/web_portal/templates/demo/base.html`
- `apps/web_portal/templates/demo/dashboard.html`
- `apps/web_portal/templates/demo/game_detail.html`
- `apps/web_portal/templates/demo/games.html`
- `apps/web_portal/templates/demo/profile.html`
- `apps/web_portal/templates/demo/game_day.html`
- `apps/web_portal/templates/demo/officer.html`
- `apps/web_portal/tests/test_demo_portal.py`
- `docs/coordination/reports/TASK-024-CODEX.md`
- `docs/coordination/HANDOFF.yaml`

本任務開始時工作樹乾淨；無既有未提交變更混入。
