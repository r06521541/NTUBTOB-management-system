# Mobile staging operator package

This runbook prepares an isolated staging activation for a later Owner-approved
task. Nothing in this document authorizes resource creation, database migration,
deployment, IAM, Secret, LINE Console changes, real login, notification, signing
or distribution.

## Fixed boundary

- Production project `ntubtob-schedule-405614` is always rejected.
- Target service is `mobile-api-staging` in `asia-east1`, minimum instances 0,
  maximum 1 to 3. An update candidate receives no traffic; Cloud Run requires
  the first revision of a bootstrap service to receive 100% service traffic,
  so that bootstrap remains private until a separate IAM approval.
- Staging uses a dedicated project and dedicated PostgreSQL database at exact
  revision `0005_mobile_auth_api_foundation`.
- Runtime names are `PORTAL_DATA_DATABASE_URL`, `MOBILE_API_AUDIENCE`,
  `MOBILE_ACCESS_SIGNING_KEY`, and `MOBILE_REFRESH_REPLAY_KEY`. Only the LINE
  channel ID/audience is plain configuration; the other three are Secret
  references. This package never creates, reads or prints their values.
- The provider subject is private execution input. It must only be supplied as
  `MOBILE_STAGING_PROVIDER_SUBJECT` in a private process environment. It must
  never appear in a command line, transcript, manifest, hash or repository file.

## Discovery and exact Owner checkpoint

1. Choose a dedicated non-production project and database. Owner supplies the
   database provider and immutable provider project/resource ID independently of
   the DSN. Produce staging and production SHA-256 identities over canonical
   `provider/resource/postgresql://host:port/database`. The operator rejects
   equality or mismatch and never trusts a DSN to label itself staging. The
   manifest exposes only provider, approved alias and resource/target hashes.
2. Use `tools/mobile_staging_preflight.py` helpers with an injected/read-only
   runner. Cloud inventory only uses `gcloud config get-value`, Cloud Run list and
   Secret metadata list. Database inventory starts an explicit read-only
   transaction, requires revision 0005 and rejects production-shaped People or a
   partial TASK-112 fixture.
3. Render the redacted manifest with `redacted_manifest`. It contains no host,
   username, password, provider subject or Secret payload.
4. Main Work presents the exact project/billing/APIs, database provider/resource
   and monthly cost, LINE Provider and Developing channel, separate dedicated
   build and runtime service accounts,
   IAM/public ingress, Secret resource versions, scaling, full commit, image
   digest, migration/seed counts, smoke and cleanup plan to Owner.
5. Store Owner approval JSON and operator recovery state outside the repository.
   The approval must use the exact schema enforced by `load_approval`; extra or
   missing fields fail closed.

The LINE Login channel must remain `Developing`, under the same Provider as the
related channels. Configure Mobile app identities `tw.org.ntubtob.portal` for
Android and iOS. Channel ID is non-secret; no channel secret is required by the
official ID-token verification flow. This task does not operate LINE Console.

## Local PostgreSQL rehearsal

Use only an isolated local database named `ntubtob_portal_local`:

```powershell
$env:PORTAL_DATA_DATABASE_URL = 'postgresql+psycopg2://<local-only>'
python tools/setup_portal_data_legacy.py
python -m alembic upgrade 0005_mobile_auth_api_foundation
$env:MOBILE_STAGING_PROVIDER_SUBJECT = '<private-fake-test-value>'
python tools/mobile_staging_seed.py
$env:MOBILE_STAGING_ACTION = 'cleanup'
python tools/mobile_staging_seed.py
```

The fixture uses three fictional active Basic People, bounded guest-player
qualifications, three future Games, multiple attendance states and exactly one
private tester mapping. Seed is retry-safe; partial rows, changed labels or a
different tester mapping stop both seed and cleanup. Cleanup validates the exact
fixture before deleting it. Output contains counts only.

## Remote data operation

`tools/mobile_staging_data.py` defaults to a redacted, zero-mutation plan. A
future approved execution gates the private DSN with provider/resource identity.
For an exact empty dedicated database it uses one controlled connection and one
PostgreSQL transaction to execute the repository-owned legacy fixture, stamp
`0001_legacy_baseline`, and upgrade through exact 0005. It then verifies the
complete table/legacy-backfill fingerprint, seeds the separate TASK-112
fictional fixture, and performs a second read-only post-check.

