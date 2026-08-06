# TASK-042 Work 驗收

- 日期：2026-08-06（Asia/Taipei）
- Branch：`codex/deploy-task-040`
- 實作 commit：`769f846`
- 結論：`accepted`

## 實際查驗

- `/account` 以 session `member_id` 在 request-time 查詢 Member，只顯示姓名、LINE 登入方式與集中 policy 解析的角色。
- 一般隊員不顯示 Member 配對入口；管理 route 仍由 server-side capability guard 保護。
- `/logout` 僅接受 POST，使用獨立 session-bound CSRF token 與 constant-time 比較；只有合法請求才執行 `session.clear()`。
- Demo route 未取得 production account/logout bypass；未新增 production officer 來源。
- 未修改 schema、model、環境變數、dependency、Secret、IAM、LINE Login callback、通知或 deployment 設定。

## Work 獨立驗證

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 89 tests - OK (skipped=2)

python -m compileall -q apps/web_portal
OK

Python 3.10 AST grammar check
18 Python files - OK

git diff --check
OK
```

兩項 skip 是既有 Windows 缺少 Unix `make/sh` 的 deployment contract 測試，不影響本次 account/logout 行為。

## 未完成與後續

- 尚未做 375px 與桌面瀏覽器視覺驗收；將與 TASK-043 品牌色及共用元件調整一起驗收。
- TASK-041、TASK-042 與 TASK-043 預計合併為同一 Web Portal PR 工作包，避免純協作文件形成多個獨立 PR／main commits。
- 本次驗收未 push、建立 PR、merge、部署或存取 production。

