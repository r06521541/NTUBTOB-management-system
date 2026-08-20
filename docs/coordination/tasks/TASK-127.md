# TASK-127: Launcher principal-provenance consumer

- Task type: repository implementation
- Delivery group: `mobile-staging-acceptance-automation`
- Requires independent PR: false
- Status: ready for hosted CI
- Owner gate: none

## Goal

Teach TASK-123 `status` to consume only the accepted TASK-124 package-1
principal provenance vocabulary so Basic/Officer authorization can distinguish
fresh server evidence from offline cache or unknown presentation. Do not consume
report, reply, cache/session aggregate, or scenario vocabulary in this slice.

## Scope and ownership

One writer owns `tools/Invoke-MobileStaging.ps1`, its direct launcher tests,
`docs/operations/mobile/MOBILE_STAGING.md`, and one TASK-127 report. Flutter,
database, fixture, broker, harness, runtime, cloud, and global coordination are
out of scope.

## Invariants and acceptance

- Foreground-only bounded in-memory accessibility parsing and all TASK-123
  no-disclosure/zero-mutation gates remain unchanged.
- Accept exactly one principal projection whose role/report state is mutually
  consistent and whose provenance is exactly `fresh_server`, `offline_cache`,
  or `unknown`. Missing, duplicate, malformed, or coexisting projections fail
  closed.
- `fresh_server` may produce canonical Basic/report-disabled,
  Officer/report-enabled, or Officer/report-disabled states. Offline/unknown
  never masquerade as authorization PASS and return stable non-authoritative
  states for a future harness to classify as `EVIDENCE_GAP`.
- Logged-out remains mutually exclusive with every principal projection.
- Output contains only bounded state/count/provenance tokens; no localized raw
  label, identity, capability string, endpoint, token, body, hierarchy, path,
  or cache material.
- Existing accepted-main APKs using the pre-provenance projection classify
  `DRIFT`, not fresh evidence.
- Direct tests cover all three fresh role/grant states, offline/unknown,
  logged-out, duplicate/coexisting/malformed/legacy projection, sentinel
  redaction, release-vocabulary absence contract, and zero UI dump outside the
  portal foreground.

## Verification budget

- Writer: one affected direct launcher suite plus parser/format/diff/scope.
- Main: delta-only parser/vocabulary review.
- Hosted CI: one deployment-tool/final gate; no Flutter suite rerun is required
  unless change detection currently cannot avoid it.

## Five-line checkpoint

1. Goal: consume accepted bounded principal provenance in launcher status.
2. Files: launcher, direct tests, runbook, one report.
3. Invariants: fresh only is authoritative; offline/unknown bounded; no raw UI or identity.
4. Tests: exact semantic matrix, ambiguity/redaction, foreground zero-dump, parser/diff/scope.
5. Blockers: none; report/reply/cache/session/scenario vocabulary stays deferred.
