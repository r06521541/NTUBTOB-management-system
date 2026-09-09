# TASK-187 implementation evidence

- Writer `/root/csr_writer`, claim `task-187-writer-20260910`, lease 1; report_to `/root`.
- Branch `codex/task-187-ios-profile-signing-preparation`; current HEAD/base
  `c458d29326072444987fff70b43aa3ec46a5bfa1`. Writer made no commit/push.
- Owned dirty/new files: `tools/ios_profile_validation.py`,
  `tools/tests/test_ios_profile_validation.py`, this report. Main's existing
  coordination, CI and runbook changes were preserved.

## Behavior

`validate_profile(decoded_plist, *, expected_bundle, expected_team,
expected_certificate_der, now)` accepts only in-memory bytes and explicit
expectations. No CLI, path reader, subprocess, network, CMS decoder, keychain or
native import is implemented. Success is `PROFILE_CONTENT_MATCH_ONLY`; every
CMS/certificate/Apple trust, revocation, private-key, import and authority flag
remains false. Fixed STOP reasons never include identity, input or exception data.

XML input is limited to 256 KiB, 32 nested elements and 8192 total elements;
expected certificate DER is limited to 64 KiB. Expat rejects unsafe DTD/entity
declarations and processing instructions; the fixed Apple external DTD declaration
is recognized without resolving it. A strict tree-shape pass rejects duplicate
keys, multiple roots/values, unknown tags/attributes and invalid scalar forms
before standard-library plist decoding. Binary plist is unsupported.

The narrow contract requires one exact DER certificate, explicit BasicConstraints
CA=false, certificate validity, aware verification time, profile creation <= now
and expiration > now. Missing BasicConstraints is unsupported, not inferred safe.
It requires exact single TeamIdentifier and team-equal ApplicationIdentifierPrefix,
exact application identifier, matching team entitlement, Sign in with Apple
`[Default]`, Platform `[iOS]`, `get-task-allow=false`, `beta-reports-active=true`,
and no ProvisionedDevices or all-device authorization. Legacy differing prefixes
or multi-certificate profiles are outside this contract; this is not a claim that
Apple universally prohibits them. Certificate signatures are not verified.

## Verification

Writer ran with Python 3.10:

- `py -3.10 -m unittest tools.tests.test_ios_profile_validation -v`: 8 tests PASS,
  including parameterized XML attacks, duplicate keys, bounds, type confusion,
  exact correspondence, CA/missing constraints, timezone/date boundaries,
  development/device rejection, no-I/O and no-disclosure assertions.
- `py -3.10 -m tools.repository_quality format --paths tools/ios_profile_validation.py tools/tests/test_ios_profile_validation.py`:
  applied only owned-file formatting.
- `py -3.10 -m tools.repository_quality check --paths tools/ios_profile_validation.py tools/tests/test_ios_profile_validation.py`:
  PASS for both owned Python files.
- `git diff --check`: PASS; `git status --short` and full HEAD reviewed.

Main separately reported CI workflow contract: 14 run, PASS with one designed
skip; existing six-suite regression: 92 run, PASS with one skip outside the
sandbox. Its initial sandbox fixture ACL errors were environment failures, not
fixed by this change. These are Main-supplied evidence, not additional writer runs.

## Limits and handoff

Independent final review and hosted Windows/Linux required CI remain pending at
writer handoff. No downloaded Owner profile, P12, API key, password or real
certificate was read. All new crypto/plist fixtures were fictional and in memory.
External mutations: none. Existing CMS decoding, signature/trust, native PKCS12
import, actual signing and cloud delivery gates remain unimplemented/unverified.
Do not use content match as permission or proof for any of those operations.

## Main acceptance

Independent advisor `/root/task181_review`, security lease 2: ACCEPT, no blocking
findings; independently ran new pure suite (8 PASS) and diff check. Main received
completion before integration. Main reran new core plus workflow contract (22 run,
one environment skip), and working-tree quality passed for all three Python files.
Final hosted evidence will be attached to the same PR at the immutable final SHA;
this pre-CI checkpoint does not claim hosted success or real profile readiness.
