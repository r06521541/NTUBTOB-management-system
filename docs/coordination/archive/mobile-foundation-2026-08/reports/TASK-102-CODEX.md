# TASK-102 Codex report

## 狀態

in_progress。Production 已回切 `web-portal-00046-g8v=100%`；正在修正 exact rollout-vector contract。

## 事件與安全處置

- `web-portal-00047-wdb` 出現 `/manage/people` 503 與 lineup lab 403，符合 Phase C repository disabled。
- 依原核准 rollback package 回切 `web-portal-00046-g8v`；首頁 200、production demo 404。
- 未修改 Secret、IAM、schema 或資料，未讀取完整 runtime env 或 Secret payload。

## 初步證據

- Deployment wrapper targeted：27 passed。
- 既有 deployment evidence 確認 rollback revision 的核准向量為 `true / false / false`。
- Web Portal full offline：180 passed（2 skipped）。
- 受影響 Python `py_compile` 與 `git diff --check` passed。
- Bundled Windows isort/Black 受既有 CRLF／formatter stall 限制，最終 formatter evidence 交由 hosted Python
  3.10 quick gate；未修改 formatter 或 Makefile。

## 首次 deployment attempt correction

- Owner 核准 `true / false / true` 後，Cloud Build `c7b0a06c-6457-4225-8765-12a6455e29f1` 在 validation
  step fail closed；未 build image、未建立或 promote revision，production 維持 `web-portal-00046-g8v=100%`。
- 原因為 Windows temporary `.env.yaml` 使用 CRLF，Cloud Build exact LF line check拒絕尾端 `\r`。
- Generator 改為明確 LF，並新增 raw-byte assertion；不放寬 exact flag check。
