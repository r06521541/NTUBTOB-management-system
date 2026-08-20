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

### Runtime attendance residue repair

TASK-120 adds a separate, one-purpose repair for the two documented fictional
runtime attendance rows left by the TASK-115 acceptance sequence. It is not a
general attendance reset and it never changes any `mobile_*` record. Before an
execution checkpoint, run the read-only command with the same private,
process-only tester-subject input required by the Officer commands:

```powershell
python -m tools.mobile_staging_data --approval C:\private\candidate-approval.json --inspect-runtime-residue
```

The only executable state has the canonical TASK-112/TASK-118 replies (IDs
`-112003`, `-112002`, and `-112001`, all at `2000-01-01T00:00:00Z`) plus exactly
these two rows: ID `3` is Game/Person `-112001`, null legacy user/member,
reply `5`, and `2026-08-19T16:33:02.723958Z`; ID `4` has the same ownership,
reply `1`, and `2026-08-19T16:36:23.695486Z`. Any timestamp, tuple, row count,
or additional attendance row is drift and stops without mutation.

The Officer state machine can coexist with empty mobile tables or with any
nonempty fictional runtime history whose ownership is exact. Every session must
belong to linked identity and Person `-112001`; every refresh token, refresh
attempt, exchange, and idempotency row must join to one of those sessions;
exchanges must be LINE and idempotency rows must target that Person. This lets a
legitimate Officer login or refresh add sessions and children without breaking a
later restore. The operator reads only ownership metadata and counts—never
tokens, assertions, attempts, installation identifiers, encrypted payloads, or
their hashes. Cross-principal, orphaned, malformed, or unowned history fails
closed.

With the existing private candidate approval and identity gate, the bounded
mutation is:

```powershell
python -m tools.mobile_staging_data --approval C:\private\candidate-approval.json --execute-runtime-residue-repair
```

One transaction rechecks the full state, deletes only the two full-tuple,
timestamp-qualified rows, requires rowcount `2`, and postchecks the canonical
baseline. An already repaired exact state is a zero-delta success. Any uncertain
result requires another inspection; do not retry with ad-hoc SQL. This repair
does not establish provenance beyond those task-defined tuples and does not
touch production, schema, notifications, mobile records, or another Person/Game.

### Mobile principal aggregate diagnostic

TASK-121 adds one read-only diagnostic for investigating a possible mismatch
between the TASK-119 fictional Officer Person and active mobile sessions. It
requires the existing private candidate approval and exact database identity,
but it does not require `MOBILE_STAGING_PROVIDER_SUBJECT`:

```powershell
python -m tools.mobile_staging_data --approval C:\private\candidate-approval.json --inspect-mobile-principal
```

The action opens an explicit read-only transaction, requires revision
`0005_mobile_auth_api_foundation`, and reads only Person `-112001` access level,
status and version plus aggregate active-session ownership counts. Output states
are `no_active_sessions`, `expected_only`, `mixed_principals`, `other_only`, or
`binding_drift`; `expected_person_match` is true only for active Officer version
2. Expected tuple, expected-Person binding mismatch and other-principal counts
are mutually exclusive and must sum to total or the diagnostic fails closed.
Revoked sessions are excluded.

The query and output never include session IDs, installation identifiers,
tokens, refresh attempts, assertions, idempotency values, hashes, encrypted
payloads, provider subjects, or another Person's identity or role. Aggregate
`expected_only` does not prove which session a particular device token uses.
Correlating a client requires its existing redacted `/me` response containing
only `id`, `access_level`, and `capabilities`; do not provide the token to the
operator or copy it into a transcript.

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

## Bounded mobile staging launch console

`tools/Invoke-MobileStaging.ps1` runs exactly one declared local action. `help`,
`preflight`, `status`, and every routine action stay on a separate code path
from the Owner-private actions: they do not initialize `gcloud`, resolve a
Secret reference, read the private tester subject/database URL, or load the
staging mutation operator. Repository tests mock every executable; TASK-123
does not run this console against an emulator, staging, or cloud resources.

Every invocation writes exactly one compressed, de-identified JSON object. Its
top-level classification is one of `PASS`, `OWNER_ACTION_REQUIRED`, `DRIFT`,
`TIMEOUT`, or `FAILED`, with fixed `standing_authorization=DEC-098`,
`report_to=main-work`, bounded `stop_only_on`, action-specific `operator` and
`owner_gate`, and `retention_owner=TASK-123`. A non-`PASS` result exits nonzero.
No caller needs raw process output to classify an action.
Every non-PASS `details` object also contains exactly one bounded allowlisted
`reason_code`: `CONFIG_INVALID`, `SNAPSHOT_INVALID`, `DISK_UNAVAILABLE`,
`TOOLCHAIN_UNAVAILABLE`, `LOCK_UNAVAILABLE`, `OWNER_ACTION_REQUIRED`,
`RUNTIME_TIMEOUT`, `RUNTIME_FAILED`, or `OUTPUT_REDACTION_FAILED`. Raw
exception text, paths, child output, and sensitive values are never copied into
the governed result. If the nominal result itself fails the sensitive-output
gate, the fixed `OUTPUT_REDACTION_FAILED` fallback replaces it as the only JSON
line and forces process exit 2; a `FAILED` envelope never exits successfully.

