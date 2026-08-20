# TASK-127 Work review

## Decision

Accepted for hosted CI.

## Findings

- The launcher accepts exactly one provenance-bearing principal projection and
  preserves the existing foreground, bounded XML and no-disclosure gates.
- Only `fresh_server` retains authoritative Basic/Officer semantic states.
  `offline_cache` and `unknown` are explicitly non-authoritative; legacy,
  duplicate, coexisting, malformed and role/report-inconsistent projections
  fail closed.
- Logged-out remains mutually exclusive and emits `provenance=none`. Report,
  attendance, cache/session aggregate and harness vocabularies are not consumed
  by this slice.
- Main requested one test-only correction: the inherited output-redaction test
  had placed its sentinel in the bounded `result` field and no longer reached
  `Write-SafeJson`. The corrected test keeps a valid result and proves the
  actual fallback returns one safe FAILED envelope with exit code 2.

## Evidence

- Launcher direct suite: 48/48 passed after the targeted correction.
- PowerShell parser, `py_compile` and `git diff --check` passed. The writer's
  environment lacked isort; hosted CI remains the final Python/format gate.
- No emulator, staging, Secret, database, cloud or deployment action ran.

## Remaining gate

- Run the selected hosted deployment-tool/final gates. Runtime consumption is
  deferred until the remaining TASK-124 producers are accepted.
