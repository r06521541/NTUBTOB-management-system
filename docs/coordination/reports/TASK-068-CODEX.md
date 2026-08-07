# TASK-068 Codex report

## Result

Status: `ready_for_review`

Implemented the repository-only Phase C maintenance freeze and cross-model identity drift detector. Production Member
and LINE mapping maintenance remains frozen by default. No production service, database, Secret, notification,
deployment, schema/RLS change, ignored-user mapping, Person activation, or dual-write behavior was used or added.

Implementation commit: `a6b8b10` (`fix(identity): freeze legacy matching and detect cross-model drift`).

## Behavior

- `WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED` enables legacy match/ignore writes only when its value is exactly `true`.
  Missing, empty, differently-cased, false, numeric and unknown values fail closed.
- Both POST routes still require admin and CSRF checks, then return a fixed 503 before form parsing, ORM lookup/write or
  Discord notification while maintenance is disabled.
- The admin GET route remains available to authorized admins, lists pending rows, shows a maintenance notice and
  disables match/ignore controls. Demo behavior is unchanged.
- The checksummed SQL inventory is a read-only rollback transaction and returns only the fixed six-column aggregate
  contract. It checks the Phase A boundary, Member/Person state, reliable identities, pending/ignored candidates,
  qualification drift, duplicate/orphan links, and unexpected/inconsistent audit state.
- The validator rejects checksum mutation, missing/extra/duplicate/reordered fields or metrics, wrong value types,
  sensitive-looking values and every nonzero unsafe drift. Pending and ignored candidate counts are nonnegative,
  informational metrics.

## Verification

- Web Portal suite: 110 tests passed, 2 skipped because this Windows environment lacks `make`/`sh`.
- Full `tests/portal_data` suite against repository Compose PostgreSQL 16.4 on `127.0.0.1:55432`: 127 tests passed.
- TASK-068 PostgreSQL fixtures cover the Phase B-consistent state, safe pending/ignored candidates, and fail-closed
  detection for missing/wrong/unreliable identities, missing/extra/revoked qualification, duplicate subject, orphan
  Member link, and unexpected/inconsistent audit rows.
- `python -m compileall -q apps/web_portal shared_lib tools tests/portal_data`: passed using bundled Python 3.12.13.
- isort check for the three new Python modules: passed.
- `git diff --check`: passed.

The repository's baseline is Python 3.10, but the machine's registered Python 3.10 executable is unavailable and the
bundled runtime is Python 3.12.13. The bundled Black 26.3.1 process repeatedly produced no output and did not terminate,
including with one worker, so it was stopped; Black verification remains for review/CI. No source file was changed by
those stopped Black checks.

## Local-only boundary and remaining review items

- The PostgreSQL container used only the checked-in localhost-only Compose configuration and fake fixture credentials.
- The inventory was not run against production and no production drift conclusion is claimed.
- Enabling the maintenance flag would deliberately restore the existing legacy single-write path; this task does not
  make that path Phase C-safe and does not authorize enabling it in production.
- Work should review the fixed metric definitions and reproduce formatting/CI under the repository's Python 3.10
  environment before approval.
