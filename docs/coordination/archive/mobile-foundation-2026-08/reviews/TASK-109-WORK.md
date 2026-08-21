# TASK-109 Work review

status: accepted
reviewer: main_work
reviewed_at: 2026-08-18T19:35:00+08:00
branch: codex/mobile-auth-api-foundation
implementation_commit: c80b7efea6ecce5b3dbefa123d2a056f51d89b19

## Review result

TASK-109 accepted。交付內容符合 Owner 核准的 revision 0005 exact 五表邊界、獨立 `apps/mobile_api/`
部署單元與 Basic-only API scope；未改 production allowlist、Officer/Admin capability 或既有 Web cookie/CSRF
runtime。

首次 review 發現兩個 blocker：LINE native ID token 誤用固定 RS256 public key，以及 attendance mutation
與 idempotency terminal response 之間存在不誠實失敗窗口。補正後改用 LINE 官方 Verify ID token endpoint
的 injectable adapter，並以 durable claim、serialized execution、authoritative readback 與 recoverable finalize
處理 mutation；未知歷史結果明示 `changed=null`／notification `unknown`，不重做 mutation 或通知。

## Evidence reviewed

- Main Work 重跑 mobile API 14 tests、mobile service 6 tests：通過。
- Main Work 以不落 `__pycache__` 的 compile gate 驗證五個核心 Python modules：通過。
- Codex 證據：Web Portal 185 passed／2 skipped、LINE webhook 26 passed、PG 15.8／16.4 各 8 passed、
  migration graph／Phase C targeted 12 passed、Black／isort／diff checks通過。
- Canonical OpenAPI、runtime route、錯誤 envelope、五態 reply、Basic roster privacy、revision fail-closed、
  refresh replay與 idempotency recovery 已逐檔核對。
- LINE correction依官方 native server guidance核對：`https://developers.line.biz/en/docs/line-login/verify-id-token/`。

## Residual risk and release gate

- Hosted Python 3.10/Linux CI仍須補 canonical checksum gate及 PostgreSQL matrix；Windows full portal-data discovery
  的35個錯誤來自未修改受控SQL的CRLF raw-byte既存問題，不視為本task通過。
- 尚未 build Docker image、呼叫真 LINE、執行 production migration、建立或綁定 Secret、部署或發送通知。
- Revision 0005為 expand-only artifact；production rollout、runtime config、Secret binding、IAM與post-deploy驗證必須
  另取得 Owner 精確批准，不由本 review 自動授權。
