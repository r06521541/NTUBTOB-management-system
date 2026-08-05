# TASK-033：Wait for Web Portal Rollout Convergence Before Verification

狀態：`ready_for_codex`
優先級：P1 deployment reliability
規劃者：Work
執行者：Codex
Base commit：`53fbd0617aca241107c64cd72907f6da905fdd73`

## 1. 任務目標

修正Web Portal deployment wrapper在Cloud Build成功後只讀一次Cloud Run service／revision，可能因control-plane尚未收斂而誤判失敗並rollback的問題。Wrapper應以有時限、可測試的polling等待new revision、Ready、approved digest與100% traffic一致後，才執行IAM與HTTP smoke checks；真正錯誤或timeout仍fail closed並rollback。

## 2. Production證據

- TASK-032 merge commit `53fbd0617aca241107c64cd72907f6da905fdd73`部署產生`web-portal-00030-jmg`。
- Wrapper回報`Deployment verification failed; rollback succeeded`，production已回到Ready的`web-portal-00027-fwf=100%`。
- Rollback後欄位白名單查驗確認`00030-jmg`：Ready=True、digest符合approved image、runtime identity與三個Secret references正確、必要plain env keys存在、demo env缺席、public invoker存在。
- 唯一revision最近15分鐘request metadata為0筆，證明wrapper在`GET /`與`GET /demo/`之前失敗。
- 現有code在Cloud Build success後只各describe service/revision一次，沒有rollout convergence polling，且對外只保留generic failure訊息。
- 以上支持「control-plane短暫未收斂」為最合理推論，但沒有直接證據能指出當下是revision、traffic或其他欄位；不得寫成已確診。

## 3. 工作範圍

### 3.1 Bounded rollout convergence polling

- 新增可獨立測試的poll helper，反覆以欄位既有安全command取得service與new revision狀態。
- Polling應等待：
  - `latestCreatedRevisionName`出現且不同於baseline；
  - new revision Ready；
  - image digest等於approved digest；
  - runtime identity、Secret classifications、必要plain keys與demo gate contract正確；
  - service traffic明確為new revision 100%。
- timeout、interval、clock與sleeper須可注入；不得busy loop或無限等待。
- 尚未出現new revision、Ready尚未收斂或traffic仍舊值可視為transient並重試。
- 明確的security/config drift（錯誤digest、identity、Secret classification、demo gate出現、public boundary缺失）不得被無限重試掩蓋；應安全停止並rollback。
- Polling完成前不得執行HTTP checks。

### 3.2 Safe failure stage

- 對外錯誤至少區分`build`、`rollout_convergence`、`iam`、`http`與`rollback`等安全stage，並保留rollback succeeded／failed差異。
- 可回報HTTP status code，但不得讀取或輸出response body、URL query、env value、Secret payload、cookie或authorization header。
- 不得把完整gcloud stderr／JSON直接包進最終錯誤。

### 3.3 Regression coverage

- service／revision連續數次回舊狀態後收斂：成功且不rollback。
- new revision延遲出現、Ready延遲與traffic延遲各有測試。
- convergence timeout：只rollback至exact approved revision。
- 明確digest／identity／Secret／demo drift：fail closed並rollback，不等到timeout掩蓋。
- IAM failure與HTTP非200／404：stage清楚、各HTTP endpoint最多一次、rollback正確。
- rollback failure仍與original stage分開回報。
- temporary env在成功、timeout、hard failure與exception皆清除。
- Windows `gcloud.cmd` resolution、POSIX與既有wrapper tests保持通過。

## 4. 非目標與禁止事項

- 不執行`--execute`、gcloud、HTTP、Cloud Build、Cloud Run、logs或production query。
- 不部署、不rollback、不切traffic、不刪除revision／image。
- 不修改Web Portal routes、cookie／LINE Login邏輯、shared library、schema或production data。
- 不讀取、顯示或複製env value、Secret、LINE code/state、cookie或個資。
- 不修改Secret、IAM、LINE Console、Scheduler或callback。
- 不新增第三方dependency，不使用shell command string或`shell=True`。
- 不push、不建立PR或merge，除非Owner另行批准TASK-033 PR工作包。

## 5. 驗收條件與命令

```powershell
python -m unittest discover -s tools/tests -v
python -m unittest discover -s apps/web_portal/tests -v
python -m compileall -q tools apps/web_portal
python tools/deploy_web_portal.py
git diff --check
git status --short
```

- 所有polling、gcloud與HTTP必須fake/mock，測試離線執行。
- Python 3.10相容，dry-run不得呼叫cloud或HTTP。
- Codex report列明production只提供「可能的eventual consistency」證據，不誇大為確診。
- PROJECT_STATE與HANDOFF依協作流程更新。

## 6. 部署後續

TASK-033 merge後，Work須以新的main commit重新建立exact deployment source與再次確認rollback revision。不得直接重跑`53fbd061...`，也不得因新revision`00030-jmg`為Ready就未經批准切回其traffic。
