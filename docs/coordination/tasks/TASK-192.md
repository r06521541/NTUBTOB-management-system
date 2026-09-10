# TASK-192: one bounded CMS predicate diagnostic refinement

Type delivery; delivery_group task-192-cms-predicate-diagnostics; L3.
Branch codex/task-192-cms-predicate-diagnostics.
Base/HEAD 2a5cd24889b0505a78c95defa7e3729068992611.
Main /root, main-work, task-192-main-20260910 lease1; TASK191 claims completed.
Carry forward Main's four uncommitted TASK191 gate records without discarding them.

## Owner exception / checkpoint

Owner explicitly approved the bounded exception proposed in TASK191 on 2026-09-10.
This supersedes COLLABORATION5's layer-split cap only for ONE comprehensive local
diagnostic refinement and, after reviewed exact-SHA confirmation, ONE Owner run.
If insufficient, stop inconclusive; no third diagnostic iteration or automatic retry.
No algorithm/parser/trust rule relaxation or real upload/signing is approved.

Goal: locate all independently diagnosable failing CMS predicates in one local run.
Core: existing CMS/intake modules, their existing tests, and bounded documentation.
Invariant: preserve production acceptance/rejection, exception args, native/trust,
limits and private custody; no diagnostic network/native/lock/output-file actions.
Tests: fictional per-predicate failures, combined failures, malformed corpus parity,
prerequisite NOT_CHECKED, fixed enum output, no values or raw exceptions, no side effects.
Owner gate: software preparation only now; new reviewed exact-SHA hidden confirmation
is required before true local input. No agent reads of private assets in development.

## Scope

TASK191 Owner result: Team format, DER, BasicConstraints and envelope size PASS;
CMS_ALGORITHM_REJECTED. This does not establish Team match, signature or trust.
The local diagnostic path has no network calls: slow network cannot cause that
predicate result during this run. Download integrity is not inferred either way.

Produce a fixed per-predicate PASS/REJECTED/NOT_CHECKED matrix for the algorithm
stage and downstream structural checks that can safely run after bounded parsing.
Cover digest set/cardinality/algorithm, signer version/identifier/unsigned attrs,
signature algorithm/size/parameters, signed attributes, certificates/signer binding
and canonical DER; avoid stopping at the first unsupported algorithm and masking
other diagnosable constraints. Malformed prerequisites must prevent unsafe descent.
Reuse the same policy predicates, not a second permissive validation path; preserve
existing preflight public contract and acceptance, including no diagnostic granting
trust or permission. Architecture review should select minimal maintainable sharing.
No raw algorithm names/OIDs, counts/lengths/hashes, identifiers, contents, exception
strings or private paths. Fixed matrix keys describe rules, not observed values.
All existing trust/signature/profile/sign/upload/release flags stay false.
Existing --diagnose-input is sole intake entry; default/execute behavior unchanged.
No dependency/workflow/native/root-anchor/provider/cloud changes.

Main owns task/HANDOFF/PROJECT_STATE/runbook and final review integration, including
the four carried TASK191 records. Writer owned paths only:
- tools/ios_profile_cms_verification.py
- tools/ios_profile_intake.py
- tools/tests/test_ios_profile_cms_verification.py
- tools/tests/test_ios_profile_intake.py
- docs/coordination/reports/TASK-192.md

## Architecture assignment

task=TASK-192; branch/base/head as above; actor_id=/root/task181_review;
role=advisor; claim_id=task-192-security-20260910; lease_version=1;
scope=bounded architecture and invariant review; owned_paths=none; write=read-only;
report_to=/root; stop_conditions=weakened validation/private disclosure/scope expansion.
Mandatory COLLABORATION2 packet applies: immediate received/executing, heartbeat
10-15 minutes, blocker immediately, proactive completion with findings/tests/limits
and external mutations. No real inputs, API calls, edits or Git mutations.
No writer released until architecture reviewed. Final review and one full hosted
gate required before merge under standing Git authority; no status-only PR.

Architecture lease1 ACCEPT. Shared private bool/fixed-rule helpers serve BOTH
production fail-fast (same order/contract) and comprehensive diagnostic collection.
After bounded common parsing, dependency-specific NOT_CHECKED must not mask unrelated
checks. Unsupported SID blocks only binding, bad digest cardinality only its element
checks; diagnostics never return a trusted/usable parsed object. No duplicate parser,
input patch-and-retry, policy override or observed-value output. Differential tests
against the frozen base must prove acceptance/args/success data parity for fictional
valid/malformed corpus; each rule, combined failures and missing prerequisites covered.

Writer assignment: actor_id=/root/csr_writer; role=codex-writer;
claim_id=task-192-writer-20260910; lease_version=1; branch/base/head as above;
write=allowed only the five listed owned paths; report_to=/root;
scope=reviewed comprehensive diagnostic; stop_conditions=boundary weakening,
private exposure, scope expansion or inability to preserve production parity.
Mandatory COLLABORATION2 packet applies. Self-review/test and proactive completion,
then read-only; no commit/push/API/real assets. Main owns all integration documents.

Writer lease1 completed, now read-only: 35 focused tests (34 PASS/1 macOS skip),
52-case frozen-base acceptance/args/stage/success-data differential parity; owned
quality and diff checks PASS. Final reviewer /root/task181_review, role advisor,
claim task-192-security-20260910 lease2, write read-only, owned_paths none,
report_to /root. Review complete dirty delivery against exact base, including Main
carried records/runbook. Same mandatory packet, immediate ACK/proactive verdict;
no private assets/API/Git mutation. Stop on weakened boundary or incomplete semantics.

Final lease2 ACCEPT. Main expanded CMS/intake/runner/workflow: 59 run, 57 PASS/2
platform skips; owned quality/diff PASS. Reviewer independently confirmed 30-case
base parity (writer52 separately). Main may commit/push/one PR under standing Git
authority; full hosted/native gate must pass before merge. No true diagnostic yet.
