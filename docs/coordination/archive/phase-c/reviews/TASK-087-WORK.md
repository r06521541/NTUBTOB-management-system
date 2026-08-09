# TASK-087 Work review

## First review（2026-08-10）

- Reviewed branch `codex/activate-existing-linked-players`, implementation `0aa2adf34f0753ac720477c51861e8acef9eaa73`, handoff HEAD `fd1e29b5f38d6564acc77250e8210fdf308af0dc`.
- Eligibility, relationship validation, advisory/row locking, all-or-nothing status/audit transaction, partial-state rejection, idempotent completion, redacted output and checksum boundaries are otherwise sound.
- Work reran TASK-087 plus adjacent exact-two contract suites: 14/14 passed; compileall and diff check passed. Codex's isolated PostgreSQL 15/16 matrices each passed 6/6 plus adjacent 6/6.
- Blocking finding: the production launcher performs `discovery -> preflight -> execute -> post-check` in one invocation. It therefore mutates a dynamically discovered cohort before Work/Owner can observe and approve the exact production count. This is broader than the authorization to process the known existing cohort and defeats the explicit expected-54-but-do-not-assume boundary.
- No external or production operation occurred during review. Work-owned hardening notes remain untracked and excluded.

Conclusion: `changes_requested`. Provide a two-stage reviewed boundary in the same package: (1) an independently safe read-only discovery invocation that cannot call execute or set execution acknowledgement; (2) a separate execution invocation requiring an explicit positive approved cohort count, revalidating that exact count under the same transaction lock before any write. Wrong/missing count must fail before DML. Add subprocess/behavioral regressions proving discovery cannot mutate and execute cannot proceed with drifted count. Preserve all existing transaction behavior and do not perform external operations.

## Second review（2026-08-10）

- Correction commit `6b7449a9d4a15b373b92b8ba796963f03faaab04` separates an independently checksummed repeatable-read/read-only discovery launcher from the execution launcher.
- Discovery contains neither execution acknowledgement nor execute call. Execution requires one explicit positive approved cohort count and revalidates the same count under advisory and deterministic row locks before DML.
- Missing, non-positive, boolean, malformed or drifted counts fail before mutation; existing all-or-nothing, audit, rollback, concurrency and idempotent completion behavior is preserved.
- Work reran TASK-087 and adjacent exact-two contract suites: 16/16 passed; compileall and `git diff --check` passed. Codex's final isolated PostgreSQL 15/16 TASK-087 matrices each passed 7/7.
- No external or production operation occurred. Work-owned hardening notes remain excluded.

Conclusion: `accepted`; proceed to one ready PR and hosted CI. After squash merge, run discovery only, return the fixed cohort count to Work/Owner, and do not execute until that exact count is explicitly accepted.
