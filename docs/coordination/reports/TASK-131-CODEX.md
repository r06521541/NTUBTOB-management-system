# TASK-131 Codex report

## Delta

TASK-129 previously collapsed all exhausted accessibility states into
`STATUS_UNAVAILABLE`. The harness now retains only the existing fixed safe reason:
`ACCESSIBILITY_UNAVAILABLE`, `ACCESSIBILITY_INVALID`, or `SEMANTIC_DRIFT`.
Unknown exceptions remain redacted to `STATUS_UNAVAILABLE`. Retry count, delays,
checkpoint binding, and runtime behavior are unchanged.

## Verification

- targeted terminal-reason tests: 2 passed;
- affected acceptance harness suite: 18 passed;
- PowerShell parser, Python compile/isort, and diff checks: passed;
- Windows Black 24.4.2 retains the documented local-stall limitation; hosted
  formatting and CI remain pending.

## External effects

Repository-only implementation. No launcher, emulator, staging, private console,
cloud, Secret, login, or notification action.
