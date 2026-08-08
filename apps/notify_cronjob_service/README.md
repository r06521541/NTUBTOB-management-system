# Notify Cronjob Service

Private Cloud Run service for scheduled team announcements and attendance
summaries.

## Health check

`GET /healthz` returns a process-level JSON health response. It does not query
the database or call LINE, Discord, the crawler, weather, or other external
services. The endpoint therefore confirms only that Flask is serving routes;
it does not prove that business dependencies are available.

The Cloud Run service remains private. Calling this endpoint after deployment
requires an identity token for an authorized identity. Do not use the existing
notification trigger routes as smoke tests.

When `PORTAL_DATA_PHASE_C_ENABLED` is exactly `true`, the shared attendance
analyzer emits eligible Person participants, including bounded guest players,
using formal/Member names before display-name fallback. Guest players are not
part of the unanswered team-player denominator. The setting defaults to false;
TASK-070 does not authorize changing production runtime configuration.

Phase C activation is a coordinated three-service contract, not an independent
cron toggle. Follow
`docs/operations/data/PORTAL_DATA_PHASE_C_APPLICATION_ROLLOUT.md` and keep this
service private; do not use notification routes as smoke checks.

When `PORTAL_DATA_ROLLOUT_FREEZE_ENABLED` is exactly `true`,
`POST /run-game-attendance-count` returns HTTP 200 with the fixed JSON
classification `rollout_freeze` before database, analyzer, clock, LINE or Discord
work. This successful no-op avoids Scheduler retry storms during a separately
approved transition. `GET /healthz` and the non-attendance future-game route keep
their existing contracts. The freeze is not authorization to invoke either route.
