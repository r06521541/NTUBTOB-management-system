# Phase C application rollout and rollback runbook

Status: repository-only readiness evidence for TASK-076. This document does not
authorize a production deployment, runtime flag mutation, traffic change,
Scheduler invocation, database operation, or real notification. TASK-077 must
lock exact commits, revisions, flag values, observation ownership, and rollback
targets and obtain Owner approval before any external mutation.

## Locked database and runtime assumptions

- Production schema is already `0004_phase_c_identity_lifecycle`; emergency
  application rollback retains 0004 and never runs a downgrade, `DROP`, cleanup,
  restore, or audit mutation.
- `PORTAL_DATA_PHASE_C_ENABLED` and
  `WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED` remain exactly `false` until a later
  approved activation window.
- Missing, empty, case-variant, padded, or unknown flag values are runtime-off.
  Maintenance requested while Phase C is off is invalid and effectively off.
- The offline preflight accepts only explicit `true` or `false`; it never reads
  production env files or Secret values.

## Caller and artifact matrix

| Deployment unit | Direct Phase C caller/data flow | Shared artifact required | Existing deployment entry |
| --- | --- | --- | --- |
| Web Portal | LINE principal/session, pending Member/Person approval, identity maintenance, Person attendance read/write and roster/admin pages | yes | `tools/deploy_web_portal.py`; `makes/deploy_apps.mk` `deploy-web-portal` |
| LINE webhook | Attendance postback resolves the LINE principal and writes a Person reply when enabled | yes | `makes/deploy_functions.mk` `deploy-line-webhook-handler` |
| notify cron | Shared attendance analyzer supplies Person-aware counts and formal/display names | yes | `tools/deploy_scheduled_service.py notify-cronjob-service`; `makes/deploy_apps.mk` `deploy-notify-cronjob-service` |
| shared library | Flag state machine, lifecycle repository, 0004 models, attendance compatibility projection | source artifact | `makes/shared_lib.mk` |
| game broadcast | Not a Phase C caller; it does not read these flags or the lifecycle repository | no rollout deployment | excluded from TASK-076 |

All three rollout units require `shared_lib-0.0.1.tar.gz`. Each artifact is
independently verified against every current `shared_lib/shared_module/**/*.py`
source file and `shared_lib/setup.py`; gzip byte hashes may differ because sdist
metadata is not deterministic. The artifact path and package version remain
exact.

## Offline artifact preparation and preflight

Use only a clean reviewed task checkout. These commands build local ignored
artifacts; they do not call GCP.

PowerShell, using the configured Python executable:

```powershell
Push-Location shared_lib
python setup.py sdist --dist-dir dist
Pop-Location
Copy-Item shared_lib/dist/shared_lib-0.0.1.tar.gz apps/web_portal/dist/shared_lib-0.0.1.tar.gz -Force
Copy-Item shared_lib/dist/shared_lib-0.0.1.tar.gz functions/line_webhook_handler/dist/shared_lib-0.0.1.tar.gz -Force
Copy-Item shared_lib/dist/shared_lib-0.0.1.tar.gz apps/notify_cronjob_service/dist/shared_lib-0.0.1.tar.gz -Force
python -m tools.phase_c_rollout_preflight --web-portal false --line-webhook false --notify-cron false --identity-maintenance false
```

Unix-like environments may use `python3`, `cp`, and the same module command.
The preflight also verifies that all example environments default both features
off and that Docker/gcloud contexts exclude env files, credentials, private
backup/database files, and unrelated `dist` content. Its output contains only
the mode and a source-content fingerprint, never env or credential values.

Run the preflight again with all three Phase C arguments `true` and maintenance
`false` before preparing an activation package. Run it with all four `true` only
for the final maintenance stage. Any single-service or two-service vector is
rejected.

## Supported and prohibited states

| Schema/artifacts and runtime state | Classification | Boundary |
| --- | --- | --- |
| 0004 + current production apps + all flags off | supported legacy | Confirmed production starting point; no Phase C runtime write |
| 0004 + new artifacts + all flags off | supported feature-off | Required deployment and rollback baseline |
| Portal on; webhook/notify off | prohibited for normal traffic | Phase C reader can project new legacy Member rows, but guest visibility and cross-service behavior are not consistent |
| Webhook on; Portal/notify off | prohibited for normal traffic | Legacy readers safely ignore Member-less guest rows, but guests are not visible until every reader is on |
| Notify on; Portal/webhook off | prohibited for normal traffic | Read compatibility exists, but user-facing writers/readers are not one coordinated contract |
| Any two services on | prohibited for normal traffic | Same bounded visibility inconsistency; do not use as an observation stage |
| All three Phase C on; maintenance off | supported Phase C | Required first active state |
| All three Phase C on; maintenance on | supported final state | Enable only after the Phase C state has passed observation |
| Maintenance on while Portal Phase C off | invalid, fail closed | Runtime disables maintenance; preflight rejects the plan |
| Any rollback transition with only some flags off | transition only | Freeze attendance mutations and scheduled notifications until all flags are off |

