# TASK-086 Cloud Run env metadata fallback Work review

## Review（2026-08-10）

- 驗收 branch `codex/phase-c-bootstrap-env-metadata-fix`，implementation `d00dead085ed0823fee50f6c9cf69427dc6c754c`，handoff HEAD `da606563d920cd56a90a64ba1aa1a4bbbba717ec`；接棒時工作樹乾淨。
- 固定 gcloud describe 僅投影 `spec.template.spec.containers[0].env`，並保留精確 account、project、service 與 region；不呼叫 Secret Manager，也不解析 Secret payload。
- Parser 僅接受單一 container、唯一明文 `WEB_PORTAL_ADMIN_MEMBER_IDS` 與嚴格正整數清單；missing、duplicate、empty、malformed、secret-backed allowlist 或額外 schema 一律 fail closed。
- Metadata stdout/stderr 使用 bytes capture，完整 response、parsed tree、allowlist 與 private PG state 均在 `finally` 清除；例外與最終輸出維持固定分類，不包含 metadata 值。
- Work 實跑 diagnostic、recovery、launcher 與 operator 合併測試 41/41 passed；compileall、`git diff --check` 通過。
- 未執行 gcloud、未讀 private env/Secret、未連 production、未執行 DDL/DML 或 56-Person activation。

結論：`accepted`；可建立唯一 ready PR。Hosted CI 與 squash merge 通過後，只執行一次已授權的固定 production read-only diagnostic，依八欄分類結果決定 TASK-086 是否完成或停止。
