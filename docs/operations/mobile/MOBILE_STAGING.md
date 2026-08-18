# Mobile staging operator package

This runbook prepares an isolated staging activation for a later Owner-approved
task. Nothing in this document authorizes resource creation, database migration,
deployment, IAM, Secret, LINE Console changes, real login, notification, signing
or distribution.

## Fixed boundary

- Production project `ntubtob-schedule-405614` is always rejected.
- Target service is `mobile-api-staging` in `asia-east1`, minimum instances 0,
  maximum 1 to 3, and a new candidate receives no traffic.
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
future approved execution gates the private DSN with provider/resource identity,
runs the repository Alembic upgrade to exact 0005, seeds the fictional fixture,
then performs a read-only post-check. It does not retry an ambiguous mutation.
After interruption, `--recover` only reads revision/cardinality and reports
`not_started` or `completed`; anything else fails closed. This task did not run
this operator against any remote database.

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
python tools/mobile_staging_operator.py
```

With a private approval artifact and private database URL, omitting `--execute`
still only prints a redacted manifest:

```powershell
$env:MOBILE_STAGING_DATABASE_URL = '<private-dedicated-staging-dsn>'
python tools/mobile_staging_operator.py --approval C:\private\approval.json
```

A later task needs the matching fresh Owner approval before each mutation:

```powershell
python tools/mobile_staging_operator.py --approval C:\private\build-approval.json --state-file C:\private\build-state.json --execute build
python tools/mobile_staging_operator.py --approval C:\private\build-approval.json --state-file C:\private\build-state.json --execute recover-build
python tools/mobile_staging_operator.py --approval C:\private\candidate-approval.json --state-file C:\private\candidate-state.json --execute candidate
python tools/mobile_staging_operator.py --approval C:\private\candidate-approval.json --state-file C:\private\candidate-state.json --execute recover-candidate
python tools/mobile_staging_operator.py --approval C:\private\approval.json --state-file C:\private\state.json --execute promote
python tools/mobile_staging_operator.py --approval C:\private\approval.json --state-file C:\private\state.json --execute rollback
```

Google documents that `--no-traffic` prevents the deployed revision receiving
traffic, including a first revision, and that service traffic is managed
separately. The operator therefore treats revision describe as image/readiness
evidence but service describe as the authoritative traffic topology. Bootstrap
requires no prior service and `rollback_revision=null`; failed promotion cleanup
or service deletion needs separate approval. Update requires one exact baseline
revision at 100% before candidate promotion and can roll back to it. Both modes
reject candidate traffic, digest, ingress, runtime identity or scaling drift.
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
artifact validation, no-traffic candidate, revision/digest/runtime-reference
post-check, explicit promotion, smoke, then rollback if needed. Expected future
external mutations are exactly one build/image upload, one no-traffic Cloud Run
candidate and one explicit traffic update. Cleanup may delete the candidate,
image, staging data/database and eventually the dedicated project only under a
separate approval that includes residual billing checks.
