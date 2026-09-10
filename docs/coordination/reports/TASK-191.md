# TASK-191 writer report

- Writer `/root/csr_writer`, claim `task-191-writer-20260910`, lease 1.
- Branch `codex/task-191-profile-diagnostics`; unchanged full HEAD
  `76ec2d0d35ee90d3b8033b34f294b2c3de21864c`. No commit/push.
- Owned: intake/CMS modules, their existing two test modules, and this report.
  Main's task/HANDOFF/state/runbook edits remain separate.

## Delivered

- Added `--diagnose-input`, mutually exclusive with `--execute`. Exact clean local
  SHA/dependencies and fixed same-handle two-file metadata checks precede action
  display and hidden `DIAGNOSE PROFILE <SHA>` confirmation. Repository is rechecked
  before hidden Team and payload reads. No remote API, GitHub object, lifecycle,
  native helper/compiler, local lock or automatic execution is reached.
- One enum-only matrix independently reports Team format, CMS structural stage,
  certificate DER, BasicConstraints and envelope size. Size uses the existing
  pre-dispatch envelope check with a fixed valid Team placeholder, so malformed
  Team does not hide size status. This is not trust, Team matching or upload readiness.
- Both same-handle reads must finish before any matrix claim. Upstream metadata,
  cancellation or read failure leaves all checks `NOT_CHECKED`; invalid certificate
  DER leaves its downstream BasicConstraints `NOT_CHECKED`.
- Existing CMS preflight predicates, ordering, limits and exception args remain
  unchanged. A fixed `diagnostic_stage` attribute identifies size/dependency/decode/
  container/schema/algorithm/attributes/certificates/canonical failure. Unexpected
  exceptions use a fixed unknown stage. All old callers retain old classifications.
- Outputs contain no private contents, OIDs, names, serials, hashes or observed
  parser counts; existing hidden-input length-only feedback is retained. All real
  profile/signature/trust/signing/upload/release flags remain false, including PASS.

## Evidence / limits

- Before implementation, two targeted regression tests failed as expected because
  diagnostic mode and safe stage attribute did not exist. Both pass after the change.
- `py -3.10 -m unittest tools.tests.test_ios_profile_intake
  tools.tests.test_ios_profile_cms_verification -q`: 29 run, 28 PASS, 1 native macOS
  skip. Includes existing malformed corpus acceptance/rejection, unchanged exception
  args, stage categories, independent results, cancellation/read-failure NOT_CHECKED,
  exclusive CLI routing, and no external/native/file-output paths.
- Scoped escalation used only for the existing disposable fictional Windows ACL/lock
  fixture in this combined suite. No real file access or live GitHub request.
- Owned four Python files repository_quality format/check and git diff --check PASS.
- No real input diagnosis was performed. This change does not identify why Owner's
  private input was rejected. Reviewed merge/full CI plus a fresh exact Owner local
  diagnostic gate are required; prior upload approval is not reused.
- External mutations: none. No dependency/native/runner/workflow changes, real assets,
  private output files, API calls, signing/upload, commits or pushes.
