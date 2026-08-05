# TASK-019 Work Review

日期：2026-08-05
結論：`changes_requested`
Branch：`codex/immutable-scheduled-service-deployments`
驗收HEAD：`f10e7b8602e7ebf388faf6e38ceeaea21de6acb0`
Draft PR：[#33](https://github.com/r06521541/NTUBTOB-management-system/pull/33)

## 已通過項目

- Working tree乾淨；PR open／draft／mergeable。
- Final Python 3.10.20 CI run `30980415328`成功。
- Work以bundled Python重跑：game broadcast 28/28、notify cron 9/9、wrapper 7/7，compile及`git diff --check`通過。
- 兩個scheduled services的Cloud Build與legacy Make target已使用Git SHA `_IMAGE_TAG`，不再使用固定`:tag1`。
- Wrapper預設preflight不呼叫gcloud，service白名單、exact SHA／rollback revision與temporary env gate已存在。
- Web Portal、shared library source、schema、Secret／IAM／Scheduler及其他服務未修改；沒有production操作。

## Blocking Findings

### 1. 可能把部署前既有stale revision誤認為本次new revision

Wrapper沒有在Cloud Build前記錄`latestCreatedRevisionName`。Build後只檢查revision不等於rollback revision；若production如TASK-018當時為rollback `00030`、stale latest `00031`，而deploy再次no-op，wrapper會接受舊`00031`並可能將100% traffic切過去。這正是TASK-019必須防止的實際事故型態。

必須在build前取得baseline latest created revision，build後要求new revision與baseline不同；新增rollback revision與baseline latest不同、deploy no-op的回歸測試，確認不會切traffic並明確失敗／安全rollback。

### 2. Revision digest未與本次immutable tag產物建立關聯

目前只確認revision有任意`sha256:`，沒有查得本次approved SHA tag的Artifact Registry digest並比較。若同時間有其他deployment改變latest revision，wrapper可能驗證並導流至不屬於approved commit的image。

必須取得本次`${service image}:${approved_commit}`對應digest，並與new revision的`status.imageDigest`精確比較；新增digest mismatch測試且不得導流。

### 3. 前置空白的敏感env key不會被過濾

`parse_env_key()`遇到任何leading whitespace直接回傳`None`。Work已重現`parse_env_key("  CHANNEL_ACCESS_TOKEN: fake")`結果為`None`，因此該行會原樣寫入temporary env。既有Make grep明確允許前置空白，wrapper也必須同等fail safe。

必須安全辨識／排除具前置空白的top-level敏感key，並加入fixture secret不可出現在destination或command／error output的測試。

### 4. Clean checkout可能因不存在`shared_lib/dist`而在build前失敗

`preflight()`在approved commit存在時要求artifact parent已存在，但`execute_deployment()`本來就會先執行`setup.py sdist --dist-dir dist`建立它。Clean clone通常不保證ignored `dist/`存在；目前測試在setUp預建該目錄而遮蔽此問題。

應移除此不必要前置條件，並新增dist目錄不存在時仍能由fake build產生artifact的測試。

## 必要補測

- Stale latest revision／deploy no-op不得被誤判成功。
- Approved image tag digest與revision digest mismatch時停止且不導流。
- Traffic command失敗與驗證失敗均清理temporary env，並只rollback至exact approved revision。
- 前置空白secret keys全部排除。
- Clean checkout缺少shared library dist目錄仍可進入build流程。

## 安全邊界

補正只能使用offline fake runner與CI；不得執行wrapper `--execute`、gcloud、deployment、production存取、通知或merge。

## 下一步

交回Codex在同一Draft PR #33補正。完成後更新Codex report、最終CI證據與HANDOFF為`ready_for_review / work`，再由Work重新驗收。

## 第二輪驗收（HEAD `75eaf9a`）

第一輪四項finding均已補正，Work重跑wrapper 11/11、game 28/28、notify 9/9、compile與diff check皆通過；final Python 3.10 CI run `30981527045`亦成功。但以TASK-018實際Cloud Run metadata形狀比對後，仍有兩項blocking production-shape落差：

### 5. Pinned-traffic new revision會被錯誤判定not ready

Wrapper在切traffic前要求service `latestReadyRevisionName == latestCreatedRevisionName`。TASK-018實際證據顯示：新`00033-mdp`在0% traffic時，revision自身`Ready=True`／Retired，但service `latestReadyRevisionName`仍是舊`00031-s65`；只有切traffic後latest ready才更新。現有wrapper會在這個預期的pinned-traffic情境先rollback，無法完成其核心目標。

應改為在切traffic前查驗new revision本身的Ready condition與digest；切traffic後再驗證service latest ready／traffic。Fake runner必須模擬pre-traffic service latest ready仍為baseline、revision Ready=True，並證明流程能安全完成。

### 6. 真實Cloud Run imageDigest格式不相容

Wrapper要求revision `status.imageDigest`以`sha256:`開頭；TASK-017／018實際metadata為完整`registry/path/image@sha256:...`。現有wrapper會對健康revision回報缺少digest。

應安全normalize bare digest與full image reference的digest suffix，再與Artifact Registry approved tag digest精確比較；測試至少涵蓋真實full-reference格式及mismatch。

補正仍限offline fake runner與CI，禁止execute、gcloud、production或merge。完成後再交回Work第三輪驗收。
