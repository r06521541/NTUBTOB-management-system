# Web Portal production deployment — 9c7b82b

- 日期：2026-08-28（Asia/Taipei）
- 結果：成功；未需要 rollback
- PR：#213
- Exact merge commit：`9c7b82b3857a20c6e53f99d108264a04726aac2f`
- Hosted run：`33164033852`（成功）
- Cloud Build：`ba69d5d1-9386-4a3d-ab98-4df0466b0c93`
- Previous／rollback revision：`web-portal-00052-xcg`
- New revision：`web-portal-00053-wzw`
- Image digest：`sha256:827e41b1bd42038b9684ed93d0f5e71cd97e32f3b60b53f9fdb9083da8ede0f8`

## Outcome

Production Event-management navigation and all managed routes now use the canonical runtime allowlist capability. The PostgreSQL adapter independently requires an active Person linked to an exact allowlisted Member; persisted Officer／Admin fallback remains local-preview-only.

## Verification

- Hosted PostgreSQL 15／16, Web Portal, full selected suites and final gate passed.
- `web-portal-00053-wzw` is Ready and receives 100% traffic.
- Runtime identity, four existing Secret references, non-empty admin allowlist, Phase C=true, rollout freeze=false, identity maintenance=true and public invoker remained unchanged. Identity-link keys remain absent.
- HTTP checks: `/` 200, `/demo/` 404, `/identity-recovery` 404; unauthenticated `/manage/events` 302. New-revision ERROR count was 0 during the bounded post-check.

No Event was created, no production database write was performed, and no Secret payload, IAM, provider, notification or unrelated service was accessed or modified. Authenticated Event creation remains an Owner product smoke.
