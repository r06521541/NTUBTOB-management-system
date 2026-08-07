# TASK-070 Codex report

## Result

Status: `ready_for_review`

Implemented the repository-only Phase C identity lifecycle, transactional administration, pending-review conversation,
Person-based legacy attendance bridge and strict migration evidence. The new runtime paths remain disabled unless
`PORTAL_DATA_PHASE_C_ENABLED` is exactly `true`; the existing admin Member allowlist remains the sole production admin
authority.

No production database, migration, deployment, Secret, IAM, Scheduler, LINE/Discord delivery, production feature flag,
push or pull request was used or changed.

## Delivered behavior

- Added Alembic revision `0004_phase_c_identity_lifecycle` as the single head after revision 0003. It adds Person profile
  fields, the review thread/message schema, exact audit actions and a nullable Person attendance bridge. Review tables
  have RLS enabled with zero policies. Guest-player validity is bounded in both the database and domain layer.
- The attendance migration backfills missing attendance-linked Member/Person relationships locally and aborts the whole
  transaction if any reply remains unresolved. Fresh install, legacy upgrade, downgrade/upgrade and rollback-negative
  paths are covered by PostgreSQL tests.
- Added a transactional `IdentityLifecycleRepository` for pending identity creation, principal resolution, approval,
  ignore/unignore, reject/unblock, enable/disable, unlink/remap, Person profile/status, qualification lifecycle, review
  messages, notification throttling and retention redaction. Mutations use locks, append-only audit records and
  post-commit notification callbacks; validation failures fail closed.
- LINE Login stores only stable identity references in the session and refreshes identity, Person, optional Member and
  qualifications on every protected request. Pending/rejected users receive dedicated UX and non-Member Persons no
  longer require a synthetic Member row.
- Added an allowlist-admin dashboard and CSRF-protected lifecycle mutations, plus self-service display-name editing. The
  legacy match/ignore routes use the lifecycle repository only when the existing maintenance gate and Phase C flag are
  enabled.
- Added pending-user conversation with a database-enforced 24-hour request throttle and post-commit admin notification
  hook. The local demo reproduces the lifecycle UX using session-only fake data and makes no external calls.
- Web Portal, LINE webhook and notify attendance analysis can use Person eligibility when Phase C is explicitly enabled.
  Active `team_player` and time-bounded `guest_player` qualifications are evaluated at game start. Guest status does not
  create a fake Member, and guest reply value 5 is excluded from unanswered counts.
- Added deterministic, checksummed migration and read-only pre/post evidence artifacts with repository verifiers. The
  CI workflow checks their formatting, checksums and PostgreSQL behavior under Python 3.10/PostgreSQL 16.

## Verification

- Local PostgreSQL 16 full portal-data suite: 141/141 passed. This includes migration rollback on unresolved attendance,
  fresh/legacy/downgrade rehearsals, RLS and zero-policy checks, exact five-calendar-year guest bounds, lifecycle state
  transitions, locks/audits, 24-hour throttle, retention dry-run/mutation, Person attendance and evidence negative gates.
- Web Portal suite: 115 passed, 2 skipped because this Windows environment lacks `make`/`sh`.
- LINE webhook suite: 19/19 passed.
- Notify cronjob service suite: 9/9 passed.
- Game broadcast service suite: 28/28 passed.
- Update game schedule suite: 5/5 passed.
- Deployment/tool suite: 41/41 passed.
- `python -m tools.portal_data_phase_c_migration verify`: passed.
- `python -m tools.portal_data_phase_c_evidence verify`: passed.
- Shared library source distribution rebuilt and installed into the bundled local runtime with no production access.
- `python -m compileall -q apps/web_portal apps/notify_cronjob_service functions/line_webhook_handler shared_lib tools tests/portal_data`: passed.
- Black API check for the 11 files required by hosted CI: passed. `isort --profile black --check-only` for all changed
  Python modules: passed. The bundled runtime is Python 3.12.13; hosted Python 3.10 CI has not yet run.
- `git diff --check`: passed. The local PostgreSQL Compose container/network was stopped; its fake-data volume was
  retained.

## Safety and review boundaries

- Environment examples contain only the disabled Phase C flag. No real credential or sensitive environment file was
  read, copied, logged or committed.
- HTTP, LINE, Discord, weather and database integration tests used mocks or the repository localhost-only PostgreSQL
  fixture. No real notification was sent.
- Production migration execution, pre/post evidence collection, deployment, feature enablement and notification delivery
  remain separately gated Owner/Work tasks. Passing local tests does not establish production data compatibility.
- This task deliberately does not add People-based admin/officer authority, Person merge, Event eligibility, dual-write,
  production cleanup scheduling or automatic production rollout.
- Work should review the large lifecycle transaction surface, the 0003-to-0004 backfill/recovery contract, all exact audit
  relationships, and the default-off caller branches before approving any later production plan.
