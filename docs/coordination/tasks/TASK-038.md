# TASK-038：恢復 LINE Auto-login 並保留安全 Browser Fallback

狀態：`awaiting_owner_approval`
優先級：P1 authentication UX／security
規劃角色：Work
執行角色：Codex（Owner核准後）
Base commit：`4b9ddd483a197d00a41403858efd36ff964e6e10`

## 1. 目標

讓從LINE App內建瀏覽器或LINE官方支援環境啟動的一般登入重新具備auto-login機會，同時保留OAuth state簽章、browser session nonce binding與安全fallback。正常登入不再固定停用auto-login；只有使用者在state continuity失敗頁主動選擇「改用瀏覽器登入」時，才以全新transaction加入`disable_auto_login=true`。

## 2. 已確認現況與根本原因

- `/line/login`目前對所有authorization request固定加入`disable_auto_login=true`。
- LINE官方文件定義此參數會停用auto-login；因此LINE in-app browser原本可用的自動登入也被關閉。
- TASK-029加入此參數，是為避免mobile external browser auto-login跳轉LINE App後，callback落在不同browser cookie context而發生`Invalid state parameter`。
- TASK-032已處理stale／colliding cookie並提供versioned production session cookie；Owner後續確認一般／無痕external browser可正常登入。
- 現有callback仍要求signed state中的nonce與發起browser session nonce一致；本任務不得降低此CSRF邊界。
- 現有錯誤頁只能重新進入同一個固定停用auto-login的流程，沒有區分normal auto-login與manual browser fallback。

## 3. 設計決策

### 3.1 Normal login恢復auto-login eligibility

- 一般`/line/login`不得傳送`disable_auto_login`參數。
- 保留既有`response_type`、client ID、callback URI、scope、signed state、fresh nonce與safe return path。
- 不使用User-Agent、LINE App版本、OS或browser名稱猜測流程；支援環境由LINE authorization endpoint依官方行為決定。

### 3.2 明確的manual browser fallback

- 提供固定、可驗證的internal login mode，例如`/line/login?mode=browser`；只接受明確allowlisted mode。
- Browser fallback才加入`disable_auto_login=true`。
- 每次fallback request必須建立全新nonce與signed state，不得重用失敗callback的authorization code、state或nonce。
- `next`仍須經既有`safe_return_path`處理；未知mode、重複／模糊參數或外部return target須fail closed至安全預設。

### 3.3 Invalid state錯誤頁

- Missing、tampered、expired或跨session state仍在LINE token exchange與DB前回400。
- 錯誤頁主要按鈕改為「改用瀏覽器登入」，連到明確browser fallback mode。
- 若incoming state可通過簽章／期限驗證但session nonce不相符，可保留其中已驗證的safe internal return path供fallback使用；若state本身無效則使用`/attendance`等固定安全預設。
- Invalid handler仍只清除OAuth transaction keys與TASK-037 legacy identity cleanup，不得清除既有`user_id`／`member_id`、CSRF或demo state。
- 頁面不得回顯authorization code、state、nonce、cookie或LINE錯誤body。

### 3.4 Tests與文件

- 先更新／新增能重現「normal login固定停用auto-login」的測試，再實作。
- 至少涵蓋：
  - normal login authorization query不含`disable_auto_login`。
  - explicit browser fallback恰好含`disable_auto_login=true`。
  - normal與fallback都產生fresh、session-bound nonce/state。
  - 跨session但signed-valid state的錯誤頁使用安全internal return path；點fallback後建立全新transaction。
  - tampered／expired／missing state只使用安全預設return path。
  - fallback不重用舊code/state/nonce，且LINE／DB在錯誤callback不呼叫。
  - unknown／ambiguous mode與外部next fail closed。
  - TASK-032 cookie migration、TASK-037 minimal identity session、admin、roster、CSRF與demo行為不退化。
- README更新normal auto-login與manual browser fallback的使用者行為與限制；不得宣稱所有OS/browser一定支援auto-login。

## 4. 非目標

- 不移除state signature、nonce compare、session cookie binding或safe return path。
- 不建立跨browser可轉移的bearer state，不把identity或authorization結果放入URL。
- 不使用User-Agent sniffing或特定LINE App deep link workaround。
- 不修改LINE Console、callback URI、Channel Secret、Secret Manager、cookie policy或session lifetime。
- 不改schema、Member model、RBAC、attendance、roster、demo或其他服務。
- 不讀取`.env.yaml`／Secret payload、不連production DB、不呼叫真實LINE endpoint。
- 不部署、不操作Cloud Run／IAM、不發送LINE／Discord通知。

## 5. 離線驗收條件

- Normal authorization URL允許LINE自行選擇auto-login；manual fallback明確停用auto-login。
- 所有成功callback仍必須由同一browser session nonce驗證，安全邊界不退化。
- State continuity失敗可由當前browser啟動全新manual transaction，不重用失敗credential。
- Tampered／expired state、外部redirect與ambiguous inputs均fail closed。
- 全部Web Portal tests、compile、deployment dry-run與diff check通過。

## 6. 驗證命令

```powershell
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal
python tools/deploy_web_portal.py
git diff --check
git status --short
```

Hosted Python 3.10 CI與真實LINE in-app／Safari／Chrome矩陣屬後續PR與受控人工驗證；離線測試不得宣稱已證明LINE App行為。

## 7. 建議人工驗證矩陣（部署另行批准後）

- LINE in-app browser：normal login是否自動完成或明顯減少登入步驟。
- iOS Safari／Android Chrome：normal auto-login成功時callback session continuity。
- Auto-login continuity失敗：錯誤頁的browser fallback是否在當前context成功。
- Desktop browser：normal與fallback均能使用LINE提供的browser登入方式。
- 所有案例均確認callback停留在預期browser、return path正確、重新整理不重用舊code/state。

## 8. 授權邊界

本文件目前只供Owner確認。Owner若批准TASK-038，可授權repository-only實作、離線測試與描述性本機commit；PR工作包、push、merge、deployment及真實LINE人工驗證仍須另行明確批准。
