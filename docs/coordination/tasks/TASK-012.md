# TASK-012：Mobile-first Web Portal Local Demo MVP

狀態：`completed`
優先級：P1/P2 product prototype
規劃者：Work
執行者：Codex
`base_commit`：`b25b3ad6ca3ba355756cc938259d11b7be163398`

## 1. 任務目標

在既有 Flask/Jinja Web Portal 上建立可離線瀏覽與操作的 mobile-first MVP，作為未來 Android/iOS App 的產品原型。Owner 必須能在沒有 LINE Login、production DB、Secret 或外部 API 的 local 環境，瀏覽 Dashboard、賽程、賽事詳情、個人頁與等待核可頁，並在 demo session內操作出席回覆。

今晚的完成定義是可在 local 實際操作的 MVP，不只規劃或靜態 mockup。

## 2. 已確認現況

- Web Portal 是單一 `apps/web_portal/app.py` Flask app，templates 沒有共用 base layout，部分頁面依賴 CDN Bootstrap。
- 既有 LINE routes：`/redirect-to-login`、`/line/login`、`/line/callback`；不得移除或改成 demo-only。
- 既有 `/attendance` 以 session 中的 `member` 授權並查 production-style models；現有 session保存 ORM object 的風險不是本任務全面修復範圍。
- 現有 `/future-games` 與 `/game-roster/<id>` 會查 DB；demo routes不得呼叫它們背後的 DB helpers。
- 現有 `/match-member` routes 缺少授權／CSRF；本任務不擴張到管理後台修復。
- Owner 提供未追蹤素材 `apps/web_portal/static/images/logo_square.png`；可引用但不得修改原圖。
- Repository 沒有 Web Portal tests、app-specific README、`docs/STATUS.md`、`docs/ROADMAP.md` 或 `docs/tasks/`；canonical coordination task 位於本文件路徑。

## 3. 產品與設計決策

### 3.1 資訊架構

建立一致的 portal shell：desktop header、mobile bottom navigation、cards、buttons、status badges、empty/error states。視覺方向為 Notion 的清楚親切加上 Airbnb 式賽事圖卡，使用 local CSS 與既有 Logo，不新增大型前端 framework，也不依賴外部 CDN 才能正常呈現。

主要頁面：

1. Dashboard：下一場、近期賽程、我的出席、快速回覆入口、未回覆提醒。
2. 賽程列表：日期、時間、球場、對手與我的狀態。
3. 賽事詳情：完整賽事資訊、出席／不出席／待確認、已回覆與未回覆名單，以及 demo session內的快速回覆操作。
4. 個人頁：虛構 Member 資料、LINE connected UI、Google/Apple disabled demo UI、通知分類 UI；通知切換可為純 UI 或 session-local，不得寫 DB。
5. 登入／等待核可：LINE、Google、Apple 產品原型；LINE 保留連至既有登入，Google/Apple disabled；等待頁清楚說明管理員確認狀態。

### 3.2 Development-only demo boundary

- 以明確環境設定啟用，例如同時要求 `WEB_PORTAL_ENV=development` 與 `WEB_PORTAL_DEMO_MODE=true`。名稱可合理調整，但必須雙重 fail-closed：缺任一值、值拼錯或 production環境都視為關閉。
- Demo mode關閉時，demo登入／資料 routes回傳 404或拒絕；portal受保護頁不得讓匿名使用者直接看到內容，應導向登入產品頁或既有登入入口。
- Demo mode開啟時提供明確入口，建立只存在 Flask session 的虛構登入身分；不得查 DB、呼叫 LINE/Discord/crawler/weather或任何外部 API。
- Demo資料使用 dataclass／plain dict 等 repository-local provider，所有姓名、隊伍、球場與帳號均需明顯虛構。
- Demo POST出席回覆只更新 session，使用 allowlist 驗證 game ID/status，並採 POST/redirect/GET。不得寫入 model或 production data。
- 不可用 query parameter、header或單一 cookie直接開啟 demo mode。
- 為 local demo提供固定非敏感 development secret fallback只能在雙重 demo gate成立時使用；其他情況缺正式 `SECRET_KEY` 應 fail closed或維持既有行為，不得產生 production auth bypass。

### 3.3 最小結構調整

允許將 demo data/provider、portal routes/helper與 app setup從 `app.py` 做最小拆分，以便 import與離線測試；禁止全面重寫、改 shared models或正式 schema。需保持從 repository既有方式執行 `apps/web_portal/app.py` 的相容性。

## 4. 工作範圍

