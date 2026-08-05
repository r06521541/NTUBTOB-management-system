# TASK-012 Work Review

日期：2026-08-05
結論：`accepted`
下一位角色：Owner

## 驗收基準

- Branch：`codex/fix-broadcast-request-time`。
- Base／HEAD commit：`b25b3ad6ca3ba355756cc938259d11b7be163398`；本任務依 Owner要求未 commit。
- 工作樹非乾淨：TASK-012 實作／文件均未提交；既有未追蹤 `apps/web_portal/static/images/logo_square.png` 為 Owner提供素材，本任務只引用、未修改。
- Work 已查閱實際 route、demo provider、templates、CSS、tests、README與 Codex report，不只採信摘要。

## 驗收結果

- [x] 雙重 gate只接受 `WEB_PORTAL_ENV=development`及 `WEB_PORTAL_DEMO_MODE=true`；其他組合fail closed。
- [x] Demo process不載入 ORM、DB engine、attendance helper或Discord notifier，既有資料型routes在demo process回404。
- [x] Dashboard、賽程列表、三個詳情頁、個人頁、登入與等待核可頁完成。
- [x] 出席回覆採allowlist及POST/redirect/GET，只寫session並跨Dashboard／detail反映。
- [x] LINE login/callback routes仍註冊；Google／Apple與通知偏好明確為prototype。
- [x] 共用layout、desktop header、mobile bottom navigation、cards、buttons及status badges完成。
- [x] README提供PowerShell與POSIX的一條啟動指令，不需要Secret、DSN或外部服務。
- [x] 沒有修改schema、shared_lib、deployment、Secret或其他服務。

## Work 獨立驗證

Runtime：Python 3.12.13（不是Python 3.10）。

```text
python -m unittest discover -s apps/web_portal/tests -v
10/10 passed

python -m compileall -q apps/web_portal
passed

移除 DSN_*、SECRET_KEY與LINE登入設定後 import app並檢查routes
passed

git diff --check
passed
```

Codex另以375×812本機瀏覽器操作登入、Dashboard與賽事詳情，三頁均無水平溢位，bottom navigation與回覆按鈕正常。Work嘗試建立第二份本機瀏覽器證據時，瀏覽器控制介面初始化失敗，因此未重複該視覺實測；Work已獨立檢查responsive CSS契約與HTML route輸出。

## Prototype 與風險

- Google／Apple OAuth、通知偏好儲存、正式出席寫入、管理員核可及跨裝置狀態均未實作。
- 既有LINE callback、production DB routes與正式授權流程未做線上驗證。
- 本機沒有Python 3.10實跑證據；需未來CI或Python 3.10環境補驗證。
- Demo登入頁保留既有LINE登入連結；點擊它會離開離線demo並進入真實LINE流程，local preview應使用「進入虛構Demo」。
- Web Portal Secret/build context blocker仍存在，本成果不得部署production。

## 結論

需求範圍、fail-closed邊界、離線性、主要操作及mobile contract均符合TASK-012；無blocking issue，建議Owner local瀏覽後決定是否接受及後續commit／PR。
