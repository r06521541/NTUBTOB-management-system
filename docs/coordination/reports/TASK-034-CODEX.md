# TASK-034 Codex 實作報告

更新時間：2026-08-06（Asia/Taipei）

## 任務狀態

- 狀態：`ready_for_review`
- Branch：`codex/promote-web-portal-traffic`
- Base commit：`96ee2a0d8fefce74b35b410069f0e1bafb405eeb`
- Planning commit：`d8c0da5`
- Implementation commits：`b7d13bc`、`05ef544`
- Draft PR：[PR #43](https://github.com/r06521541/NTUBTOB-management-system/pull/43)

## 完成內容

- 將新 revision readiness／runtime contract 驗證與 traffic convergence 拆成兩個 bounded polling 階段。
- 新 revision 必須不同於 baseline、Ready，且 image digest、runtime identity、Secret/plain env classification及production demo gate全部符合核准契約，才可能切換流量。
- pinned old traffic 情境會以固定project／region／service及exact new revision執行單一argument-list、`shell=False`的`update-traffic ... <revision>=100`，再等待100% traffic收斂。
- 切流量前的revision timeout或hard drift保留原健康舊流量，不執行不必要rollback；promotion開始後的promotion、convergence、IAM或HTTP失敗才切回exact approved rollback revision。
- 若新revision已自動取得100% traffic，不重複promotion，但後續驗證失敗仍保留rollback安全性。
- failure stage明確區分`build`、`revision_convergence`、`traffic_promotion`、`traffic_convergence`、`iam`、`http`與`rollback`。

## 測試與驗證

- GitHub Actions run `31043954172`／job `92434796238`：CPython 3.10.20，完整repository workflow成功。
- Tools tests：41項通過（2項非Windows runner上的既有platform skip）。
- Workflow亦依序完成Web Portal、game broadcast、notify cron、update schedule及LINE webhook suites。
- `git diff --check`：通過。
- 本機`python`指令不存在，`py -3.10`指向已失效的Windows Store安裝，因此本機未重複執行unittest／compileall／dry-run；Python 3.10實跑證據來自hosted runner。

新增／調整的離線案例涵蓋：pinned traffic promotion、revision暫態／hard drift、traffic收斂、已自動promotion、promotion failure、IAM／HTTP failure、exact rollback及rollback failure。所有cloud command與HTTP均由fake runner／mock隔離。

## 安全聲明

- 未執行wrapper `--execute`、gcloud、HTTP、Cloud Build、Cloud Run、Artifact Registry、IAM或logs查詢。
- 未部署、切production traffic、rollback、修改Secret／IAM／schema／DB或發送LINE通知。
- 未讀取或輸出真實`.env.yaml`內容、Secret value或production data。
- Production仍由既有revision承接traffic；PR合併與後續production deployment均需Owner另行批准。

## 變更檔案

- `tools/deploy_web_portal.py`
- `tools/tests/test_deploy_web_portal.py`
- `docs/coordination/reports/TASK-034-CODEX.md`
- `docs/coordination/PROJECT_STATE.md`
- `docs/coordination/HANDOFF.yaml`
