# TASK-039：建立跨平台 LINE 登入入口與復原 UX

狀態：`completed`
優先級：P1 authentication UX
規劃角色：Work
執行角色：Codex
Base commit：`bd0ddd6`

## 1. 目標

讓iOS Safari、Android browser、LINE in-app browser與desktop使用者在進入LINE Login前，能清楚選擇一般LINE登入或安全的browser fallback，不必先經歷callback state錯誤才看到復原入口。登入入口須mobile-first、可理解且可鍵盤操作，同時保留TASK-038的OAuth安全邊界。

## 2. 已確認產品觀察

- Owner已在production確認LINE in-app browser可auto-login。
- Desktop browser可透過QR／其他裝置確認完成登入，callback回原desktop session。
- Owner使用iOS Safari時難以直接喚起LINE mobile app；Android browser行為尚未實測。
- Production normal `/line/login`已不含`disable_auto_login`；`mode=browser`才加入該參數。
- 現有`/redirect-to-login`頁以0.5秒meta refresh自動前往`/line/login`，secondary fallback在跳轉前不可見，也缺少明確平台說明。
- Server-side normal／browser fallback routes與invalid-state error fallback已由TASK-038實作；本任務只建立可見入口與復原UX，不重寫OAuth。

## 3. 實作範圍

### 3.1 明確的登入選擇頁

- 將`redirect_page.html`改為繁體中文、mobile-first登入選擇頁。
- 移除0.5秒meta refresh與其他無使用者操作的自動redirect；兩種登入都由明確click／keyboard activation啟動。此使用者gesture也避免以程式自動跳轉假設app handoff一定可用。
- Primary action：「使用 LINE 登入（推薦）」或同等清楚文案，連到normal `/line/login`，不帶`mode=browser`。
- Secondary action：「無法開啟 LINE？改用瀏覽器登入」，連到`/line/login?mode=browser`。
- 說明LINE App內建瀏覽器通常最順；iPhone Safari／Android browser實際能否喚起App由LINE、OS與browser決定，不宣稱保證支援。
- Desktop提示可簡短說明LINE可能提供QR／browser登入；不得記錄或顯示credential。
- 使用`url_for`生成URL，不硬編碼production hostname或LINE URL。

### 3.2 Return path continuity

- `/redirect-to-login?next=...`仍先用既有`safe_return_path`保存站內目標。
- Normal與browser兩個選項都必須在點擊後建立fresh nonce/state，且state中的return path與原安全目標一致。
- 外部、encoded-backslash、ambiguous或重複`next`不得進入state；重複`next`要明確fail closed，而不是靜默選第一個。
- 選擇頁本身不得把next放進可被外部改寫的absolute URL；可沿用server session或明確的validated relative path。

### 3.3 一致的錯誤與等待狀態

- `line_login_error.html`沿用TASK-038的fresh browser fallback，視覺與登入選擇頁一致。
- `not_authenticated.html`可做最小文案／導覽整理，清楚區分「LINE登入完成但尚未配對Member」與「登入流程失敗」；不得自動重試或觸發外部呼叫。
- 不擴張為整站UI重寫，不修改demo登入prototype。

### 3.4 視覺與無障礙

- 375px寬度無橫向捲動，主要按鈕有足夠觸控高度與清楚focus狀態。
- 使用現有本機Logo／品牌素材；不得新增外部圖片、字型或追蹤script。
- HTML語意、`lang="zh-Hant"`、heading順序與link文字須清楚；不要只靠顏色區分primary／secondary。
- 優先新增小型auth stylesheet或重用現有安全local asset，不引入前端framework。

## 4. 離線測試

- 登入選擇頁不含meta refresh、JavaScript auto redirect或`line://`／custom scheme。
- 頁面同時具有normal與browser fallback兩個可見連結；normal不含mode，fallback恰好`mode=browser`。
- 從有效`next=/future-games`進入後，分別點兩種連結所得signed state都保存`/future-games`且nonce各自fresh。
- 外部、encoded、重複或ambiguous next fail closed；錯誤輸入不得進LINE redirect。
- Error page fallback仍使用fresh transaction，不重用舊code/state/nonce。
- HTML不輸出OAuth state、nonce、code、cookie或Secret。
- 375px responsive contract、focus與button/link可見性有靜態或response HTML測試。
- 既有71項Web Portal tests、minimal session、cookie、admin、roster、demo與deployment contracts不退化。

## 5. 非目標

- 不使用User-Agent sniffing、自動OS判斷、`line://`、Universal Link手工拼接或App Store redirect。
- 不保證iOS／Android一定喚起LINE App，不宣稱離線測試證明平台UX。
- 不修改OAuth state、nonce compare、callback URI、cookie policy、Channel Secret或LINE Console。
- 不實作Google／Apple OAuth，不修改RBAC、schema、DB、attendance、roster或其他服務。
- 不讀取`.env.yaml`／Secret payload，不呼叫真實LINE／HTTP／production DB。
- 不部署、不操作Cloud Run／IAM、不發送LINE／Discord通知。

## 6. 驗收命令

```powershell
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal
python tools/deploy_web_portal.py
git diff --check
git status --short
```

本機可使用bundled Python；另做Python 3.10 grammar check。真實LINE in-app、iOS Safari、Android Chrome與desktop矩陣留待merge／deployment另行批准後由Owner人工驗證。

## 7. 授權邊界

Owner已同意建立TASK-039並直接交棒Codex。Codex可做repository-only實作、離線測試、文件與描述性本機commit，完成後交回Work。尚未批准push、PR、merge、deployment、真實LINE測試、production／DB存取、Secret／IAM／schema／data或通知。

## 8. PR、merge與production結果

- Owner後續授權Work完成驗收、PR、CI、merge與受控deployment完整鏈。
- PR #47 hosted Python 3.10 CI run `31066974072`成功。
- PR #47 squash merge commit：`7082afd4a1d9fe579f02956c77ecbc85b58fd7b7`。
- 執行前rollback target：`web-portal-00034-7lm`，Ready且承接100% traffic。
- Cloud Build ID：`19abfd4c-09bc-4122-aa5a-b877c33427b5`。
- 新revision：`web-portal-00035-mcl`，Ready且承接100% traffic。
- Image digest：`sha256:b63df5755c2991d46e4998ca7c3084b605d23a4a933e38db69d7d2af7da81649`。
- `GET /`為200；`GET /demo/`為404。
- `GET /redirect-to-login?next=/future-games`為200，無meta refresh／script redirect，normal與browser fallback兩個same-site入口及文案均存在；未點擊連結。
- Temporary env已清理；未觸發rollback。
- 未修改Secret、IAM、DB、schema、data、LINE Console、通知或其他服務。
