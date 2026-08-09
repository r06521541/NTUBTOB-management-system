# TASK-040 Work 驗收報告

驗收日期：2026-08-06（Asia/Taipei）

## 驗收結論

- 結論：`accepted`
- Branch：`codex/task-039-closeout`
- Task base：`7082afd4a1d9fe579f02956c77ecbc85b58fd7b7`
- Planning commit：`d84d637`
- Implementation commit：`a369123`
- Codex handoff commit：`ad08ce1`
- Whitespace correction：`f8a754b`
- Repository：乾淨
- 下一位角色：Owner

## 實際 diff 驗收

- 登入選擇頁明確區分手機與電腦：手機回到 LINE 內開啟 Portal；電腦可使用帳號或 QR Code 登入。
- 登入狀態過期頁不再直接啟動 `mode=browser`，改為返回 server 產生的 same-site `/redirect-to-login` 說明頁。
- safe internal return path 仍經 `safe_return_path()` 驗證後才帶入登入說明頁。
- 舊 authorization code、state 與 nonce 不會出現在新的登入選擇頁；stale OAuth session keys 仍先被清除。
- 正常 `/line/login` 與明確 `mode=browser` route 均保留，OAuth state 簽章、nonce binding、session cookie 與 CSRF 行為沒有被放寬。
- 未加入 User-Agent sniffing、JavaScript/meta 自動登入、LINE custom scheme、新 dependency 或跨瀏覽器 bearer state。
- 修改僅限 Web Portal README、route 呈現、兩份 auth templates、相鄰測試及協作文件；沒有 shared library、schema、Secret、IAM、deployment config 或其他服務變更。

## 驗收條件

1. 手機與電腦登入指引清楚：通過。
2. 不再宣稱手機外部瀏覽器的 browser-mode 是可靠復原：通過。
3. 過期頁可安全返回登入說明，不直接進入同機 QR 死路：通過。
4. LINE Login、browser mode、state/nonce 安全驗證未移除或放寬：通過。
5. 無 UA sniffing、自動跳轉或 custom scheme：通過。
6. 離線測試通過且無外部副作用：通過。

## Work 獨立驗證

```text
Bundled CPython 3.12.13
python -m unittest discover -s apps/web_portal/tests -v
Ran 75 tests — OK (skipped=2)

python -m compileall -q apps/web_portal
OK

git diff --check 26b4d47..HEAD
OK（Codex 依 Work 意見修正報告檔尾空白後重驗）

git status --short
clean
```

兩項 skip 是 Windows 本機缺少 Unix `make`／`sh` 的既有 deployment contract coverage，與本次呈現修改無關。

## 回歸風險與未驗證事項

- 尚未取得 GitHub hosted Python 3.10 CI；應在獲准的 PR 工作包中補齊。
- 尚未部署與實機檢視新文案；375px 無橫向破版目前由既有 auth CSS 與測試契約間接支持，本任務未修改 CSS。
- Android 外部瀏覽器行為仍未實測，但現在不再承諾它是可靠路徑。
- 頁面基於不使用 UA sniffing 的決策，手機仍看得到標示為「使用電腦瀏覽器登入」的選項；這是刻意保留能力而非自動猜測裝置。

## Blocking 問題

無。

## 建議

接受 TASK-040 repository 成果。若 Owner 批准 PR 工作包，下一步可 push、建立 Draft PR、取得 hosted Python 3.10 CI，再交由 Owner 決定 merge；本次驗收不包含部署。
