# Phase C zero-admin bootstrap

This is a one-time, owner-approved recovery boundary. It does not grant a
database role or alter `portal_access_level`. Portal administration remains
defined exclusively by `WEB_PORTAL_ADMIN_MEMBER_IDS` after the linked LINE
principal resolves.

The operator must supply the approved pending identity, allowlisted Member,
reason, and opaque request ID through the approved private operator channel.
Do not place those values in shell arguments, repository files, SQL text, logs,
or a transcript.

Use the checksummed executable artifact from the repository root. The only
command-line input is the fixed mode; all identifiers, the full allowlist,
reason, request ID, and execution acknowledgement are read interactively with
echo disabled:

```powershell
python tools/portal_data_zero_admin_bootstrap.py --mode preflight
python tools/portal_data_zero_admin_bootstrap.py --mode dry-run
python tools/portal_data_zero_admin_bootstrap.py --mode execute
```

Run preflight and dry-run before execute. Stop unless each produces exactly the
documented redacted JSON fields (`mode`, `status`, `target_ready`, the before
and after admin counts, `audit_delta`, and `applied`) without an identifier.
Execute additionally requires the fixed `EXECUTE TASK-085` acknowledgement.
The artifact accepts only the repository's local-only PostgreSQL database
boundary; production execution remains separately gated by an Owner-approved
package and is not authorized by this runbook alone.

Before any execution, obtain a pager-off, read-only aggregate inventory and
stop unless it proves exactly zero active linked allowlisted administrators.
The target must be an allowlisted Member with a pending LINE identity, an
unlinked and non-ignored legacy LINE row, an eligible Person, and an open,
unredacted review thread. Any missing, duplicate, disabled, blocked, linked,
or otherwise drifted row is a stop condition.

The application boundary is
`IdentityLifecycleRepository.bootstrap_zero_admin_member`. It takes the same
transaction advisory lock as normal administration, rechecks the zero-admin
condition, and reuses the normal Member-linking transaction. It creates only
the existing `identity_linked` audit action with a null actor. A retry with
the identical request ID is accepted only when the linked identity and Member
record exactly match that audit; a different request or any existing active
allowlisted administrator is rejected.

After a successful commit, re-run the aggregate inventory. Require exactly
one active linked allowlisted administrator, the expected linked principal,
one `identity_linked` audit for the request, and no unrelated count changes.
Do not attempt SQL repair or a second bootstrap if any check fails; preserve
the evidence and escalate to the Owner.

## TASK-086 production boundary

The TASK-085 commands above remain local-only. Production uses the separate
checksummed artifact `tools/portal_data_production_zero_admin_bootstrap.py` only
after its implementation commit has passed Work review, the one ready PR,
hosted PostgreSQL 15/16 CI, and squash merge. The artifact verifies its own
canonical-LF SHA-256 before it opens a database connection.

Do not manually prepare `PORTAL_DATA_DATABASE_URL` or copy the allowlist into a
shell variable. The reviewed production path is the checksummed launcher below;
the mode commands are its internal sequence and must not be run separately:

```powershell
python tools/portal_data_production_zero_admin_bootstrap.py --mode discovery
python tools/portal_data_production_zero_admin_bootstrap.py --mode preflight
python tools/portal_data_production_zero_admin_bootstrap.py --mode dry-run
python tools/portal_data_production_zero_admin_bootstrap.py --mode execute
python tools/portal_data_production_zero_admin_bootstrap.py --mode post-check
```

Discovery, preflight, and dry-run use an explicit read-only transaction. They
stop unless revision 0004 and the approved statement-logging predicate are
true, there are zero active linked allowlisted administrators, and discovery
finds exactly one eligible allowlisted Member and exactly one eligible pending
LINE identity. This uniqueness is the only automatic association rule; zero or
multiple candidates require Owner review and no identifier is printed.

Execute additionally requires the private process environment value
`TASK086_PRODUCTION_EXECUTION=EXECUTE TASK-086`. The operator generates a fresh
opaque request ID internally, calls the existing advisory-lock transaction,
checks the exact aggregate transitions and audit relationships, then performs
one same-request idempotency verification. The request ID and all identity,
Member, Person, LINE, connection, and allowlist values remain absent from
stdout and ordinary errors.

Successful stdout is exactly one fixed redacted JSON object containing only
mode/status classifications, Boolean gates, candidate counts, administrator
count, audit delta, applied state, and retry verification. Any logging/schema
drift, candidate ambiguity, concurrent winner, database error, uncertain
connection result, unexpected aggregate delta, or relationship mismatch is a
terminal stop. Do not run ad-hoc SQL, generate a replacement request, or retry
after an uncertain result; preserve the fixed classification and return to the
Owner.

TASK-086 authorizes at most the single bootstrap transaction after all review
gates pass. It does not authorize deployment, schema changes, Secret/IAM/
Scheduler/flag/traffic changes, notifications, or activation of the other 56
People.

### Exact no-disclosure launcher