The normal Alembic CLI remains localhost-only. Remote migration is possible only
through the operator-injected Alembic connection after database identity
validation; no environment flag can turn the general CLI into a remote runner.
The canonical recovery states are `not_started` (no `ntubtob` schema),
`seed_pending` (exact 0005 legacy fixture, no mobile fixture), and `completed`
(both exact fixtures). A schema without the exact table set, unknown rows,
partial fixture IDs, an unexpected revision, or legacy attendance/backfill drift
stops recovery without retry. Database errors are returned as redacted operator
errors without the DSN.

Legacy fixture IDs 9101 through 9604 remain repository-owned and are not
replaced by the mobile seed. Migration 0004 links the attendance-bearing legacy
Member to its inactive Person/qualification/audit row. Mobile seed and cleanup
own only IDs -112001 through -112003 and reply types 1 through 5 when they were
fixture-created. Cleanup does not remove the legacy fixture. Downgrade, database
deletion, or recreation remains a separate exact Owner approval. This task did
not run this operator against any remote database.

On Windows, invoke the data operator as a repository module so both `tools` and
`shared_lib` resolve from the repository root:

```powershell
python -m tools.mobile_staging_data --approval C:\private\candidate-approval.json --execute
```

The database URL and private tester subject remain process-only environment
inputs. A failed import, identity check or recovery check performs no mutation;
do not retry a later-stage failure until read-only recovery classifies it.

### Attendance fixture repair

TASK-118 adds one bounded forward repair for the original TASK-112 fictional
attendance state. Run `--inspect-attendance-repair` first. The only executable
pre-state is exact revision 0005 with all three original fixture replies still
timestamped at `2035-01-10T10:00:00Z` and exactly the two proven additional
reply IDs `1` and `2` for Person/Game `-112001`. Both rows must be `undecided`, have
null legacy user/member ownership, and each must match its own UTC window:
ID `1` is `2026-08-19T15:39:15Z` through `15:39:35Z`; ID `2` is
`2026-08-19T15:44:45Z` through `15:45:05Z` (inclusive). These windows bound the
saved request timestamps `15:39:23.883620Z` and `15:44:55.572527Z`; they allow
only the small request-to-`utc_now()` persistence delay. Any different count,
reply, relationship, ID-specific timestamp or fixture content is drift and
stops without mutation.

After a separate Owner/Main Work execution checkpoint, the existing private
candidate approval and database identity gate may invoke
`--execute-attendance-repair`. One transaction deletes only the two inspected
row IDs and changes only the three TASK-112 reply timestamps to deterministic
`2000-01-01T00:00:00Z`. Its postcheck must report `state=repaired`, zero hidden
rows and `removed_hidden_rows=2`. A retry after an exact completed state is a
zero-delta success. After an uncertain result, inspect again; never blindly
rerun or use ad-hoc SQL. The repair does not mutate schema, notification state,
production data or any non-fictional Person/Game.

### Fictional Officer acceptance state

TASK-119 adds a separate bounded state machine for the already-linked fictional
tester only. First run `--inspect-officer`; it is read-only and accepts only
revision `0005` plus the complete TASK-112/TASK-118 fixture. The only mutable
Person is `-112001`; every other fixture row, identity, qualification, Game,
reply, legacy audit, audit request ID, access level and version is exact-checked.

The accepted semantic states are: `baseline` (active Basic, version 1, no
TASK-119 audit); `granted` (active Officer, version 2, exactly one fixed
TASK-119 grant audit); and `restored` (active Basic, version 3, exactly the
fixed grant and restore audit pair). The task-owned audit IDs and request IDs
are fixed in repository code. Audits are append-only: restore never deletes or
updates either audit and therefore returns to a semantic Basic baseline, not
the raw pre-grant database bytes. Unknown audit rows, request IDs, versions,
identity links or non-fixture rows are drift and stop before mutation.

With the existing private candidate approval and identity gate, the bounded
commands require the same private, process-only tester-subject environment input
used by the fictional seed. It is validated against the linked identity but is
never printed, persisted, or included in an approval artifact. The commands are:

```powershell
python -m tools.mobile_staging_data --approval C:\private\candidate-approval.json --inspect-officer
python -m tools.mobile_staging_data --approval C:\private\candidate-approval.json --grant-officer
python -m tools.mobile_staging_data --approval C:\private\candidate-approval.json --restore-basic
```

