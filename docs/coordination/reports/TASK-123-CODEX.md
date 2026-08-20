# TASK-123 Codex Report

## Outcome

Implemented one repository-owned PowerShell launch console for bounded mobile
staging preparation and local acceptance actions. Routine and Owner-private
dispatch are separate: routine actions never initialize the private staging
operator, `gcloud`, database Secret resolution, or private subject handling.
Every invocation returns one de-identified governance envelope with a stable
classification, an allowlisted non-sensitive reason code for non-PASS results,
and no raw exception or child output.
The output-redaction fallback now changes the effective classification before
the final exit decision, so its fixed `FAILED`/`OUTPUT_REDACTION_FAILED` JSON
always exits 2 rather than inheriting a nominal action's successful exit.

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
first derives package/activity. Package absent, portal background, and portal
stopped return bounded states and zero projection/login counts without an
accessibility call. Activity parsing uses exactly one anchored current
resumed/top-resumed/focused record, ignores retained back-stack entries, and
fails closed on duplicate or malformed current records. Only an exact portal
foreground component parses one bounded in-memory hierarchy
using exact `adb -s <serial> exec-out uiautomator dump /dev/tty` arguments,
without a device temp file or follow-up file command. DTD/external resolution
remains prohibited, and the classifier accepts exactly one logged-out,
Basic/report-disabled, Officer/report-enabled, or Officer/report-disabled
state. Logged-out specifically requires one enabled, clickable portal
`android.widget.Button` with exact `LINE 登入`; duplicated Flutter prompt
semantics and other unapproved labels are ignored. Cold launch
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
- Targeted output fallback plus parser regression: 2 passed; the fallback test
  forces a nominal `help` success to contain a test sentinel and proves one
  fixed JSON line, `FAILED`, `OUTPUT_REDACTION_FAILED`, exit 2, empty stderr,
  and no sentinel/raw exception disclosure.
- Targeted status-state plus parser regressions: 4 passed. They cover logged-out
  and all three authenticated foreground states; package absent/background/
  stopped with zero accessibility calls; duplicate/coexisting/missing states;
  malformed/oversized input; zero Secret/mutation access; and sentinel/raw
  hierarchy non-disclosure.
- Targeted foreground parser/status regressions: 4 passed. They prove a retained
  portal task plus current Chrome remains `portal_background` with zero UI
  calls; retained portal without a current component remains `portal_stopped`;
  an exact current portal alone permits one UI call; and duplicate, malformed,
  oversized, or timed-out inventories fail closed without sentinel disclosure.
- Targeted API36 accessibility transport/status regressions: 4 passed. They
  assert the exact `exec-out` argv and absence of shell/device-file commands,
  preserve bounded hierarchy classification, and reject empty, malformed,
  oversized, timed-out, or nonzero-exit results without raw/sentinel output.
- Targeted logged-out semantic/status regressions: 4 passed. A realistic API36
  hierarchy with duplicated prompt semantics and one exact portal login button
  classifies `logged_out`; duplicate/coexisting buttons, wrong package/class,
  disabled/nonclickable nodes, and missing state fail closed without raw XML or
  sentinel disclosure.
- Targeted governed status-reason regressions: 4 passed. Process-level cases
  prove exact `ADB_UNAVAILABLE`, `ADB_INVALID`, `PACKAGE_UNAVAILABLE`,
  `ACTIVITY_UNAVAILABLE`, `ACTIVITY_INVALID`,
  `ACCESSIBILITY_UNAVAILABLE`, `ACCESSIBILITY_INVALID`, and `SEMANTIC_DRIFT`
  envelopes, one JSON line, exit 2, preserved normal PASS, and no fixed message,
  raw exception, or sentinel disclosure.
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
- Output-redaction fail-closed correction commit:
  `17774cd05e1586322d147955bdb0834367808759`
- Complete status-state correction commit:
  `e362650232255a4c31a109d981a3cc2db357eacc`
- Current foreground activity correction commit:
  `d3fa5f493b0da97910d28dd97f70871f1016c5ae`
- API36 accessibility transport correction commit:
  `0fa86e0aeabb08515a0df88c323de55a35dc3583`
- Logged-out button semantic correction commit:
  `1d5c0c38e8a6ac3333e3ec4e13f09608ef2fe5ed`
- Governed status reason correction commit:
  `196924a7a5bda9856c1e40536f1971c087ee7498`
- Complete status-stage reason correction commit:
  `1c2e473fb80cd925e5fdbc2ede1c7cf2f845f304`
- Authoritative shared ancestry: `dfb172646648627d0a85495600254438f513dd34`
- External side effects: none; repository-only tests used mocked executables.
- Unverified: real emulator/ADB/Flutter build, Owner-private console, staging and
  hosted Black/Python 3.10 remain Main Work/final CI evidence.

Main Work owns integration, hosted CI, PR, and merge.
