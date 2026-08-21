# TASK-139 — Isolated status process equivalence

## Goal

Make the acceptance harness preserve a deterministic, bounded stage result when
its isolated launcher status child cannot be invoked or returns a malformed
transport object. A real local PowerShell child that emits the accepted status
envelope must remain equivalent to the standalone governed launcher result.

## Scope

- `tools/Invoke-MobileStagingAcceptance.ps1`
- `tools/tests/test_mobile_staging_acceptance.py`
- this task, its report, and the existing mobile staging runbook

## Invariants

- No additional runtime retry, UI input, build, install, cold launch, login, or
  checkpoint transition.
- Raw child output, exception text, paths, XML, credentials, and provider data
  never enter the governed envelope.
- Existing accessibility readiness and terminal reason behavior is unchanged.

## Acceptance

- A real local PowerShell child with the exact PASS envelope returns one
  `observed` object and no extra success-stream object.
- Child invocation exceptions become `STATUS_CHILD_INVOKE_UNAVAILABLE`.
- Missing transport fields become `STATUS_CHILD_TRANSPORT_INVALID`.
- Both failures are terminal, one-attempt, no-wait and no-disclosure.
- Affected tests, parser, compile/isort, Domain targeted review, and hosted CI
  pass before any further emulator invocation.

## Verification budget

- Writer: one affected suite.
- Domain: one targeted review; no full replay.
- Main: integration diff check.
- Hosted CI: one final gate; infrastructure-only retry may reuse the same SHA.
