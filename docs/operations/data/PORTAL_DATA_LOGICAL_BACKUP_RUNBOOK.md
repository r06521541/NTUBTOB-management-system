# Portal Data logical backup and restore-readiness runbook

> **STOP: this runbook does not authorize production access, `pg_dump`, restore, SQL or migration.**
> Each production backup needs Owner approval of the exact source commit, maintenance window,
> connection boundary and repository-external destination. Restore is permitted only to a separately
> confirmed isolated non-production database under a distinct approval.

## Recovery objective and artifact contract

The recovery artifact is one PostgreSQL custom-format archive containing only schema `ntubtob`, plus
an adjacent SHA-256 sidecar and sanitized JSON manifest. The archive name is fixed as
`portal-data-backup-YYYYMMDDTHHMMSSZ.dump`; sidecars use the same stem with `.sha256` and
`.manifest.json`. All three remain outside the repository in an encrypted location that is not
synchronized to a general-purpose cloud folder.

The repository tool can only preflight paths, run local `pg_restore --list`/`--version`, and create or
verify sidecars. It has no connection, dump, restore, SQL or deletion capability:

```powershell
py -3.10 -m tools.portal_data_logical_backup preflight <absolute-archive-path> <absolute-manifest-path> <absolute-checksum-path>
py -3.10 -m tools.portal_data_logical_backup create <absolute-archive-path> <absolute-manifest-path> <absolute-checksum-path>
py -3.10 -m tools.portal_data_logical_backup verify <absolute-archive-path> <absolute-manifest-path> <absolute-checksum-path>
```

If the host has no `pg_restore`, the explicitly selected Docker inspection backend uses only the
repository-fixed local image ID. It never pulls an image, joins a network or receives credentials:

```powershell
py -3.10 -m tools.portal_data_logical_backup create <absolute-archive-path> <absolute-manifest-path> <absolute-checksum-path> --backend docker
py -3.10 -m tools.portal_data_logical_backup verify <absolute-archive-path> <absolute-manifest-path> <absolute-checksum-path> --backend docker
```

This maps internally to a fixed `docker run --rm --pull never --network none --read-only --cap-drop
ALL --security-opt no-new-privileges` command. Only the archive parent is bind-mounted at `/backup`
read-only, and the only container commands are `pg_restore --list /backup/<archive-basename>` and
`pg_restore --version`. There is no image/backend passthrough, Docker socket/repository/home mount,
environment forwarding or restore command. `preflight` never starts either inspection backend,
including when `--backend docker` is present.

It rejects repository paths, relative/traversal paths, symlinks/reparse points, wrong filenames,
non-regular or empty archives, existing planned outputs, overwrite attempts, invalid custom-format
listings, foreign schemas, checksum drift and manifest field drift. It never prints the listing or
subprocess output.

## Approval and preflight gate

Stop unless all items are confirmed immediately before the approved window:

- exact 40-character application/migration source commit and the intended Phase A SQL checksum;
- Owner-approved Taiwan-time maintenance window, operator and reviewer roles;
- PostgreSQL server major and locally installed `pg_dump`/`pg_restore` majors are compatible;
- direct production reachability is confirmed by the operator without sharing connection metadata;
- encrypted repository-external storage has sufficient free space for archive plus verification copy;
- the destination is not a repository, workspace, home-directory sync folder, removable shared
  folder or automatic consumer cloud-sync location;
- restore authority and a separate isolated non-production restore target are available;
- no migration, deployment, backfill, maintenance job or other schema work overlaps the window;
- the three exact output paths pass the repository tool's `preflight` action and do not exist.

A provider plan name, successful catalog query or `pg_dump --version` is not backup proof.

## Credential boundary

- Supply connection fields only through the operator's temporary process environment or a
  permission-restricted PostgreSQL password file. Passwords must never appear in argv, command
  templates, shell history, URLs, logs, screenshots, clipboard transcripts, archive names,
  sidecars, manifests or Git.
- Do not use a DSN/URI. Do not enable shell tracing, transcript recording or verbose client output.
- Give the temporary credential only the approved backup scope and lifetime. Clear the temporary
  process environment and dispose of the password file according to the approved credential process
  after both archive checks finish.
- If any credential or connection identity is displayed, copied, logged or included in evidence,
  stop immediately, preserve only a sanitized incident reference and ask Owner to initiate the
  credential-exposure response. Do not continue with the same credential.

## Reviewed `pg_dump` contract

The following is a review template, not an executable production wrapper. The operator must first
set the approved connection environment privately and assign `$archive` to the exact preflighted,
nonexistent repository-external path.

```powershell
pg_dump --format=custom --schema=ntubtob --no-owner --no-privileges --lock-wait-timeout=5000 --file=$archive
```

Required invariants:

- custom format only; exactly schema `ntubtob`;
- `--no-owner` and `--no-privileges` for portable ownership/ACL behavior;
- bounded five-second lock wait; the first timeout stops the attempt;
- archive goes to the reviewed file, never stdout, and the path must not already exist;
- no parallel dump, blobs outside the schema, ad-hoc excludes, data filters or post-processing;
- do not retry by editing options. Resolve the cause, re-preflight a new timestamped name, then obtain
  confirmation for one full retry within the approved window.

## Archive validation and retention

