# TASK-013 Work Review

日期：2026-08-05
結論：`accepted`
下一位角色：Owner

## 驗收基準

- Branch：`codex/add-scheduled-service-health-checks`。
- Task base：`3389f96d6221f6ca0c566e6c74bf516012d83a83`。
- Implementation evidence HEAD：`9b98e6ee19e98903756c20b8941d5ccacdbc712e`。
- Draft PR：[#30](https://github.com/r06521541/NTUBTOB-management-system/pull/30)，base `main`，title `feat(scheduled-services): add side-effect-free health checks`。
- Working tree於Work獨立測試前乾淨；本review與handoff尚未commit。

## 實作驗收

- [x] 兩個private scheduled services各有固定最小JSON的`GET /healthz`。
- [x] Response為200、`application/json`、`Cache-Control: no-store`；POST為405。
- [x] Actual service apps以isolated import載入；連續health calls未觸發接入的DB、LINE、Discord、crawler或weather fail-on-call dependencies。
- [x] 既有business route paths及POST methods維持不變。
- [x] Cloud Build private flag與deployment settings沒有修改。
- [x] README及deployment runbook明確限制health只代表Flask process/route，production invocation仍需exact授權。
- [x] 沒有shared_lib、schema、Scheduler、Secret、IAM或其他service功能變更。

第一次review曾退回無效的standalone Blueprint mocks；commit `a6273e8`已完成actual-app測試補正，該blocking code issue已解除。

## Work獨立測試

Local runtime：Python 3.12.13。

```text
python -m unittest discover -s apps/game_broadcast_service/tests -v
26/26 passed

python -m unittest discover -s apps/notify_cronjob_service/tests -v
6/6 passed

python -m compileall -q apps/game_broadcast_service apps/notify_cronjob_service
passed

git diff --check 3389f96..HEAD
passed
```

GitHub實際查驗：PR HEAD `9b98e6e`，Python 3.10 run `30964752095`／job `92176191809`為`SUCCESS`。

## Blocking PR scope

`main`目前為`086d663`，但TASK-013 branch沿用尚未合併的：

- `b25b3ad`：production deployment governance與結案文件。
- `3389f96`：TASK-012 Web Portal local demo MVP。

因此PR #30相對main包含上述兩批變更，不是單純TASK-013。Owner已接受並授權commit TASK-012，但尚未批准將TASK-012與部署文件建立／納入PR；Work不得把TASK-013 PR工作包擴張為其他任務的PR授權。

## 建議解除方式

優先建立一個prerequisite Draft PR，head為`codex/fix-broadcast-request-time`的`3389f96`、base為`main`，內容是已接受的部署治理文件及TASK-012 MVP。Owner review並merge該PR後，PR #30會自然縮為TASK-013 commits，不需force-push或改寫歷史。之後Work再做一次final PR diff/CI查驗。

在Owner批准前，不建立此前置PR、不force-push、不merge，也不部署或呼叫production。

## Prerequisite PR 狀態

Owner已批准建立前置工作包。Work已查驗Draft [PR #31](https://github.com/r06521541/NTUBTOB-management-system/pull/31)：

- Base／head：`main`／`codex/fix-broadcast-request-time`，HEAD `3389f96`。
- Commits僅`b25b3ad`與`3389f96`，符合已接受的deployment governance closeout及TASK-012 MVP。
- Python 3.10 run `30969552190`／job `92190712559`為`SUCCESS`。
- PR維持Draft且尚未merge。

PR #31 merge後需重新查驗PR #30的base diff與最新CI，才能把本review結論改為`accepted`。

## Final scope verification

- PR #31已以merge commit `b5d33e7`合併。
- TASK-013 branch以正常merge commit `ab5769d`納入最新main；沒有rebase或force-push。
- PR #30現只包含15個TASK-013相關檔案：兩個services、其tests／README、Python workflow、TASK-013 coordination docs及deployment runbook。
- Web Portal、TASK-012及先前deployment closeout files已不在PR #30 diff。
- PR #30為`MERGEABLE`；同步後Python 3.10 run `30970101898`／job `92192361234`為`SUCCESS`。

Implementation與PR scope均符合TASK-013，無blocking issue；建議Owner將PR #30標記ready並merge。未部署或呼叫production。
