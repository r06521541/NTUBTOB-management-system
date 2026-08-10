# TASK-099 Work Review

status: changes_requested
reviewer: work
reviewed_at: 2026-08-11T01:01:14+08:00
branch: codex/phase-d-portal-management-closure
implementation_commit: a9bf9878f9ce1d2e896aac15f95eee01453f73e4

## Review result

Changes requested. The implementation is in the correct isolated worktree and covers the intended routes, role matrix,
Windows date path, PostgreSQL integration and browser personas. Four contract gaps remain before acceptance.

## Blocking findings

1. `change_person_access` validates only `request_id.startswith("person-access-")` instead of reusing the existing
   `_required_request_id()` bounded ASCII/length validator. Oversized or malformed values can reach the repository and
   database rather than fail with 400 before side effects, and deployment/database errors are not domain errors.
2. Fictional fixture recognition accepts any additional `access_audit` row whose actor/target IDs are in the reserved
   range and whose request ID starts with `person-access-`. Action, before/after state, reason and exact transition are not
   fingerprinted, so an arbitrary mixed/drifted local state can be silently accepted and deleted by reset/cleanup.
3. The fixture is described and tested as deterministic, but four Game rows use transaction-time `now()`. Consecutive
   seed/reset operations therefore produce different row values. A required explicit anchor date/time or another canonical
   input must make the same invocation byte/value deterministic while still allowing useful future/recent/past QA.
4. `shared_lib/shared_module/models/games.py` was reformatted almost completely for a four-line Windows fix (91 additions,
   61 deletions even with end-of-line whitespace ignored). This violates the focused-diff boundary and obscures review.
   Restore the base formatting and retain only the platform-safe date behavior. TASK-099 also claims mobile tightening but
   has no production CSS change; either add the minimal nav/hub/Attendance density adjustment required by the task with
   390px evidence, or explicitly return that acceptance item to Owner before claiming delivery.

## Required correction

- Use `_required_request_id("person-access-")`; add oversized, non-ASCII and malformed regression cases proving 400 and
  zero repository calls.
- Make demo-state recognition exact for every permitted post-seed Officer mutation/audit, or use a canonical fixture
  fingerprint. Unknown audit action/state/reason/request drift must fail closed and remain unchanged.
- Add an explicit validated anchor input and fixed timestamps (or an equivalently deterministic contract), then assert
  complete Game/timestamp equality across reset rather than only counts/access level.
- Revert unrelated `games.py` formatting. Address or explicitly hand back the mobile-density acceptance item.
- Re-run targeted/full Web Portal, affected portal-data, PostgreSQL 15/16, formatter/diff and 390px QA as applicable;
  update the single report/HANDOFF and formally return to Work. Do not change schema, preview POST, production or export
  boundaries.

## Evidence reviewed

- Branch, origin and handoff HEAD are synchronized at `6b1ac23b3842981873d4dee66ea7211ba30a582e`; worktree clean.
- No schema, migration, controlled SQL, production operation, Secret, deployment or external service change is present.
- Codex reports Web Portal 163 passed/2 skipped, affected PostgreSQL 15/16 integration passing, and desktop/390px
  Basic/Officer/Admin QA. The broader three raw-byte checksum failures are confined to unchanged CRLF-controlled artifacts
  and are not treated as TASK-099 regressions.

The original dirty repository and excluded owner export helper remain untouched.

## Second correction review

reviewed_at: 2026-08-11T01:21:20+08:00
correction_commit: 64ea3075cf60ec68676ec2cc1708074546430183

Bounded request-ID validation, exact fictional audit drift rejection, anchored deterministic Game timestamps and the
minimal <=420px density layer are accepted. The `games.py` correction is still incomplete: commit `64ea3075` did not
touch that file, but the original implementation's repository-wide Black rewrite remains in the cumulative branch diff.
Relative to base `44925dad`, `games.py` still shows 141 additions and 111 deletions (91/61 even ignoring EOL whitespace)
instead of the intended four-line date change.

Required final correction: restore the exact base `games.py` blob and reapply only the Windows-safe
`get_formatted_date()` return change. Do not run Black/isort on that legacy file. Verify the cumulative base-to-HEAD diff,
not only the latest commit diff; update the report claim and rerun its targeted compile/date tests plus `git diff --check`.
No PostgreSQL or browser rerun is needed for this formatting-only correction.
