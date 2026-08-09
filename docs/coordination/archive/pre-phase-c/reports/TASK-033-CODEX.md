# TASK-033 Codex 實作報告

更新時間：2026-08-06（Asia/Taipei）

## 任務狀態

- 狀態：`ready_for_review`
- Branch：`codex/poll-web-portal-rollout`
- Base commit：`53fbd0617aca241107c64cd72907f6da905fdd73`
- Planning commit：`ebbd152eddd7a8506774c48bb8d747bf725d2c42`
- Implementation commit：`99f0b82`
- 未 push、未建立 PR、未 merge、未部署

## 完成內容

- Cloud Build 成功後，以可注入 clock、sleeper、timeout、interval 的 bounded polling 等待 Cloud Run control-plane 收斂。
- polling 依序等待新 revision 出現、Ready、核准 image digest／runtime contract 與新 revision 100% traffic；完成前不查 IAM、不送 HTTP。
- 尚未出現的新 revision、尚未 Ready 與尚未收斂的 traffic 視為暫態；Ready revision 的 digest、runtime identity、Secret/plain env classification及production demo gate漂移視為hard failure，立即rollback而不等待timeout。
- IAM與HTTP仍為polling後的獨立驗證階段；`GET /`及`GET /demo/`成功路徑各只執行一次。
- 失敗只回報安全stage：`build`、`rollout_convergence`、`iam`、`http`或`rollback`，並保留rollback success／failure區分，不回顯gcloud stderr、JSON、env、Secret或HTTP body。
- temporary env在成功、timeout、hard drift、IAM／HTTP失敗與rollback失敗路徑均由既有`finally`清理。
- Windows `gcloud.cmd`與POSIX executable resolution維持既有唯一runner邊界。

## 測試與驗證

使用workspace bundled Python執行：

```text
python -m unittest discover -s tools/tests -v
Ran 38 tests — OK

python -m unittest discover -s apps/web_portal/tests -v
Ran 58 tests — OK (skipped=2)

python -m compileall -q tools apps/web_portal
通過

ast.parse(..., feature_version=(3, 10))
通過

python tools/deploy_web_portal.py
Preflight passed; no cloud or HTTP commands were run.

git diff --check 53fbd061...HEAD
通過
```

新增／加強的離線案例涵蓋：

- baseline→新revision缺席→未Ready→traffic未收斂→成功。
- convergence timeout在IAM／HTTP前rollback。
- Ready revision runtime contract drift立即hard fail，不等待timeout。
- IAM stage、HTTP failure／transport failure、rollback failure與安全stage訊息。
- HTTP成功路徑各endpoint只呼叫一次。
- cleanup、exact rollback revision、Windows／POSIX command resolution與既有scheduled-service wrapper回歸。

兩項skip是Windows缺少Unix `make`／`sh`的既有Web Portal Make contract，與本任務無關。Bundled Python未安裝Black，因此未執行formatter；已人工維持附近格式並通過diff check。

## 安全聲明

- 所有gcloud與HTTP均由fake runner／mock完成。
- 未執行`--execute`，未呼叫gcloud、Cloud Build、Cloud Run、Artifact Registry、IAM、logs或production HTTP。
- 未讀取真實`.env.yaml`、Secret payload／value、cookie、LINE code/state或production data。
- 未部署、切traffic、rollback、刪除revision、修改IAM／Secret／schema或呼叫LINE／DB。

## 尚未驗證與風險

- Fake JSON不能證明真實Cloud Run eventual-consistency時間、gcloud schema或production rollout；需PR的hosted Python 3.10及另行批准的exact deployment驗證。
- Ready condition在timeout內持續非True時視為暫態並最終rollback；wrapper不解讀未核准的application log或condition message。
- IAM仍在rollout convergence後查一次；若IAM control-plane本身也有短暫延遲會fail closed並rollback，本任務未擴張IAM polling。
- TASK-033尚無PR工作包授權，不得push／PR／merge。後續production source必須使用merge後新exact commit，不能沿用`53fbd061...`。
