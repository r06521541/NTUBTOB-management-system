# Portal Data Phase B rehearsal

TASK-065 prepares, but does not authorize, the Member/Person/LINE identity backfill.
The committed SQL is repository-only and must not be pasted into production until a later exact execution task has
fresh inventory evidence and explicit Owner approval.

## Approved mapping

- Every permanent-roster `members` row receives one `people` row with `portal_access_level='basic'` and
  `portal_status='inactive'`.
- Mapping is by `members.id` and the new `members.person_id` FK only. Names and LINE nicknames are never matching keys.
- A legacy LINE user is linked only when `line_users.member_id` is non-null and `ignored=false`.
- Only a Person reached through that reliable LINE-to-Member link receives active `team_player` qualification.
- Unlinked and ignored LINE users are unchanged. No Person becomes officer/admin and no runtime allowlist is read.
- Multiple distinct LINE subjects linked to one Member are allowed; a duplicated subject fails closed.

## Artifacts

- `TASK-065-phase-b-inventory.sql`: read-only, de-identified pre-inventory.
- `TASK-065-phase-b-backfill.sql`: bounded, advisory-locked and idempotent transaction. It fails closed on revision,
  identity, foreign-key or non-batch portal-row drift.
- `TASK-065-phase-b-postcheck.sql`: read-only, de-identified relationship/count checks.
- `python -m tools.portal_data_phase_b verify`: verifies SQL checksums and static safety contracts.
- `python -m tools.portal_data_phase_b compare INVENTORY.csv POSTCHECK.csv`: strict aggregate comparison without
  persisting raw identity or Member values.

The SQL Editor CSV contract is exactly `section,metric,status,boolean_value,integer_value,text_value`. Outputs contain
only booleans, counts and the expected migration revision.

## Local rehearsal

PowerShell, using an installed Python environment with repository requirements:

```powershell
docker compose -f docker-compose.portal-data.yml up -d portal-postgres
$env:PORTAL_DATA_DATABASE_URL = 'postgresql+psycopg2://portal_local:local-only-password@127.0.0.1:55432/ntubtob_portal_local'
$env:PORTAL_DATA_TEST_DATABASE_URL = $env:PORTAL_DATA_DATABASE_URL
python -m unittest tests.portal_data.test_phase_b_artifacts -v
docker compose -f docker-compose.portal-data.yml down
```

The integration suite rebuilds the local fixture and Phase A schema, executes the full backfill, executes it again,
checks the sanitized post-state, injects drift, and renders the exact checksummed transaction with its final `COMMIT`
replaced by `ROLLBACK` to prove exact pre-state restoration before commit.

## Recovery boundary

Before `COMMIT`, any error rolls the complete transaction back, including Member links, People, identities,
qualifications and audit rows. The fixed advisory lock serializes TASK-065 executions and the row locks prevent a
concurrent Member remap.

After `COMMIT`, exact deletion is intentionally unavailable: `access_audit` is append-only and its trigger rejects
UPDATE/DELETE. A later production execution package must therefore use fresh post-check evidence and define forward
compensation for a committed semantic error. It must not disable the append-only trigger or claim that a committed
batch can return to a byte-identical pre-state. Phase C must not start until Phase B is accepted.

Stopping the Compose service does not remove its dedicated named volume. Use the separately documented
`docker compose -f docker-compose.portal-data.yml down -v` only when intentionally removing this local-only data.
