# TASK-176 implementation report

## Outcome

- Added linear, expand-only `0012_persistent_admin_authority`. The singleton state begins in
  `legacy_allowlist` with epoch 1; Person role remains `people.portal_access_level`, and existing append-only
  `access_audit` remains the mutation evidence. Downgrade intentionally retains authority state.
- Added exact runtime selection for `legacy_allowlist|persistent`. Unknown or missing selection grants no admin;
  persistent mode does not read or union the Member allowlist and requires an active admin Person with an active linked
  identity. A Member row is optional.
- Centralized the transaction lock keys and Admin-then-Event helper. Role, Person-status, identity-status, unlink and
  remap writers revalidate under that order and preserve at least one reachable persistent admin.
- Added versioned admin grant/revoke with fresh request-time actor authorization, self/last-admin denial, exact replay,
  one append-only audit row and transaction rollback. Web POST adds CSRF, reason, bounded request ID, expected version
  and a five-minute fresh LINE-login proof; a memberless persistent admin has admin-management capabilities without
  inheriting Member-only portal behavior.
- Added a default-offline inventory wrapper. Its execute path requires exact host/port/database/revision, opens a
  bounded read-only transaction, rejects multi-head state, and renders fixed ASCII presence/parse/mode/category/count
  output only. It never prints IDs, names, subjects, allowlist values, URLs, credentials or digests.
- Preserved older runtime/schema consumers by pinning historical 0011 integration suites and allowing the Mobile API,
  Apple lifecycle, notification reads and Event lifecycle operations to recognize exact additive 0012 while continuing
  to reject unknown/future revision values.

## Safety boundary

This repository change did not read a real allowlist, account, provider subject, Secret or production row. It did not
connect to a database, invoke the inventory execute path, deploy, flip authority mode, seed production roles, remove the
allowlist or mutate any external system. Production discovery, seed, state flip, runtime deployment and rollback
observation remain separate Owner-gated work packages.

## Verification

- Python 3.10 full Web Portal suite: 250 passed.
- Python 3.10 full Portal Data suite: 336 passed, 163 skipped because the isolated PostgreSQL/runtime inputs are absent.
- Python 3.10 full Mobile API suite: 78 passed.
- Python 3.10 full LINE webhook suite: 26 passed.
- Focused portal authority, inventory, Mobile revision and migration-readiness suites: 45 passed, 9 PostgreSQL tests
  skipped without the isolated local database URL. Event/authority cleanup static regressions: 24 passed, 3 skipped.
  The hosted-targeted repository contract suite passed 23 local cases and skipped 25 PostgreSQL cases without that URL;
  its PostgreSQL admin mutation fixtures now create deterministic fictional linked identities while retaining the
  explicit unlinked-admin denial case.
- Black 24.4.2 and isort 5.13.2 formatter API check over the exact changed Python paths: passed. Selected `compileall`,
  `git diff --check`, branch/status and diff self-review: passed before commit.
- Alembic static head/history: one exact head, `0012_persistent_admin_authority`, linearly after 0011.
- PG15/16 migration/metadata, exact replay, append-only rollback, concurrent last-admin revoke, Event-holder lock-order
  and cross-suite retained-evidence isolation tests are included for the hosted matrix; local PostgreSQL execution was
  unavailable and remains the required hosted acceptance limit.

## Lease 2 correction

- Both explicit runtime modes now verify an exact single Alembic revision and, whenever the retained authority table is
  present, an exact singleton whose mode and positive integer epoch agree with runtime. Exact 0011 legacy compatibility
  applies only when that table is absent; mismatch, missing/malformed/multiple state and retained reverse-mode evidence
  authorize nobody. Web checks this boundary before either legacy allowlist or persistent role resolution.
- Apple terminal revocation now takes the canonical ADMIN then EVENT locks before identity, Person or reachability row
  reads. If the revoked identity was the last reachable persistent admin, the transaction still disables the identity,
  revokes sessions/credential, leaves durable mode persistent, appends bounded `identity_disabled` recovery-required
  evidence and returns the bounded `recovery_required` outcome. It never restores provider login or switches authority
  source.
- Added direct/static mismatch and lock-order regressions plus hosted PostgreSQL tests for last-Apple-admin recovery and
  a competing provider-disable/admin-revoke transaction. Local PostgreSQL remains unavailable, so those deterministic
  PG15/16 cases still require hosted acceptance.
- Correction validation: focused authority 16 passed/5 PostgreSQL skipped; full Portal Data 342 passed/165 PostgreSQL
  skipped; full Web Portal 251 passed; full Mobile API 78 passed; shared Mobile service 26 passed. Exact-path formatter,
  compile and diff checks were rerun before the correction commit.
