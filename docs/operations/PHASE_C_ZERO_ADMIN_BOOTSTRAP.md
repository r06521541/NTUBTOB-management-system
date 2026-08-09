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
