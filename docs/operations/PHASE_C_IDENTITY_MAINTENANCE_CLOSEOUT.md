# Phase C identity maintenance closeout runbook

This is a repository-only execution contract, not production authorization.
The operator must stop unless Stage B and the exact Stage C Owner package are
approved. Do not record target IDs, names, LINE subjects, Member IDs, Person
IDs, Secret values, full environment output, or request bodies in this file.

## Prepared read-only commands (do not run without Stage B approval)

```powershell
gcloud run services describe web-portal --project ntubtob-schedule-405614 --region asia-east1 --format="json(status.latestCreatedRevisionName,status.latestReadyRevisionName,status.traffic)"
gcloud run revisions describe <owner-approved-candidate> --project ntubtob-schedule-405614 --region asia-east1 --format="json(status.imageDigest,status.conditions,spec.serviceAccountName)"
gcloud run services get-iam-policy web-portal --project ntubtob-schedule-405614 --region asia-east1 --format="json(bindings.role,bindings.members)"
```

The operator must separately project only the approved non-secret Phase C,
freeze and maintenance booleans plus Secret *binding name/version metadata*.
If that cannot be obtained without printing an environment payload, stop rather
than widening the command. Execute the checksummed SQL through the approved
read-only database channel and pass only its six sanitized columns plus the
aggregate metadata to `tools.phase_c_closeout.build_manifest`.

Before supplying any allowlist or request ID, use the approved read-only channel
to query only `log_statement`, `log_min_duration_statement`,
`log_min_duration_sample`, and `pgaudit.log`. Stop unless statement logging is
`none`, both duration settings are `-1`, and `pgaudit.log` is absent or `none`.
Also stop if the database provider or approved access channel cannot confirm
that it does not retain full SQL statements. This preflight must run before the
parameterized inventory: discovering unsafe logging from the inventory itself
would be too late.

```sql
SELECT current_setting('log_statement') = 'none'
   AND current_setting('log_min_duration_statement')::integer = -1
   AND coalesce(current_setting('log_min_duration_sample', true), '-1')::integer = -1
   AND coalesce(current_setting('pgaudit.log', true), 'none') = 'none'
   AS statement_logging_safe;
```

The only acceptable result is one boolean `true`; do not broaden this query to
print configuration or extension rows.

Use PostgreSQL 16 psql, not an earlier client. Before connecting, verify the
isolated client image exactly as follows:

```sh
docker run --rm postgres:16.4-alpine psql --version
```

Stop unless the result identifies PostgreSQL 16. Start the Owner-approved
read-only PostgreSQL 16 interactive session with `-X -n`; this runbook never
contains a DSN, password or environment value:

```sh
docker run --rm -it postgres:16.4-alpine psql -X -n <owner-approved-read-only-connection>
```

Only after the logging preflight in that same session, enter these psql
meta-commands exactly, supplying values only at the three interactive prompts:

```text
\set ON_ERROR_STOP on
\pset format csv
\prompt 'Approved admin Member-ID allowlist:' admin_member_ids
\prompt 'Opaque mutation request ID:' mutation_request_id
\prompt 'Opaque recovery request ID:' recovery_request_id
\i docs/operations/sql/TASK-084-phase-c-closeout-inventory.sql
```

The checksummed artifact keeps `BEGIN TRANSACTION READ ONLY`, all local
timeouts, and `ROLLBACK`. Its final query uses `$1`, `$2` and `$3`; its one
fixed `\bind … \g` meta-command binds the three prompted values in that order
and executes the query via PostgreSQL 16's extended query protocol. The values
therefore do not enter the server-bound SQL statement text or the representative
statement. Do not use SQL colon interpolation, command-line arguments, a
different bind count/order, `\g` before binding, `\p`, query echo, or a
noninteractive transcript.

Extended parameters still do not prove that a client, provider, proxy or audit
product never captures parameter payloads. Stop if the approved channel cannot
confirm that its parameter-payload logging boundary is acceptable; do not relax
that condition based only on `log_statement`, pgAudit, or a lack of observed
output. The fixed SQL output contains only aggregate counts and never selects
the supplied values.

1. Run fresh account/project/region guards, the logging preflight, the
   checksummed read-only SQL, and the closeout verifier with aggregate evidence.
   Require schema 0004, all-on/unfrozen Phase C, at least one classified active
   allowlisted admin, zero duplicate request IDs, and every non-audit identity,
   Member/Person, and qualification drift gate carried forward from TASK-068.
2. Lock the current Web Portal revision/digest as rollback. Create only the
   Owner-approved maintenance=true candidate. Before 100% promotion, require
   Ready, unchanged image digest, exact public IAM, approved Secret binding
   metadata, Phase C=true, freeze=false, maintenance=true, and every other
   service unchanged. Any unknown candidate or metadata is a stop.
3. Promote only the verified candidate. If promotion/verification fails, return
   traffic to the locked maintenance-off revision. Do not change other services.
4. Capture the sanitized `before` snapshot. Use the Owner-provided,
   repository-external safe candidate classification and two opaque request
   IDs. Capture `action` after one supported ignore action with a reason; require
   safe-ignore `-1`, safe-unignore `+1`, and exactly one `identity_ignored`
   audit. Replay the exact same POST/request ID and capture `retry`; require both
   candidate counts and audit count unchanged. Recover only through the
   approved unignore domain action with the second request ID and capture
   `recovery`; require candidate counts restored, exactly one
   `identity_unignored` audit, and `bounded_same_target_count=1`. Capture a final
   `post` snapshot and require it identical to recovery for all protected
   counts. Never delete audit data or repair with SQL.
5. Pass the five snapshots to the single `compare_sequence` post-check. The two
   Owner-approved request IDs may add exactly the bounded ignore/unignore pair;
   no other audit delta is accepted, while the full TASK-068 non-audit drift
   rules remain zero throughout. Every snapshot must also have the exact same
   complete runtime vector (revisions, traffic, IAM, Phase C, freeze and
   maintenance) and the same aggregate People, Member, identity, reliable LINE,
   active team-player and game-attendance-reply counts. On recovery or
   audit mismatch, set maintenance=false or return to the locked revision,
   retain Phase C, stop, and escalate to Owner.

`set_ignored()` has no notification caller: it changes the qualified legacy
LINE row and appends its access audit inside the domain transaction. The
inventory deliberately does not query the deprecated `line_notify_tokens`
table or infer a notification count. During Stage D, use only the approved
production notification error/log classification to confirm that no unexpected
notification side effect or delivery error accompanied the smoke; do not print
notification payloads, recipients, tokens or full logs.

The admin pre-check is an aggregate classification only: an active Person with
a linked identity and a Member ID present in the runtime allowlist. The operator
must confirm its count is at least one without printing the allowlist or any
principal identifier. The action operator obtains CSRF, target and opaque
request ID only from the authenticated browser/session at execution time; it
uses browser developer tools' Network tab to select the first POST and choose
"Replay XHR"/"Resend" before navigating away. The replay must preserve the
same authenticated cookie, CSRF token, target, reason and mutation request ID.
The operator then uses a newly rendered form and the distinct recovery request
ID for recovery. No exported HAR, copied shell command, special endpoint, CSRF
bypass or persisted request body is allowed.
