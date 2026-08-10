# TASK-098 Codex delivery report

## Outcome

TASK-098 adds a schema-neutral, read-only Game command center for runtime-
allowlisted production admins and request-time active Person officers. It also
adds honest attendance insights and a coarse/fine lineup lab whose drafts exist
only in the current browser tab's `sessionStorage`.

Planning commit: `3cc81408ac822b04b8aa590a3f96ad9acdb8848f`

Implementation commit: `3bb2b6b69ad2bd33dfaa5a258dc5ee38bb6c7d53`

## Delivered

- Added GET-only `/manage/games`, `/manage/games/<int:game_id>`,
  `/manage/game-insights`, and `/manage/games/<int:game_id>/lineup-lab` routes.
  They use the existing invited-Game reader and Phase C attendance summary;
  malformed scope, missing Game, unavailable reads, and cancelled-Game lineup
  requests fail closed.
- Added a bounded Game-route authorization bridge. Every request reloads the
  lifecycle principal. Production grants these routes only to an active officer
  or a runtime-allowlisted admin; Person admin alone remains denied. The bridge
  does not grant the existing identity, qualification, Person access, member,
  notification, or audit management capabilities.
- Corrected local-preview principal mapping so Person officer/admin access is not
  promoted into the portal's global Officer/Admin roles. Preview officer/admin
  parity is limited to the new Game routes, while Basic and all preview mutation
  POSTs remain denied.
- Limited Game reads to invited Games within one year before/after request time,
  de-duplicated and capped at 250 rows. The UI reports current recorded reply
  counts, current effective `team_player`/`guest_player` summaries, unresolved
  current team-player counts, future 7/30-day counts, cancellation count, data
  time, and incomplete-read states. It does not claim historical response rates,
  historical roster snapshots, player performance, transport, or equipment data.
- Added local templates and responsive styling for command center, detail,
  insights, empty/error states, and lineup lab. Fine lineup includes P/C/1B/2B/
  3B/SS/LF/CF/RF/DH on an accessible native HTML/CSS/SVG field plus synchronized
  selects; coarse lineup supports coach/pitcher/catcher/infield/outfield, including
  Member player-coaches.
- Added a local-only script that stores separate coarse/fine drafts in
  `sessionStorage`, prevents duplicate formal positions, confirms replacement,
  detects stale candidate IDs, supports independent reset/copy/print, and clears
  all drafts on logout or preview identity change. It contains no fetch/XHR,
  beacon, API, database, server-session, cache, audit, log, or notification caller.

## Verification

- Bundled Python targeted helper/static suite: `6 tests`, `OK`.
- Bundled Python targeted route/security suite: `78 tests`, `OK`.
- Bundled Python full Web Portal suite: `154 tests`, `OK`, `2 skipped`.
- Bundled Python `py_compile` for the affected app/helper/tests: passed.
- Black 24.4.2 formatter API and isort 5.13.2 with `profile=black`, per affected
  Python file: passed. The bundled Windows Black CLI stalled without output and
  was terminated in accordance with `AGENT_ENVIRONMENT.md`.
- `git diff --check`: passed before report/handoff finalization and rerun before
  commit.
- Localhost-only desktop browser QA at 1280x900: preview admin login, command
  center, Game detail, insights, and lineup lab rendered from the actual routes;
  all pages had no horizontal overflow. The lineup page exposed 12 native selects,
  an SVG `title`/`desc`, local assets, and the read-only/session-only warning.
- Mobile/touch/focus/print static contracts: passed, including the <=700px layout,
  44px controls, `:focus-visible`, native selects, and print rules.

## Boundaries and review notes

- Database revision remains `0004_phase_c_identity_lifecycle`. No schema, model,
  migration, controlled SQL, export contract, database fixture, or PostgreSQL
  integration path changed, so no PostgreSQL 15/16 matrix was run.
- No Game, Roster, Attendance, Person, Identity, Qualification, notification, or
  external-service mutation was added or executed. No production, deployment,
  Secret, IAM, Scheduler, crawler/weather, LINE, or Discord operation occurred.
- The existing read model has no per-Game invitee snapshot or exact historical
  roster/response denominator. The implementation therefore shows only current
  effective attendance/qualification projections and explicitly bounded counts.
- Actual 390px browser evidence is not claimed. After desktop QA, the in-app
  browser security policy terminated further access to the localhost tab before
  the 390px pass; no bypass was attempted. Mobile behavior remains covered by the
  offline DOM/CSS contracts and requires Work/hosted browser review for final
  visual evidence.
- Hosted Python 3.10 and any final browser acceptance remain for the final PR CI/
  Work review. No PR was created by Codex.
