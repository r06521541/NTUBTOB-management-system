# TASK-123 Codex Report

## Outcome

Implemented one repository-owned PowerShell launch console for bounded mobile
staging preparation and local acceptance actions. Routine and Owner-private
dispatch are separate: routine actions never initialize the private staging
operator, `gcloud`, database Secret resolution, or private subject handling.
Every invocation returns one de-identified governance envelope with a stable
classification, an allowlisted non-sensitive reason code for non-PASS results,
and no raw exception or child output.

Controlled dogfood found that the real config loader used `$home` as an
iterator; Windows PowerShell treats it as the read-only automatic `$HOME`
variable because names are case-insensitive. The iterator and the writable
`$Matches` collisions were renamed. A complete, unstubbed value-free config now
loads in direct regression tests, exact invalid variants fail closed, and a
source contract rejects assignment/iteration over PowerShell automatic or
read-only names.

The console validates an explicit full commit and clean detached snapshot,
task-owned E-drive paths, one AVD/serial, a unique allowlisted existing debug
signer, exact `tw.org.ntubtob.portal` APK identity through one absolute package
inspector, fresh APK evidence, and session-preserving `adb install -r`. Status
parses one bounded in-memory accessibility hierarchy with DTD/external
resolution prohibited, then returns only allowlisted Basic/Officer and report
enabled/disabled counts. Cold launch
uses semantic package/activity/PID checks, has no timeout retry, and restores a
temporary network change in `finally`. Flutter defines use a named pipe and do
not enter argv, files, evidence, or output.

Owner-private inspect/grant/restore remains interactive. The provider subject
and approved database Secret payload exist only in the child environment and
are cleared in `finally`. A mutation follows inspect, exact non-sensitive
confirmation, at most one mutation attempt, and independent postcheck. An
interruption permits read-only reconciliation only.
The task-owned exclusive lock now covers that entire private lifecycle and is
acquired before Secret resolution or operator initialization.

## Security and scope review

- No emulator, staging, `gcloud`, Secret, database, LINE, cloud, deployment, or
  production action was executed.
- No backend, schema, migration, Flutter source, workflow, or non-task test was
  changed by the implementation. Authoritative shared ancestry was
  fast-forwarded intact and carries its task, HANDOFF, COLLABORATION 2.2,
  review, and planning rationale without Codex rewriting them.
- Output/evidence exclude endpoints, channel IDs, subjects, DSNs, tokens,
  assertions, keystore data/path, raw UI XML, logcat, and child response bodies.
- Cleanup is restricted to TASK-123 temp/evidence roots; it does not clear app
  data or global Android, Gradle, Pub, or process state.

## Verification

Using the repository bundled Python on Windows:

- `python -m unittest tools.tests.test_mobile_staging_launcher -v`: 29 passed.
- `python -m py_compile tools/tests/test_mobile_staging_launcher.py`: passed.
- `python -m isort --check-only tools/tests/test_mobile_staging_launcher.py`:
  passed after applying isort to the new file.
- Windows PowerShell 5.1 parser: passed as part of the direct suite.
- `git diff --check`: passed.

The direct suite covers parser/action matrix, one-result JSON governance,
strict private/routine separation, snapshot/disk/lock/AVD/serial gates,
concurrent/stale lock handling (including private dispatcher rejection and
failure cleanup), stale and partial artifacts, exact package identity, signer
inventory, session-preserving install, bounded accessibility classification,
bounded child-process cleanup, launch
timeout/anomaly and network restoration, private
confirmation/mutation/reconciliation order, child-environment cleanup, and
adversarial redaction sentinels.
It now also covers complete real config loading, exact invalid config variants,
automatic/read-only variable collision scanning, stable reason-code mapping,
and actual one-line governed config/Owner-gate failures without raw exception
or path disclosure.

Bundled Black CLI and formatter API both remained unresponsive for more than
the bounded local check window and were terminated, matching the documented
Windows Black limitation. No Black pass is claimed; hosted CI remains the final
Black gate. No real emulator, Flutter build, ADB device, staging endpoint, or
Owner-private action was run.

## Deferred follow-up (not implemented)

- A: named resumable Staging Acceptance Harness.
- B: no-disclosure credential launcher/broker.
- C: relational fictional fixture lifecycle/reset/reconcile preserving audits.
- D: acceptance observability contracts defined before runtime claims.

## Handoff

- Branch: `codex/task-123-mobile-staging-launcher`
- Base: `20f393778a9010ac52ad9c8935f3992d72ce06a0`
- Implementation commit: `3998b9681595b503b6d9b12eb1778d8ac51ccfcc`
- Changes-requested implementation commit:
  `3f424d775395d33a449a480c0c14c2dde802c1d4`
- Controlled-dogfood correction commit:
  `5384882f43dc9cfe5e514924a97ebf91d9085c9c`
- Authoritative shared ancestry: `b9f3e10ad08b84ee1aee290cd5d34b6c2dc52698`
- External side effects: none; repository-only tests used mocked executables.
- Unverified: real emulator/ADB/Flutter build, Owner-private console, staging and
  hosted Black/Python 3.10 remain Main Work/final CI evidence.

Main Work owns integration, hosted CI, PR, and merge.
