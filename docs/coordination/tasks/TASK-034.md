# TASK-034：Promote Verified Web Portal Revision Under Pinned Traffic

狀態：`ready_for_codex`
優先級：P1 deployment blocker
規劃者：Work
執行者：Codex
Base commit：`96ee2a0d8fefce74b35b410069f0e1bafb405eeb`

## 1. 任務目標

修正Web Portal deployment wrapper在Cloud Run traffic已pin至舊revision時，只等待新revision自然取得100% traffic而永不收斂的問題。Wrapper應先等待並驗證新0% revision Ready與完整runtime contract，再以exact revision name顯式切100% traffic，最後bounded poll traffic收斂後執行IAM與HTTP checks；任一步失敗仍只rollback至Owner批准的exact revision。

## 2. 已確認production證據

- TASK-033 merge commit `96ee2a0...`部署產生`web-portal-00031-zvr`，revision Ready且image digest存在。
- 部署前與本機外層timeout後，traffic都維持`web-portal-00027-fwf=100%`；新revision為0%。
- Wrapper等待約10分鐘仍未收斂；本機外層時限先中止程序，temporary env已精確清理。
- `apps/web_portal/cloudbuild.yaml`沒有`--no-traffic`，但service已明確pin revision traffic；此狀態下Cloud Run deploy保留既有traffic allocation。
- 現有wrapper只把`update-traffic`用於rollback，沒有把已驗證的新revisionpromote至100%。
- Production目前仍安全由Ready的`web-portal-00027-fwf`承接100% traffic；`00031-zvr`不得未經另行部署批准直接切流量。

## 3. 工作範圍

### 3.1 分離revision readiness與traffic convergence

- Phase A bounded poll只等待new revision name不同於baseline、revision Ready及完整approved runtime contract；不得要求traffic已指向new revision。
- Phase A完成前不得執行traffic mutation、IAM或HTTP。
- Digest、runtime identity、Secret／plain env classification或demo gate drift為hard failure；在切traffic前停止，且不得為「rollback」反而對既有healthy traffic做不必要mutation。

### 3.2 Exact traffic promotion

- Phase A成功後，執行單一argument-list、`shell=False`的Cloud Run `update-traffic`，target必須是剛驗證的exact new revision `=100`。
- Project、region、service固定；不得接受任意service／revision字串或tag。
- Promotion command失敗時，按既有授權模型將traffic明確確認／回復至exact rollback revision，並安全回報`traffic_promotion`stage。
- 不刪除舊／新revision或image。

### 3.3 Traffic convergence與後續驗證

- Phase B以可注入clock／sleeper／timeout bounded poll等待service traffic明確為exact new revision 100%。
- 收斂前不得查IAM或HTTP；timeout或錯誤即rollback。
- 收斂後維持既有public IAM一次查驗，以及`GET /`和`GET /demo/`各一次、無redirect／無body。
- Safe stages至少區分`build`、`revision_convergence`、`traffic_promotion`、`traffic_convergence`、`iam`、`http`、`rollback`。

### 3.4 Offline regression tests

- Pinned old traffic＋new revision Ready：驗證contract後exact promotion一次，traffic數次舊值後收斂成功。
- New revision未Ready或hard contract drift：promotion完全不執行，HTTP／IAM不執行。
- Promotion command失敗、traffic timeout、IAM failure、HTTP failure：exact rollback一次並stage正確。
- 若traffic在promotion前本來就意外指向new revision 100%，不得重複promotion；仍須驗證contract與後續流程。
- Rollback failure與original stage可區分，不洩漏command output、env、Secret或body。
- Temporary env在所有路徑清理；Windows `gcloud.cmd`、POSIX與scheduled-service tests保持通過。

## 4. 非目標與禁止事項

- 不執行wrapper `--execute`、gcloud、HTTP、Cloud Build、Cloud Run或logs。
- 不部署、不切traffic、不rollback、不刪除revision／image。
- 不直接使用production既有`web-portal-00031-zvr`。
- 不修改Web Portal application、LINE Login、cookie、shared models、schema或production data。
- 不讀取env value、Secret payload、LINE code/state、cookie、URL query或個資。
- 不修改Secret、IAM、LINE Console、callback或Scheduler。
- 不使用shell command string、`shell=True`或第三方dependency。

## 5. 驗證命令與驗收

```powershell
python -m unittest discover -s tools/tests -v
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q tools apps/web_portal
python tools/deploy_web_portal.py
git diff --check
git status --short
```

- 所有cloud／HTTP都必須fake/mock，dry-run不得呼叫外部服務。
- Python 3.10相容。
- Report明確區分已確認pinned-traffic事實與未驗證的下次production結果。

## 6. PR工作包授權

Owner已批准TASK-034與PR工作包：允許建立／切換branch、修改wrapper／tests／文件、建立描述性commit、push、建立Draft PR、唯讀監看CI並在同一PR更新驗收證據。仍不包含merge、production deployment／traffic mutation、gcloud／HTTP、Secret／IAM／DB／schema／LINE或通知。

Merge後production rollout仍須Owner以新的exact main commit、target與rollback revision另行批准。
