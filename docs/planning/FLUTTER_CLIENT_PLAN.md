# Flutter Client 第一階段規劃

狀態：`planning`
Owner 確認日：2026-08-18
本文件是 TASK-104 的產品與技術規格草案，不授權 schema、migration、production、Secret、IAM、通知、商店發布或任何 cloud mutation。

## 1. 產品目標、平台與範圍

### 已確認（Owner：2026-08-18）

- 交付 Android／iOS 手機 App，第一階段以手機直向為主，使用繁體中文、友善口吻。
- 支援明亮／深色模式，預設跟隨系統設定；提供可略過的 2～3 頁新手導覽。
- 一般會員可登入、查看帳號、賽程、出席與比賽名單，並可回覆及修改自己的出席。
- 一般會員只能看到已回覆的隊員姓名；Officer／Admin 可查看單場完整出席報告與尚未回覆名單。
- 第一階段不包含訪客模式、帳號密碼、群組管理、聊天、完整角色管理、活動 CRUD 或全域搜尋。
- 提供聯絡管理員入口、隱私／資料使用／通知權限說明與版本更新提示。
- 可離線查看最近同步的帳號、賽程與通知；出席回覆及通知發送必須在線上完成。

### 建議／延後

- `proposed`：無障礙基線包含可讀字級、對比、focus／按鈕狀態與一致的 loading、empty、error、offline 狀態。
- `deferred`：平板、橫向、全域搜尋、App 內客服與 App 內帳號刪除。

## 2. Personas 與 capability matrix

| Persona | 第一階段能力 | 備註 |
| --- | --- | --- |
| Basic | 自己的帳號、賽程、出席、已回覆名單、通知 | 不看未回覆者；可修改自己的出席 |
| Officer | Basic + 單場出席報告、未回覆名單、個人／賽事／隊務通知 | 只取得後端明確授予的 capability |
| Admin | Officer 全部能力 + 系統公告、置頂與治理能力 | production authority 仍受既有 allowlist／resolver 邊界約束 |

### 邊界與既有決策

- Member、Person 與登入 identity 分離，Person 可有多個 auth identity：參照 DEC-079、DEC-080。
- Production admin authority 目前以 `WEB_PORTAL_ADMIN_MEMBER_IDS` runtime allowlist 為準：參照 DEC-082。
- DEC-089 的 bounded Game route 與「不因 demo 自動取得其他管理能力」仍有效；本規劃不自行啟用 production Officer resolver 或擴張 production capability。
- fictional demo 可模擬 Basic／Officer／Admin，但 demo role 不等於 production authorization：參照 DEC-090。

## 3. 導航與功能面

### 已確認（Owner：2026-08-18）

- 登入／重新登入、首頁、賽程、單場比賽、出席回覆、通知中心、帳號／設定、聯絡管理員。
- Officer 增加單場出席報告、通知撰寫／預覽／結果與通知紀錄。
- Admin 增加系統公告、到期設定與最多三則置頂管理。
- 推播點擊支援 deep link：比賽提醒到比賽頁、出席提醒到回覆頁、個人／公告到通知詳情。

### 建議／延後

- `proposed`：所有列表使用分頁、下拉刷新、載入更多與安全空狀態；日期以 Asia/Taipei 顯示，API／storage 使用明確 timezone。
- `deferred`：App 內生物辨識鎖、裝置管理、登出其他裝置、多身份切換。

## 4. LINE Login、token、session 與 account linking

### 已確認（Owner：2026-08-18）

- 使用原生 LINE Login；Flutter 取得 authorization code 後交由後端 exchange。
- 使用短期 access token 與 refresh token；access token 僅存在記憶體，refresh token 存 Android Keystore／iOS Keychain。
- refresh token rotation；主動登出只撤銷目前裝置。
- App 啟動自動恢復登入；refresh 失敗時清除 session、顯示登入過期並回到 LINE Login。
- 不保存 LINE channel secret、provider secret、production Secret 或 provider token。
- 未來 Google／Apple identity 連到同一 Person，不建立 Flutter-local 會員帳號，也不以 email、姓名或頭貼自動合併。

### 延後／未決

- `deferred`：Google／Apple OAuth、provider linking、account recovery、conflict、unlink last usable identity 的正式流程另立 authentication task。
- `deferred`：正式 mobile auth contract 必須定義 PKCE、state、nonce、redirect binding、authorization code single-use／expiry、refresh token server-side revocation、device record 與 rotation replay detection；本 planning task 不自行建立跨端契約。

既有 identity／狀態分離參照 DEC-079、DEC-080；Web Portal 的 LINE session／state／CSRF 邊界參照 DEC-084。

## 5. Mobile API 與出席回覆

### 已確認（Owner：2026-08-18）

- Flutter 使用獨立、版本化的 JSON API，例如 `/api/v1/...`，不依賴 HTML route。
- LINE webhook、Web Portal、Flutter 應共用 server-owned attendance reply application service；client 不複製「開打前 12 小時」判定或 Discord 行為。
- 出席可隨時回覆與修改；已改變才產生後端副作用，未改變不得重複通知。
- API 必須表達 `changed=true／false`、認證／授權失敗、retry、idempotency 與通知失敗語意。

### 延後／未決

- `deferred`：現行 repository 所稱五種 attendance reply 的正式 enum、request／response schema、錯誤碼與 compatibility mapping，須由後續 API contract task 依現行 code／tests 定稿，不在本文件猜測名稱。
- `deferred`：offline queue 是否進入正式 client；目前只允許線上 mutation，離線操作顯示未送出。

