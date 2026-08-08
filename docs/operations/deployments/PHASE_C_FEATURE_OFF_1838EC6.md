# Phase C feature-off production deployment package

Status: awaiting Owner approval; **not executable** until the missing current
production inventory is collected with the approved account and project.

This document prepares TASK-078 only. It does not authorize a Cloud Build,
image build/push, deploy, revision creation, traffic or environment mutation,
endpoint invocation, Scheduler action, Secret/IAM/database operation, or
notification.

## Locked local inputs

| Item | Value |
| --- | --- |
| Approved application source commit | `1838ec6fc77a74e23700f9cd29b8ea910c0a29fb` |
| Planning commit | `228861c99f929c9ff8c3defa39c80ef185aaad3e` |
| Project / region | `ntubtob-schedule-405614` / `asia-east1` |
| Shared source fingerprint | `bd3d932b5c5dc55695d73a203ffe9efbe24405fffd356993bcf7fc53a33a2298` |
| Shared sdist byte SHA-256 | `b1018a678c1ff0b44c9b0eadc89651d1d6947467c9f697534866a002b6eb8ab1` |
| Artifact package path/version | `shared_lib-0.0.1.tar.gz` / `0.0.1` |

The only difference from the approved source commit to the planning commit is
coordination documentation and `AGENTS.md`; no `shared_lib` source changed.
The same rebuilt artifact byte hash was copied to all three local deployment
contexts:

| Target | Local artifact path | SHA-256 |
| --- | --- | --- |
| Web Portal | `apps/web_portal/dist/shared_lib-0.0.1.tar.gz` | `b1018a678c1ff0b44c9b0eadc89651d1d6947467c9f697534866a002b6eb8ab1` |
| LINE webhook | `functions/line_webhook_handler/dist/shared_lib-0.0.1.tar.gz` | `b1018a678c1ff0b44c9b0eadc89651d1d6947467c9f697534866a002b6eb8ab1` |
| Notify cron | `apps/notify_cronjob_service/dist/shared_lib-0.0.1.tar.gz` | `b1018a678c1ff0b44c9b0eadc89651d1d6947467c9f697534866a002b6eb8ab1` |

`python -m tools.phase_c_rollout_preflight` passed for all Phase C, freeze and
maintenance values set to `false`. The offline controller also accepted the
planning checkout's all-off/unfrozen state with zero steps. Its source-commit
lock is the planning checkout commit, not a claim about the approved image tag.

## Required production inventory: blocked locally

The current shell has no `gcloud` or `gcloud.cmd` executable. Therefore none of
the following have been read or inferred:

| Target | Current ready revision | 100% traffic revision | Rollback revision | Non-secret flag vector |
| --- | --- | --- | --- | --- |
| Cloud Run `web-portal` | unverified | unverified | unverified | unverified |
| Gen2 function `line-webhook-handler` | unverified | n/a: Gen2 source recovery uses immutable GCS source | unverified immutable GCS bucket/object/generation | unverified |
| Cloud Run `notify-cronjob-service` | unverified | unverified | unverified | unverified |

Historical revision names in older deployment records are **not** valid rollback
targets for this package. Do not substitute them for a fresh read-only result.
The current Scheduler job name, URI and OIDC target are also unverified.

Before Owner approval, an authorized operator must run these read-only commands
and record only the returned revision names, traffic percentages, image digest,
ingress/auth classification, runtime identity and the four named flag values.
Do not redirect full service/function JSON to a terminal or a committed file,
because it can contain unrelated environment settings or Secret references.

```powershell
# Identity and target guard. Read-only; stop if account or project is unexpected.
gcloud auth list --filter=status:ACTIVE --format="value(account)"
gcloud config get-value project

# Cloud Run revision and traffic only.
gcloud run services describe web-portal --project ntubtob-schedule-405614 --region asia-east1 --format="yaml(status.latestReadyRevisionName,status.traffic,spec.template.metadata.annotations,metadata.labels)"
gcloud run services describe notify-cronjob-service --project ntubtob-schedule-405614 --region asia-east1 --format="yaml(status.latestReadyRevisionName,status.traffic,spec.template.metadata.annotations,metadata.labels)"

# Gen2 function metadata only; do not invoke the function. Record the complete
# immutable storage source identity (bucket, object and generation) separately
# from the other non-secret metadata.
gcloud functions describe line-webhook-handler --gen2 --project ntubtob-schedule-405614 --region asia-east1 --format="yaml(state,serviceConfig.service,serviceConfig.uri,serviceConfig.runtime,serviceConfig.availableMemory,serviceConfig.serviceAccountEmail,buildConfig.entryPoint,buildConfig.dockerRepository,buildConfig.source.storageSource,labels)"

# Scheduler metadata only. Do not run, pause, resume or modify a job.
gcloud scheduler jobs list --project ntubtob-schedule-405614 --location asia-east1 --format="table(name.basename(),schedule,timeZone,httpTarget.uri,httpTarget.oidcToken.serviceAccountEmail,state)"
```

