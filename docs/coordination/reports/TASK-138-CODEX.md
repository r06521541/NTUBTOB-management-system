# TASK-138 Codex report

## Delta

- Added an optional TASK-134 broker config input to the TASK-129 harness.
- Added a bounded isolated broker-client adapter for status, grant, restore and
  same-ID reconcile.
- Added task-private atomic operation sidecars bound to the exact acceptance
  artifact/device vocabulary and exact value-free broker-config fingerprint.
  Operation IDs remain absent from the public checkpoint and governed output.
- Split broker mutation reconciliation from portal logout reconciliation.

## Safety behavior

- The sidecar is durable before the intent checkpoint and broker request.
- Grant/restore issue at most one mutation request. Intent/result resume performs
  only `reconcile` with the retained ID.
- Private file reads reject reparse paths, hardlinks, replacement races and
  oversized content. Broker child results require TASK-134's exact governance
  envelope as well as bounded result fields.
- Sidecar creation validates the complete destination ancestor chain before
  generating or writing private bytes. Every launched broker child performs the
  broker-config fingerprint post-check, including timeout and malformed-output
  paths.
- Broker provisioning, drift, timeout, unavailable and unknown-result states are
  bounded and never expose child stdout/stderr or generate a replacement ID.
- No Flutter, broker, launcher, schema, cloud, Secret or production source was
  changed. Offline control/report navigation remain explicit later seams.

## Verification

- `python -m unittest tools.tests.test_mobile_staging_acceptance -v`: 22/22 PASS.
- Final broker-envelope/result mapping delta: focused 2/2 PASS; unchanged full
  suite evidence reused under the task verification budget.
- Domain correction delta (file identity, broker-config binding and governance
  envelope): focused 4/4 PASS; no full replay.
- Residual correction delta (pre-write ancestor validation and unconditional
  post-child config check): focused 2/2 PASS; no full replay.
- PowerShell parser for `Invoke-MobileStagingAcceptance.ps1`: PASS.
- `python -m py_compile tools/tests/test_mobile_staging_acceptance.py`: PASS.
- `python -m isort --check-only tools/tests/test_mobile_staging_acceptance.py`: PASS.
- `git diff --check`: PASS.
- Windows Black CLI and same-version formatter API both reproduced the known
  bounded local hang and were terminated after 30 seconds; no Python process
  remained. Final formatting evidence is deferred to hosted CI.

No launcher, emulator, ADB, broker request, gcloud, Secret, database, staging or
production action ran during repository implementation.
