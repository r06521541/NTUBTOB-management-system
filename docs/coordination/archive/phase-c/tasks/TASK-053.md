# TASK-053：相容 Supabase CSV 的 SQL NULL 匯出格式

## 背景

Owner 已在 Supabase SQL Editor 執行 TASK-052 的唯讀盤點 SQL。實際下載的 CSV 會把 SQL `NULL`
輸出成文字 `null`，但目前 validator 只接受空字串代表未填值，因此拒絕了結構與內容原本符合固定
33-row contract 的結果。這是匯出格式相容性問題，不是資料庫盤點失敗。

原始 production CSV 位於 repository 外，視為一次性驗證輸入；不得複製、重新命名或提交至 Git。

## 目標

- 讓 TASK-052 validator 接受 Supabase CSV 對「未填 value 欄位」輸出的 `null`。
- 維持既有固定欄位、固定 metrics、單一有效值與敏感內容 fail-closed 邊界。
- 用明顯虛構的 fixture 與離線測試證明相容性，不使用 production 輸出建立測試資料。

## 實作範圍

1. 在 `tools/supabase_access_inventory.py` 的結果驗證路徑加入最小 normalization：
   - 只處理 `boolean_value`、`integer_value`、`text_value` 三個 value 欄位。
   - 欄位值去除頭尾空白後，僅當完整值不分大小寫等於 `null` 時轉成空字串。
   - 不得 normalization `section`、`metric`、`status`、CSV header 或其他內容。
   - validator 回傳 normalized rows，使後續使用者不會誤把字面 `null` 當成實際值。
2. 新增一份明顯虛構、符合固定 33-row contract 的 Supabase-style CSV fixture。
3. 新增 regression tests，至少證明：
   - Supabase-style `null` fixture 可通過，且輸出語意等同既有空白 fixture。
   - identity/contract 欄位中的 `null` 仍被拒絕。
   - `null@example.invalid`、URL、DSN、SQL expression、`null-value` 等內容不會被誤轉並仍被拒絕。
   - 每列仍必須恰有一個有效 value，boolean/integer/text 型別規則不變。
4. 更新 TASK-052 操作文件，說明 SQL Editor 匯出的 SQL NULL 可能呈現為 `null`，validator 會在受限 value 欄位內正規化。
5. Codex 僅使用 repository 內虛構資料驗證。Work 驗收時才會以唯讀方式對 repository 外的 Owner CSV 執行 validator。

## 非目標與禁止事項

- 不連線 Supabase 或 production DB，不執行 SQL。
- 不讀取或提交 `.env.yaml`、DSN、secret、project ref、角色名稱或 application row data。
- 不把 Owner 的 CSV 複製進 repository、fixture、report 或 log。
- 不修改 SQL 盤點 metrics、schema、RLS、role、grant、backup/PITR 或 migration。
- 不 push、建立 PR、merge 或部署。

## 驗收條件

1. 既有空白 fixture 與新增 Supabase-style `null` fixture 均通過，共同產生 33 筆 normalized rows。
2. normalization 僅限三個 value 欄位與完整 `null` token，contract identity 不被放寬。
3. 既有 SQL 靜態安全測試與敏感資料防線全部通過。
4. Python 3.10 compile、Black、isort、`git diff --check` 通過。
5. Codex report 清楚聲明未接觸 repository 外 CSV、Supabase、production 或 secrets。

## 驗證命令

```powershell
py -3.10 -m unittest tests.portal_data.test_supabase_access_inventory -v
py -3.10 -m compileall -q tools tests/portal_data
py -3.10 -m black --check tools/supabase_access_inventory.py tests/portal_data/test_supabase_access_inventory.py
py -3.10 -m isort --profile black --check-only tools/supabase_access_inventory.py tests/portal_data/test_supabase_access_inventory.py
git diff --check
git status --short
```

## 預期變更檔案

- `tools/supabase_access_inventory.py`
- `tests/portal_data/test_supabase_access_inventory.py`
- `tests/fixtures/task053_supabase_null_export_fake.csv`
- `docs/operations/data/TASK-052-SUPABASE-ACCESS-INVENTORY.md`
- `docs/coordination/reports/TASK-053-CODEX.md`
- `docs/coordination/HANDOFF.yaml`

## 建議 commit

`fix(data): accept Supabase null CSV exports safely`

Commit body/footer 加上 `Refs TASK-053`。

## Base commit

`7f53c12e590944e3d98b17df33cd8180b57869b1`
