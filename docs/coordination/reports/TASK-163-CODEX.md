# TASK-163 Codex Report

## Delivered

- Active Officer／Admin 可由 Web Portal 建立與編輯 Event 草稿、編輯起訖、管理 Activity 並維持同 Event position 連續。
- 草稿資格人數維持聚合；人工 include／exclude selector 僅投影 display name 與不透明 person key，保存 3–300 字理由、actor 與 append-only audit，不投影 contact/provider identity。
- 發布與資格／人工 override 共用序列化邊界；InMemory 先在 local copy 完成 invitee/audit/event snapshot 後再原子交換，建構中失敗不留 partial state。
- Published mutation 的 request ID 綁定 exact operation、target 與 payload fingerprint；Event edit 另綁 validated expected version，Activity move 在 boundary no-op 前先判定 exact replay／collision；只有精確重送可回傳既有結果，cross-operation／不同內容碰撞一律 conflict。
- Published Event 基本資料與行程可編輯但不重算 snapshot；published edit 與 cancel 都 audit，cancel 保留 snapshot。
- Web mutation 使用 session CSRF、canonical positive bigint key、server-owned actor、Taipei timezone-aware input、PRG 與 fail-closed站內確認；所有操作不觸發通知。
- `0009_event_management_writes` 只擴充 edit/cancel audit action；downgrade 保留 Event、snapshot 與 audit evidence。

## Evidence

- `py -3.10 -m unittest tests.portal_data.test_repository_contract tests.portal_data.test_event_management_migration -v`：41 outcomes，in-memory 20 passed、migration 2 passed、PostgreSQL 19 skipped（本機未設定 isolated database URL）。
- `py -3.10 -m unittest discover -s apps/web_portal/tests -v`：221/221 passed。
- Hosted correction direct suites：Phase C artifact 10/10 passed；migration readiness static 9/9 passed；Event migration 2/2 passed；兩個 canonical `verify` commands皆通過。Verifier只接受唯一 `0009_event_management_writes` head，並持續拒絕 additional／divergent heads；Phase C SQL artifact/checksum與 mobile staging/broker revision pins未修改。
- Hosted run `33075904432` 的 PostgreSQL 15／16 jobs 未通過：upgrade-to-head tests仍把 `0008` 當 current revision，且 Phase C fixture reset透過 `head -> downgrade 0003` 遇到 `0009`刻意保留的 audit constraint。修正僅更新三個 test expectations，並改為 drop isolated schema、重建既有 fictional legacy fixture、再 upgrade至`0003`；不宣稱 PostgreSQL 已通過。
- Python compile、`node --check apps/web_portal/static/event_management.js`、selected Black check與`git diff --check` passed。

## Remaining gates

- PostgreSQL 15／16 migration/constraint evidence仍須由 hosted rerun補足；本報告不把 failed run `33075904432` 或本機 skip 宣稱為通過。
- 等待 independent Data／Authorization reviewer 與 Main acceptance；尚未建立 PR、roll out schema、deploy或操作正式資料。
- 零 runtime、cloud、Secret、IAM、provider、notification 或 production mutation。
