# TASK-127 Codex report

## Delivery

- Base/spec SHA: `031406194ab0cdd601867f6997ac38161e7354d7`
- Implementation branch: `codex/task-127-principal-provenance-implementation`
- Scope: TASK-123 launcher principal-provenance consumer slice 5a only
- Owned paths: launcher, direct launcher tests, mobile staging runbook, this report

## Implemented behavior

`status` now consumes exactly one accepted TASK-124 package-1 principal
projection. It validates the role/report relationship and the matching source
label for `fresh_server`, `offline_cache`, or `unknown`, while preserving the
existing foreground-only, in-memory accessibility and no-disclosure gates.

Fresh projections retain the canonical Basic and Officer semantic states.
Offline and unknown projections return bounded `*_non_authoritative` states
with their provenance token and cannot be treated as authoritative
authorization evidence. Logged-out returns `provenance=none`. Legacy,
duplicate, coexisting, malformed, inconsistent, and mismatched projections
fail closed without returning localized text or hierarchy data.

No report, reply, cache/session aggregate, harness, private/runtime, Flutter,
database, cloud, or deployment behavior was added.

## Verification

- PowerShell parser: passed.
- `git diff --check`: passed after the targeted review correction.
- Direct launcher suite: 48 tests, 48 passed.
- Three new provenance tests cover fresh Basic, fresh Officer enabled/disabled,
  offline/unknown non-authoritative states, legacy/duplicate/coexisting and
  malformed projections, source-label mismatch, sentinel redaction, deferred
  vocabulary absence, and existing foreground zero-dump behavior.
- Main targeted review found that the inherited redaction-fallback regression
  put its sentinel in `result`, so bounded result validation stopped before
  `Write-SafeJson`. The corrected direct test keeps a legal result token and
  places the sentinel in another bounded details field. It now proves the
  actual no-disclosure fallback emits exactly one
  `FAILED/OUTPUT_REDACTION_FAILED` envelope, exits 2, and discloses neither the
  sentinel nor raw exception text.
- No emulator, staging, Secret, runtime, database, cloud, or deployment command
  was executed.

## Handoff limits

Hosted CI remains responsible for the final Python/format gate.