1. Confirm `pg_dump` exited zero and the archive is a non-empty regular file at the exact path.
2. Run the tool's `create` action. It invokes only `pg_restore --list` and `--version`, verifies custom
   format and the `ntubtob` scope, then exclusively creates the checksum and fixed manifest.
3. Move/copy all three files only via the approved encrypted repository-external storage process.
4. Run the tool's `verify` action against the retained copy. This recomputes SHA-256, size and listing
   validation and requires exact sidecar/manifest agreement.
5. Record only basenames, byte size, SHA-256, generic client major, UTC timestamp and pass/fail in the
   migration evidence. Never record the archive listing or connection/identity metadata.
6. Retain the verified set through Phase A execution, post-checks and Owner confirmation. Any later
   deletion needs a separate exact-target approval and recoverable/safe disposal method; this tool
   never deletes artifacts.

If dump exit status, listing, size, checksum, manifest, second-copy verification or output location is
ambiguous, Phase A remains blocked. Preserve the artifact without opening it and request review.

## Isolated restore-readiness gate

Production restore, `--clean`, `--create`, `--if-exists`, drop, overwrite and restore into any shared,
staging-with-real-data or production database are forbidden. A later approved rehearsal may restore
the verified archive only into a newly created isolated non-production PostgreSQL database whose
local/sandbox identity is independently confirmed.

The reviewed restore shape is:

```powershell
pg_restore --exit-on-error --single-transaction --no-owner --no-privileges --dbname=<approved-isolated-database> <absolute-archive-path>
```

Before declaring restore-ready, compare sanitized results with the source evidence:

- expected `ntubtob` schema objects, tables, columns, indexes, PK/FK/check constraints and triggers;
- aggregate row counts by approved generic category (do not commit exact production counts);
- sequence ownership and next-value behavior without consuming production sequences;
- RLS enabled/forced flags and policy presence, noting that ownership/ACL was intentionally omitted;
- successful application of constraints against conspicuously fake local verification rows only;
- a second archive checksum verification after the rehearsal.

Do not inspect or copy production row contents for evidence. A successful import alone does not prove
application rollback, runtime-role grants, API exposure or provider disaster recovery.

### Fail-closed rehearsal wrapper

`tools.portal_data_restore_rehearsal` separates path-only preflight from execution. Preflight validates
that the existing archive, manifest and checksum are adjacent, repository-external regular files with
the fixed basename contract. It neither resolves Docker nor starts a container:

```powershell
py -3.10 -m tools.portal_data_restore_rehearsal preflight <absolute-archive-path> <absolute-manifest-path> <absolute-checksum-path>
```

Execution is not authorized by the presence of the tool or by a successful preflight. After Work
review, merge and an Owner approval naming the exact commit and artifact set, the fixed acknowledgement
is required:

```powershell
py -3.10 -m tools.portal_data_restore_rehearsal execute <absolute-archive-path> <absolute-manifest-path> <absolute-checksum-path> --acknowledge TASK-057-EPHEMERAL-LOCAL-RESTORE
```

The wrapper first and last invokes the existing Docker archive verifier. Between those checks it uses
only the repository-fixed PostgreSQL image ID with `--pull never`, `--network none`, no published port,
no Docker volume and no Docker socket/repository/home mount. The PostgreSQL data directory, runtime
socket and temporary directory are bounded tmpfs mounts. Only the archive parent is bind-mounted at
`/backup` read-only. The container has a generated TASK-057 name and label, runs read-only with all
capabilities dropped and is removed on both success and failure; failure to confirm cleanup is itself a
terminal failure.

The database exists only inside that container and uses local trust authentication in the no-network,
no-port namespace. The wrapper accepts no DSN, host, port, database target, image, environment file,
credential, restore option or SQL argument. Restore uses only `--exit-on-error --single-transaction
--no-owner --no-privileges`; destructive restore flags and parallel jobs are absent.

The fixed catalog query returns only named booleans. It compares the restored schema with the
deidentified TASK-049 table/column/type/nullability/default/identity, PK/FK, validated-constraint,
primary-index, trigger, RLS/policy and identity-sequence contract. It scans every legacy table only to
prove that count queries complete; it does not return row values or exact counts. Reports may record
only generic pass/fail categories and cleanup status.

TASK-057 development and tests may use conspicuously fake archives only. Running this wrapper against
the retained production archive remains a separate Owner gate; do not infer that approval from this
runbook, a merged PR or a fake-data rehearsal.

## Failure and stop handling

- Client/server major mismatch, missing client, direct-path ambiguity, insufficient storage,
  pre-existing output, lock timeout, nonzero exit, unexpected schema/listing, checksum drift,
  credential exposure or unclear destination: stop before migration.
- Never delete or overwrite an ambiguous/partial archive. Quarantine its exact path and obtain a
  separate cleanup decision; use a new timestamped filename for any approved retry.
- If restore fidelity differs, retain archive and sanitized findings, abandon the isolated target,
  and keep Phase A blocked. Do not compensate by changing production or editing the archive.
- If the destination may synchronize or expose data, stop transfer and invoke the approved data
  exposure response. Do not place the artifact in Git, issue trackers, chat or CI artifacts.

## Current status

TASK-056 produced and independently verified the retained production logical-backup artifact set.
TASK-057 prepares the isolated restore wrapper and tests it with fake data only. Until a production
archive rehearsal is separately approved, executed and reviewed, Phase A migration remains blocked.
