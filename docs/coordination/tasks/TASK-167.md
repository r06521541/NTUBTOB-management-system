# TASK-167 Android 實機 staging 相容性與 APK runtime ABI gate

## Classification

- task_type: delivery
- risk: L2 staging release artifact／physical-device acceptance
- delivery_group: `mobile-physical-acceptance-202608`
- requires_independent_pr: true
- authority_branch: `codex/task-167-android-physical-device-acceptance`
- repository_authority: `0d6efacac2f20fe1ff66f1aa9ae84fd888ab0961`
- production_or_real_data: prohibited

## Execution authority

- role: `main-work`
- claim_id: `main-work-20260825`
- lease_version: 17
- actor_id: `01a03587-d263-7e92-9965-54816f38b8a3`
- scope: Owner-authorized bounded recovery after an accepted staging APK crashed on an arm64 physical device
- owned paths:
  - `tools/Invoke-MobileStaging.ps1`
  - `tools/tests/test_mobile_staging_launcher.py`
  - `docs/coordination/tasks/TASK-167.md`
  - `docs/coordination/reports/TASK-167-CODEX.md`
  - `docs/coordination/PROJECT_STATE.md`
  - `docs/coordination/HANDOFF.yaml`
- acceptance: Main is not the sole formal acceptor; independent Flutter/release-artifact review and hosted CI remain required
- stop_conditions: non-staging target, personal account requirement, unknown device ownership, signing/config drift, Secret/provider/cloud mutation or unrelated dirty overlap

## Observed failure

The previously accepted staging APK installed on one Owner-authorized borrowed Android 15 arm64 device but terminated at launch. A bounded package-only crash diagnostic reported that `libflutter.so` was available only for `x86_64`. Archive inspection confirmed that arm／arm64 directories contained plugin libraries but not the Flutter runtime, so a directory-level ABI check would have been a false positive.

## Required behavior

1. The controlled staging debug build produces Flutter runtimes for `armeabi-v7a`, `arm64-v8a` and `x86_64` from one exact build.
2. Before package, signer, checksum or manifest acceptance, the launcher opens the APK and requires `lib/<abi>/libflutter.so` for every supported ABI. Missing, malformed or unreadable coverage fails closed and removes the candidate artifact.
3. Binary SHA-256 remains raw-byte hashing and must not depend on PowerShell module autoload.
4. Existing staging defines, private-input redaction, detached snapshot, allowlisted debug signer, package identity and evidence retention contracts remain unchanged.
5. Physical-device work is limited to the exact package: no file/account inventory, extra permissions or personal LINE／Google login. The borrowed device must not become a provider-test credential holder.

## Verification budget

- Focused regression for complete versus incomplete runtime ABI coverage, build-time artifact rejection/removal and exact universal target arguments.
- Existing launcher contract suite, with unrelated local PowerShell module-autoload failures reported separately rather than hidden.
- Exact artifact checksum, package, signer and per-ABI `libflutter.so` matrix.
- One physical-device replacement install and cold launch; provider login is not required on a borrowed device.
- Independent Flutter/release-artifact review, one hosted gate, final PR and merge before this repository correction is accepted.

## Current evidence

- Android 15／API 35 arm64 physical device: one authorized device, package-only access, no personal data inspection.
- Corrected staging artifact: package and allowlisted signer exact; checksum matches manifest; all three required runtime libraries present.
- Replacement install passed; process remained alive after five seconds and the bounded app-only diagnostic found zero fatal crash entries.
- LINE／Google login was intentionally not attempted because it would require placing a personal provider account on a borrowed device. Prior emulator staging provider evidence is not reclassified as physical-device evidence.

## Acceptance status

- Independent review requested two bounded corrections: signer-check/install now cannot bypass the ABI gate, and runtime integrity now verifies CRC32 rather than trusting ZIP names or declared length.
- Final independent Flutter/release-artifact verdict: `ACCEPT`; focused 4/4, complete launcher 61/61 and `git diff --check` passed.
- Hosted CI, single PR/merge and final borrowed-device cleanup remain pending.
