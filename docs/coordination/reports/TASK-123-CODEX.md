# TASK-123 Codex Report

## Outcome

Implemented one repository-owned PowerShell launch console for bounded mobile
staging preparation and local acceptance actions. Routine and Owner-private
dispatch are separate: routine actions never initialize the private staging
operator, `gcloud`, database Secret resolution, or private subject handling.
Every invocation returns one de-identified governance envelope with a stable
classification and no raw child output.

The console validates an explicit full commit and clean detached snapshot,
task-owned E-drive paths, one AVD/serial, a unique allowlisted existing debug
signer, fresh APK evidence, and session-preserving `adb install -r`. Cold launch
uses semantic package/activity/PID checks, has no timeout retry, and restores a
temporary network change in `finally`. Flutter defines use a named pipe and do
not enter argv, files, evidence, or output.

Owner-private inspect/grant/restore remains interactive. The provider subject
and approved database Secret payload exist only in the child environment and
are cleared in `finally`. A mutation follows inspect, exact non-sensitive
confirmation, at most one mutation attempt, and independent postcheck. An
interruption permits read-only reconciliation only.

## Security and scope review

- No emulator, staging, `gcloud`, Secret, database, LINE, cloud, deployment, or
  production action was executed.
- No backend, schema, migration, Flutter source, workflow, task specification,
  global coordination, or non-task test was changed.
- Output/evidence exclude endpoints, channel IDs, subjects, DSNs, tokens,
  assertions, keystore data/path, raw UI XML, logcat, and child response bodies.
- Cleanup is restricted to TASK-123 temp/evidence roots; it does not clear app
  data or global Android, Gradle, Pub, or process state.

## Verification

Using the repository bundled Python on Windows:

- `python -m unittest tools.tests.test_mobile_staging_launcher -v`: 23 passed.
- `python -m py_compile tools/tests/test_mobile_staging_launcher.py`: passed.
- `python -m isort --check-only tools/tests/test_mobile_staging_launcher.py`:
  passed after applying isort to the new file.
- Windows PowerShell 5.1 parser: passed as part of the direct suite.
- `git diff --check`: passed.

The direct suite covers parser/action matrix, one-result JSON governance,
strict private/routine separation, snapshot/disk/lock/AVD/serial gates,
concurrent/stale lock handling, stale and partial artifacts, signer inventory,
session-preserving install, bounded child-process cleanup, launch
timeout/anomaly and network restoration, private
confirmation/mutation/reconciliation order, child-environment cleanup, and
adversarial redaction sentinels.

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

Implementation commit and branch HEAD are recorded in the formal repository
handoff after commit. Main Work owns integration, hosted CI, PR, and merge.
