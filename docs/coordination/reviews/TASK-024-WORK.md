# TASK-024 Work Review

驗收日期：2026-08-05
驗收者：Work
結論：`accepted`（第二輪）

## 驗收範圍

- Branch：`main`
- Task base：`8ee73f660aad8edf7145a8510ebd7cb923c01227`
- Implementation：`1572d1bbeed14204f4245a722c2b82698a2d7ecd`
- Report head：`3f63edd`
- 驗收前working tree：clean

## 已接受部分

- Demo雙重gate、登入保護與既有LINE routes沒有退化。
- 新增Dashboard營運摘要、公告、人力卡、Game Day、建議打序、checklist、裝備／ride互動、幹部prototype與`.ics`下載。
- 進階出席回覆具CSRF、status／arrival／position allowlist及note長度限制。
- 主要可變狀態使用JSON-compatible session primitives，沒有修改production routes、`app.py`、shared_lib、schema或deployment。
- `.ics`具Asia/Taipei、CRLF、escaping helper與下載headers；沒有Calendar API。
- 所有資料明顯虛構，未見外部服務或DB呼叫。

## Blocking補正

### 1. Game Day狀態必須依賽事隔離

目前`demo_operations`只有全域`ride`與`claimed_gear`；在`demo-game-01`選擇共乘或認領裝備後，開啟其他賽事會顯示相同選擇。請改為以`game_id`分區的JSON-compatible session state，並新增兩場賽事互不污染的測試。Checklist目前已有game-prefixed key，可一併整理為一致結構。

### 2. 完成任務明訂的交通產品流程

目前只能在兩個既有ride卡片間切換，未提供「自行前往／需要接送／可提供座位」、虛構集合點與提供座位數。請建立allowlist validation、PRG route、session-only state與成功／畸形輸入／CSRF tests。不得收集真實電話、地址或位置。

### 3. 通知偏好必須能在session切換

個人頁目前只有沒有`name`、form或route的靜態checkbox，不符合TASK-024。請實作三種通知偏好的session-local POST、CSRF、allowlist及reset，畫面持續明示不會發送通知，並測試未知key／錯誤CSRF不改state。

### 4. 補齊賽程月曆／主客場篩選

目前只有status filter，沒有月曆／時間軸切換，也沒有主場／客場filter。請完成最小可用的month/timeline視圖與`all／home／away`篩選；query values必須allowlist。可採server-rendered卡片式月曆，不需JavaScript。

### 5. 補齊出席規格

目前arrival只有準時／晚到／早退，沒有「僅觀賽」；也沒有可選的預計抵達時間。請以明確allowlist時間選項完成，保存後表單要反映既有選擇，並測試invalid status時必須在提供有效CSRF的情況下仍被拒絕。不得用單純缺CSRF測試取代欄位validation證據。

### 6. Dashboard待辦必須由session狀態導出

目前Dashboard只有待回覆數，未顯示「尚未選交通／尚未認領裝備」等我的待辦，也不會隨Game Day操作更新。請建立可測試helper與跨頁流程測試，證明回覆、交通與裝備操作後Dashboard待辦同步變化。

## 驗證證據

Work使用bundled Python 3.12.13實際執行：

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 30 tests: OK (skipped=2)

python -m compileall -q apps/web_portal
passed

git diff --check
passed
```

兩項skip為既有Windows環境缺`make`／`sh`的deployment executable coverage。本機Python 3.10 launcher仍失效，沒有本輪Python 3.10證據。

Work嘗試啟動development demo進行瀏覽器視覺驗收，但in-app browser runtime因本機kernel assets路徑錯誤無法連線；因此尚未驗證375×812或desktop實際畫面，不宣稱視覺通過。

## 回歸風險

- 目前測試通過，但部分測試只證明route可回200，未覆蓋任務要求的完整產品狀態轉換。
- `demo_operations`跨賽事共用會造成明顯錯誤展示。
- 靜態通知checkbox容易讓使用者誤以為設定已保存。
- 未執行瀏覽器視覺驗收，四欄bottom nav與新增內容仍可能在小尺寸裝置出現可用性問題。

## 安全確認

- 未部署、push、建立PR。
- 未讀取或修改Secret／IAM／Cloud Run。
- 未連production DB、未呼叫正式LINE或其他外部服務、未發通知。
- TASK-023 deployment blocker仍存在且未被本任務繞過。

## 下一步

第一輪已交回Codex補正；第二輪結果如下。

## 第二輪驗收

- 補正implementation：`637d9b9`
- Report head：`109ebf6`
- Game Day state已改為依`game_id`隔離，測試證明兩場賽事互不污染。
- 交通流程已涵蓋自行前往、需要接送、提供1–4席、虛構集合點及欄位組合validation。
- 三類通知偏好已具session-only POST、CSRF、allowlist與reset。
- 賽程已具timeline／month view與home／away filters，query values均allowlist。
- 出席已具僅觀賽、ETA、表單回填，invalid status在有效CSRF下仍拒絕。
- Dashboard待辦由session-derived helper產生，回覆、交通及裝備跨頁操作後會同步更新。

Work重跑Web Portal 33項tests全部通過，2項既有Windows `make`／`sh`相依測試skip；compileall與`git diff --check`通過，working tree於驗收開始時clean。

驗收結論為`accepted`。尚未完成瀏覽器實際視覺驗收與Python 3.10本機／CI實跑；這兩項列為Owner接受前的已知限制，不阻擋離線prototype程式驗收。
