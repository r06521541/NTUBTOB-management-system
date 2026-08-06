# TASK-043：統一Web Portal深藍／灰品牌介面

## 目標

將目前偏綠的Web Portal視覺調整為符合隊徽的簡潔、專業且親切品牌系統：深藍為主色、中性灰為基底、少量暖金／沙色為非語意強調；同時統一正式會員頁、登入／恢復頁與Demo的共用元件，保持mobile-first與既有功能相容。

## 已確認產品決策

- Primary：隊徽背景相近的深藍，建議起始值`#29415D`；hover／active使用更深藍如`#20344A`。
- Secondary：冷中性灰，包含畫布`#F5F6F8`、白色surface、文字`#18212B`、muted文字`#66717E`與border`#D9DEE5`。
- Accent：低飽和暖金／沙色，建議`#C39A55`與淡底`#F3E9D7`，限少量選取、highlight或裝飾。
- Red：只用於警示、錯誤、取消、拒絕、刪除或其他danger語意。
- Green：只保留LINE官方品牌按鈕，以及成功／出席等明確正向語意；不得再作Portal一般主按鈕或大面積品牌色。

精確色階可在確保對比與現有Logo協調的前提下微調，但不得改變上述語意分工。

## 工作範圍

1. 建立可重用的CSS design tokens：
   - 品牌色、canvas、surface、文字、border、focus、shadow、radius與semantic success/warning/danger。
   - 正式會員頁、auth/recovery與Demo使用同一核心token來源，避免各檔案再各自定義互相矛盾的品牌色。
   - 保留既有class與template契約；若需新增共用CSS，明確控制載入順序與fallback。
2. 漸進套用至主要體驗：
   - 公開首頁、登入選擇、LINE登入錯誤／恢復頁。
   - 正式account、attendance、game roster與共用member navigation。
   - Demo dashboard、賽程、詳情、個人、等待核可、幹部／活動原型及bottom navigation。
   - cards、primary/secondary buttons、status badges、tabs、forms、links、empty states與focus states。
3. 保留語意與第三方品牌：
   - LINE登入按鈕可維持官方綠色，但其他一般CTA改用深藍。
   - 出席／成功可使用語意綠；不出席、取消、刪除與錯誤使用受控紅色。
   - 待確認／一般highlight優先使用暖金或中性灰，不以紅色造成警報感。
4. 補上可離線執行的靜態／route測試：
   - 核心token stylesheet被各入口載入。
   - 主要templates不重新引入舊綠色作一般品牌主色。
   - auth、production member pages與Demo主要routes仍可render，且無外部請求。
5. 更新Web Portal README或既有UI規劃文件，記錄色彩角色、例外與本機視覺驗收方式。

## 非目標

- 不改route、session、LINE Login、role/capability、Member查詢、活動資料或通知行為。
- 不重寫Jinja／Flask架構，不引入React、Vue、Tailwind或其他大型framework。
- 不新增schema、migration、環境變數、dependency、外部字體、外部圖片或追蹤服務。
- 不重新設計隊徽、不產生比賽照片，不實作暗色模式或動畫系統。
- 不修改其他apps/functions/shared_lib。
- 不push、不建立PR、不merge、不部署、不存取production或正式DB。

## 工程限制

- 修改前確認並保留所有既有變更；只修改`apps/web_portal`及必要協作文件。
- 使用既有本機Logo與素材，不讀取`envs/**/.env.yaml`。
- 避免為整理舊minified CSS造成無關的大範圍格式diff；必要變更須可review。
- focus ring需清楚，正文／按鈕文字需維持可讀對比，不能只用顏色傳達狀態。
- 約375px不得橫向捲動、遮住幹部入口或讓bottom navigation不可操作；桌面版也須正常。

## 驗收條件

1. 正式Portal、auth/recovery與Demo明顯採一致深藍／灰品牌，不再由綠色主導一般介面。
2. LINE按鈕與success可保留綠色；紅色只出現在danger／error／cancel／declined等語意。
3. 共用tokens集中且有測試，後續元件不必複製色碼。
4. account、attendance、roster與Demo幹部入口在375px可見、可操作且無橫向捲動。
5. 鍵盤focus、hover／active、disabled、badge與form狀態清楚且文字對比合理。
6. 既有LINE Login、account/logout、role policy與Demo雙重gate測試保持通過。
7. 完整Web Portal離線測試、compile、Python 3.10 grammar與`git diff --check`通過。

## 驗證命令

```text
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q apps/web_portal
git diff --check
git status --short
```

另執行Python 3.10 AST grammar檢查，並以local demo人工檢視約375px與桌面頁面；不得因視覺驗收呼叫production或外部API。

## 主要相關檔案

- `apps/web_portal/static/auth.css`
- `apps/web_portal/static/portal.css`
- `apps/web_portal/static/member_portal.css`
- `apps/web_portal/static/events.css`
- `apps/web_portal/static/operations.css`
- `apps/web_portal/static/interactions.css`
- `apps/web_portal/static/officer_nav.css`
- `apps/web_portal/templates/`
- `apps/web_portal/tests/`
- `apps/web_portal/README.md`
- `docs/planning/WEB_PORTAL_PLAN.md`

## 交付方式

- 主要實作使用一個描述性commit，例如：`style(web-portal): align portal UI with navy team branding`。
- report與handoff可併入同一完成commit，避免新增純流程commit。
- 完成後更新`docs/coordination/reports/TASK-043-CODEX.md`與`HANDOFF.yaml`為`ready_for_review / work`。
- 不得push、PR、merge或deployment；Work驗收後再向Owner整理TASK-041至TASK-043的單一PR工作包。

## Base commit

`6e6c8cf5ecf06245c510e7767c1e49be564728e8`

## 後續候選

TASK-044：移除LINE webhook出席回覆後對不存在`/clear-cache/attendance`的過時HTTP invalidation，避免無timeout外部呼叫拖慢webhook；另案處理shared library與function部署邊界。
