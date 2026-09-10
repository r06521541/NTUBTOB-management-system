# TASK-191: bounded local profile input diagnostics

Type delivery; delivery_group task-191-profile-diagnostics; L3.
Branch codex/task-191-profile-diagnostics.
Base/HEAD 76ec2d0d35ee90d3b8033b34f294b2c3de21864c (TASK190 PR245 merged).
Main /root, main-work, task-191-main-20260910 lease1; prior TASK190 claims complete.

## Checkpoint

Goal: explain local INPUT_REJECTED without exposing private content or retrying upload.
Core: existing intake/CMS parser and their existing tests; no new dependency/workflow.
Invariant: preserve every parser/trust/custody predicate; diagnostic never calls GitHub,
native compiler, dispatch, Secret API, signing or keychain; no private files/log artifacts.
Tests: fixed classifications, malformed/valid fictional data, unchanged validation,
hidden confirmation before reads, zero network/mutations and no private-value output.
Owner gate: new reviewed exact SHA local diagnostic reads need Owner confirmation;
old upload approval is not reused for new artifact. No live private input in this task.

## Current bounded evidence

TASK190 full CI34396447873 and independent review PASS; merge PR245. Owner configured
the Environment. Exact GET-only checks confirmed Owner/repository/protection/main-only
policy and absent target Secret; the undocumented bypass field was present and false.
Owner copied profile and metadata preflight passed. Their execution returned STOP,
stage input, INPUT_REJECTED, run_id null; confirmation length55 was already accepted,
Team length10 does not establish allowed characters. No dispatch/PUT reached according
to that result and code path. Current dependencies and fictional CMS parse pass.
Do not infer the true private-input failure or re-read files through ad-hoc scripts.

## Proposed scope

- Add mutually exclusive --diagnose-input to the existing repository-owned intake CLI.
  Verify exact clean local SHA/dependencies and same-handle fixed two-file metadata,
  print fixed action, then require hidden DIAGNOSE PROFILE <SHA> and hidden Team input.
  No GitHub object, remote_preflight, lifecycle, lock-file write or automatic execute.
- Run independent in-memory Team-format, CMS structural, certificate DER/BasicConstraints
  and envelope-size checks and return one fixed enum-only matrix. No Team match/trust
  success is inferred. All signing/upload/release/real-profile verification flags false.
- CMS structural diagnostics use the SAME preflight predicates, no alternate permissive
  parser. Preserve existing preflight exception args/classifications for all callers;
  a fixed allowlisted detail identifies first failed stage (size/decode/container,
  collection/schema, algorithm, attributes, certificates/signer binding, canonical DER).
  No observed values/counts/OIDs/subjects/serials/hashes are emitted. Unexpected exception
  becomes a fixed unknown category, never raw error. No added trust override.
- Do not change lifecycle mutation semantics or loosen limits. Known real read/transport
  cannot be repeated until reviewed software and exact Owner gate. One diagnostic result
  should classify independent checks together, avoiding repeated Owner trial-and-error.
- Main owns task/HANDOFF/PROJECT_STATE/runbook/report-review integration. Writer owns only
  tools/ios_profile_intake.py, tools/ios_profile_cms_verification.py,
  tools/tests/test_ios_profile_intake.py, tools/tests/test_ios_profile_cms_verification.py,
  docs/coordination/reports/TASK-191.md. Native source/runner/workflow/dependency untouched.

## Architecture review assignment

Advisor /root/task181_review, role advisor, claim task-191-security-20260910 lease1,
write read-only, owned_paths none, report_to /root. Mandatory COLLABORATION2 packet.
Assess bounded architecture before writer release; stop on policy weakening, private
exposure, scope expansion or inability to diagnose without outputting private content.
No real file/API access, writes, commit/push or external operations. ACK immediately,
proactive completion per packet. Software scope only; final independent review and
one full CI remain required before merge. No writer released yet.

Architecture lease1 ACCEPT complete. Writer /root/csr_writer, role codex-writer,
claim task-191-writer-20260910 lease1, write allowed only the five paths above,
report_to /root. Mandatory COLLABORATION2 packet, no commit/push/live input/API.
Return dirty implementation/self-test report then read-only. Preserve old exception
args and success/failure corpus acceptance. Size check independent of Team format;
upstream custody/read rejection leaves checks NOT_CHECKED rather than fake PASS.
Existing metadata size stop remains enforced before any read. No new paths/native
or runner/workflow changes. Stop on invariant weakening or inability to classify
safely. Main owns docs while sole writer owns implementation.

Writer lease1 completed and read-only: 29 tests, 28 PASS/1 macOS skip;
owned quality/diff checks PASS. Final independent reviewer /root/task181_review,
role advisor, claim task-191-security-20260910 lease2, read-only, owned_paths none,
report_to /root. Review current complete dirty delivery against exact base above;
no real inputs, API calls, edits or external mutations. Return proactive verdict,
tested evidence, findings and limits. Stop on any weakened boundary or scope drift.

Final independent lease2 ACCEPT and Main focused evidence PASS. Main integrates
this single delivery, commit/push/one final PR under existing standing Git authority.
Required full hosted CI must pass before merge. Next gate is Owner release for a
new exact merged SHA local diagnostic only; no true input read or upload retry here.

## Post-merge Owner result and next gate

PR246 merged at 2a5cd24889b0505a78c95defa7e3729068992611; CI34488581114 SUCCESS.
Owner explicitly approved this exact local diagnostic, then supplied the sanitized
DIAGNOSTIC_COMPLETED result recorded in the report. That approval was used for this
run, not a future changed artifact or upload. Main did not read the private files.

Root cause is still inconclusive: CMS_ALGORITHM_REJECTED groups multiple checks.
COLLABORATION5 allows only one read-only layer split for the same runtime blocker;
TASK191 has consumed that split. Another reason-code iteration is NOT authorized
by general continuation/Git approval. Preserve assets unchanged and stop live intake.

Next Owner decision: a one-time exception permitting one comprehensive local-only
predicate diagnostic refinement, with fictional coverage and independent review,
without changing any accepted algorithm/trust/parser rule. Proposed output is only
fixed per-predicate PASS/REJECTED/NOT_CHECKED categories; no observed algorithms,
OIDs, subjects, identifiers, values or private bytes. New exact reviewed SHA and
explicit private-read confirmation would still be required before one Owner run.
If the resulting evidence is insufficient, stop inconclusive; no third diagnostic
iteration or automatic upload. Any compatibility/trust-policy change is a separate
decision requiring primary evidence and targeted security review. This proposal is
approved by Owner on 2026-09-10; implementation and its one-run boundary are now
carried by TASK-192. This does not approve changed validation or upload.

Main records this gate on codex/task-191-diagnostic-gate, base above, lease1;
prior writer/reviewer claims remain completed. Only task/report/state/HANDOFF changed;
no status-only PR. These records are carried into TASK-192's substantive delivery.
