# TASK-189 writer report

- Writer `/root/csr_writer`, claim `task-189-writer-20260910`, lease 1.
- Branch `codex/task-189-cms-verification`; unchanged full HEAD
  `b25a1c2834dd6418a1acd3bf4f868f4e154dc9fd`. No writer commit/push.
- Owned dirty paths: `tools/ios_profile_cms_verification.py`,
  `tools/native/ios_profile_cms_verify.swift`, `tools/ios_profile_cms_rehearsal.py`,
  `tools/tests/test_ios_profile_cms_verification.py`, and this report.
  Main's dependency/workflow/CI/task/HANDOFF/state/runbook changes are separate.

## Delivered boundary

- Public pure-input API `verify_profile_cms(data, *, expected_bundle, expected_team,
  expected_certificate_der, now)` has no file/CLI/private input or trust override.
  The result contains fixed categories and booleans only, never profile/certificate data.
- Pinned `asn1crypto==1.5.1` and `cryptography==50.0.0`: CMS <=1 MiB, embedded content
  <=256 KiB, certificate <=64 KiB, ASN.1 depth <=32, nodes <=4096 and collections <=128.
  Library schema traversal materializes all allowed fields and rejects extra Sequence
  children before full `.native` and `dump(force=True)` exact canonical DER comparison.
  This is structural parsing, not hand-written ASN.1 signature verification.
- Restrictive subset: SignedData v1, one issuer/serial signer, SHA256 with RSA PKCS1v1.5,
  embedded id-data, unique required contentType/messageDigest and optional signingTime.
  Reject encrypted/nested/detached/unsigned/multisigner/trailing/noncanonical CMS, CRLs,
  alternative certificate choices, duplicate certificates and unsigned/unsupported attributes.
  Sole native verification site repeats structural preflight, so a fabricated parsed
  dictionary cannot bypass the no-decryption boundary.
- macOS15+ native public CMSDecoder API: deferred trust, OSStatus success **and** signer
  `.valid`; undefined deferred certVerifyResultCode ignored. Checked basic-X509 policies,
  fixed compiled root, anchor-only, network-off and injected aware UTC date setters all
  precede SecTrust evaluation. No exceptions, private policy SPI, system-anchor fallback,
  keychain writes or implicit permission to use actual assets.
- Evaluated chain exactly three, leaf equals CMS signer, root equals fixed repository pin.
  Per accepted clarification, embedded certificates must equal exactly leaf+intermediate,
  optionally plus pinned root; no unrelated/duplicate certificates or missing intermediate.
  Exact single CNs are checked from parsed certificate names, not display summaries.
- Native content must exactly equal structural content before TASK187 content validation.
  Success is `CMS_PROFILE_VERIFIED_RESTRICTED`, **not** Apple's private-policy parity.
  Revocation/private-key possession/P12 import/signing/upload/release remain false.
- Production builds compile only the repository public root after DER SHA256 pin check.
  A structurally separate fictional build marker cannot produce production results.
  Only code/public anchor files occupy an automatically cleaned build directory; CMS,
  profiles and private fixture keys remain in memory/bounded pipes. Output <=700000 bytes,
  native timeout 30s, compile timeout 60s; no raw errors/payload logs or artifacts.

## Evidence / remaining limits

- `py -3.10 -m unittest tools.tests.test_ios_profile_cms_verification -v`: 11 run,
  10 PASS, 1 explicit macOS native skip on Windows. Focused tests cover full structural
  negatives/no-native-call, canonical BER rejection, schema extra/depth/count rejection,
  payload/chain/build-marker bindings, fixed results, no-I/O fictional generation,
  bounded pipe/crash/timeout and separate public-anchor compilation artifacts.
- Owned `repository_quality format` / `check`, `git diff --check`: PASS.
- During test construction, recursively constructing an ASN.1 Any fixture was slow;
  that single run was interrupted. Replaced only the test fixture construction with
  bounded fictional encoded nesting; guards unchanged and subsequent suite passed.
- No local macOS SDK: Swift compile and native signature/trust are **not locally proven**.
  Mandatory hosted `python -m tools.ios_profile_cms_rehearsal` must verify included/omitted
  root positives, tampered signature/content, wrong purpose/root, expiry, missing
  intermediate, fictional-build rejection as production and production rejection of
  fictional trust. Negative cases demand narrow fixed categories, not crashes/timeouts.
  Missing intermediate may fail native trust or final membership if cached by trustd;
  both are explicit rejection, never success. Safe case stages identify failures.
- API scope does not establish real Owner asset custody, private policy equivalence,
  revocation, real signing readiness or live profile acceptance. No real files were read.
  Future live intake remains a separate reviewed Owner gate.
- External mutations: none; no real Apple assets, private files, keychains, cloud/store,
  signing/upload, commits or pushes. Disposable public-code test directories were cleaned.

References: [Apple CMSDecoder.h](https://raw.githubusercontent.com/apple-oss-distributions/Security/main/CMS/CMSDecoder.h)
and [Apple SecPolicy.c](https://raw.githubusercontent.com/apple-oss-distributions/Security/main/OSX/sec/Security/SecPolicy.c).
