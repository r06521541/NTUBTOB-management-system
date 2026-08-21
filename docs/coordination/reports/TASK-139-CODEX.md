# TASK-139 Codex report

## Delta

- Added fixed isolated-status invocation and transport-shape terminal reasons.
- Added a real local PowerShell child regression for PASS stream equivalence.
- Added direct one-attempt/no-disclosure regressions for invocation failure and
  malformed transport shape.

## Runtime boundary

No launcher, emulator, ADB, staging, broker, Secret, database, or cloud action
is part of this repository correction. The existing TASK-138 checkpoint remains
at `await_observation` and is not advanced by this task.

## Verification

- `python -m unittest tools.tests.test_mobile_staging_acceptance -v`: 27/27
  PASS.
- Real child equivalence focused regression: 1/1 PASS.
- PowerShell parser, Python compile/isort, scope and diff checks: PASS.
- Windows Black remains deferred to hosted CI under the established bounded
  local formatter limitation.
