# TASK-170：Android Basic-only Closed Testing Candidate

## Task metadata

- type: `delivery`
- delivery_group: `task-170-android-closed-testing-candidate`
- acceptance_level: `L3`（release signing／store upload／isolated staging runtime）
- base: `0f81084c8c1e16c8b32f4634927e91a19617b206`
- branch: `codex/task-170-android-closed-testing-candidate`
- report_to: `main-work`
- owner_approved: 2026-08-31

## 2026-09-02 candidate-operator continuation

- actor_id: `/root`
- role: `codex-writer`
- claim_id: `task-170-candidate-operator-writer-20260902`
- lease_version: 1
- base: `5af3410dfbb7d8f748b25941b35c920070f8caa3`
- branch: `codex/task-170-candidate-operator`
- owned_paths: Android release Gradle/runtime config, Flutter bootstrap/config tests, mobile release/candidate tools and tests,
  Flutter hosted workflow, TASK-170 release/task/report/checklist files, `PROJECT_STATE.md` and `HANDOFF.yaml`.

Execution checkpoint: goal is a repository-owned, one-pass candidate operator from exact merged main. The invariant is that
runtime/signing values never enter command arguments, environment, Git, retained temporary input or emitted child output; Gradle
receives them once over an authenticated loopback memory channel and the inspector hashes the actual bundled runtime config against
the public contract. Minimum evidence is Python tool suites, Flutter test/analyze/format, fictional signed release build plus strict
inspection, independent Release/Security review and one hosted gate. Real key creation/backup, candidate derivation, device, Play
Console/upload and any provider/cloud mutation remain later Owner-visible gates.

## Owner decisions and bounded authority

1. Permanent Google Play package identity is `tw.org.ntubtob.portal`.
2. Android distribution uses Play App Signing with a repository-external upload key.
3. Owner authorizes creation of the exact Basic-only candidate, external signing, real-device staging verification, and upload to Google Play Closed Testing. This does not authorize production backend/data, open testing, production rollout, public publication, paid account changes, or destructive key rotation/deletion.
4. Repository branch push, the single ready PR, hosted CI, conflict-free merge and coordination closeout remain authorized under DEC-076.
5. Owner-only interaction is limited to account login/MFA and private password input when an existing signed-in surface or secure local input cannot satisfy the operation. Any new billing, irreversible store action, package ownership conflict, production target, or unknown signing lineage stops before mutation.

## Product and security contract

1. The candidate is `android-closed`, Basic-only, `staging:real`, and must bind only to the approved isolated mobile staging runtime/data. A production backend endpoint or mixed environment fails closed.
2. The AAB uses package `tw.org.ntubtob.portal`, API 36, a monotonic version code, repository-external signing material, and the exact signer fingerprint accepted for the upload key. No keystore, password, provider ID, endpoint, account, token, or Secret payload enters Git, logs, reports, command history, or retained artifacts.
3. Play App Signing enrollment and Closed Testing upload are distinct from public publication. No production/open-track rollout or tester notification is performed.
4. The exact AAB must pass strict repository inspection before upload. The uploaded artifact/version must match the reviewed local evidence; a rebuild after acceptance requires reinspection.
5. Real-device validation uses only fictional/test accounts and staging data. It covers install/upgrade, cold start, LINE and Google login where safely available, refresh/logout, schedule/Event/attendance, and offline behavior; unavailable provider steps are reported, never fabricated.
6. Data Safety, privacy/support/account-deletion paths, Basic-only limitations, push/deep-link/crash-reporting exclusions and tester notes must describe the exact candidate. Unknown Console requirements stop submission rather than being guessed.

## Work lanes

### Android candidate contract writer

- actor_id: `/root/task170_android_candidate_writer`
- role: `codex-writer`
- claim_id: `task-170-android-candidate-contract-writer-20260831`
- lease_version: 1
- scope: model and test the `android-closed + staging:real` release contract, candidate evidence tooling and version/package invariants
- owned_paths:
  - `clients/flutter_app/android/**`
  - `clients/flutter_app/pubspec.yaml`
  - `clients/flutter_app/README.md`
  - `tools/mobile_release.py`
  - `tools/tests/test_mobile_release.py`
  - `docs/coordination/reports/TASK-170-ANDROID-CANDIDATE.md`

### Store evidence writer

- actor_id: `/root/task170_play_evidence_writer`
- role: `codex-writer`
- claim_id: `task-170-play-closed-evidence-writer-20260831`
- lease_version: 1
- scope: exact Closed Testing checklist/evidence contract, deidentified listing/Data Safety/tester notes and fail-closed operator boundary
- owned_paths:
  - `docs/releases/**`
  - `tools/android_closed_testing.py`
  - `tools/tests/test_android_closed_testing.py`
  - `docs/coordination/reports/TASK-170-PLAY-CLOSED.md`

Each writer must acknowledge `received/executing`, self-review and run focused tests, send a heartbeat at least every 10–15 minutes, report blockers immediately, and on completion proactively notify Main with exact paths, full SHA if committed, tests, findings and remaining limits. Writers may not access real signing material, Console, provider, cloud, production or device data.

## Ordered execution

1. Persist this task and reconcile repository release contracts for staging-only Closed Testing.
2. Writers complete focused implementation and handoff; Main integrates and reviews the combined diff.
3. One independent Release/Security reviewer accepts an immutable candidate-contract commit.
4. Run the single hosted gate required by the selected changes and merge the repository delivery only when green and conflict-free.
5. From the merged exact commit, perform sanitized staging/config discovery, prepare or verify the repository-external upload key, build and strictly inspect the exact AAB.
6. Install the exact candidate on the connected Android 15 device and execute the bounded staging matrix.
7. Complete only the exact Play Console Closed Testing listing/Data Safety/tester gates, upload the accepted AAB, and verify its package/version/track/processing state without open/public rollout.
8. Record deidentified evidence and close TASK-170. Store availability and tester delivery remain external observations, not inferred from upload acceptance.

The Owner has since created the Play application with permanent package `tw.org.ntubtob.portal`, app name `NTUBTOB`, locale zh-TW,
application/free classification. No AAB, track release, tester notification, open/production rollout or public publication has occurred.

## Verification budget

- Writers: focused tooling/Gradle contract tests and format/static checks.
- Main: full affected Flutter tests/analyze, Android release build/inspection with fictional signer first, exact scope/diff review.
- One independent Release/Security targeted review after integration.
- One ready PR and change-selected hosted CI before any real candidate is derived from the merged commit.
- External phase: exact AAB hash/signature inspection, one Android 15 real-device staging matrix, Play Console closed-track post-check.

## Stop conditions

- Package `tw.org.ntubtob.portal` is already owned by an incompatible application or Console account.
- Signing lineage/upload certificate is absent, ambiguous, mixed, repository-resident, or requires destructive rotation.
- Candidate points to production, an unknown runtime/data environment, or discloses a provider/Secret value.
- Store requires billing, open/public rollout, production declarations, destructive action, or unsupported compliance claims.
- Hosted CI/review fails, exact AAB differs from accepted evidence, device result is crash/uncertain, or Console processing becomes ambiguous.

No stop condition may be bypassed by weakening auth, artifact inspection, signing, staging isolation or store declarations.