- 新增或更新 Flask routes/helper，完成上述頁面與 demo session flow。
- 建立 Jinja base layout及 reusable partial/macro（若合理）。
- 建立 local CSS，375px左右不得有頁面級水平捲動；touch target、focus state與基本色彩對比需合理。
- 沿用 Logo；圖片不存在時頁面仍不應崩潰。
- 更新 root README 或新增 Web Portal README，記錄 Windows PowerShell及POSIX的一條清楚啟動方式、URL、環境 gate與關閉方式。
- 新增完整離線 Flask tests，mock/patch任何可能觸發 model或外部服務的界線。
- 撰寫 `docs/coordination/reports/TASK-012-CODEX.md` 並在完成時將 HANDOFF改為 `ready_for_review / work`。

## 5. 非目標

- 不實作真正 Google/Apple OAuth。
- 不修改 database schema、models、migration或 production data。
- 不修完整管理員權限、match-member CSRF、Secret deployment boundary或 session ORM風險；若新頁會碰到這些區域，保持隔離並記錄後續風險。
- 不部署、commit、push、建立 PR或操作任何雲端資源。
- 不發 LINE/Discord通知，不呼叫 crawler、weather或 production API。
- 不引入 React/Vue/Svelte/Flutter、Node build chain或大型 CSS framework。
- 不把 demo auth或 demo data接入既有 production routes。

## 6. 驗收條件

- [x] README提供一條清楚的 local demo啟動指令，從乾淨 shell不需 Secret／DB／外部 API即可啟動。
- [x] Demo gate開啟後，可瀏覽登入原型、Dashboard、賽程列表、至少兩個賽事詳情、個人頁與等待核可頁。
- [x] Demo使用者可在賽事詳情快速切換出席／不出席／待確認，redirect後頁面與 Dashboard反映 session-local狀態。
- [x] 所有 demo資料明顯虛構，測試證明 demo flow不呼叫 DB model或外部 request。
- [x] Demo gate關閉、只設定其中一個 gate、或 environment不是 development時，demo登入／資料不可用，匿名者不可直接瀏覽 protected portal內容。
- [x] `/line/login` 與 `/line/callback` routes仍存在；既有 LINE登入流程未被 demo route取代。
- [x] Google/Apple按鈕清楚標示即將推出或 demo，disabled且沒有 OAuth request。
- [x] 375px viewport沒有已知水平破版；沒有固定寬度大於 viewport，bottom navigation不遮住主要內容。
- [x] 共用 layout、cards、buttons、badges在mobile與desktop一致。
- [x] 無 schema、deployment、Secret、shared_lib或其他服務變更。

## 7. 必要測試與驗證

至少執行：

```text
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal
git diff --check
git status --short
```

測試至少涵蓋：

- demo config truth table（雙 gate、單 gate、production）。
- demo登入、登出或清 session、protected redirect。
- Dashboard、games、game detail、profile、pending頁成功。
- unknown game與invalid reply安全失敗。
- reply只改 session且PRG後跨頁反映。
- demo mode關閉時不暴露demo route/data。
- LINE routes仍註冊。
- patch DB/model與HTTP clients為「呼叫即失敗」，主要 demo navigation仍通過。
- HTML基本 responsive contract：viewport meta、無明顯固定寬度、主要 navigation與status labels存在。

若本機不是 Python 3.10，需明確回報實際版本；不得宣稱Python 3.10已在本機驗證。

## 8. 安全停止條件

遇到下列事項立即停止相關操作並在 report記錄，不等待 Owner也不嘗試繞過：

- 需要讀取 `envs/**/.env.yaml`、Secret value或 production credentials。
- 需要連線 production DB或外部正式服務才能讓demo運作。
- 需要改 schema、部署、IAM、Secret或正式通知。
- 發現現有未提交檔案與本任務修改同一檔案且無法安全保留。

除此之外，以最安全合理假設持續完成，不因小型文案或mock data選擇等待 Owner。

## 9. 相關檔案

- `apps/web_portal/app.py`
- `apps/web_portal/templates/`
- `apps/web_portal/static/`
- `apps/web_portal/tests/`（新增）
- `apps/web_portal/README.md` 或 root `README.md`
- `docs/planning/WEB_PORTAL_PLAN.md`
- `docs/coordination/reports/TASK-012-CODEX.md`
- `docs/coordination/HANDOFF.yaml`

## 10. 已知風險與後續

- MVP demo通過不代表 production DB query、LINE callback或正式權限已驗證。
- 真正出席寫入產品規則與endpoint目前不在 Web Portal；本任務只做session prototype。
- Google/Apple、通知偏好 persistence、管理員核可及跨裝置狀態均是prototype。
- 現有 Web Portal deployment Secret/build boundary仍阻擋production deployment；本任務不得解除或繞過該 blocker。
- UI需由 Owner日後以實機／瀏覽器主觀驗收；離線HTML/CSS測試只能降低明顯回歸。
