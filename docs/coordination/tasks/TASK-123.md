# TASK-123: Mobile staging launch console

task_type: delivery
delivery_group: mobile-staging-launch-console
requires_independent_pr: true
status: ready_for_hosted_ci
base_commit: ff5dfd13da930226a8195f53e0c931f6c9d2fb31
shared_branch: codex/mobile-staging-launcher
implementation_branch: codex/task-123-mobile-staging-launcher

## Goal

Provide one fail-closed PowerShell entry point for routine Flutter staging and
emulator operations, while reducing private staging-data operations to one
Owner-launched interactive console. The launcher must encode the safety gates
learned from TASK-113 through TASK-122 instead of requiring copied command
sequences.

## Repository scope

- `tools/Invoke-MobileStaging.ps1`
- `tools/tests/test_mobile_staging_launcher.py`
- `docs/operations/mobile/MOBILE_STAGING.md`
- this task and one `TASK-123` Codex report
- the already accepted TASK-122 report-only closeout commit carried by the
  shared branch

No Flutter source, backend/runtime API, schema, migration, model, OpenAPI,
workflow, Secret, IAM, Cloud Run, LINE Console, production, release signing,
store, notification, or external-environment change.

## Command contract

One invocation performs one bounded action. The entry point exposes explicit
actions rather than a hidden multi-step default:

- `preflight`: read-only approved E-drive Flutter/Android/JDK/AVD, disk,
  accepted commit/snapshot and task-owned process checks.
- `avd-start`: start or reuse only the configured approved AVD and wait a
  bounded time for one explicit `adb` serial; never create or wipe an AVD.
- `status`: read-only toolchain/emulator/package/activity and allowlisted UI
  state. It does not retrieve Secret values or call authenticated APIs.
- `build`: require `fake` or `staging`, a full commit SHA and a clean detached
  snapshot. Emit a task-local redacted artifact manifest.
- `signer-check`: when session preservation is requested, require exactly one
  allowlisted task-scoped existing debug certificate matching the installed
  package signer.
- `install`: session-preserving mode permits only exact package/signer match
  and `adb install -r`; never fall back to uninstall, clear data, downgrade or
  a newly generated signer.
- `cold-launch`: one package force-stop and one MAIN/LAUNCHER start followed by
  bounded activity/PID classification; never retry solely because
  `am start -W` returned timeout/UNKNOWN.
- `health`: local checks only by default. An explicit public-health option may
  perform one bounded status-only `/health` request and discard the body; it
  never calls authenticated endpoints.
- `stop`: package-scoped stop only. It never clears data or touches LINE or
  another package.
- `cleanup`: remove only task-owned temporary build/evidence paths permitted
  by retention policy; never global Gradle/Pub/Android caches or app data.
- `private-inspect`, `grant-officer`, and `restore-basic`: Owner-private-console
  actions wrapping only the existing staging data operator. Mutating actions
  require their exact typed confirmation and are never bundled with normal
  launch, acceptance or cleanup.

## Security and safety invariants

- No action is implicit. Missing or conflicting action/mode/commit/config is a
  hard failure before side effects.
- Routine and Owner-private execution are separate code paths. Help, status,
  preflight and every routine action must not initialize `gcloud`, inspect a
  private environment variable, resolve a Secret value reference, or load the
  mutation operator path.
- Routine actions are agent-operable under DEC-098. LINE QR, credentials,
  login/consent, Secret payloads, private provider subject, paid/public IAM,
  production, release signing and store actions remain Owner-only.
- The private actions accept a private approval path but never accept the
  provider subject or database URL on the command line. They capture the exact
  approved Secret reference and interactive subject only inside the Owner's
  local process, pass them only through one child-process environment, and
  clear variables in `finally` on success, failure and interruption.
- The launcher never prints or persists endpoint values, channel IDs, DSN,
  provider subject, token, assertion, response body, secure-store content,
  keystore path/material/password, raw UI XML, raw logcat or unredacted
  screenshots.
- Flutter build arguments may contain only the public compile-time identifiers
  `APP_FLAVOR`, `CLIENT_MODE`, `API_BASE_URL`, and `LINE_CHANNEL_ID` as direct
  `--dart-define` arguments. Fake mode uses only the first two; staging uses
  exactly all four. This allowance never extends to a Secret, token, subject,
  DSN, assertion, credential, or an unapproved key/value. Child command lines,
  output, and define values are never emitted or copied into evidence, errors,
  reports, or governed JSON; in-memory collections are cleared in `finally`.
- Redacted evidence may contain only accepted commit, mode, package/version,
  artifact SHA-256, public signer fingerprint, AVD/API/ABI versions, bounded
  result classification and allowlisted static labels/counts.
