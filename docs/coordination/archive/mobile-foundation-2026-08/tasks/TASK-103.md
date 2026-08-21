# TASK-103 — Attendance insights and Person overview

## 目標

改善 Dashboard／Attendance 的等待體驗與查詢形狀，並在 schema 0004 不變的前提下交付 Person 統整頁、球員回覆洞察及幹部單場出席報告。

## 範圍

- Attendance 以批次 read model 取代逐場、逐人查詢；同一 request 重用 fresh principal。
- Dashboard 天氣改為同源延後載入，主頁不等待外部天氣服務；站內導頁顯示可存取的 loading 狀態。
- `/manage/people/<id>` 提供基本資料、校友會成員、參與資格、參賽紀錄四個 tabs。
- 幹部與管理員可查看球員回覆區段及單場高頻回覆但尚未回覆清單；一般使用者不得進入。

## Invariants

- 不修改 schema、migration、Game、Roster 或 Attendance 資料。
- 洞察只描述最多 120 場可觀測邀請賽事；高頻待回覆採前 12 場、至少 3 場且回覆率 60% 的透明門檻。
- 天氣 endpoint 僅接受 signed active session、同源請求與目前已邀請且位於既定天氣視窗的賽事。
- 無部署、Secret、IAM、Scheduler、通知或正式資料異動。

## 驗證

- Web Portal full offline suite、portal-data offline suite。
- Python compile、JavaScript syntax、Black/isort、diff check。
- localhost desktop／390px 角色與視覺 QA；若本機資料環境不可用，交由 final PR acceptance 補證。
