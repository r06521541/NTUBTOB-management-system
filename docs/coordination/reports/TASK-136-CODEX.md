# TASK-136 Codex report

## Delta

- Update candidates no longer pass an IAM-changing unauthenticated flag;
  bootstrap remains explicitly private.
- Candidate, promotion and rollback traffic validation accepts only the active
  approved revision at 100% and its approved counterpart at 0%.
- Direct regressions cover update/bootstrap command separation, retained-zero
  acceptance, and unknown/duplicate/nonzero extra traffic rejection.

## Runtime boundary

This repository correction performs no build, deployment, traffic, IAM,
Secret, database, migration or broker action. The preceding dogfood was rolled
back to the healthy TASK-117 revision before implementation began.

## Verification

- Affected direct tests: 3 passed.
- `py_compile` and `git diff --check`: passed.
- The bundled Windows `isort --check-only` proposes the same broad import
  compaction across pre-existing multiline imports; it was not applied. Hosted
  CI remains the final format gate.
