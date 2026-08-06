# TASK-043 Codex 完工摘要

更新時間：2026-08-06（Asia/Taipei）

## 任務狀態

- 狀態：`ready_for_review`
- Branch：`codex/deploy-task-040`
- Base commit：`6e6c8cf5ecf06245c510e7767c1e49be564728e8`
- 未 push、未建立 PR、未 merge、未部署。

## 完成內容

- 新增共用 `brand.css`，集中深藍、灰、暖金與 success／warning／danger／LINE 語意 tokens。
- Demo 延續既有 class 契約，以相容別名改為深藍主品牌；正式 auth／recovery 與會員頁共用相同 tokens。
- 保留 LINE 官方綠色；一般 CTA、導覽、選取與大面積品牌色改為深藍；紅色僅用於危險／錯誤／取消／拒絕語意。
- 公開首頁改用本機隊徽與品牌卡片，不再依賴遠端圖片完成主要呈現。
- 正式會員共用導覽新增「首頁」，account、attendance、roster 在窄螢幕仍可橫向操作。
- 新增靜態樣式載入／token／導覽契約測試，並補正式 route render 的首頁連結驗證。
- 更新 Web Portal README，記錄品牌色彩角色與本機視覺驗收方式。

## 驗證結果

```text
Python 3.9 local runtime (repository code separately checked with Python 3.10 AST grammar)
python -m unittest discover -s apps/web_portal/tests -v
Ran 93 tests - OK (skipped=2)

python -m compileall -q apps/web_portal
OK

Python 3.10 AST grammar check
19 Python files - OK

git diff --check
OK
```

兩項 skip 為既有 Windows 缺少 Unix `make`／`sh` 的 deployment contract coverage，與本次 UI 變更無關。

## 本機視覺驗收

- 雙重 gate Demo 以虛構資料啟動，沒有呼叫 production、DB、LINE 或其他外部 API。
- 375px 等效 viewport：dashboard 的 document／body 無水平 overflow，五個含幹部入口的 bottom navigation 均可見。
- desktop viewport：Dashboard 深藍／灰品牌、卡片、導覽與暖金 highlight 正常呈現，bottom navigation 依 breakpoint 隱藏。
- 正式 account／attendance／roster route render 由離線測試驗證；未以 production 身分或資料做瀏覽器驗收。

## 邊界與未驗證事項

- 未修改 route、auth/session、role policy、資料、schema、shared library 或其他服務。
- 未驗證真實手機 Safari／Android 的字型與 browser chrome 差異；375px DOM 尺寸與 overflow 契約已驗證。
- Bootstrap CDN 為既有正式 attendance／roster 依賴，本任務未新增、移除或改寫。
