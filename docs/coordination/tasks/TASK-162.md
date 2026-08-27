# TASK-162 Dashboard 同日賽事卡與出席確認

## Classification

- task_type: delivery
- risk: L2 attendance mutation presentation / accessibility
- delivery_group: `web-portal-reliability-202608`
- authority_branch: `codex/task-162-dashboard-game-card-confirmation`
- repository_authority: `5d389f6c7c293a362551111a5be025ca058d9d60`
- production_execution: prohibited until separate exact Owner gate

## Active writer claim

- role: `codex-writer`
- claim_id: `task-162-dashboard-game-card-confirmation-writer-20260827`
- lease_version: 1
- actor_id: `codex-writer:task162-dashboard-game-card-confirmation`
- state: `completed`
- scope: unify same-day game presentation and add site-native attendance confirmation
- owned paths:
  - `apps/web_portal/templates/dashboard.html`
  - `apps/web_portal/templates/_portal_base.html`
  - `apps/web_portal/static/dashboard_reply.js`
  - `apps/web_portal/static/production_portal.css`
  - `apps/web_portal/tests/test_admin_security.py`
  - `apps/web_portal/tests/test_brand_ui.py`
  - `docs/coordination/tasks/TASK-162.md`
- write: exact task branch and owned paths only; commit/push handoff authorized; Main owns acceptance, PR, merge and deployment
- report_to: `main-work`
- stop_conditions: backend/API/notification semantics change, CSRF weakening, browser-native confirm dependency, inaccessible dialog/focus behavior, unexpected dirty overlap, production/runtime/cloud need

## Required behavior

1. Every game on the next calendar day uses the same full featured-game card structure: date tile, detail link/arrow, complete matchup/location/home-away text, current reply and five reply choices. Weather remains attached only where the existing forecast contract supplies it.
2. Every Dashboard attendance form is marked for confirmation. Selecting a reply opens one reusable site-styled dialog describing the game and selected status; the original POST happens only after explicit confirmation.
3. Cancel button, Escape/close and dismissed dialog perform zero submission and return focus to the initiating control. Confirmation submits the exact original form/button once, preserving CSRF, game endpoint and reply value.
4. Do not use `window.confirm()` or another browser alert. Native `<dialog>` may be used only with a site-styled fallback that remains an in-page dialog when `showModal` is unavailable.
5. Existing backend reply/notification/idempotency semantics, LINE in-app behavior, routes and schema remain unchanged.

## Verification budget

- Add regressions before implementation for identical same-day card structure, per-game forms/current reply, dialog semantics and JS confirmation contract.
- Writer runs affected Web Portal tests, formatter/compile, `git diff --check` and scope review.
- One independent Web Accessibility/State reviewer checks dialog focus/cancel/single-submit, progressive fallback and card interaction layering.
- Main performs focused regressions/diff review; one hosted change-selected gate before merge.

## Acceptance status

- Writer affected evidence: `test_admin_security.py` 116/116 passed; Brand UI 9/9 passed; Node syntax, Black formatter API, Python compile and `git diff --check` passed.
- Independent Web Accessibility/State review: ACCEPT after closing a P1 no-JS bypass; server-rendered buttons now remain disabled until the complete dialog controller initializes.
- Main evidence: Brand confirmation contract and Node syntax passed; supported root-level `test_admin_security.py` discover 116/116 passed. One earlier direct-module invocation failed only because that harness did not expose `shared_lib`, then the supported invocation passed.
- External mutation: none; no deployment, cloud, provider, Secret, schema, notification or production-data operation occurred.

## Writer implementation checkpoint

- state: reviewer fail-safe correction complete; awaiting correction review
- card contract: every first-calendar-day game uses the shared featured-card macro and retains five reply controls
- confirmation contract: one in-page dialog preserves original form, submitter, CSRF, action and reply value
- no-script contract: every reply button is server-disabled and unlocks only after complete dialog listener registration
- focused evidence: Brand UI 9 tests pass; Web Portal security 116 tests pass; JavaScript syntax check passes
- external mutation: none; no backend, notification, schema, runtime, cloud or production operation was performed