For each Cloud Run service and the Gen2 function, extract only these exact
non-secret values from the runtime environment using the cloud console's
configuration view or an approved redacting procedure:

| Runtime | Required exact values |
| --- | --- |
| Web Portal | `PORTAL_DATA_PHASE_C_ENABLED=false`, `PORTAL_DATA_ROLLOUT_FREEZE_ENABLED=false`, `WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED=false` |
| LINE webhook | `PORTAL_DATA_PHASE_C_ENABLED=false`, `PORTAL_DATA_ROLLOUT_FREEZE_ENABLED=false` |
| Notify cron | `PORTAL_DATA_PHASE_C_ENABLED=false`, `PORTAL_DATA_ROLLOUT_FREEZE_ENABLED=false` |

Any missing, empty, case-variant or non-`false` value blocks this feature-off
deployment. Do not display or copy other variables, Secret bindings or values.

## Owner approval fields

The following values are intentionally blank. The deployment commands below are
invalid until Owner fills every field from the fresh read-only inventory.

| Approval field | Required value |
| --- | --- |
| `WEB_PORTAL_ROLLBACK_REVISION` | Ready, 100%-traffic current revision from the inventory |
| `LINE_WEBHOOK_ROLLBACK_SOURCE_BUCKET` | Current function's approved immutable GCS source bucket |
| `LINE_WEBHOOK_ROLLBACK_SOURCE_OBJECT` | Current function's approved immutable GCS source object |
| `LINE_WEBHOOK_ROLLBACK_SOURCE_GENERATION` | Current function's approved immutable GCS source generation |
| `NOTIFY_ROLLBACK_REVISION` | Ready, 100%-traffic current revision from the inventory |
| `WEB_PORTAL_LINE_LOGIN_SECRET_REF` | Existing approved resource:version reference; never the value |
| `WEB_PORTAL_SESSION_SECRET_REF` | Existing approved resource:version reference; never the value |
| Current traffic / image digest / runtime identity | Fresh per-target values, recorded without secrets |
| Scheduler metadata | Existing relevant job name and target, recorded without invocation |

## Commands prepared but not executed

These commands are a review artifact, not authorization. They must be copied
only after the Owner has replaced each angle-bracket field with an approved,
freshly inventoried non-secret value. The order is Web Portal, LINE webhook,
then notify cron. Observe 15 minutes of metadata/readiness after each approved
target; do not invoke business endpoints.

```powershell
# DO NOT EXECUTE without Owner approval and all fields above locked.
# Web Portal wrapper performs its own exact SHA and rollback validation.
& <PYTHON> tools/deploy_web_portal.py --execute `
  --approved-commit 1838ec6fc77a74e23700f9cd29b8ea910c0a29fb `
  --rollback-revision <WEB_PORTAL_ROLLBACK_REVISION> `
  --line-login-secret-ref <WEB_PORTAL_LINE_LOGIN_SECRET_REF> `
  --session-secret-ref <WEB_PORTAL_SESSION_SECRET_REF>

# LINE webhook Gen2 deployment uses the existing repository target. Do not
# alter its runtime, entry point, public signature boundary or Secret bindings.
make deploy-line-webhook-handler

# Notify cron wrapper performs exact SHA and rollback validation.
& <PYTHON> tools/deploy_scheduled_service.py notify-cronjob-service --execute `
  --approved-commit 1838ec6fc77a74e23700f9cd29b8ea910c0a29fb `
  --rollback-revision <NOTIFY_ROLLBACK_REVISION>
```

