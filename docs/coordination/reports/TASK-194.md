# TASK-194 writer report

Writer `/root/csr_writer`, claim `task-194-writer-20260911` lease1.
Branch `codex/task-194-cms-compatibility`;
base/HEAD `c2e14164ace77a5691bbe17e8980b4bc97a26cbf`. Dirty handoff; no commit/push.

## Implemented policy

Shared CMS preflight implements TASK193's finite SHA256/384/512 digest and RSA
PKCS1v1.5 policy, cross-field digest/signature consistency, absent/NULL receiver
parameters, and recomputed eContent messageDigest. Signed attributes remain unique,
single-valued, with required contentType/messageDigest and only the three approved
optional typed attributes; total 2..5. SMIMECapabilities allows at most32 metadata
entries, not negotiation or actual weak crypto. AlgorithmProtection requires a
signature, no MAC, exact outer digest/signature OIDs, and same-OID-only NULL/absent
comparison. No input or signed-byte rewrite occurs.

Five new fixed predicates bring the shared schema to30. Existing intake output
schema validation derives keys from the shared constant and remains strict; no
intake production source change was necessary. Tests show content-digest failures
stop before API dispatch and before runner/native invocation. Parser success still
does not establish signature, trust or authority. Native trust/root, dependencies,
workflow, file/tree/cert/resource limits and all existing custody gates are unchanged.

## Fictional signatures and native gate

The no-argument existing rehearsal reuses one fictional key/chain and one fictional
native compilation for408 vectors:384 outer combinations and24 independently varied
AlgorithmProtection parameter combinations. Local tests verify every RSA signature
using cryptography, exact unchanged payload/CMS bytes,384 distinct DER encodings,
384 distinct decoded outer/attribute combinations, and24 decoded protection variants.

Outer matrix order: SHA256/384/512 × legacy rsaEncryption/digest-specific RSA OID ×
eight absent/NULL triples (digest-set, signer-digest, signature) × eight optional
subsets (signingTime, capabilities, protection), with absent/false preceding NULL/true.
Fixed failure aliases `compatibility_000`..`compatibility_383` identify that order;
`compatibility_384`..`compatibility_407` identify digest/encoding × four protected
digest/signature parameter pairs, with outer parameters and optional attrs present.
Only these predefined aliases are emitted, never CMS bytes or raw exceptions.

Actual macOS rehearsal is extended to verify all408 and preserve existing root,
purpose, expiry, invalid-signature and test-build separation negatives. Added signed
capability/protection tampering requires native signature rejection. Content tamper
now correctly fails preflight instead of being deferred to native.
**Windows cannot provide the required macOS native compatibility evidence.** Main's
independent review and hosted native/full gate remain required; a native format
incompatibility must stop, not trigger a trust/policy workaround.

## Validation

- Tests-first: new compatibility-fixture test failed before implementation; content
  tamper test also proved the old parser accepted an input now explicitly rejected.
- `py -3.10 -m unittest tools.tests.test_ios_profile_cms_verification
  tools.tests.test_ios_profile_intake tools.tests.test_ios_profile_verification_runner
  -q`: final50 run,48 PASS,2 macOS skips. Scoped escalation used only for the existing
  disposable fictional Windows ACL fixture; sandbox initially rejected that fixture.
- Negative coverage includes SHA1/MD5/SHA224/unknown actual digest, non-allowlisted
  signatures, cross-field mismatch, digest length/value, OID-family mismatch,
  protection MAC/missing signature/parameters/duplicate/multiple values, capabilities
  32/33 boundary/multiple values/deep parameters, existing malformed DER/resources,
  metadata tamper, fixed output/sentinels, and no native/network/private output.
- One-time exact-base expected-delta comparison loaded only public historical source
  into memory via `git show`:32 unchanged valid,376 newly accepted (352 outer plus24
  protection),2 newly rejected content/digest-value inputs,25 unchanged malformed
  rejections. Successful unchanged parsed return data and unchanged rejection args
  match. Persistent tests do not depend on Git history in shallow CI.
- Owned five Python files: repository quality format/check PASS; `git diff --check`
  PASS. One test-only deeply nested object construction was stopped for excessive
  construction time and replaced by a linear bounded encoded fixture; no production
  limit was changed and final suite completed in approximately10 seconds.

## Handoff / limits

Changed writer files: CMS verifier/rehearsal, CMS/intake/runner test modules, this
report. The owned intake source was intentionally unchanged; Main coordination and
runbook dirty files were preserved. No true assets/private key files, third diagnostic,
Git/API/cloud mutation, production native verification, signing/upload or dependency
change occurred. Tests use in-memory fictional keys; temporary files/ACLs are only
the existing fictional/public-code fixtures. No external service mutation occurred.

Owner's actual profile may remain unsupported. This software preparation does not
authorize real input or infer its algorithms/OIDs; any later real verification needs
the separate reviewed exact-SHA Owner gate. Writer becomes read-only after handoff.
