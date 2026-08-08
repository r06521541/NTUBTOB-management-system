# TASK-075 Work review

## 結論

結果：`accepted_pending_hosted_ci`

未發現blocking finding。Shared branch可建立唯一ready PR；GitHub必須成功解析新workflow，且本次因workflow、
classifier與policy bundle同時變更，classifier必須選擇唯一`full=true`並成功完成全部既有service suites、
PostgreSQL 15／16 matrix及名稱固定的`CI final gate`。Hosted evidence通過且branch不再改變後，可依standing Git
授權squash merge；不另建closeout／run-ID PR。

## 查驗對象

- Branch：`codex/task-075-change-aware-ci`
- Base：`945375c82761efe9a19e5a477c53f7fd4d3c5c49`
- Implementation：`cd76a94924f237d6eb464f4be4d58e5a51864b72`
- Completion evidence：`e52fc30`
- Worktree：clean
- PR：依新流程尚未建立

## 實際diff與設計查驗

- Owner-reviewed policy bundle完整保留於implementation commit，且Codex report明確區分既存文件與Codex實作。
- Classifier使用stdlib、固定outputs、NUL-separated Git diff與40-character SHA validation；PR走merge-base，main
  push走before／after，manual／unknown／invalid／empty皆fail conservative為full。
- 一般docs-only只走quick gate；`docs/operations/sql/**`、`docs/operations/data/**`、`.gitattributes`、migration、
  portal-data、shared library、requirements、workflow與未知path不會降級為一般文件。
- Workflow保留PR、main push、manual dispatch及main safety net，加入同PR／ref concurrency與
  `cancel-in-progress`，沒有修改repository settings或使用第三方path-filter action。
- Database job保留Python 3.10、PostgreSQL 15.8／16.4、Black、三個Phase C verifier與完整portal-data suite。
- 各非DB job只在對應scope／full執行；quick gate不啟動PostgreSQL或安裝application dependencies。
- `CI final gate`永遠觀察classify、quick及所有optional jobs；合法skip可通過，required failure／cancel／skip、
  invalid／empty classification及非預期執行的unselected job會失敗。
- Main push昂貴重跑尚未移除，符合branch protection未建立前的安全邊界。

## Work獨立驗證

- `python -m unittest discover -s tools/tests -p "test_ci_*.py" -v`：20/20 passed。
- `python -m tools.ci_change_classifier classify --git-diff <base> <implementation> --merge-base`：只有
  `full=true`，其餘outputs皆false，base/head完整SHA正確。
- `git diff --check <base>..HEAD`：passed。
- `git status --short`：驗收開始時clean。
- 實際檢閱`.github/workflows/python-tests.yml`、classifier及兩份contract tests。

Codex另記錄並已本機執行：tools 61/61、Web Portal 118 passed／2 Windows skips、game broadcast 28/28、
notify 9/9、schedule 5/5、LINE webhook 19/19，以及PostgreSQL 15.8與16.4各157/157。Work本輪依新版
risk-based規則不重跑這些完整suites；hosted full baseline將提供獨立Python 3.10證據。

## 尚待hosted確認

- 本機沒有YAML parser／actionlint，因此必須由GitHub hosted parser接受workflow。
- Final PR必須實際顯示`full`分類下所有jobs成功，且`CI final gate`成功。
- Docs-only時optional jobs合法skip的真實Actions證據，需等後續真正docs-only PR驗證；本任務不為製造該證據
  另開測試PR，現階段由離線contracts覆蓋。

## 安全邊界

本驗收不包含production、Supabase、migration、deployment、Secret、IAM、Scheduler、通知、branch protection或
其他GitHub settings變更。TASK-073仍停在production inventory前；TASK-075不授權任何production操作。
