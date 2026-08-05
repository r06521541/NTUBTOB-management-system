# TASK-033 Work 驗收報告

驗收時間：2026-08-06（Asia/Taipei）

## 結論

- 結果：`accepted`
- Branch：`codex/poll-web-portal-rollout`
- Base：`53fbd0617aca241107c64cd72907f6da905fdd73`
- Implementation：`99f0b82`
- Codex completion：`1ec6dcb`
- 下一位角色：Owner（決定是否批准PR工作包）

## 驗收結果

- Cloud Build success後新增bounded rollout polling，timeout／interval／clock／sleeper皆可注入，不會busy loop或無限等待。
- New revision尚未出現、未Ready或traffic尚未100%時視為transient；收斂後才進IAM與HTTP。
- Ready revision的digest、runtime identity、Secret／plain env classification及demo gate drift仍是hard failure，不會被retry掩蓋。
- HTTP endpoints成功路徑各呼叫一次；poll完成前不呼叫HTTP或查IAM。
- Failure message只輸出安全stage：build、rollout_convergence、iam、http、rollback；不回顯command output、env、Secret或HTTP body。
- Rollback只使用exact approved revision，rollback success／failure仍可區分；temporary env各路徑由finally清理。
- Windows `gcloud.cmd`與POSIX resolution保持既有單一runner boundary。

## Work獨立驗證

```text
tools tests: 38 passed
Web Portal tests: 58 passed, 2 existing Windows make/sh skips
compileall: passed
Python 3.10 grammar: passed
Web Portal dry-run: passed; no cloud or HTTP
git diff --check 53fbd06..HEAD: passed
working tree: clean
```

## 尚未驗證與風險

- Fake runner不能證明真實Cloud Run收斂時序；仍需GitHub Python 3.10 CI與另行批准的production rollout。
- IAM只查一次；若IAM control-plane也暫時延遲，wrapper會fail closed並rollback。本任務未擴張IAM polling。
- Ready持續非True會在timeout後rollback，不讀condition message或application log。
- 未push、PR、部署、gcloud、HTTP或production存取，未修改Web Portal功能、schema、Secret、IAM或LINE。

## 建議

接受TASK-033。Owner若批准PR工作包，可push、建立Draft PR並查驗Python 3.10 CI；merge與production deployment仍須分別批准。部署source必須使用merge後的新main commit，rollback仍需執行前重查。
