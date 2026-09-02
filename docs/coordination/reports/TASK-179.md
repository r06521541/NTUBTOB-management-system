# TASK-179 report：iOS Signed IPA Candidate Inspector

## Delivery delta

- 新增`tools.ios_candidate_inspector`：只讀snapshot已存在的IPA，拒絕reparse／non-regular、空檔、超限、duplicate、
  encrypted、unsafe path、symlink、multiple app與缺少signed application資料。
- 解析exact bundle/version/build/minimum iOS/executable，並在macOS以fixed、timeout、bounded-output的`codesign`與
  `security cms`唯讀驗證signature、distribution profile、expiration、identity category與exact Apple entitlement。
- 成功輸出只含artifact SHA/size、public version/build與deidentified booleans；固定錯誤不回傳path、Team/profile/
  certificate/application identifier或raw tool output。
- Actual TestFlight mode先讀committed Apple readiness contract；目前`not_implemented`使其在artifact access前fail closed。
  Fictional contract-test只證明工具行為，不構成candidate、signing、provider、upload或device evidence。
- 新增TestFlight checklist與release matrix連結；hosted deployment-tools job固定執行inspector regression。

## Verification

- `py -3.10 -m unittest tools.tests.test_ios_candidate_inspector -v`：11 passed。
- `py -3.10 -m unittest discover -s tools/tests -p "test_deploy_*.py" -v`：89 passed。
- `py -3.10 -m unittest discover -s tools/tests -p "test_ci_*.py" -v`：33 passed，1 skipped（本機Git Bash無法啟動）。
- `py -3.10 -m unittest tools.tests.test_ios_candidate_inspector tools.tests.test_ci_workflow_contract -v`：24 passed，
  1 skipped（同上）。
- `py -3.10 -m compileall -q tools/ios_candidate_inspector.py tools/tests/test_ios_candidate_inspector.py`：passed。
- `py -3.10 -m isort --check-only tools/ios_candidate_inspector.py tools/tests/test_ios_candidate_inspector.py`：passed。
- Black CLI在bundled Windows Python出現既知持續停滯；依`AGENTS.md`改以同版本formatter API逐檔比對：passed。
- `git diff --check`：passed。

## Broader local-suite observation

額外執行`py -3.10 -m unittest discover -s tools/tests -v`，TASK-179 tests仍全部通過，但整體581 tests出現13 failures、
12 errors、53 skipped。失敗皆位於既有checksum-locked／runtime operator／PowerShell module／缺少SQLAlchemy、JAVA_HOME或
isolated PostgreSQL的舊工具測試，與TASK-179 owned paths無交集；本task不修改或掩蓋它們。Hosted change-selected gate仍
須作最終證據。

## External mutations

- none：未登入Apple、未讀account／Team/provider值、未建立certificate/profile/private key、未sign/archive/upload、
  未操作App Store Connect／TestFlight／device、未變更Secret、cloud、runtime或production。

## Remaining limits

- 尚無真實signed IPA，因此未執行macOS real `codesign`／`security cms` inspection；目前只由fictional injected output
  鎖定解析與fail-closed契約。
- Apple enrollment、App ID/capability、certificate/profile、App Store Connect app、provider/runtime binding、
  TestFlight upload/install與真機auth/session仍是外部Owner gate。
- Repository Apple readiness marker仍為`not_implemented`；不得把本次交付解讀為TestFlight或public release ready。
- immutable SHA、獨立Release／Security verdict、hosted CI與PR integration待後續段落更新。
