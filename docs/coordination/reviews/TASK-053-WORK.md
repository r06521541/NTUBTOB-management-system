# TASK-053 Work 驗收

## 結論

`accepted`。實際 diff 將 standalone、大小寫不敏感的 `null` normalization 限制在
`boolean_value`、`integer_value`、`text_value` 三欄，沒有放寬固定欄位、固定 metric、單一有效值、
型別或敏感內容檢查。新增 fixture 為明顯虛構資料，Owner 原始 CSV 未納入 repository。

## 查驗基準

- Branch：`codex/task053-supabase-null-csv`
- Task base：`7f53c12e590944e3d98b17df33cd8180b57869b1`
- Work planning：`0a86c2bf7f58c0ec2564214c4600229c045b41d5`
- Implementation：`7d5bfe4a42e78cb1b59c2b1121cd5e54f04260d5`
- Codex evidence：`10e1e347b76a39db398d6e850d1cd37a394d91ef`
- 驗收開始與結束時 working tree clean。

## Work 實際驗證

- Bundled Python 3.12：`python -m unittest tests.portal_data.test_supabase_access_inventory -v`
  - 14/14 passed。
- Bundled Python 3.12：`python -m compileall -q tools tests/portal_data`
  - passed。
- `git diff --check`
  - passed。
- Repository 外 Owner CSV：以 `validate_csv(...)` 唯讀驗證
  `C:\Users\USER\Downloads\Supabase Snippet Untitled query (2).csv`
  - passed，固定 contract 共 33 rows。
  - 未輸出資料列、未複製或提交原始檔。
- Codex 另以可用 Python 3.9 執行相同 14 tests、compile 與 artifact verifier，均通過。

## 未完成證據

- 本機 `py -3.10` 指向已不存在的 Microsoft Store runtime，無法取得本機 Python 3.10 實跑證據。
- Bundled Python 的 Black/isort invocation 在 Work 驗收時逾時；Codex 的 Python 3.9 環境也未安裝兩者。
- 若建立 PR，應以 repository CI 的 Python 3.10 runner 補足版本與格式檢查證據；目前不影響本機行為驗收，
  但在 CI 成功前不可宣稱 Python 3.10 hosted validation 已完成。

## 安全邊界

- 未連線 Supabase、未執行 SQL、未讀取 secret 或 `.env.yaml`。
- 未修改 schema、migration、role、grant、RLS、backup/PITR 或任何 cloud resource。
- 未 push、建立 PR、merge 或部署。

## 後續

Owner 可決定是否授權 push 與 PR，以 GitHub Python 3.10 CI 補足最後的 hosted runner 證據。
Dashboard 的 backup/PITR、restore authority、API exposure、connection path、maintenance window 與 timeout
查驗仍是後續獨立工作，不屬於 TASK-053。