`--grant-officer` changes only exact `baseline` to `granted`; retrying exact
`granted` is a zero-delta success. `--restore-basic` changes only exact
`granted` to `restored`; retrying exact `restored` is likewise zero-delta. Any
uncertain result requires another read-only inspection; do not use ad-hoc SQL,
delete audit rows, or retry an unclassified state. This operator does not make
the Officer account an administrator, alter production, send notifications, or
change the mobile/Web role policy.

## Build, candidate, promotion and recovery

There are two separate Owner approvals and cost checkpoints:

1. Build approval fixes project, full commit, exact build ID, image URI and
   dedicated build service account, but has no digest. `build` creates a fresh
   shared sdist from that clean HEAD in a temporary directory, copies it into the
   Docker context only for the build, validates the returned build ID/image URI/
   digest, records private state, and removes both copies in `finally`. A stale
   checked-in or pre-existing dist artifact is rejected. If the response is lost,
   `recover-build` describes the exact build ID; it never resubmits the build.
2. Main Work presents the resulting digest and build evidence to Owner. Candidate
   approval fixes that existing digest and either `bootstrap` or `update` mode.
   `candidate` only deploys the approved digest and never invokes Cloud Build.

Default invocation performs no cloud command:

```powershell
python -m tools.mobile_staging_operator
```

With a private approval artifact and private database URL, omitting `--execute`
still only prints a redacted manifest:

```powershell
$env:MOBILE_STAGING_DATABASE_URL = '<private-dedicated-staging-dsn>'
python -m tools.mobile_staging_operator --approval C:\private\approval.json
```

A later task needs the matching fresh Owner approval before each mutation:

```powershell
python -m tools.mobile_staging_operator --approval C:\private\build-approval.json --state-file C:\private\build-state.json --execute build
python -m tools.mobile_staging_operator --approval C:\private\build-approval.json --state-file C:\private\build-state.json --execute recover-build
python -m tools.mobile_staging_operator --approval C:\private\candidate-approval.json --state-file C:\private\candidate-state.json --execute candidate
python -m tools.mobile_staging_operator --approval C:\private\candidate-approval.json --state-file C:\private\candidate-state.json --execute recover-candidate
python -m tools.mobile_staging_operator --approval C:\private\approval.json --state-file C:\private\state.json --execute promote
python -m tools.mobile_staging_operator --approval C:\private\approval.json --state-file C:\private\state.json --execute rollback
```

Cloud Run rejects `--no-traffic` when creating a new service. The operator
therefore deploys a bootstrap revision as the private service's required 100%
traffic target, while update candidates use `--no-traffic`. Service traffic is
not public authorization: bootstrap remains inaccessible to unauthenticated
callers until a separate IAM approval. Revision describe remains image/readiness
evidence and service describe is authoritative for traffic. Bootstrap requires
no prior service and `rollback_revision=null`; failed bootstrap cleanup or
service deletion needs separate approval. Update requires one exact baseline
revision at 100% before candidate promotion and can roll back to it. Both modes
reject traffic, digest, ingress, runtime identity or scaling drift outside their
exact mode contract.
`recover-candidate` is read-only and never redeploys. Rollback restores 100%
traffic only in update mode;
candidate/image deletion and full staging cleanup remain separately approved
cost-bearing actions.

Cloud Run semantics checked against the official
[deploy documentation](https://cloud.google.com/run/docs/deploying),
[`gcloud run deploy` reference](https://cloud.google.com/sdk/gcloud/reference/run/deploy),
and [traffic rollout documentation](https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration).

The operator never runs project/API/billing/database/Secret/service-account/IAM
or LINE-channel creation. Public ingress and IAM remain Owner-controlled steps.

## Flutter staging command template

After staging exists, Flutter Domain Work may use this value-free template:

```sh
flutter build apk \
  --dart-define=APP_FLAVOR=staging \
  --dart-define=CLIENT_MODE=real \
  --dart-define=API_BASE_URL=https://<mobile-api-staging-origin-without-api-v1> \
  --dart-define=LINE_CHANNEL_ID=<numeric-developing-channel-id>
```

Do not put a channel secret, database URL, provider subject or app session key in
the build. Do not upload, sign or distribute an APK under this task.

## Tabletop and cleanup

Sequence: read-only discovery, redacted manifest, Owner exact approval, local
artifact validation, mode-specific candidate, revision/digest/runtime-reference
post-check, explicit promotion, smoke, then rollback if needed. Expected future
external mutations are exactly one build/image upload, one Cloud Run candidate
and, for update mode, one explicit traffic update. Cleanup may delete the candidate,
image, staging data/database and eventually the dedicated project only under a
separate approval that includes residual billing checks.
