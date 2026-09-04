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

- `py -3.10 -m unittest tools.tests.test_ios_store_readiness tools.tests.test_ios_candidate_inspector tools.tests.test_ci_workflow_contract -v`：
  36 passed，1 expected local Bash-environment skip。
- `py -3.10 -m compileall -q tools/ios_store_readiness.py tools/tests/test_ios_store_readiness.py`：passed。
- `py -3.10 -m isort --check-only tools/ios_store_readiness.py tools/tests/test_ios_store_readiness.py`：passed。
- Pinned Black CLI在Windows出現專案已知高CPU停滯，終止本次exact child/parent processes後改用同版本formatter API逐檔
  比對：passed。
- `py -3.10 -m tools.ios_store_readiness`：`PREPARATION_ONLY`，13 blocked、9 required、release_ready=false。
- `git diff --check`：passed。

## External mutations

- none：未登入／修改Apple或App Store Connect、未建立App ID/capability/certificate/profile/app record、未處理private
  key、未sign/archive/upload/install、未變更provider、Secret、runtime、cloud、production或正式資料。

## Remaining limits

- App內目前只有聯絡管理員的帳號刪除說明；依一般App Store刪除要求仍是hard blocker，需另立跨Flutter/API/data lifecycle
  工作包，不在文件任務假稱完成。
- 第三方SDK privacy與archive內PrivacyInfo聚合、出口合規法律判斷、年齡問卷、content rights、DSA/地區、公開URL與
  screenshots仍需未來exact candidate／Owner-visible evidence。
- 尚待獨立Release／Privacy review、commit/push、ready PR hosted gate與merge。