既有通知渠道不可混用 LINE Notify；Discord、LINE Messaging API、LINE Login／webhook 各自維持明確 caller：參照 DEC-085。

## 6. 通知、Discord 與 push

### 已確認（Owner：2026-08-18）

- 通知類型：比賽提醒、出席提醒、比賽變更、Officer 個人通知、賽事 Broadcast、隊務 Broadcast、Admin 系統公告。
- Officer 可對特定 Person 發送個人通知、賽事 Broadcast 與隊務 Broadcast；Admin 包含 Officer 全部能力，另可發布系統公告。
- 賽事 scope 可按特定回覆狀態、尚未回覆或全體已回覆者解析；全體通知須預覽並二次確認；不建立 Group。
- 通知為單向純文字，最多 500 字；提供預設標題；送出後不可修改、撤回或刪除。
- 推播結果分為 `accepted`、`delivered`、`read`、`failed`；同一 Person 的有效裝置全部發送，任一裝置送達／讀取即計入 Person 層級。
- 會員通知保留最近 90 天；Officer／Admin 稽核紀錄永久保留；badge 只計算未讀且仍有效的通知。
- 通知中心支援篩選、分頁、全部標示已讀、deep link；Admin 最多同時置頂三則，Officer 不可置頂。
- 出席回覆距開打少於 12 小時的既有 Discord 緊急通知由後端 application service 統一處理，Flutter 不直接呼叫 Discord。

### 延後／未決

- `deferred`：push provider、device token registration、delivery receipt、失效 token cleanup 與 notification audit schema 的正式實作。
- `deferred`：Admin／Officer production resolver 是否已具備本規劃所需 capability；在 resolver 未啟用前只可使用 fictional／staging fixtures。

既有 notification channel 參照 DEC-085；production／外部操作邊界參照 DEC-078；bounded Game route、session-only lineup 與 fictional demo 分離參照 DEC-089、DEC-090。

## 7. Local、fictional demo、offline 與 retry

### 已確認（Owner：2026-08-18）

- fictional demo 與 production-shaped preview 分離；demo 使用 fake API／repository／push service，不連外部服務或 production：參照 DEC-090。
- offline 只讀最近成功同步資料並顯示最後同步時間；出席與通知 mutation 必須在線上。
- 無網路或 API 錯誤不得假裝成功；App 提供可重試狀態。

### 建議

- `proposed`：mutation 使用 client-generated idempotency key；retry 只重送未知／失敗副作用，不重送已確認成功結果。
- `proposed`：fake service 與 staging service 共用同一 application boundary，避免 demo API 形成另一套產品規則。

## 8. Staging、TestFlight、APK 與 production promotion

### 已確認（Owner：2026-08-18）

- development／staging／production 使用不同 build flavor；正式 App 不提供環境切換。
- Android 以 staging APK／Internal App Sharing 測試；iOS 以 staging TestFlight 測試。
- staging 使用測試帳號與測試資料，不連 production DB。
- 上線前需驗證真機登入、refresh、logout、推播、deep link、Officer／Admin capability 與 crash reporting。

### 安全邊界

- 本規劃不授權 production deployment、production DB、Secret、IAM、Scheduler、cloud resource、正式通知或商店發布：主要參照 DEC-078；admin authority 參照 DEC-082，bounded Game route／session-only lineup 參照 DEC-089，fictional demo 分離參照 DEC-090。
- production promotion 另需 exact target、artifact、rollback 與 Owner 明確批准。

## 9. Security、privacy 與 non-goals

### 已確認（Owner：2026-08-18）

- crash reporting 只收匿名錯誤、App／OS／裝置版本，不記錄 token、姓名、通知內容或敏感 payload。
- 提供友善繁體中文的隱私政策、資料使用與通知權限說明。
- notification preference 只存在目前裝置；新安裝預設全部開啟；OS 拒絕推播時提供前往設定入口。
- App 不直接刪除帳號；使用者透過聯絡管理員申請。

### Non-goals

- 不把規劃視為 schema／migration／production contract。
- 不在 Flutter 內執行 authorization、通知 recipient expansion 或 Discord／LINE API secret 操作。
- 不以 UI visibility 取代 server-side capability enforcement。

## 10. 候選後續 work packages

不先配置正式 TASK 編號，待總控 Work 統一拆分：

- A：Flutter fictional foundation（flavor、navigation、theme、fixtures、offline read model）。
- B：schema-neutral attendance reply application service（Web + LINE；沿用既有 schema，不做 migration）。
- C：mobile auth／API contract（LINE native exchange、token/session、Person identity、error／idempotency）。
- D：Flutter API integration（會員流程、attendance、Officer／Admin capability、notification centre）。
- E：staging／release（staging API、APK、TestFlight、真機驗證與 promotion checklist）。

## 11. Acceptance milestones

### 建議（`proposed`）

1. 規格、toolchain inventory、fake contract 與 boundary review 完成。
2. Fictional demo 可驗證登入狀態、會員／Officer／Admin navigation 與 offline read-only flow。
3. Staging API contract 通過 auth、attendance、notification error／retry review。
4. Android／iOS staging 真機通過 LINE Login、refresh、logout、push、deep link。
5. Owner 完成 product／security／data visibility 驗收後，另立 production promotion task。

## 12. Open questions

- 五種 attendance reply 的現行 enum 與 mobile API contract。
- staging API／測試資料的具體 hosting 與 reset 方式。
- Google／Apple linking 與 account recovery 的安全流程。
- push provider、delivery receipt、token lifecycle 與 audit schema。
- production Officer capability resolver 的啟用時程與 bounded route mapping。
- 最低 Android／iOS 版本的實際數字。
