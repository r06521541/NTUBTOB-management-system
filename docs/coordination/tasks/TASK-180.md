# TASK-180：iOS Store Readiness Contract

## Task metadata

- type: `delivery`
- delivery_group: `task-180-ios-store-readiness`
- acceptance_level: `L2`（store privacy／release evidence boundary；repository-only）
- base: `578b3bf0ad75983a99139da235a3e7f3146be729`
- branch: `codex/task-180-ios-store-readiness`
- report_to: `main-work`
- owner_approved: 2026-09-05

## Product outcome

在不建立Apple資源、不登入或修改App Store Connect、不簽章／upload／deploy的前提下，將第一個iOS TestFlight candidate可
預先準備的繁中beta文案、固定Basic staging scope、repository資料使用事實與所有未完成外部gate固化成machine-readable
manifest及fail-closed validator。現有帳號刪除文字不得被誤標為符合Apple完整帳號刪除要求。

## Writer claim

- actor_id: `/root`
- role: `codex-writer`
- claim_id: `task-180-ios-store-readiness-writer-20260905`
- lease_version: 1
- scope: TestFlight draft metadata、privacy facts、store readiness gates、offline validator/tests及release docs
- owned_paths:
  - `tools/ios_store_readiness.py`
  - `tools/tests/test_ios_store_readiness.py`
  - `tools/ci_change_classifier.py`
  - `tools/tests/test_ci_change_classifier.py`
  - `.github/workflows/python-tests.yml`
  - `tools/tests/test_ci_workflow_contract.py`
  - `docs/releases/ios-testflight-preparation.json`
  - `docs/releases/IOS_APP_STORE_CONNECT_ANSWERS.md`
  - `docs/releases/IOS_TESTFLIGHT_CHECKLIST.md`
  - `docs/coordination/tasks/TASK-180.md`
  - `docs/coordination/reports/TASK-180.md`
  - `docs/coordination/HANDOFF.yaml`
  - `docs/coordination/PROJECT_STATE.md`

## Required behavior

1. Manifest只允許`staging + real + Basic-only + iOS 15`，固定不使用production data、push、deep link或crash upload。
2. 繁中name/subtitle/beta description/what-to-test草稿須符合Apple公開長度邊界且不含URL、email、provider、signing或Secret類別。
3. Privacy inventory只記repository已證明的資料事實；不把它冒充App Store Connect已送出的App Privacy答案，且tracking必須為false。
4. 公開privacy/support URL、完整App內帳號刪除、第三方SDK privacy、archive manifest、年齡、出口合規、content rights、
   DSA／地區、screenshots、Beta Review聯絡資料、Apple資源、Mac/Xcode、signed IPA與真機一律保持`required`或`blocked`。
5. Validator只輸出去識別化count與`PREPARATION_ONLY`，不連網、不寫檔、不讀帳號／artifact，也不能輸出release ready。

## Verification budget

- Python unit tests覆蓋exact scope、unknown/duplicate、draft identifier/length、privacy consistency、tracking與gate fail-closed。
- CI workflow contract確認deployment-tools hosted job執行validator tests。
- changed Python quality、focused tests、獨立read-only Release／Privacy review及一次ready PR hosted gate。

## Independent reviewer

- actor_id: `/root/task178_release_security_review`
- role: `advisor/reviewer`
- claim_id: `task-180-ios-store-release-privacy-reviewer-20260905`
- round 1 lease_version: 1；reviewed SHA `a0c041353c4e4d955b877486e03fc93a5dc94557`；`REQUEST_CHANGES`
- round 2 lease_version: 2；reviewed SHA `59569f1e40ad9b471cb1d4615d758249b811a7de`；`REQUEST_CHANGES`
- round 3 lease_version: 3；reviewed implementation SHA `fce24bbbb3d8770276ef1db4400405ea9aee8818`；`REQUEST_CHANGES`
- round 4 lease_version: 4；reviewed implementation SHA `6d465b0fe495bf6d368d854755bbdeab3e706560`；`REQUEST_CHANGES`
- round 5 lease_version: 5；reviewed implementation SHA `0821849a0897d5a2ec80c683f7d6e8a2bc2cb13d`；`REQUEST_CHANGES`
- final correction rereview lease_version: 6；implementation SHA `99f7dd343c421eddf11731ec843ba7c5bef3f563`
- write: `read-only`
- report_to: `/root`
- scope: immutable manifest/parser/classifier、deidentification、Apple privacy/account deletion boundary與hosted execution

## Stop conditions

- 需要Owner決定brand/category、提供feedback email／URL、回答法律／年齡／出口問題或建立Apple資源。
- 需要修改帳號刪除data lifecycle、provider、signing、runtime、Secret、cloud、production或任何外部狀態。
