# TASK-133 Preserve bounded status child transport reasons

## Scope

Classify all status-child transport and envelope failures with fixed safe reason
codes. Do not add retries, runtime actions, raw diagnostics, or acceptance states.

## Invariants

- timeout, stderr, output shape, JSON envelope, child result, and host failures
  remain distinct and never expose child data;
- every transport reason stops after one attempt;
- existing app-stage and accessibility behavior remains unchanged.

## Acceptance

Direct tests cover each transport boundary through final classification, followed
by the affected harness suite, targeted review, hosted CI, and one controlled
resume of the retained checkpoint.
