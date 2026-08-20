# TASK-132 Preserve bounded pre-accessibility status reasons

## Scope

Carry the existing fixed ADB, package, and activity reason codes through the
TASK-129 harness. Do not add retries, runtime actions, diagnostics, or acceptance
states.

## Invariants

- the six allowlisted reasons stop after one status attempt;
- unknown codes and exceptions remain `STATUS_UNAVAILABLE` without disclosure;
- accessibility readiness, checkpoint, and mutation behavior remain unchanged.

## Acceptance

Direct tests cover the isolated child envelope through final classification for
all six reasons, followed by the affected harness suite, targeted review, hosted
CI, and one controlled resume of the existing checkpoint.
