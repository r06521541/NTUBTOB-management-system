# TASK-113：Isolated mobile staging activation and emulator acceptance

task_type: delivery
delivery_group: mobile-staging-activation
requires_independent_pr: true
status: active_local_preflight
base_commit: baee3f93357c1268cd6d8803e053983939fa3a5d

## Goal

Activate an isolated non-production mobile staging environment using the
TASK-112 fail-closed operators, then validate the TASK-110/114 Flutter client on
an Android Emulator. No Android physical device is currently available; real
device LINE callback acceptance remains an explicit deferred gate.

## Ordered checkpoints

1. Local only: install an official user-scoped Emulator/system image/AVD on the
   spacious E drive, verify acceleration, boot and run fake-client smoke.
2. Read-only: inventory candidate dedicated GCP project, database provider and
   LINE Developing channel requirements; render a redacted cost/target manifest.
3. Owner exact approval: project/billing/APIs, database immutable identity,
   service accounts/IAM, Secret references, LINE Provider/channel and tester.
4. Controlled activation: create only approved staging resources, execute 0005
   migration and fictional seed, build the exact image, deploy a private
   no-traffic candidate, post-check and explicitly promote.
5. Acceptance: build a real-config unsigned staging APK, Emulator API/session/
   Basic/Officer/offline smoke, rollback rehearsal and residual-cost inventory.

Each external mutation has its own approval/recovery evidence. An uncertain
result is diagnosed read-only and never blindly retried.

## Local toolchain boundary

- Reuse official Flutter 3.47.0/JDK 17 from TASK-107.
- Put TASK-113 Emulator SDK packages, system image, AVD and caches under a
  task-specific E-drive root. Do not delete or relocate existing C-drive caches.
- Prefer a Google Play x86_64 image compatible with minSdk 24 and current app
  target. LINE installation/login may be rejected by emulator security policy;
  that outcome does not authorize bypassing LINE authentication.
- If native LINE cannot be tested, use only an explicitly staging-only,
  server-audited fictional tester session after a separate contract review; it
  must not exist in production builds or be described as LINE acceptance.

## Safety boundary

- Production GCP project `ntubtob-schedule-405614` and production database are
  hard denied. No production schema, data, service, IAM, Secret or LINE change.
- Before checkpoint 3, all cloud/database/LINE work is read-only and redacted.
- Never print, commit or hash a provider subject, token, DSN credential or
  Secret value. Repository contains references/names only.
- No notification, push, broadcast, signing, APK distribution, TestFlight or
  store operation.

## Verification

- Emulator accelerator/boot/ADB/install/launch evidence and fake-client smoke.
- TASK-112 preflight/operator contracts and exact approval manifest.
- PostgreSQL 15/16 local rehearsal; remote 0005/seed only after exact approval.
- Mobile API suites, Flutter format/analyze/tests/debug build and final hosted CI.
- Staging API/auth/session/Basic/Officer/offline smoke with rollback and cleanup
  state documented honestly; physical Android and iOS remain deferred.

## Execution checkpoint

1. Goal: isolated staging plus Emulator acceptance, never production.
2. Core assets: TASK-112 operators/runbook, mobile API, Flutter client and E-drive task toolchain.
3. Invariants: exact non-production identities, redaction, staged approvals, no blind retry.
4. Tests: local Emulator/fake smoke, operator contracts, hosted suites, later approved staging smoke.
5. Current blocker: no physical Android; C drive is full, so all new Emulator assets use E drive.
