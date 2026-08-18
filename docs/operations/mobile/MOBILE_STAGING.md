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

1. Choose a dedicated non-production project and database. Produce two
   independently reviewed SHA-256 identities over canonical
   `postgresql://host:port/database`: one for the approved staging target and one
   for production. The operator requires both, rejects equality, rejects a target
   matching production, and does not trust a DSN to label itself staging.
2. Use `tools/mobile_staging_preflight.py` helpers with an injected/read-only
   runner. Cloud inventory only uses `gcloud config get-value`, Cloud Run list and
   Secret metadata list. Database inventory starts an explicit read-only
   transaction, requires revision 0005 and rejects production-shaped People or a
   partial TASK-112 fixture.
3. Render the redacted manifest with `redacted_manifest`. It contains no host,
   username, password, provider subject or Secret payload.
4. Main Work presents the exact project/billing/APIs, database provider and
   monthly cost, LINE Provider and Developing channel, dedicated service account,
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

## Dry run, candidate, promotion and recovery

Build the shared source distribution from the approved clean commit locally.
The operator requires exact `shared_lib-0.0.1.tar.gz`, inspects its archive paths,
copies it into the Docker context only for the candidate build and removes the
copy in `finally`.

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

A later task needs a fresh Owner approval before any of these mutations:

```powershell
python tools/mobile_staging_operator.py --approval C:\private\approval.json --state-file C:\private\state.json --execute candidate
python tools/mobile_staging_operator.py --approval C:\private\approval.json --state-file C:\private\state.json --execute recover
python tools/mobile_staging_operator.py --approval C:\private\approval.json --state-file C:\private\state.json --execute promote
python tools/mobile_staging_operator.py --approval C:\private\approval.json --state-file C:\private\state.json --execute rollback
```

Candidate execution submits one Cloud Build and deploys the exact digest as a
no-traffic revision. Promotion is a separate exact traffic command. On
interruption before the private state is saved, use `recover`: it does not build
or deploy, and only accepts the exact ready, zero-traffic revision, digest,
scaling, runtime identity, Secret references and audience. Then resume promotion
or rollback from the saved state. Ambiguous state stops. Rollback restores 100%
traffic to the approved prior revision;
candidate/image deletion and full staging cleanup remain separately approved
cost-bearing actions.

The operator never runs project/API/billing/database/Secret/service-account/IAM
or LINE-channel creation. Public ingress and IAM remain Owner-controlled steps.

## Flutter staging command template

After staging exists, Flutter Domain Work may use this value-free template:

```sh
flutter build apk --flavor staging \
  --dart-define=MOBILE_API_BASE_URL=https://<mobile-api-staging-host>/api/v1 \
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
