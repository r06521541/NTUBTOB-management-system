# TASK-131 Preserve bounded acceptance status reasons

## Scope

Preserve the final fixed accessibility reason when TASK-129 exhausts its existing
read-only status window. Do not add retries, runtime actions, raw diagnostics, or
new acceptance states.

## Invariants

- unavailable, malformed, and semantic drift remain distinct bounded reasons;
- unknown exceptions remain `STATUS_UNAVAILABLE` and disclose no source value;
- the existing checkpoint, attempt count, delays, and mutation boundaries remain unchanged.

## Acceptance

Direct tests cover all terminal mappings and retry exhaustion. Run the affected
acceptance suite, parser/compile/format checks, targeted read-only review, and one
hosted CI gate before controlled checkpoint resume.
