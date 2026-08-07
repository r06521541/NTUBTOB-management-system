# TASK-052 Supabase access-boundary inventory contract

## Safety boundary

This package prepares a query for a later Owner-run inventory. Committing or reviewing it does not
authorize execution. Codex did not connect to Supabase, run this SQL, open the Dashboard, inspect a
Secret or retrieve production values.

The reviewed query is
[`TASK-052-supabase-readonly-access-boundary.sql`](../sql/TASK-052-supabase-readonly-access-boundary.sql).
It starts one transaction with `READ ONLY`, applies transaction-local timeouts, reads only fixed
PostgreSQL catalog allowlists and ends with `ROLLBACK`. It never selects rows from an `ntubtob`
application table.

## Fixed CSV contract

Export exactly one result set with this header and no additional columns:

```csv
section,metric,status,boolean_value,integer_value,text_value
```

Each `(section, metric)` occurs exactly once. Exactly one value column is populated per row.

| value column | allowed values |
| --- | --- |
| `boolean_value` | blank, `true`, `false` |
| `integer_value` | blank or a non-negative base-10 integer |
| `text_value` | blank, `same`, `different`, `unknown` |

The allowed 33 metrics and their expected ordering are demonstrated using conspicuously fake values
in `tests/fixtures/task052_supabase_access_inventory_fake.csv`. That fixture is not a prediction of
production access and must not be replaced with an Owner export.

The query deliberately does not output database, session user, role, owner or policy names; host,
project reference, DSN or Secret; policy expressions; storage sizes; or application row values.
Role and owner evidence is reduced to current-session capability booleans, `same/different/unknown`
relationships and counts. No hashed role identifier is retained because a relationship/count is
sufficient and has lower re-identification risk.

## Result sections

| section | interpretation |
| --- | --- |
| `00_session` | Read-only state, PostgreSQL major version and generic current-role capabilities. |
| `01_schema` | Schema existence, generic privileges and owner relationship. |
| `02_catalog` | TASK-049 table/column/PK-FK fingerprints, migration marker and new-table presence. |
| `03_owner` | Counts of legacy tables owned by the current session or another role. |
| `04_privilege` | Effective current-session privileges plus generic visible grant counts; grantee names are omitted. |
| `05_rls` | RLS flags and aggregate policy classifications without names, roles or expressions. |

Fingerprint booleans compare canonical catalog strings with the deidentified TASK-049 snapshot:
10 tables, 53 columns and 16 primary/foreign-key constraints. A `false` value means the catalog has
drifted or the prior canonicalization no longer matches; it does not reveal the changed object.

## Offline validation

Before Work reads an Owner export, save it outside the repository and run:

```powershell
py -3.10 -c "from pathlib import Path; from tools.supabase_access_inventory import validate_csv; validate_csv(Path(r'C:\path\outside\repo\result.csv')); print('sanitized contract valid')"
```

Validation is structural and defensive; passing does not establish that the underlying access is
safe. Work must inspect only the generic results and must not commit the actual export until a
separate deidentification review approves a minimal derived summary.

## Fail-closed interpretation

Work must stop migration planning and request investigation when any of these is true:

- query error, timeout, more/fewer than 33 rows, extra field or validator failure;
- `transaction_read_only`, `ntubtob_exists` or any fingerprint match is `false`;
- `legacy_table_count` or `legacy_rls_enabled_count` is not 10;
- `alembic_version_exists=true` or `new_portal_table_count` is nonzero unexpectedly;
- current session is superuser, bypasses RLS or can create roles/databases;
- owner/privilege/policy evidence differs from the access boundary later approved by Owner;
- a public or write policy is present and its intent has not been separately reviewed.

The SQL cannot establish Supabase API exposure, backup recoverability, restore authority or the
correct migration connection path. Those remain manual Dashboard checks.

## Owner procedure after separate execution approval

1. Open Supabase SQL Editor directly; do not provide Work/Codex with a password, DSN or project token.
2. Copy the reviewed SQL unchanged into a new editor tab. Confirm its first statement is
   `BEGIN TRANSACTION READ ONLY` and its last statement is `ROLLBACK`.
3. Execute once. Stop on any warning, permission error, timeout, unexpected prompt or additional
   result set. Do not modify the query to gain access.
4. Export only the single six-column result as CSV. Do not attach screenshots or surrounding editor,
   project, account or connection metadata.
5. Keep the raw export outside Git. Give it to Work for local validation and deidentification review.

Supabase SQL Editor may serialize SQL `NULL` cells as the literal token `null`. The offline validator
accepts that token only when it occupies an entire `boolean_value`, `integer_value` or `text_value`
cell, and normalizes it to an empty value before enforcing the one-value-per-row contract. It does not
normalize identity/contract columns or strings that merely contain `null`.

## Dashboard checklist

Owner records only `yes`, `no`, `unknown` and the listed broad classification. No screenshot,
account name, project ref, host, role name or retention timestamps belong in Git.

| check | allowed answer | stop condition |
| --- | --- | --- |
| Backup enabled | `yes/no/unknown` | `no` or `unknown` |
| PITR enabled | `yes/no/unknown` | `no` or `unknown`, unless an approved backup alternative covers the window |
| Retention covers migration and verification window | `yes/no/unknown` | `no` or `unknown` |
| Restore authority is assigned and available | `yes/no/unknown` | `no` or `unknown` |
| `ntubtob` is in exposed schemas | `yes/no/unknown` | `yes` or `unknown` until RLS design is approved |
| REST/GraphQL/client API can reach `ntubtob` | `yes/no/unknown` | `yes` or `unknown` until RLS design is approved |
| Intended migration path | `direct/pooler/unknown` | `pooler` or `unknown` needs compatibility review |
| Intended runtime path | `direct/pooler/unknown` | `unknown` |
| Maintenance window agreed | `yes/no/unknown` | `no` or `unknown` |
| 5s lock and 60s statement timeout accepted | `yes/no/unknown` | `no` or `unknown` |

## Work intake sequence

1. Confirm the file has only the fixed six columns and 33 rows; do not open an unexpected export in
   a tool that may upload or sync it.
2. Run the offline validator from a path outside the repository.
3. Compare all required counts and fingerprint booleans with TASK-049.
4. Classify owner, privilege, RLS and Dashboard results against the stop conditions above.
5. Record only an approved, deidentified yes/no/count summary in a later Work review. Never commit the
   raw export or actual identity-bearing metadata.
6. Keep TASK-051 Phase A blocked until backup, access path, catalog freshness, RLS and migration-role
   decisions are all explicit.
