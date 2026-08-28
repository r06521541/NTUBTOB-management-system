# TASK-166 桌面 LINE Login 首次 callback continuity

## Classification

- task_type: delivery
- risk: L2 session／OAuth transaction binding
- delivery_group: `web-portal-reliability-202608`
- requires_independent_pr: true
- authority_branch: `codex/task-166-desktop-line-login-continuity`
- repository_authority: `98687a736d0f910132185c7ac1128ddbb89748b3`
- production_or_real_data: prohibited

## Completed writer claim

- role: `codex-writer`
- claim_id: `task-166-desktop-line-login-writer-20260828`
- lease_version: 2
- actor_id: `codex-writer:task166-desktop-line-login-continuity`
- state: `completed`
- final_lease_version: 2
- scope: repository-only desktop LINE Login callback continuity correction
- owned paths:
  - `apps/web_portal/app.py`
  - `apps/web_portal/README.md`
  - `apps/web_portal/tests/test_admin_security.py`
  - `docs/coordination/tasks/TASK-166.md`
  - `docs/coordination/reports/TASK-166-CODEX.md`
- write: exact task branch and owned paths only; commit/push handoff authorized; Main owns final review/PR/merge
- report_to: `main-work`
- stop_conditions: need for provider/callback registration, Secret/cookie-policy/runtime change, transferable OAuth state, production/cloud access or mutation, unrelated dirty overlap

## Observed production failure

Owner observed the exact desktop sequence: login-choice page → existing LINE account login → Portal expired-state page → login-choice page → existing LINE account login → Portal home. This is not an accepted multi-step provider flow. The first callback transaction failed before Portal authentication; the second transaction succeeded.

## Required behavior

1. The explicit desktop-browser action creates a short-lived, purpose-bound signed initiation envelope and must first commit a clean, same-origin Portal session transaction before leaving the Portal origin for LINE authorization. Unsigned, malformed, tampered, expired, wrong-purpose, wrong-host or same-browser replayed initiation fails before session clearing.
2. The subsequent authorization request must reuse only that fresh browser-bound nonce and validated local return path. Missing bootstrap state fails before contacting LINE.
3. Desktop login keeps LINE's supported `disable_auto_login=true` fallback but must not add provider reauthentication or a second OAuth transaction merely to obtain a fresh Portal transaction.
4. Callback continues to require a valid time-limited signed state and exact same-browser session nonce. No cross-browser or transferable state is introduced.
5. Normal LINE in-app login remains behaviorally unchanged.
6. Rejection diagnostics use fixed, non-sensitive categories only; never log state, nonce, code, cookie, return URL, identity or provider response.

## Invariants and non-goals

- Do not change LINE provider configuration, callback registration, credentials, Secret references, cookie security attributes or OAuth expiry.
- Do not weaken state signature, TTL, nonce comparison, safe return-path validation or identity authorization.
- Do not access provider/cloud/runtime/production data, perform deployment or run a real login in this repository round.
- Do not change identity matching, roles, database schema or notifications.

## Verification budget

- Regression first for the signed initiation envelope, expiry/purpose/tamper/host/replay rejection before side effects, same-origin bootstrap redirect, committed-cookie authorization step, callback nonce continuity and direct/missing-bootstrap rejection.
- Preserve existing invalid/tampered/expired/mismatched state, safe return-path, cookie security and normal LINE-path tests.
- Writer runs focused tests and the Web Portal affected complete suite, compile/format checks, `git diff --check` and scope/status review.
- One independent Auth/Security targeted reviewer checks transaction binding, disclosure and in-app non-regression. Main performs final diff/risk acceptance; final PR uses one hosted gate.
- Production deployment and one Owner desktop login acceptance are separate later gates.

## Writer result

- Desktop mode creates a distinct-salt, two-minute signed initiation envelope containing only exact purpose, validated return path and a random initiation nonce, then canonicalizes to the immutable origin derived from `LINE_REDIRECT_URI`. Only a valid non-replayed envelope may clear the canonical session, commit a fresh OAuth nonce and return path, and proceed through the second canonical same-origin authorization request.
- Unsigned, tampered, expired, wrong-purpose, malformed, wrong-origin, replayed or missing bootstrap state is rejected with one fixed non-sensitive category before session clearing, OAuth-state creation or LINE redirection. The initiation envelope cannot be loaded as callback OAuth state; callback signature, TTL, exact nonce and safe-return validation are unchanged.
- Normal LINE in-app mode remains the existing single-step authorization path; desktop mode retains `disable_auto_login=true` without introducing another OAuth transaction.
- Writer verification is recorded in `docs/coordination/reports/TASK-166-CODEX.md`; independent Auth/Security review, hosted CI, PR, deployment and Owner desktop acceptance remain separate gates.

## Acceptance status

- Independent Auth/Security initial review found the unsigned canonical-bootstrap replay/session-disruption gap; lease 2 corrected it with a distinct-salt, short-lived signed initiation envelope and bounded same-browser replay history.
- Independent Auth/Security lease 2 rereview: `ACCEPT`; focused 18 tests and `git diff --check` passed.
- Main risk review: `ACCEPT`; canonical origin is derived only from the fixed callback URI, invalid initiation cannot clear session or reach LINE, and callback state/TTL/exact nonce remain unchanged.
- Main critical regression sample: 5 passed. Two preceding collection attempts executed zero tests because of incorrect Windows module paths; the corrected command used the repository root in `PYTHONPATH`.
- Hosted CI, PR merge, production deployment and Owner desktop acceptance remain pending.