After squash merge, start from the exact merged commit in a clean repository
root. Set only the non-secret full SHA as `TASK086_APPROVED_MERGED_COMMIT`, then
invoke the exact verified bundled Python 3.12.13 runtime:

```powershell
& "C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" tools/launch_production_zero_admin_bootstrap.py
```

The launcher refuses any other working directory, dirty tree, commit, Python
executable or exact version, SQLAlchemy/Alembic/psycopg2 version, material source checksum,
gcloud account, project, service or region. Its fixed identity is
`yces3108@gmail.com` / `ntubtob-schedule-405614` / `web-portal` /
`asia-east1`; the gcloud executable is the reviewed absolute Windows path.

The only private file path is
`C:\Users\USER\.ntubtob-private\backup.env`. The launcher alone consumes the
exact five `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD` entries
in memory; it rejects missing, duplicate, unknown or malformed entries and
never prints the file or values. It constructs the SQLAlchemy URL in memory.

The allowlist is obtained with one Cloud Run `services describe` projection of
only
`spec.template.spec.containers[0].env[?name=WEB_PORTAL_ADMIN_MEMBER_IDS].value`.
The launcher captures that one field, validates it, and never requests the full
runtime configuration. The value is not present in argv, subprocess command
text, stdout or errors.

After all guards pass, the launcher injects the URL and allowlist only into its
own process, performs exactly `discovery` -> `preflight` -> `dry-run` ->
`execute` -> `post-check`, and clears all three temporary operator environment
variables in `finally`, including on failure. Only the execute step receives
the fixed acknowledgement. Do not enable PowerShell command tracing, Python
debug logging, SQLAlchemy echo or external process-environment capture.

If the private file cannot be consumed under this contract, the single-field
metadata projection is unsupported, or any exact guard fails, the launcher
prints only `TASK-086 production launcher stopped` and returns control to the
Owner. Do not substitute an ad-hoc environment loader or broader gcloud query.

### Uncertain-outcome recovery: post-check only

If the five-stage launcher's stdout or exit evidence is lost, never run that
launcher again and never generate another request ID. After the recovery
artifact passes Work review, hosted CI, and squash merge, set
`TASK086_APPROVED_MERGED_COMMIT` to that exact non-secret merged SHA in a clean
repository root and invoke only:

```powershell
& "C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" tools/launch_production_zero_admin_post_check.py
```

`launch_production_zero_admin_post_check.py` is independently checksum-locked
and reuses the exact runtime, dependency, material checksum, account, project,
service, region, private PG-file parser, single-field allowlist projection, and
clean-process guards above. It sets only the database URL and allowlist in its
own process, explicitly removes the execution acknowledgement, calls the
existing operator once with literal mode `post-check`, and clears all temporary
values in `finally`.

This recovery command has no sequence, execute acknowledgement, request-ID
generation, domain repository, or write-transaction entry point. Its only
database behavior is the existing read-only `post-check`, including schema and
read-logging guards. Success emits the existing fixed redacted JSON; failure
emits only `TASK-086 production post-check stopped`. Zero completed relationship,
multiple/drifted state, or any unknown result is a terminal Owner stop without
mutation.

### Owner-approved fixed-schema read-only diagnostic

If the post-check-only recovery returns its fixed stop classification, do not
rerun either earlier launcher. After this diagnostic artifact passes Work
review, hosted CI, and squash merge, set only the non-secret exact merged SHA as
`TASK086_DIAGNOSTIC_APPROVED_MERGED_COMMIT` in a clean repository root and run
exactly once:

```powershell
& "C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" tools/portal_data_production_bootstrap_diagnostic.py
```

The independently checksummed diagnostic verifies its exact runtime,
dependencies, git state, model checksum, gcloud account/project/service/region,
single-field allowlist projection, and private PG file contract. It does not
import or call either production launcher, the production operator, or the
identity lifecycle repository. It has no mode argument, execution
acknowledgement, UUID/request ID, DDL/DML, commit, or write transaction.

The database connection immediately starts an explicit read-only transaction
and sets local statement, lock, and idle-in-transaction timeouts before fixed
SELECT queries. The only output is one JSON object with this exact schema:

```json
{"runtime_artifact_git":"pass|fail","gcloud_metadata":"pass|fail","private_pg":"pass|fail","connection":"pass|fail","schema":"pass|fail","read_logging":"pass|fail","active_admin":"zero|one|other","completed_relationship":"zero|one|other"}
```

The values shown above describe the allowed classifications, not literal output
from a run. No raw exception, identifier, credential, allowlist, cloud metadata,
host, or SQL parameter may be retained or reported. All in-memory private values
and the engine are cleaned in `finally`.

Interpret only the reviewed classifications: all six guards passing plus
`active_admin=one` and `completed_relationship=one` proves the bootstrap
succeeded; all six guards passing plus both counts `zero` proves no bootstrap
was applied and requires a new Owner-approved write package. Any `other` or
guard failure is a terminal Owner stop. This diagnostic does not authorize a
second bootstrap or the 56-Person activation.