The LINE target has no existing fail-closed execute wrapper that accepts an
exact rollback identity. Its recovery boundary is therefore the repository's
existing [Gen2 immutable-source rollback runbook](../GEN2_FUNCTION_ROLLBACK.md):
an approved Cloud Functions v2 `PATCH` changes only `buildConfig.source` to a
freshly inventoried immutable GCS `bucket` / `object` / `generation`. This
package blocks its execution until the Owner records that exact triple and
separately approves both the existing deployment mutation and any rollback.

After each approved deployment, run only fresh read-only configuration/revision
commands from the inventory section. Confirm the new revision is Ready, traffic
is exactly as approved, ingress/auth and runtime identity did not drift, and the
listed feature flags remain exactly `false`. Web Portal's public home/demo and
notify health checks require separate Owner authorization; webhook has no
production invoke/smoke in this task.

## Rollback commands prepared but not executed

Rollback is a new production mutation and requires a new explicit Owner
decision after an observed failure. Preserve schema `0004`, secrets, IAM,
Scheduler and production data. Do not use a guessed revision.

```powershell
# DO NOT EXECUTE: only after a new Owner rollback decision.
gcloud run services update-traffic web-portal --project ntubtob-schedule-405614 --region asia-east1 --to-revisions <WEB_PORTAL_ROLLBACK_REVISION>=100
gcloud run services update-traffic notify-cronjob-service --project ntubtob-schedule-405614 --region asia-east1 --to-revisions <NOTIFY_ROLLBACK_REVISION>=100
```

LINE webhook Gen2 rollback is an official Functions v2 PATCH, not a Cloud Run
revision traffic update. First complete every Owner field below and the
pre-checks; then an authorized operator may construct (but must not commit)
this request body with the exact read-only-inventoried source identity:

```text
PATCH https://cloudfunctions.googleapis.com/v2/projects/ntubtob-schedule-405614/locations/asia-east1/functions/line-webhook-handler?updateMask=buildConfig.source
Content-Type: application/json
```

```json
{
  "name": "projects/ntubtob-schedule-405614/locations/asia-east1/functions/line-webhook-handler",
  "buildConfig": {
    "source": {
      "storageSource": {
        "bucket": "<LINE_WEBHOOK_ROLLBACK_SOURCE_BUCKET>",
        "object": "<LINE_WEBHOOK_ROLLBACK_SOURCE_OBJECT>",
        "generation": "<LINE_WEBHOOK_ROLLBACK_SOURCE_GENERATION>"
      }
    }
  }
}
```

### LINE webhook Gen2 rollback pre-check, PATCH boundary and post-check

This is a prepared request shape only. It is **not** a command to execute and
does not grant a bearer token, API permission or production-mutation approval.
Use the official Functions v2 `functions.patch` endpoint and the exact field
mask `updateMask=buildConfig.source`; do not add another field to the body or
field mask. In particular, do not change runtime, entry point, service account,
ingress, Secret bindings, labels, trigger or traffic-related configuration.

Before a new explicit Owner rollback decision, the authorized operator must
record all of the following without printing environment values or Secret
references:

- `LINE_WEBHOOK_ROLLBACK_SOURCE_BUCKET`,
  `LINE_WEBHOOK_ROLLBACK_SOURCE_OBJECT` and
  `LINE_WEBHOOK_ROLLBACK_SOURCE_GENERATION` from the fresh read-only
  `buildConfig.source.storageSource` inventory;
- function name, project and region matching this package;
- current function state and service URI, runtime, entry point, service account
  and ingress/auth classification; and
- explicit Owner approval of the immutable source triple, the narrow PATCH
  field mask, the observed failure and the no-invocation verification plan.

After the long-running PATCH operation reports completion, repeat the same
read-only `gcloud functions describe` command. Confirm `state=ACTIVE` and that
the resolved `buildConfig.source.storageSource` bucket, object and generation
match the approved triple exactly. Also confirm runtime, entry point, service
account, ingress/auth classification, Secret bindings and the two named
feature-off flags did not drift. Do not invoke the webhook or run Scheduler
work as a rollback check.

Stop immediately on a missing/changed flag, non-ready revision, traffic drift,
unexpected public/private boundary, startup/import failure, error increase,
unexpected notification, identity/attendance mutation, or any possible secret
exposure. Do not continue to the next target or activation task.
