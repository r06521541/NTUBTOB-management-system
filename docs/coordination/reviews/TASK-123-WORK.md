# TASK-123 Work review

## Decision

Changes requested before controlled staging dogfood.

## Findings

- The console exposes only explicit, bounded actions. Routine paths are
  separated from Owner-private credential delivery and return one stable,
  de-identified governance envelope.
- Exact detached source, E-drive task roots, AVD/serial, APK package and signer
  checks protect session-preserving `adb install -r`. Wrong, stale, partial or
  ambiguous inputs fail before install.
- Status uses one bounded in-memory accessibility hierarchy and emits only
  allowlisted Basic/Officer and report-enabled/disabled counts. It does not
  retain raw UI XML, logcat, names or sensitive runtime data.
- Owner-private operations remain interactive and locked across inspect,
  confirmation, at-most-one mutation, reconciliation and postcheck. Sensitive
  values are child-environment-only and cleared in `finally`.
- Initial review rejected stale coordination ancestry, missing semantic status
  evidence, signer-only package validation and unlocked private mutation. The
  corrected implementation closes all four findings without expanding scope.

## Evidence

- Codex: 26 direct tests, py_compile, PowerShell parser, isort and diff/scope
  checks passed. Windows Black remained boundedly stalled and is not claimed.
- Main Work: authoritative ancestry and exact writer scope passed; independent
  bundled-Python rerun passed all 26 direct tests in 23.237 seconds.
- Flutter Domain: targeted review accepted the config-variable and bounded
  reason-code corrections, but found that the output-redaction fallback can
  emit `FAILED` while preserving an earlier successful process exit. The
  fallback must return exit code 2, emit exactly one safe JSON result and have
  a direct no-disclosure regression. That correction is now accepted.
- Controlled dogfood: corrected `preflight` returned one governed `PASS` JSON.
  The first read-only `status` then returned `RUNTIME_FAILED` because its
  semantic classifier requires exactly one authenticated Basic/Officer debug
  projection. Status must safely classify the valid logged-out login gate and
  avoid UI projection reads when the package is absent or the portal is
  background/stopped. Ambiguous or duplicate allowlisted states must continue
  to fail closed, and raw accessibility data must remain undisclosed.
- The status-state correction is otherwise accepted, but current-activity
  detection still searches the entire `dumpsys` text for any retained portal
  activity. It must parse one exact resumed/top-resumed/focused component so a
  background or stopped portal cannot trigger an accessibility dump over LINE,
  Chrome or another foreground app. Ambiguous current records must fail closed.
- The anchored foreground parser correction is accepted. Controlled API 36
  dogfood then showed that `adb shell uiautomator dump /dev/tty` returns only a
  completion notice (34 bytes, zero hierarchy markers), while the same bounded
  command through `adb exec-out` returns one complete in-memory hierarchy
  (4401 bytes, one start/end pair). Status must use exact `exec-out` transport,
  retain the existing size/XML/redaction gates and never create/cat/remove a
  device-side hierarchy file.

## Deferred

Hosted Black/repository CI and a separately authorized staging dogfood remain
required. TASK-123 does not make credential delivery fully agent-operated.
The Staging Acceptance Harness, no-disclosure credential broker, relational
fixture lifecycle and acceptance observability contract remain later work.