Compatibility adapters deliberately preserve data across a bounded transition:
Phase C readers resolve a legacy Member-only attendance row through
`members.person_id`, and legacy readers ignore a Phase C guest row with no fake
Member instead of crashing. These adapters prevent corruption; they do not make
mixed-mode normal traffic an accepted product state.

## Stage 1: deploy feature-off artifacts

Owner approval is required before using any existing deployment wrapper.

1. Lock the exact source commit, the three newly built artifact source
   fingerprints, each target revision/rollback revision, and confirm all flags
   will remain exactly `false`.
2. Deploy Web Portal, LINE webhook, and notify cron artifacts one at a time.
   Feature-off makes service order data-compatible; use the exact order locked in
   TASK-077 so rollback evidence remains unambiguous.
3. After each unit becomes ready, observe for at least 15 minutes before the next
   unit. Allowed checks are process health, revision readiness, traffic/IAM and
   runtime configuration metadata, plus existing feature-off behavior that has no
   notification side effect.
4. Allowed Web Portal smoke checks: public home status and production demo 404.
   Allowed notify check: authenticated `GET /healthz`, which has no DB or external
   calls. For the webhook, inspect readiness/configuration only; do not fabricate
   or send a production LINE event.
5. Stop on startup/import error, unexpected DB query from health, 5xx increase,
   IAM/public-boundary drift, missing artifact/config, any flag not exactly off,
   unexpected notification, or identity/attendance write.

After all three units pass, observe the feature-off set together for at least 30
minutes. Existing legacy behavior must remain the acceptance baseline; no Phase C
identity row should be created by a feature-off request.

## Stage 2: coordinated Phase C activation

There is no atomic cross-service environment update in this repository. TASK-077
must therefore provide an Owner-approved bounded activation window that prevents
attendance mutations and scheduled attendance notifications while revisions are
temporarily mixed. If that freeze cannot be established and verified, activation
is blocked; do not claim that a sequential flag update is atomic.

1. Confirm feature-off revisions remain the known-good rollback set, 0004 is
   unchanged, and the all-on/maintenance-off preflight passes.
2. Begin the explicit attendance/notification freeze. Do not invoke LINE
   postbacks, Portal attendance writes, cron notification routes, identity
   maintenance, or ad-hoc SQL during the transition.
3. Activate Phase C on read surfaces first: Web Portal, then notify cron. Verify
   readiness/config metadata only; these mixed states are not opened to normal
   traffic or scheduled invocation.
4. Activate LINE webhook last. Verify all three flags are exactly `true`, then end
   the freeze.
5. Observe the all-on/maintenance-off state for at least 30 minutes. Use aggregate
   error/latency counters and fixed classifications only. Stop for principal
   resolution failures, attendance projection disagreement, duplicated audit or
   attendance effects, unexpected guest/member names, notification errors, or any
   secret/identifier in logs.
6. Only after this observation may a separately approved smoke use one explicitly
   designated fictional/non-production identity. TASK-076 itself authorizes no
   production write, endpoint invoke, or notification.

## Stage 3: identity maintenance

Identity maintenance is the final flag. It must never be an activation shortcut.

1. Confirm every Phase C service is still on and stable, the all-four-true
   preflight passes, an active allowlisted admin principal remains available, and
   the exact mutation test/rollback plan has separate Owner approval.
2. Enable maintenance only on Web Portal. Observe for at least 30 minutes before
   any approved mutation.
3. A later approved mutation must be one bounded, independently reversible test
   case with CSRF, reason, request ID, audit verification and duplicate/retry
   check. Do not use a real mutation as a generic health check.
4. Stop on an invalid flag relationship, loss of last-admin access, cross-model
   drift, unexpected qualification restoration, duplicate audit, or notification
   side effect.

## Rollback

First layer—coordinated flags off:

1. Re-enter the attendance/notification freeze.
2. Turn maintenance off first.
3. Turn Phase C off in the reverse activation order: LINE webhook, notify cron,
   then Web Portal. Do not reopen normal traffic while only some flags are off.
4. Verify the all-off preflight/runtime metadata, then end the freeze. Retain 0004
   and all committed data/audits.

Second layer—known-good revisions:

1. With every flag confirmed off, shift each deployment unit to the exact
   feature-off rollback revision locked by TASK-077. Cloud traffic mutation and
   Function rollback require Owner approval.
2. Verify readiness, IAM/public boundary, exact traffic and feature-off health
   after each shift. Observe 15 minutes per unit and 30 minutes for the complete
   rollback set.
3. Never downgrade schema 0004, delete identity/attendance/audit rows, disable an
   audit trigger, run cleanup SQL, or restore a backup as application rollback.
   Semantic data repair requires a separate forward-recovery task.

## Evidence required for TASK-077

- exact reviewed commit and all three feature-off revision names;
- local preflight mode/fingerprint and complete test results;
- exact non-secret flag plan for each deployment unit;
- named operator/observer, freeze mechanism, start/end time and stop authority;
- 15/30-minute observation windows and aggregate dashboards/log filters;
- first-layer flag-off commands and second-layer exact traffic/revision commands;
- explicit Owner approvals for deployment, flag mutation, freeze/external
  coordination, any production smoke, and rollback traffic mutation.
