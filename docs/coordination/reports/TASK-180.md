# TASK-180 report：iOS Store Readiness Contract

## Delivery delta

- 新增`ios-testflight-preparation.json`，固定第一個iOS candidate為`staging + real + Basic-only + iOS 15`，並明確關閉
  production data、push、deep link與crash upload。
- 新增繁中TestFlight name/subtitle/beta description/what-to-test草稿與repository privacy facts；feedback、URL、provider、
  signing及account值不進repository。
- 新增`tools.ios_store_readiness`，拒絕unknown/duplicate、混合scope、識別資料、tracking與不一致privacy/gate，成功也只
  回`PREPARATION_ONLY`與去識別化counts。
- 將公開privacy/support URL、完整App內帳號刪除、第三方SDK/PrivacyInfo、年齡、出口、content rights、DSA/地區、
  screenshots、Beta Review資料、Apple/signing資源、Mac/Xcode、signed IPA與真機維持required/blocked。
- Hosted deployment-tools job固定執行新validator regression。

## Verification

- Initial focused suite：35 passed，1 expected local Bash-environment skip（36 total）。
- Reviewer round-1 correction後執行`py -3.10 -m unittest tools.tests.test_ios_store_readiness
  tools.tests.test_ci_change_classifier tools.tests.test_ci_workflow_contract tools.tests.test_ios_candidate_inspector -v`：
  58 passed，1 expected local Bash-environment skip（59 total）。
- Reviewer round-2 correction後重跑同一59-test suite：58 passed，1 expected local Bash-environment skip；新增API/access key、
  Authorization/Bearer、endpoint與IPv4/IPv6禁止類別的回歸案例。
- `py -3.10 -m compileall -q tools/ios_store_readiness.py tools/tests/test_ios_store_readiness.py`：passed。
- `py -3.10 -m isort --check-only tools/ios_store_readiness.py tools/tests/test_ios_store_readiness.py`：passed。
- Pinned Black CLI在Windows出現專案已知高CPU停滯，終止本次exact child/parent processes後改用同版本formatter API逐檔
  比對：passed。
- `py -3.10 -m tools.ios_store_readiness`：`PREPARATION_ONLY`，14 blocked、9 required、release_ready=false。
- `py -3.10 -m unittest discover -s tools/tests -p "test_deploy_*.py" -v`：89 passed。
- `git diff --check`：passed。

## External mutations

- none：未登入／修改Apple或App Store Connect、未建立App ID/capability/certificate/profile/app record、未處理private
  key、未sign/archive/upload/install、未變更provider、Secret、runtime、cloud、production或正式資料。

## Remaining limits

- App內目前只有聯絡管理員的帳號刪除說明；依一般App Store刪除要求仍是hard blocker，需另立跨Flutter/API/data lifecycle
  工作包，不在文件任務假稱完成。
- 第三方SDK privacy與archive內PrivacyInfo聚合、出口合規法律判斷、年齡問卷、content rights、DSA/地區、公開URL與
  screenshots仍需未來exact candidate／Owner-visible evidence。
- Round-1 independent Release／Privacy review對SHA `a0c041353c4e4d955b877486e03fc93a5dc94557`提出五項finding：manifest-only
  CI分類、JSON exact type／禁止字串、App內privacy policy獨立gate、bounded read與durable reviewer claim。Correction已逐項
  修正並加regression。
- Round-2 review對SHA `59569f1e40ad9b471cb1d4615d758249b811a7de`補充API/access key、Authorization/Bearer、endpoint、
  IPv4/IPv6與durable implementation head finding；實作修正固定於
  `fce24bbbb3d8770276ef1db4400405ea9aee8818`。
- Round-3 review發現`IPv4:port`未被完整解析；新增host/port fail-closed處理與端到端regression，最終實作修正固定於
  `6d465b0fe495bf6d368d854755bbdeab3e706560`。
- Round-4 review發現句尾標點可使IPv4／host-port解析失敗後放行；改為獨立擷取IPv4 host並正規化IPv6候選句點，新增
  裸IPv4、IPv4:port與IPv6句尾標點regression。最終實作固定於
  `0821849a0897d5a2ec80c683f7d6e8a2bc2cb13d`，待同一reviewer lease 5複審。
- 尚待獨立最終複審、push、ready PR hosted gate與merge。
