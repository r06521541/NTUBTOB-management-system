# TASK-086 — Production zero-admin bootstrap execution

## Goal

Safely activate the Owner's existing Web Portal administrative entry by linking the one eligible pending LINE identity to the one allowlisted legacy Member/Person, then prove the resulting principal and audit state without exposing identifiers or credentials.

## Base commit

`f236f75609e6ede95a5981c2423cdada895f8100`

## Owner authorization

On 2026-08-09 the Owner explicitly authorized Work and Codex to proceed continuously through administrative-entry activation, verification, and the later 56-Person activation. For this task that authorization includes the exact production read-only discovery, preflight, dry-run, one transactional bootstrap DML, and post-check described here. It does not authorize deployment, schema/DDL, Secret/IAM/Scheduler changes, traffic or runtime-flag changes, or notifications.

## Confirmed starting state

- Production schema revision is `0004_phase_c_identity_lifecycle`.
- Phase C is enabled on Web Portal, LINE webhook and notify cron; freeze and identity maintenance are off.
- The last controlled inventory found zero active linked allowlisted administrators, 56 reliable LINE links, and 56 active team-player qualifications with no listed identity/Member/qualification drift.
- TASK-085 merged the reviewed zero-admin domain transaction and local-only operator readiness in PR #89.
- Portal administration remains defined by `WEB_PORTAL_ADMIN_MEMBER_IDS`; this task must not change `portal_access_level`.

## Scope

1. Add a production execution boundary around the TASK-085 domain operation without weakening the local-only operator.
2. Obtain the production database URL and full admin Member-ID allowlist only through an approved private environment channel. Never print, log, commit, or pass them in argv.
3. Provide redacted discovery that selects a target only when all of the following are unique:
   - exactly one allowlisted Member is eligible for bootstrap;
   - exactly one pending, unlinked LINE identity has an open, unredacted review thread and an unignored legacy LINE row;
   - zero active linked allowlisted administrators exist;
   - the target satisfies the existing TASK-085 invariants.
4. If automatic target association cannot be proven uniquely, stop without mutation and return control to Owner. Do not guess or emit raw identifiers.
5. Lock material artifacts with checksums and add offline plus isolated PostgreSQL 15/16 tests covering discovery ambiguity, wrong candidate, retry, rollback and redaction.
6. After repository review, hosted CI and squash merge, execute in order: read-only discovery → preflight → dry-run → execute → read-only post-check.
7. Use a fresh opaque request ID generated inside the approved operator boundary and never expose it in repository or ordinary logs.

## Production success conditions

- Before execution: schema revision 0004; zero active linked allowlisted admins; exactly one eligible target; no relevant drift.
- Mutation: one existing `identity_linked` audit row with null actor; target identity becomes linked; target Person becomes active; legacy Member and LINE links align; active `team_player` remains or is granted according to existing approved lifecycle rules.
- After execution: exactly one active linked allowlisted admin; audit delta exactly +1; no unrelated Person, identity, Member, qualification or attendance aggregate changes.
- A same-request retry is idempotent. Any uncertainty, unexpected delta, logging risk or connection loss stops the workflow; no ad-hoc SQL repair.

## Non-goals

- Do not activate the other 56 linked Persons in this task.
- Do not change Person access level or grant a database role.
- Do not deploy services, change flags/traffic, invoke Scheduler/webhook, send notifications, rotate/read Secret values, or modify schema.
- Do not read or display `envs/**/.env.yaml` or private env-file contents.

## Required verification

- Targeted offline operator/domain tests and checksum verifiers.
- Isolated PostgreSQL 15 and 16 integration tests, including concurrency and full rollback.
- Python 3.10 compatibility, formatter API, compileall and `git diff --check`.
- One ready PR with hosted PostgreSQL 15/16 and final gate before any production execution.
- Production transcript may contain only fixed aggregate/redacted fields and success/failure classifications.

## Stop boundaries

Stop and return to Owner if candidate uniqueness is not proven, the allowlist contains no unique eligible Member, statement logging is unsafe, schema/runtime evidence drifts, a relevant aggregate changes unexpectedly, or post-check does not prove exactly one active linked allowlisted administrator.

## Follow-up

After successful closeout, Work must create TASK-087 for the separate audited activation of the 56 existing linked Persons.

## Production execution recovery note（2026-08-10）

PR #90 was squash merged as `f7c53cd4cace5179f6f1a7f1b0b57d759570fbce`, with hosted PostgreSQL 15/16 and final gate passing. Work invoked the exact merged launcher once under the approved production authorization. The command runner completed, but the orchestration layer failed to forward the launcher's stdout and exit code to Work. The database outcome is therefore classified as uncertain even though no process error was surfaced.

Do not rerun the five-stage launcher and do not generate another request ID. Add a repository-reviewed, checksum-locked `post-check-only` launcher path that reuses all exact runtime, artifact, gcloud metadata, private environment, schema and read-logging guards, injects no execution acknowledgement, invokes only the existing read-only operator `post-check`, and emits only the existing redacted fixed output. It must be impossible for this recovery path to call discovery, execute, the domain mutation or any write transaction. After local tests, one ready PR, hosted CI and squash merge, run this path once against production. If it proves exactly one completed relationship/admin, close the bootstrap as successful; if it proves zero or drift, stop and return to Owner without mutation.

## Owner-approved read-only diagnostic（2026-08-10）

The merged post-check-only recovery returned its fixed stop classification, which intentionally did not identify the failing guard. The Owner approved one additional repository-reviewed production read-only diagnostic. It may report only the following fixed classifications, never raw values:

- runtime/artifact/git guard: `pass|fail`
- gcloud account/project/service/region and single-field metadata projection: `pass|fail`
- private PG environment contract: `pass|fail`
- production connection: `pass|fail`
- schema revision guard: `pass|fail`
- read-logging guard: `pass|fail`
- active linked allowlisted administrator count: `zero|one|other`
- completed TASK-086 relationship count: `zero|one|other`

The diagnostic must be independently checksummed and structurally unable to call the five-stage launcher, `operator.run`, `IdentityLifecycleRepository`, UUID/request-ID generation, execution acknowledgement, or any DDL/DML/write transaction. Database queries must run inside an explicit read-only transaction with local timeouts. Each stage must fail closed without printing exception text, identifiers, credentials, allowlist values, host/project metadata values or SQL parameters. Cleanup must run on every path.

After local tests, one ready PR, hosted CI and squash merge, execute the diagnostic once. Classification determines the next action:

- `admin=one` and `completed_relationship=one`, with all other guards passing: TASK-086 bootstrap succeeded; close it without further mutation.
- `admin=zero` and `completed_relationship=zero`, with all other guards passing: the original bootstrap did not apply; a new exact Owner-approved mutation recovery package is required before any write.
- any `other` or guard failure: stop and return to Owner with the redacted classification only.

The diagnostic authorization does not authorize a second bootstrap, 56-Person activation, deployment, schema, Secret/IAM/Scheduler, flags, traffic or notifications.
