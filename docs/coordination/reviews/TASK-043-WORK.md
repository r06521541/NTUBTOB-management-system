# TASK-043 Work 驗收

- 日期：2026-08-06（Asia/Taipei）
- Branch：`codex/deploy-task-040`
- 主要實作 commit：`1ca46b5`
- 驗收修正 commit：`0238288`
- 結論：`accepted`

## 實際查驗

- `brand.css` 集中深藍、灰、暖金及 success／warning／danger／LINE tokens，正式 auth、member pages與Demo依明確順序載入。
- 公開首頁、登入／恢復頁、account、attendance、roster與Demo已漸進採用新版品牌色，未修改route、auth、資料或權限規則。
- 正式共用會員導覽包含「首頁／出席／我的帳號」，管理入口仍依既有capability顯示。
- LINE綠只保留LINE action與成功語意；一般提醒使用暖金，活動取消等明確danger才使用紅色modifier。
- Work第一輪發現Demo `theme-color`仍為舊綠，且一般notice被誤套danger紅；Codex已於`0238288`修正並補回歸測試。

## Work 獨立驗證

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 94 tests - OK (skipped=2)

python -m compileall -q apps/web_portal
OK

git diff --check
OK

git status --short
clean
```

兩項skip是既有Windows缺少Unix `make/sh`的deployment contract測試。Codex另回報19個Python檔案的Python 3.10 grammar check通過。

## 限制與後續

- Codex已完成375px DOM overflow及desktop本機視覺檢查；Work嘗試重做瀏覽器驗收時，Codex Desktop瀏覽器控制因本機kernel assets路徑錯誤無法連線，因此未取得第二份畫面截圖證據。
- 尚未push、建立PR、merge、部署或存取production。TASK-041至TASK-043可整理成單一Web Portal PR工作包；須Owner批准後執行。

