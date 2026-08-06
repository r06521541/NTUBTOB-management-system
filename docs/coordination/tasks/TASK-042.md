# TASK-042：建立正式會員帳號頁、角色標示與安全登出

## 目標

把TASK-041的集中role/capability policy落實成正式Web Portal可見功能：已登入會員能查看自己的最小帳號資訊與目前角色、安全登出；管理員能從介面進入既有Member配對功能；手機上的attendance、roster與account具一致且可操作的導覽。

## 背景與已確認規則

- Production session只保存`user_id`與`member_id`，Member必須request-time重新查詢。
- Production目前只會解析`member`或既有allowlist中的`admin`，沒有officer來源。
- `/attendance`與`/game-roster/<id>`已要求有效會員session；`/match-member`及POST actions只允許具`manage_members` capability的admin。
- Production沒有logout route；既有完整帳號／通知頁只存在於double-gated offline Demo。
- Member model目前可確認的正式基本欄位只有`id`與`name`，不得憑空顯示背號、Email、電話或其他不存在／未核准欄位。

## 使用者價值

- 隊員能確認自己登入成哪一位Member與目前權限。
- 共用裝置、錯誤配對或舊session可以明確登出，不必清除瀏覽器資料。
- 管理員不必記住配對頁URL，且一般隊員不會看到或取得管理入口。
- 手機可在出席、名單與帳號間穩定導覽。

## 工作範圍

1. 新增production member-only帳號頁，例如`GET /account`：
   - 透過現有member guard與集中policy驗證session。
   - 依`member_id` request-time呼叫`Member.search_by_id()`。
   - Member不存在時清除authenticated identity並fail closed，不進入其他資料查詢。
   - 只顯示已確認安全且存在的Member姓名、登入方式「LINE」與角色標籤「一般隊員」或「系統管理者」。
   - admin依`manage_members` capability顯示既有Member配對入口；member不顯示。
2. 新增安全登出：
   - 只接受POST，不建立會由GET、圖片或crawler觸發的logout。
   - 使用獨立、session-bound、constant-time比較的CSRF token。
   - 成功後完整清除目前Web Portal session，redirect至same-site登入／首頁說明。
   - 錯誤／缺失CSRF不得清除session。
   - 不呼叫LINE logout、revoke或其他外部API。
3. 建立最小正式authenticated navigation與本機CSS：
   - account、attendance與game roster可互相到達，手機約375px不橫向破版。
   - admin才顯示管理入口；UI判斷與server authorization使用同一capability policy。
   - 不引入大型前端framework或外部JavaScript；若現有頁面使用CDN Bootstrap，不擴增對它的依賴。
   - 不全面重寫公開首頁、future-games或其他模板。
4. 補齊離線測試：
   - anonymous、畸形session、valid member、allowlisted admin。
   - Member不存在時清除identity且在額外query／外部呼叫前停止。
   - member看不到管理入口，直接存取管理route仍403。
   - logout GET不可用；POST缺失／錯誤CSRF不清session；正確CSRF完整清session且後續protected route需重新登入。
   - account／logout測試不可呼叫真實DB、LINE、Discord或HTTP。
5. 更新Web Portal README與route access matrix。

## 非目標

- 不新增或修改role schema、Member model欄位、migration或DDL。
- 不建立officer persistence、角色指派、帳號核可、audit log或正式活動管理。
- 不實作Google／Apple OAuth、LINE token revoke或跨裝置logout。
- 不新增環境變數、dependency、Secret、IAM、Scheduler或deployment設定。
- 不改LINE callback、OAuth state/nonce、session cookie安全屬性或public route邊界。
- 不連production DB、不發通知、不push、不建立PR、不merge、不部署。

## 設計與安全限制

- 使用TASK-041的production principal與capability policy，不在template另造角色mapping。
- Server-side guard是授權來源；隱藏管理連結只是UX。
- account頁不得把完整ORM物件、role或其他個資寫回cookie session。
- logout CSRF token與Member配對CSRF token分離，避免不同操作域互相重用。
- 登出後不可保留authenticated identity、OAuth暫存、admin CSRF、Demo或其他Web Portal session資料。
- Demo mode須維持隔離；production account/logout不得讓Demo繞過雙重gate或連接production models。
- Python 3.10相容，保持diff聚焦。

## 驗收條件

1. 有效member可查看帳號頁及「一般隊員」；allowlisted admin看到「系統管理者」與配對入口。
2. Anonymous、畸形session與不存在Member均fail closed，且不執行不必要查詢／外部副作用。
3. Member即使手動輸入admin URL仍403；admin成功行為保持相容。
4. Logout只有POST，正確CSRF才完整清session；錯誤CSRF不改session。
5. 登出後account、attendance與roster都要求重新登入。
6. account／attendance／roster具一致mobile navigation，admin入口依capability顯示。
7. 沒有新增officer production來源、schema、env、dependency或外部API呼叫。
8. 完整Web Portal離線測試、compile、Python 3.10 grammar與diff check通過。

## 驗證命令

```text
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal
git diff --check
git status --short
```

另做Python 3.10 AST grammar檢查。Windows既有make/sh deployment tests可依設計skip並記錄；hosted Python 3.10待TASK-041＋TASK-042合併PR工作包另行批准。

## 主要相關檔案

- `apps/web_portal/app.py`
- `apps/web_portal/admin_security.py`
- `apps/web_portal/role_policy.py`
- `apps/web_portal/templates/attendance.html`
- `apps/web_portal/templates/game_roster.html`
- 新account／navigation template與本機CSS
- `apps/web_portal/tests/`
- `apps/web_portal/README.md`
- `docs/planning/WEB_PORTAL_ACCESS_MATRIX.md`

## 已知風險與假設

- 現有production templates結構不一致；只做最小partial／CSS整合，不趁機全面重寫。
- 完整`session.clear()`會中止同一browser中的未完成OAuth transaction，這正是明確logout的預期行為。
- LINE provider端登入狀態不會被本任務撤銷；再次選擇LINE登入可能透過auto-login重新認證，README與UI需避免宣稱已登出LINE帳號。
- 角色標籤代表目前Portal authorization，不代表球隊職稱或資料庫已存在role欄位。

## 交付

- 主要實作使用描述性commit，例如：`feat(web-portal): add account role status and secure logout`。
- 完成後新增`docs/coordination/reports/TASK-042-CODEX.md`並更新`HANDOFF.yaml`為`ready_for_review / work`。
- 不得push、PR、merge或deployment；由Work驗收後再向Owner提出TASK-041＋TASK-042整合PR工作包。

## Base commit

`ad17ac7908ed833fba1827364fb87e72e1ed4b06`

## 下一任務候選

TASK-043候選為移除LINE webhook在出席回覆後對不存在`/clear-cache/attendance`的過時HTTP呼叫，並補上無外部cache invalidation也能顯示fresh attendance的契約。該工作跨shared library與LINE webhook function，應獨立規格、PR與部署，不混入本次Web Portal批次。
