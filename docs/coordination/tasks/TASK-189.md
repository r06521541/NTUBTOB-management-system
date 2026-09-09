# TASK-189: CMS signature and profile trust verification

- Type: delivery; delivery_group: task-189-cms-verification; risk L3.
- Branch: `codex/task-189-cms-verification`.
- Base/head: `b25a1c2834dd6418a1acd3bf4f868f4e154dc9fd`; TASK188 merged PR243,
  full CI34385755425 PASS including actual macOS memory-only import. Prior claims complete.
- Main `/root`, role main-work, claim task-189-main-20260910 lease 1, owns task,
  HANDOFF, state, integration documentation/workflow after architecture acceptance.
- Advisor `/root/task181_review`, role advisor, claim task-189-security-20260910
  lease 1; read-only, owned_paths none, report_to `/root`.
- Mandatory ACK/heartbeat/proactive completion: COLLABORATION section 2.

## Architecture checkpoint

Goal: authenticated CMS content and constrained Apple profile signer verification, not decoding alone.
Core: public macOS CMSDecoder/SecTrust APIs, pinned repository Apple anchor, existing content validator.
Invariants: no private SPI or undocumented policy OID, no default system trust/network/keychain writes.
Tests: fictional signed/tampered/unsigned/detached/multiple signer CMS, wrong anchor/purpose and bound content.
Blockers: unprovable public API semantics, unsafe trust separation/custody or unsupported signer chain.

Review proposed design before implementation: CMSDecoderCopySignerStatus with trust
evaluation deferred verifies signature, then explicitly constrained SecTrust evaluation
(only pinned root, network disabled) and exact signer-purpose checks. Generic X509 alone
is insufficient. Apple source's iPhone provisioning signer policy is a distinct chain,
not the WWDR Distribution identity policy. Do not invoke its private SPI/OID indirectly.
Determine whether public APIs plus explicit reviewed chain/purpose checks suffice.
No hand-rolled CMS/ASN.1 cryptography, no caller trust boolean or production anchor injection.
Fictional fixture trust must be structurally separate from real verification configuration.

No real downloaded CMS/P12/API keys/passwords/Owner files, persistent keychains, Secrets,
signing/upload/Apple operations. No new live intake wrapper until verification design and
its no-disclosure interface are accepted. Existing tools may be reused only within their
documented bounds. Main researches official API semantics while advisor checks architecture.
One sole writer after scope acceptance; independent final review, local focused tests and
one evidence-bearing PR/hosted macOS gate before merge. Do not fragment into a decoder-only
delivery that claims trusted profile readiness. Explicitly document remaining live gates.

## Architecture correction

Advisor lease1 REQUEST_CHANGES: CMSDecoder can decrypt during finalize, so post-decode
encrypted-content rejection is insufficient. Lease1 complete. Main proposes pinned
`asn1crypto==1.5.1` only in isolated certificate-tool requirements for structural preflight:
bounded strict DER ContentInfo, exactly SignedData with embedded id-data, exactly one
signer, no encrypted/nested/detached/trailing/ambiguous objects. No native call before
this boundary passes; parser never grants signature/trust. Native receives the same bytes.
Use canonical strict parsing/re-encoding and explicit field constraints, not custom ASN.1.

Advisor task-189-security-20260910 lease2 reviews this corrected architecture, read-only,
owned_paths none, report_to `/root`. Require evaluated chain exactly three, signer DER
equal evaluated leaf, pinned root DER, embedded chain membership, exact single CNs via
cryptography (never summaries), and current aware time. All SecTrust setters checked before
evaluation; disable network, anchor-only, no exceptions/private SPI. Scope is a restrictive
subset rather than equivalence with Apple's private policy; revocation stays unverified.
Production root must be compiled from fixed repository pin, not runtime input; fictional
trust has separate test-only build target. Test production rejection of fictional root.
Only authenticated content reaches TASK187 validator; external results are fixed categories.

## Accepted implementation scope

Advisor lease2 ACCEPT: force full ASN.1 field parsing and canonical DER re-encoding,
not lazy/default dump. Reject unsupported certificate choices, CRLs, unsigned attributes,
nested timestamp/countersignatures; signed attributes allowlist with unique required
contentType/messageDigest. Bound all sizes/counts. Production/test trust configuration
and result markers remain distinct; no real-input CLI/path/secret prompts.

- Writer `/root/csr_writer`, role codex-writer, claim task-189-writer-20260910 lease1.
- Owned: `tools/ios_profile_cms_verification.py`, `tools/native/ios_profile_cms_verify.swift`,
  `tools/ios_profile_cms_rehearsal.py`, `tools/tests/test_ios_profile_cms_verification.py`,
  `docs/coordination/reports/TASK-189.md`; write allowed; report_to `/root`.
- Main owns isolated dependency, CI, runbook, task/HANDOFF/state. No other tools changed.
- Public verification core accepts memory bytes/expected identities/aware time only; fixed
  repository anchor, no caller trust flags. Native internal binary has compile-time anchor
  and test marker; test target cannot yield production verification. No raw public CLI output.
- Rehearsal generates fictional CMS/profile/certificate chains in memory; includes matching
  content, tampered signature/content, wrong root/purpose, expired, multisigner, detached,
  encrypted/nested/unsigned/trailing inputs. Production target must reject fictional chain.
- Tests must prove rejected structural inputs never invoke native decoding. Native signature
  and evaluated chain/payload binding are mandatory hosted evidence, not mock assertions.
- No persistent keychain or file assets; code/public anchor compilation only. Bounded child
  pipes and timeouts; no payload logs/cache/artifacts. CMS structure parser adds no trust.
- Claims from advisor lease2 complete. Independent final lease required; one Draft PR may
  obtain missing local macOS evidence before ready/merge. Preserve all live Owner gates.

Lease2 architecture clarification ACCEPT: evaluated leaf/intermediate must be embedded
by exact DER; the evaluated root need not be embedded because authority comes from the
compiled repository pin. Allow exactly leaf+intermediate, optionally pinned root; reject
extra/unrelated/duplicate certs or omitted intermediate. All chain3, anchor-only, signer,
purpose/time/signature checks remain. Test omitted-root/included-root positive and
wrong-root/omitted-intermediate negative cases. This is not final implementation acceptance.

## Independent implementation review

Writer lease1 completed; five owned paths delivered dirty, 10 focused PASS/1 macOS skip,
quality/diff checks PASS. No external mutation. Main integration paths are included.
Advisor `/root/task181_review`, role advisor, claim task-189-security-20260910 lease3,
read-only, owned_paths none, report_to `/root`, reviews complete working-tree delta
against the exact base above. Writer remains read-only. Review all CMS trust/custody,
fixtures and CI boundaries; native runtime evidence remains mandatory after acceptance.

Lease3 source ACCEPT: full 13-path delta reviewed with HEAD/status unchanged; no blocking
findings. Independent 33 tests: 31 PASS, 2 environment SKIP (macOS/Bash). Main combined
42 tests: 39 PASS, 3 environment SKIP; quality 4 Python paths/diff check PASS. Writer and
advisor claims complete. Main resumes integration/one Draft PR and hosted evidence;
ready/merge only after mandatory native rehearsal and full CI success. No live operation.
