# TASK-179：iOS Signed IPA Candidate Inspector

## Task metadata

- type: `delivery`
- delivery_group: `task-179-ios-candidate-inspection`
- acceptance_level: `L2`（release／signing evidence boundary；repository-only）
- base: `dea9571a7b446f37c600c7e2f70146810e534c57`
- branch: `codex/task-179-ios-candidate-inspection`
- report_to: `main-work`
- owner_approved: 2026-09-02

## Product outcome

在不登入Apple帳戶、不建立或讀取private key、不簽章、不上傳TestFlight，也不接觸provider／runtime的前提下，
新增一個離線、fail-closed的signed IPA inspector。未來由受控macOS builder產生candidate後，工具可將exact artifact綁定
SHA-256、version/build、bundle identity、codesign、distribution profile與Apple entitlement分類；輸出不得包含Team ID、
profile UUID/name、certificate、application identifier、provider value或原始tool output。

## Writer claim

- actor_id: `/root`
- role: `codex-writer`
- claim_id: `task-179-ios-candidate-inspector-writer-20260902`
- lease_version: 1
- scope: signed IPA snapshot／archive safety、metadata/signature/profile/entitlement classification、offline tests、TestFlight checklist與CI gate
- owned_paths:
  - `tools/ios_candidate_inspector.py`
  - `tools/tests/test_ios_candidate_inspector.py`
  - `.github/workflows/python-tests.yml`
  - `tools/tests/test_ci_workflow_contract.py`
  - `clients/flutter_app/ios/README.md`
  - `docs/releases/IOS_TESTFLIGHT_CHECKLIST.md`
  - `docs/releases/MOBILE_RELEASE_MATRIX.md`
  - `docs/coordination/tasks/TASK-179.md`
  - `docs/coordination/reports/TASK-179.md`
  - `docs/coordination/HANDOFF.yaml`
  - `docs/coordination/PROJECT_STATE.md`

## Required behavior

1. Inspector只接受單一regular `.ipa` artifact，先建立bounded immutable snapshot，再解析ZIP；拒絕空檔、超限、duplicate、
   encrypted、absolute／backslash／traversal path、symlink與多個／缺少`Payload/*.app`。
2. Candidate須有exact production-shaped bundle identity、三段numeric version、正整數monotonic build、最低iOS 15、單一
   executable、`embedded.mobileprovision`及`_CodeSignature/CodeResources`。
3. macOS actual inspection只可用fixed `codesign`與`security cms`命令、empty/bounded環境、timeout及bounded output；
   任一工具缺失、timeout、非零、輸出過大或invalid plist都fail closed，不回傳raw stdout/stderr。
4. Distribution profile及app entitlements須互相符合bundle category，`get-task-allow=false`，Apple entitlement exact array
   `Default`；任何development、missing、mixed或額外Apple entitlement值皆拒絕。
5. 實際TestFlight mode須同時確認repository marker為`ready`；目前marker仍為`not_implemented`，因此真實candidate維持
   fail-closed。fictional contract-test只驗證工具，不能作為signing、provider、archive、TestFlight或device evidence。
6. 成功輸出只含schema、classification、artifact SHA/size、version/build及去識別化match booleans；錯誤固定、不得洩漏
   path、archive entry、tool output或signing/provider資料。

## Independent reviewer

- actor_id: `/root/task178_release_security_review`
- role: `advisor/reviewer`
- claim_id: `task-179-ios-candidate-release-security-reviewer-20260902`
- lease_version: 2
- write: `read-only`
- report_to: `/root`
- scope: immutable TASK-179 SHA的snapshot/archive safety、macOS command boundary、plist/profile/entitlement validation、
  deidentification、actual-marker block與CI execution

Reviewer須依mandatory assignment packet立即ACK、10–15分鐘heartbeat、blocker即報、完成主動回報SHA／tests／findings／
limits／external mutations；不得修改working tree、commit、push、PR或任何外部狀態。

## Verification budget

- Python unit tests覆蓋valid fictional vector、actual marker block、metadata/signature/profile/entitlement drift、unsafe archive、
  size/output/timeout與redacted error/output。
- CI workflow contract確認tool tests在deployment tools hosted job執行。
- changed Python quality、focused tests、獨立Release／Security review及一次ready PR hosted gate。

## Stop conditions

- 需要Apple登入、MFA、account/team/provider值、certificate/profile/private key payload、codesign mutation、archive、upload、
  TestFlight、真機、Secret、cloud/runtime/deployment或production資料。
- 無法以去識別化分類驗證signed artifact，或必須放寬目前public-release fail-closed marker。