The value-free config contains only the exact detached snapshot, absolute
toolchain/cache paths (including one absolute `apkanalyzer` package inspector),
one AVD and serial, package/activity constants, task-owned
`E:\codex-evidence\task-123` and `E:\codex-temp\task-123` roots, disk floor,
artifact name, Android user-home inventory, and one allowed signer fingerprint.
It contains no endpoint, channel ID, provider subject, DSN, token, Secret value,
or keystore path. A typical routine invocation is:

```powershell
.\tools\Invoke-MobileStaging.ps1 `
  -Action preflight `
  -Mode fake `
  -Commit <full-accepted-sha> `
  -ConfigPath C:\private\task-123-launcher.json
```

The real config loader is contract-tested with the complete value-free schema,
including its Android user-home array. Loop and assignment names are checked
against PowerShell automatic/read-only variables so case-insensitive collisions
such as `$home`/`$HOME` fail review rather than runtime dogfood.

The routine actions are `help`, `preflight`, `avd-start`, `status`, `build`,
`signer-check`, `install`, `cold-launch`, `health`, `stop`, and `cleanup`.
`status` derives package/activity first. Package absent, portal background, and
portal stopped return their stable state with zero login/projection counts and
never invoke the accessibility dump. Activity classification accepts exactly
one anchored resumed/top-resumed/focused activity record; retained back-stack
entries are ignored, while duplicate or malformed current records fail closed.
Only an exact portal foreground component captures one
bounded accessibility hierarchy directly in memory through exact
`adb -s <serial> exec-out uiautomator dump /dev/tty` arguments. It never uses a
device temp file, `cat`, `pull`, or `rm`; it prohibits DTD/external resolution,
and accepts exactly one mutually exclusive state. Logged-out requires one
enabled, clickable `android.widget.Button` in package `tw.org.ntubtob.portal`
with exact `LINE 登入` content description; merged prompt text is ignored.
The remaining states are
Basic/report-disabled, Officer/report-enabled, or Officer/report-disabled. It
returns only that stable state and allowlisted counts; duplicate, coexisting,
missing, malformed, or oversized states fail closed. It never persists or
returns the hierarchy, labels, names, coordinates, OCR, screenshots, or logcat.
Governed status failures expose only fixed stage codes: `ADB_UNAVAILABLE`,
`ADB_INVALID`, `PACKAGE_UNAVAILABLE`, `ACTIVITY_UNAVAILABLE`,
`ACTIVITY_INVALID`, `ACCESSIBILITY_UNAVAILABLE`, `ACCESSIBILITY_INVALID`, or
`SEMANTIC_DRIFT`. Operational unavailable/invalid stages classify `FAILED`;
semantic mismatch classifies `DRIFT`. All exit 2, and no exception, command
output, path, XML, or label is included.
`install` additionally requires `-PreserveSession` and only issues
`adb install -r` after the absolute package inspector proves the artifact is
exactly `tw.org.ntubtob.portal` and artifact/installed signers agree. Build
evidence likewise records only the package identity returned by that exact
inspection; missing, duplicate, malformed, or mismatched output fails closed.
`cold-launch`
uses semantic package/activity/PID checks, performs no coordinate/OCR/raw UI XML
or logcat classification, and does not retry a timed-out `am start`. Any network
setting changed by that action is restored in `finally`. Cleanup is limited to
the two task-owned roots and retains evidence unless `-PurgeEvidence` is
explicit. Staging Flutter defines are delivered to the child through a named
pipe so values are absent from argv, files, evidence, and console output.

Owner-private actions are one interactive invocation only:

```powershell
.\tools\Invoke-MobileStaging.ps1 `
  -Action grant-officer `
  -Mode staging `
  -Commit <full-accepted-sha> `
  -ConfigPath C:\private\task-123-launcher.json `
  -ApprovalPath C:\private\candidate-approval.json
```

They are `private-inspect`, `grant-officer`, and `restore-basic`. Non-interactive
execution returns `OWNER_ACTION_REQUIRED` before config, `gcloud`, Secret, or
operator initialization. The Owner enters the private provider subject as a
secure prompt; the approved database Secret value and subject exist only in the
single child environment and are cleared in `finally`. Grant/restore always run
read-only inspect, require exact non-sensitive `GRANT-OFFICER` or
`RESTORE-BASIC` confirmation, attempt at most one mutation, then independently
inspect the terminal state. An interrupted or unknown mutation is never retried;
only read-only reconciliation is permitted. The console never prints child
stdout, endpoint/channel values, DSN, subject, token/assertion, keystore
material/path, raw UI/log output, or sensitive exception text.

The same task-owned exclusive lock covers the complete Owner-private lifecycle:
inspect, confirmation, at most one mutation, independent postcheck, and
`finally` cleanup. A concurrent or stale lock fails before Secret retrieval or
operator initialization. An acquired lock is removed on a handled failure or
interruption; an unowned stale lock is never silently removed.

Artifact evidence is bounded to accepted commit, mode, package, artifact hash,
public signer fingerprint, classification, and retention owner. Concurrency and
stale task ownership fail closed through the exact task lock; the launcher kills
only the child process it started and never performs global process/cache/app
cleanup.

TASK-123 deliberately defers these four follow-ups:

- A: named resumable Staging Acceptance Harness.
- B: no-disclosure credential launcher/broker.
- C: relational fictional fixture lifecycle/reset/reconcile preserving audits.
- D: acceptance observability contracts defined before runtime claims.

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
