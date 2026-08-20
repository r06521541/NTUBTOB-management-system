# TASK-129: Mobile staging acceptance harness

- Task type: repository implementation after producer readiness
- Delivery group: `mobile-staging-acceptance-automation`
- Requires independent PR: false
- Status: planned; waits for TASK-124 package 4
- Operator: agent under DEC-098
- Owner gate: LINE login/consent only when a named scenario reports it

## Goal

Compose the accepted TASK-123/127 atomic launcher actions and TASK-124 bounded
evidence producers into explicit, resumable staging scenarios. The harness must
reduce manual coordination without hiding side effects, weakening evidence or
turning an uncertain step into an automatic retry.

## Scope and ownership

One later writer owns `tools/Invoke-MobileStagingAcceptance.ps1`, its direct
tests, the mobile staging runbook and one TASK-129 report. Existing launcher,
Flutter producers, broker, database operator and cloud resources are read-only
dependencies. Producer or policy defects return to their owning task; the
harness does not patch around them.

## Named scenarios

### `basic-authorization`

1. exact accepted-SHA preflight and AVD/status observation;
2. session-preserving build/signer/install/cold only when the accepted artifact
   is missing or provenance differs;
3. if logged out, emit `OWNER_ACTION_REQUIRED/LINE_LOGIN_CONSENT` and checkpoint
   without polling or tapping;
4. after explicit resume, require exactly `basic + report disabled +
   fresh_server`, guarded report entry absent, and a valid cache/session
   aggregate;
5. emit one bounded PASS receipt without navigation or mutation.

### `officer-authorization-roundtrip`

1. require a fresh authoritative Basic baseline and valid aggregate;
2. invoke the accepted broker grant operation when B is provisioned; otherwise
   emit `OWNER_ACTION_REQUIRED/BROKER_PROVISIONING` before credential access;
3. one portal cold and require `officer + report enabled + fresh_server`;
4. perform one read-only Officer report observation, then one offline cached
   report observation with network restoration in `finally`;
5. invoke broker restore, cold once, require fresh Basic/report-disabled and
   physical Officer-cache absence;
6. logout strictly last, cold once, require logged-out plus session/basic/
   officer/pending aggregate all absent.

## Invariants

- There is no default multi-step scenario. Every scenario name and mode is
  explicit; atomic launcher actions remain independently callable.
- Durable non-secret checkpoint state binds scenario, step, accepted full SHA,
  artifact SHA, public signer fingerprint, package/version, AVD/serial,
  producer vocabulary version and prior bounded result. It contains no endpoint,
  account, subject, person/session ID, token, body, Secret reference or raw UI.
- Resume verifies every binding and the live precondition before advancing.
  Completed mutating steps are reconciled read-only; they are never replayed
  from the checkpoint alone.
- Each step has exact pre-state, one bounded action, exact post-state,
  stop/reconcile rules and operator metadata. Unknown, timeout, drift or missing
  evidence stops with one governed result.
- UI evidence comes only from foreground-gated accessibility allowlists and
  hard debug projections. No coordinates, OCR, screenshot inference, raw XML or
  logcat.
- Offline/network changes are restored in `finally`; package/session/data,
  LINE, other apps and global caches are never cleared as cleanup.
- Owner interaction is limited to LINE login/consent and later B provisioning.
  The harness exits before those gates and never captures or waits on private UI.
- Report and mutation scenarios cannot start until all required TASK-124
  producers and the matching TASK-127 consumer vocabulary are accepted.

## Acceptance

1. Mocked state-machine tests cover fresh run, resume, stale/mismatched
   checkpoint, already-completed step, timeout, crash, unknown result and
   read-only reconciliation without duplicate action.
2. Basic scenario proves exact Owner gate/resume and authoritative projection;
   non-authoritative offline/unknown projection returns `EVIDENCE_GAP`.
3. Officer roundtrip proves ordered grant/read/offline/restore/purge/logout and
   `finally` restoration; injected failure at every step stops at the correct
   checkpoint and never skips mandatory restore.
4. Concurrency/stale lock, multiple serials, artifact/signer drift and malformed
   producer output fail before scenario mutation.
5. Output is exactly one de-identified JSON envelope per invocation and retained
   evidence follows TASK-123 retention boundaries.
6. Repository review/CI precede one separately authorized controlled dogfood.

## Verification budget

- Writer: one full mocked harness matrix plus parser/diff/format.
- Flutter reviewer: targeted scenario-to-producer vocabulary and runtime stop
  boundary only.
- Main Work: targeted state transition, resume/idempotency and finally review.
- Hosted CI: one final deployment-tool gate. Controlled dogfood is one separate
  evidence round after repository acceptance.

## Five-line execution checkpoint

1. Goal: compose atomic actions into explicit resumable Basic and Officer scenarios.
2. Files: one harness, direct tests, runbook and report.
3. Invariants: no hidden default, exact checkpoint binding, no blind replay, finally restore.
4. Tests: mocked interruption/resume matrix and exact producer vocabulary.
5. Blocker: implementation waits for TASK-124 package 4; Officer mutation additionally waits for provisioned TASK-128 broker.