- Debug signer inventory is restricted to a declared allowlist of task-scoped
  Android user homes. Zero, multiple, mismatch or unknown ownership fails
  closed; the launcher never creates/copies a key or edits Gradle signing.
- Any network/offline setting changed by the launcher is restored in `finally`.
  Process cleanup is task-owned and must not kill unrelated Java/Gradle jobs.
- Owner-private actions must refuse non-interactive or missing-confirmation
  execution. Agent execution stops with `OWNER_ACTION_REQUIRED` before Secret
  retrieval or mutation.
- Every action emits one fixed, de-identified JSON result with stable
  classification `PASS`, `OWNER_ACTION_REQUIRED`, `DRIFT`, `TIMEOUT`, or
  `FAILED`. It includes `operator`, `owner_gate`,
  `standing_authorization=DEC-098`, `stop_only_on`, and
  `report_to=main-work`; callers never need raw logs or prose to classify the
  result.
- A private mutation always executes read-only inspect, exact typed
  confirmation, at most one mutation, and an independent read-only post-check.
  An unknown result or interruption is never retried as a mutation; the next
  permitted action is read-only reconciliation. Confirmation text never
  contains a provider subject, DSN, token, or Secret value.
- Runtime classification uses semantic/accessibility identifiers and
  allowlisted debug projections. It never depends on screen coordinates, OCR,
  raw UI XML, or raw logcat.

## Verification

- Test the complete action/mode matrix, help and unknown/conflicting arguments.
- Prove default/status/preflight perform zero mutation and do not retrieve
  Secret values.
- Mock Flutter, Android, ADB, Java, Git, gcloud and Python executables; verify
  bounded timeouts and exact allowed commands without external access.
- Cover stale/partial APK, dirty/wrong commit, unknown disk/lock/AVD/serial,
  signer zero/multiple/mismatch and successful session-preserving install.
- Cover launcher timeout classification without automatic retry.
- Cover Owner-private interactivity, exact mutation confirmation, approved
  Secret reference selection, child-only environment, redaction and `finally`
  cleanup on success/failure/interruption.
- Cover process interruption and child-process residue, concurrent launcher
  invocation, stale lock, multiple ADB serials, partial APK, wrong signer, and
  launcher timeout where the target process actually started.
- Prove output/evidence contain none of the forbidden sensitive fields or test
  sentinel values.
- Prove exact fake/staging define keys and counts, reject an adversarial
  Secret-like key/value before child start, and preserve cleanup after child
  timeout, nonzero exit, or a partial APK.
- Run affected Python tests, PowerShell parser/static checks where available,
  py_compile, Black/isort for Python test files, `git diff --check`, scope and
  sensitive-string scans. Hosted CI supplies final Python 3.10 evidence.

## Collaboration

- Shared/Web Codex is the sole implementation writer for TASK-123.
- Flutter Domain Work performs a read-only review of toolchain, AVD, signer,
  session-preserving install and runtime stop boundaries after implementation.
- Main Work owns task integration, hosted CI, the single final PR and merge.
- No launcher command is executed against an emulator, staging, Secret or
  cloud during repository implementation or review.

## Explicit limitation and deferred follow-up

TASK-123 does not make Owner-private actions fully agent-operated. The current
credential-delivery model keeps the provider subject and database Secret value
inside the Owner's private console, which an agent shell cannot safely inherit.
This task reduces that boundary to one private-console invocation and explicit
confirmation; it does not weaken or bypass it.

Do not expand this delivery with multi-step acceptance scenarios, a credential
broker, fixture lifecycle redesign, IAM/Secret changes, or new runtime
observability. After repository acceptance, run one separately authorized
staging dogfood in which the agent performs routine actions and the Owner uses
only the private console. Use its remaining manual checkpoints to scope later
work for:

- a named, resumable Staging Acceptance Harness with explicit pre/post states;
- a no-disclosure credential launcher or broker, subject to separate approval
  for any IAM, Secret version or cloud-resource change;
- relational fictional fixture ownership and reset/reconciliation; and
- acceptance observability contracts defined before each runtime scenario.

## Execution checkpoint

1. Goal: replace copied staging/emulator command sequences with one bounded launcher.
2. Core files: one PowerShell entry, one direct contract test, runbook, task/report.
3. Invariants: zero-mutation default, exact signer/session preservation, no sensitive output, explicit Owner gates.
4. Tests: action matrix, mocks, timeouts, signer/install, private confirmation, redaction and cleanup.
5. Blocker: none; implementation is repository-only and must not execute the launcher externally.
