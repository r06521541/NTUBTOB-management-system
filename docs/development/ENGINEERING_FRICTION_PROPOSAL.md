# 工程減摩擦：實作與待決方案

核對基準：`9a5158ab285dad6f60e51dff520106104aaf0cb0`；2026-09-07。
本文件是 TASK-181 的分析，不是第二套 authority。**以下提案尚未生效**；COLLABORATION、
現行 Owner gate、review 與 CI 規則維持不變。不以本文件授權任何外部操作。

## 本次實際改善

- 沿用 `tools.repository_quality`，新增 check-only `--working-tree`，不增加 formatter 或 wrapper。
- README／AGENTS／環境指南統一局部品質入口；`format --paths` 才寫 owned files。
- 移除環境指南重複的 production admin／maintenance 值；PROJECT_STATE 明確標為最近紀錄而非 live observation。
- Mobile API README 依 code allowlists 校正 revision compatibility；TASK-180 merge 以固定 Git 證據記錄。

## 狀態與證據分工（提案，須另核准）

HANDOFF 在已合併的基準仍是 ready_for_pr；新增 review SHA 又會改變文件 commit。
可變進度、固定設計與 immutable evidence 混在同一更新流程，不應靠更多 checklist 解決。

1. Task保存scope/risk/acceptance；可變phase只存於一個選定的任務載體，不再重複於task/report/review/state。
2. PR／CI是merge與suite結果來源；report引用固定implementation SHA，不要求包含自己的commit SHA。
3. PROJECT_STATE保存能力與帶日期的環境紀錄；目前HEAD由Git取得，不再稱固定字串為現在HEAD。
4. 進度區分implemented、integrated、deployed、observed；repo PASS不自動改寫後兩者。
5. 實施前須選定單一任務載體、斷線恢復方式、舊HANDOFF轉換與授權來源；不得直接以sidebar取代authority。

驗收：新session只需入口＋active task，即可辨識目前actor、固定證據與未驗證環境，不需遍歷歷史訊息。

## 審查與授權（提案，須另核准）

| 層級 | 建議工作量 | 保留邊界 |
| --- | --- | --- |
| 純文案／presentation | 實作者focused tests＋一次整合驗收 | 不改auth/state/data |
| session／權限／資料寫入 | 一位targeted reviewer＋affected suite | 稽核、併發、重試、失敗路徑 |
| migration／部署／signing | exact計畫＋既有Owner gate＋post-check | 結果不明先reconcile |

- Reviewer首輪先檢查威脅模型／機制是否值得存在，再查契約符合性；一次列出同層級finding。
- 委派僅用於可獨立完成的子問題；不要為小diff增加常駐角色或多輪完整context搬運。
- ACK／heartbeat／完成回報沿用現行packet。可靠性由Main核對交付狀態，不靠不斷加長提示詞。
- 公開設定、內部識別、個資與真正secret的分級另做決策；本次不放寬既有識別碼處理限制。
- Owner決定付費、公開、資料保留與真實副作用；不應被要求修理shell、encoding、輸入schema。

## CI實測分類與成本方向（只盤點，不修改）

以下是 `classify_paths([path])` 的實際輸出，不是runner耗時或帳務估計。

| 代表路徑 | 現行slice | 後續改善與必要證據 |
| --- | --- | --- |
| README.md | docs_only | 已足夠；不加full |
| apps/web_portal/templates/dashboard.html | web_portal | 已有service切片；保留DOM／CSRF測試 |
| apps/mobile_api/app.py | full | 增mobile_api slice前，明列service／shared contract／DB依賴與final gate |
| tools/ios_store_readiness.py | full | 離線tool可做具名suite mapping，不能進quick allowlist |
| shared_lib/shared_module/portal_data/repository.py | full | 先建立callers圖及schema/model分類；不可只看目錄縮減 |
| clients/flutter_app/lib/support_app_info.dart | flutter | 現在觸發Android與iOS；研究Dart/widget和native build分層 |
| tools/repository_quality.py | full | 影響所有Python gate，本次維持full |

PR與main push皆觸發workflow。不能直接視為重複而移除main驗證：merge結果、dependency、環境與artifact都必須相同
才有重用基礎。後續可選merge queue或artifact-based evidence，但先要有required checks與失敗回復設計。

驗收：新slice有正反分類測試、未知路徑仍full、final gate不漏必跑job、失敗不能被skip當成功。
先觀察數次真實PR耗時與命中率，再計算節省；本次不宣稱節省特定分鐘或費用。

## 本機入口與後續工作

Python先確認runtime並安裝pinned quality requirements；本機check用working-tree，CI仍用exact base/head，
format明列owned paths。Flutter沿用Invoke-FlutterToolchain.ps1；status只确认工具檔存在，不視為真正版本或build
成功證據。需要時在client目錄用dart/flutter子命令，保留hosted平台驗證。

| 後續項目 | 性質 | 完成判準 |
| --- | --- | --- |
| 狀態載體與審查簡化 | Owner流程決策 | 單一進度來源、一次acceptance、無自引用SHA |
| 公開設定／secret分級 | 安全設計決策 | integrity與confidentiality分離，無secret回歸 |
| CI Mobile/API與離線tools切片 | 工程實作 | 分類／final gate測試及hosted證據 |
| operator安全錯誤分類統一 | 獨立工具實作 | stage/category/mutation-state/next-action，不輸出raw exception |

不在本包：App帳號刪除、登入修正、架構拆分、依賴升級、任何部署；不能以工程減摩擦名義夾帶。
