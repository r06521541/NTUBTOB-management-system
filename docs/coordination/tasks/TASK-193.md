# TASK-193: bounded CMS compatibility design

Type planning; delivery_group cms-compatibility; no standalone status/design PR.
Branch codex/task-193-cms-compatibility-design.
Base/HEAD c2e14164ace77a5691bbe17e8980b4bc97a26cbf.
Owner approved DESIGN ONLY on 2026-09-11. Main /root, main-work,
task-193-main-20260911 lease1. TASK192 writer/reviewer claims completed.
Preserve carried TASK192/HANDOFF records. No implementation/private input/diagnostic
rerun/Secret/native execution/upload/signing authorized in this planning task.

## Evidence and proposal

Owner's consumed TASK192 run proves five policy mismatches, not exact algorithms,
extra attribute identities, authenticity or damaged download. Never label it SHA1
without evidence. Generic CMS standards do not specify Apple's profile issuance
format or guarantee this proposal will accept that profile.

Proposed first implementation scope, pending Owner approval after design review:

| Boundary | Proposed policy |
| --- | --- |
| Content digests | SHA256/SHA384/SHA512 only, lengths32/48/64; SHA224 deliberately excluded for scope, not claimed insecure |
| Consistency | Single SignedData digest equals SignerInfo digest; recompute eContent digest and compare signed messageDigest before native verification; length alone never proves integrity |
| RSA signature | Retain RSA PKCS1v1.5; rsaEncryption plus selected digest, or matching sha256/384/512WithRSA identifier; reject mismatch, PSS/ECDSA/unknown in this scope |
| Parameters | Accept absent or NULL for SHA2 digests and SHA2-with-RSA identifiers per RFC5754 sections2/3.2; generation conventions are not receiver rejection rules. Maintain existing rsaEncryption absent/NULL compatibility with explicit fixtures; never accept arbitrary parameters |
| Signed attrs | Unique contentType and messageDigest required; optional signingTime, SMIMECapabilities, CMSAlgorithmProtection only; 2..5 attributes, each single value |
| SMIMECapabilities | RFC8551 typed sequence, max32 entries, each bounded by existing tree/byte limits; data-only signed metadata, not algorithm negotiation, trust, encryption or capability execution; OIDs inside do not expand actual crypto policy |
| AlgorithmProtection | RFC6211 one value, digest/signature OIDs exactly match their outer identifiers; normalize permitted NULL/absent only for the same OID, not across equivalent crypto families (rsaEncryption is not sha256WithRSA); signature present, MAC absent; mismatch rejects |
| Unknown attrs | Reject, no wildcard pass-through; no unsigned attrs/CRLs/encrypted/detached/multiple signers |
| Authenticity | Native CMS signature verification AND pinned Apple anchor/chain/purpose, payload byte binding and Team/App/certificate/profile checks remain mandatory |

Keep canonical DER, input/tree/depth/node/certificate/resource limits, same-handle
custody, hidden confirmation, one-shot/TTL/no-disclosure and output flags. SMIME
capability metadata is a proposed typed exception to the old three-attribute list,
not a statement Apple uses it or a claim its contained algorithms are safe to use.
No MD5/SHA1 allowance, native-default crypto fallback, arbitrary trust root or network
trust fetch. Offline trust still cannot prove revocation; preserve that limitation.
Do not alter profile content requirements or application's login/provider behavior.
Normalization is comparison-only: never rewrite signed bytes or the native input.
Retain existing RSA signature-size bound; native verifies signature against signer
key, and byte length alone is not a complete key-strength policy. Capability metadata
must not trigger nested CMS decoding, OID lookup, negotiation or execution; Any
parameters remain subject to full canonical tree/depth/node/byte bounds.

This changes accepted inputs: old diagnostic parity is NOT the correct acceptance
criterion for new supported vectors. Require an explicit expected-delta corpus;
everything outside approved deltas stays rejected. MacOS native support remains
unverified until fictional actual-signature tests pass; do not claim support from
parser tests or use the real Owner profile to discover policy by trial and error.

## Required implementation evidence (not executed in design)

- Genuine fictional signed CMS for each supported digest/signature encoding and
  optional attribute combination; native success plus constrained fictional trust.
- Wrong digest length/value, cross-field mismatch, tampered content/signed attrs,
  invalid signature, wrong root/purpose/expiry, duplicate/missing/unknown attrs,
  malformed parameters, AlgorithmProtection mismatch/MAC, oversize capability sets,
  existing malformed DER and resource corpus; all reject at intended boundary.
- Capabilities may describe a non-supported algorithm without authorizing its use;
  actual use still rejects. No network/file output/private access in unit tests.
- Shared preflight at intake/runner/native-call boundary, focused suites, independent
  security review, one relevant hosted/native gate and exact commit before merge.
- Only then propose one separately authorized real verification run with exact
  target/retention/cancellation/cleanup. No new diagnostic run implicit in design.

## Decision and risk

Recommend bounded standards-based compatibility over removing preflight restrictions.
Risks: larger parser surface, metadata ambiguity, OS behavior differences; mitigated
by finite typed allowlists, limits, negative tests and native cryptographic evidence.
Residual: real profile may still be outside this set. Then stop unsupported; no
automatic weak-algorithm exception, new diagnostic or speculative asset regeneration.
Owner next decides whether to implement this exact policy; current strict code stays.

## Primary sources (checked 2026-09-11)

- RFC5652 sections5.3/5.6/11.2: https://www.rfc-editor.org/rfc/rfc5652.html
- RFC5754 sections2/3.2 (SHA2/RSA encoding): https://www.rfc-editor.org/rfc/rfc5754.html
- RFC6211 section2 (algorithm protection): https://www.rfc-editor.org/rfc/rfc6211.html
- RFC8551 section2.5.2 (S/MIME metadata, not Apple issuance contract): https://www.rfc-editor.org/rfc/rfc8551.html

## Independent design review assignment

task=TASK-193; branch/base/head as above; actor_id=/root/task181_review;
role=advisor; claim_id=task-193-security-20260911; lease_version=1;
owned_paths=none; write=read-only; report_to=/root;
scope=source-backed proposed policy/security/design completeness;
stop_conditions=unjustified weak policy/private access/scope expansion.
Mandatory COLLABORATION2 packet: immediate ACK, heartbeat10-15m, blocker immediately,
proactive verdict/findings/evidence/limits/external mutations. No code/private/native
execution, edits or Git mutation. Main concurrently checks source/plan integration.

Design lease1 ACCEPT after NULL/absent receiver and same-OID normalization clarifications.
No implementation release: next actor Owner decides this exact bounded policy.
Main recorded review separately; source unchanged, no tests/CI warranted for design.
Expected delta includes newly supported formats AND newly rejected inconsistent/tampered
inputs formerly deferred to native; do not claim all old parser successes stay accepted.

Owner approved this implementation scope on 2026-09-11. TASK194 now carries software
delivery; private input, real verification/signing/upload remain unapproved here.
