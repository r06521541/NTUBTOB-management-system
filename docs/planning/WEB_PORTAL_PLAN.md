# Web Portal 產品與風險規劃

更新時間：2026-08-04
狀態：`planning`
維護角色：Work

## 1. 產品方向

Web Portal 採 Notion 型的清楚、專業、親切資訊架構，搭配 Airbnb 型圖卡呈現賽程與球隊內容。第一階段使用隊徽、品牌色及圖片占位，待 Owner 後續提供比賽、合照與球場照片後逐步替換。

本規劃不主張大型重寫；優先補齊權限、登入、Secret、測試與隱私邊界，再以可獨立驗收的小任務改善體驗。

## 2. 已確認事實

- 現有功能包含首頁、LINE Login、出席查詢、未來賽程、比賽名單與 LINE user/member 配對。
- `/match-member`、`/match-member/match`、`/match-member/ignore` 未見登入或管理員授權檢查；後兩者會修改資料，亦未見 CSRF 防護。
- 登入前的 `next` 值會存入 session，callback 後直接 redirect，未見站內 URL 驗證。
- LINE token/profile HTTP 請求未設定 timeout，亦未見完整 HTTP 狀態與外部例外處理。
- Session 保存 `user_id`、顯示名稱及完整 SQLAlchemy `Member` 物件。
- `/game-roster/<game_id>` 為公開頁面，會顯示成員姓名。
- Web Portal 使用程序內 `SimpleCache`；shared cache helper 呼叫的 `/clear-cache/attendance` route 在目前 app 中未找到。
- Web Portal 尚無獨立 route、auth、authorization 或 error-path tests。
- 部署流程會將 `.env.yaml` 複製進服務目錄，目前未見 Web Portal 專用 `.dockerignore`／`.gcloudignore`。
- LINE callback URI 硬編碼於 application code。
- Templates 沒有共同 base layout，混用 Bootstrap 與原生 HTML，並有標籤、語意及行動版一致性問題。
- Owner 已加入未追蹤隊徽 `apps/web_portal/static/images/logo_square.png`；目前尚未納入任務或 commit。

## 3. 推論與待驗證風險

- ORM `Member` 物件放入 Flask cookie session 可能有序列化、相容性與資料暴露問題；建議以離線測試重現，設計上只保存必要 ID。
- 程序內 SimpleCache 在 Cloud Run 多 instance／revision 情境可能不同步或過期。
- Cookie secure、same-site、有效期限與撤銷政策未明確設定，實際 runtime policy 待確認。
- 公開姓名與 LINE nickname/member 配對屬個人資料，現有可見範圍可能超過產品必要性。
- 缺少 rate limit、操作稽核及統一安全錯誤頁，會降低濫用防護與事件追查能力。

## 4. 待 Owner 決策

1. 誰是管理員，權限資料應存於既有資料庫、runtime allowlist 或其他來源？
2. 首頁、未來賽程、比賽名單與姓名應分別設為公開、登入會員可見或管理員限定？
3. 所有登入成員是否都能看到完整名單與出席姓名？
4. Session 應維持多久，是否需要 logout 與所有裝置撤銷？
5. 現有 callback URL 是否為唯一正式網域；是否需要 staging callback？
6. 賽程更新與 LINE 出席回覆可接受多久的快取延遲？
7. 排陣結果只需瀏覽器暫存，或需要保存、分享及權限控制？
8. 是否需要隱私告知、資料使用說明及照片使用同意規則？

## 5. P1：安全與可靠性

| 任務候選 | 使用者價值 | 風險／影響範圍 | 依賴 |
| --- | --- | --- | --- |
| `WEB-SEC-01` 存取矩陣、管理員 guard、CSRF | 防止未授權配對或修改資料 | 影響 routes、session、templates；規則錯誤可能鎖住管理員 | Owner 定義管理員與頁面可見範圍 |
| `WEB-SEC-02` Secret 與 build context | 避免 LINE Login secret、session key 進入 image | 影響 Docker、Cloud Build、deploy；錯綁會中斷登入 | 確認既有 Secret 名稱/version，不讀取 value |
| `WEB-AUTH-01` LINE Login、safe redirect、session、logout | 登入安全、失敗可理解且可登出 | 影響所有登入者與 callback | Session lifetime、允許 callback domains |
| `WEB-PRIV-01` 姓名與名單可見範圍 | 降低不必要個資暴露 | 影響 roster、attendance、分享 metadata | Owner 的公開規則 |
| `WEB-TEST-01` Flask route/auth 測試 | 降低後續安全與 UI 回歸 | 影響 tests、CI；mock 不完整會有假信心 | Access matrix |
| `WEB-CACHE-01` 快取一致性與安全失效 | 回覆與賽程能及時顯示 | 不可建立無驗證的公開清 cache endpoint | Freshness 需求、呼叫身分、cache backend |

## 6. P2：核心產品體驗

| 任務候選 | 使用者價值 | 風險／影響範圍 | 依賴 |
| --- | --- | --- | --- |
| `WEB-UI-01` 共用 layout 與視覺基礎 | 一致、專業、手機友善 | 多模板變更易回歸 | P1 tests；現有隊徽 |
| 首頁個人儀表板 | 顯示下一場、我的出席與快速操作 | 查詢與快取可能拖慢首頁 | 登入/session、可見範圍 |
| 賽程圖卡、球場地圖、加入行事曆 | 減少查找資訊時間 | 日期、時區及外部連結需正確 | Asia/Taipei 規則與場地品質 |
| 管理員配對工作區與操作紀錄 | 安全處理未知 LINE user 並可追查 | 紀錄含個資；若需 schema 要 migration plan | 管理員授權 |
| 公告、FAQ、球隊規範 | 集中常用資訊 | 內容容易過期 | Owner 指定維護者與公開範圍 |
| Empty/error/loading states | 使用者知道下一步 | 錯誤訊息不可洩漏內部資料 | 統一錯誤分類與安全 logging |
| 無障礙與手機操作 | 提升各裝置可用性 | 需鍵盤、對比、focus 實際驗收 | 共用 layout |

## 7. P3：有需求再做

- PWA／手機桌面捷徑與離線殼層。
- 個人通知偏好、個人資料與球員檔案。
- 出席趨勢與管理報表。
- 排陣保存、版本及分享。
- 照片與球隊內容管理。
- 更完整的 rate limiting、稽核查詢與營運 dashboard。

## 8. 建議順序

1. `WEB-SEC-01`：頁面存取矩陣與成員配對保護。
2. `WEB-SEC-02`：Secret 與建置邊界。
3. `WEB-AUTH-01`：LINE Login、safe redirect、session、logout。
4. `WEB-TEST-01`：route/auth/error-path tests 與 Python 3.10 CI。
5. `WEB-UI-01`：Notion × Airbnb 視覺基礎與首頁骨架。
6. `WEB-CACHE-01`：快取一致性與安全失效。

若管理員規則尚未決定，`WEB-SEC-02` 可先作為下一個 repository-only 任務；若規則已確定，優先執行 `WEB-SEC-01`。

## 9. 非目標與安全限制

- 未經證據不改用大型前端框架或全面重寫。
- 不在 UI 任務中順帶改 database schema、通知行為或部署架構。
- 不建立公開且無身分驗證的 cache invalidation／管理 endpoint。
- 不因測試方便降低 OAuth state、session、authorization 或 CSRF 防護。
- 未經 Owner 明確批准，不部署、操作 Secret、讀寫 production DB 或發送真實 LINE／Discord 訊息。
