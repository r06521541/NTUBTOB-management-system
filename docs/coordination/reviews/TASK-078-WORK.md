# TASK-078 Work review

## 驗收結論

結論：`accepted_local_package_pending_production_inventory`

Work已查驗branch `codex/phase-c-feature-off-deployment`、implementation commit
`b925d392b25fb4b8499c334cb427a77a076825fa`、completion commit
`763f113d5b319c3b3b717b2608565aa74d1bc5c7`、修正commit
`d5e9bb494e2946f481180bc8bba6dce1609fe88d`、實際diff、Codex report與部署工作包。本機artifact、離線
deployment tooling與Gen2 rollback boundary均可接受；尚缺fresh production inventory，因此本結論不構成部署批准。

## Blocking finding

Repository既有`docs/operations/GEN2_FUNCTION_ROLLBACK.md`已定義Cloud Functions Gen2以immutable GCS source
generation及官方Functions v2 PATCH回復`buildConfig.source`的受支援路徑。TASK-078工作包未沿用該runbook：

- 唯讀`gcloud functions describe`沒有取得`buildConfig.source.storageSource`的bucket／object／generation。
- `LINE_WEBHOOK_ROLLBACK_REVISION`以revision稱呼，與Gen2實際source-generation recovery model不一致。
- rollback命令仍是`<APPROVED_GEN2_ROLLBACK_COMMAND>`，因此Owner目前沒有exact rollback target或可審核的request shape。

Codex需做最小文件補正：

- 將LINE webhook rollback欄位改為exact immutable source bucket／object／generation與必要的current function metadata。
- 以既有Gen2 rollback runbook為唯一方法，加入針對`line-webhook-handler`的prepared-but-not-executed v2 PATCH request
  shape、field mask、pre-check與post-check；不得執行或宣稱已驗證production value。
- 唯讀inventory指令只輸出上述必要的非機密source metadata及既有service boundary，不可擴張輸出env／Secret。
- 將狀態交回`ready_for_review / work`；production inventory仍缺時，由Work驗收後再明確告知Owner要執行的最小唯讀步驟，
  不能提前標示為可批准部署。

修正結果：以上項目均已完成。LINE webhook現在以immutable GCS source bucket／object／generation作為rollback
identity，並沿用官方Functions v2 PATCH、`updateMask=buildConfig.source`、pre-check與post-check boundary；沒有填入
猜測production值，也沒有執行request。

## Work獨立驗證

- Deployment tooling指定suite：67／67通過。
- `git diff --check 1838ec6..HEAD`：通過。
- 工作樹在Work review前乾淨；本review與HANDOFF為Work-owned變更。
- 本機同樣沒有`gcloud`可執行檔，因此沒有production read、build、deploy或mutation。

修正後Work重跑相同deployment tooling suite：67／67通過；`git diff --check 1838ec6..HEAD`通過。

## 非阻擋限制

- Codex依新AGENTS規範未執行Windows Black CLI；本task沒有Python source變更，未格式化既有檔案是正確行為。
- Production revisions、traffic、flags、Scheduler與Gen2 source generation仍須fresh唯讀inventory，不能以歷史文件替代。
- Owner下一步僅需選擇已驗證身分的Cloud SDK或Cloud Shell執行工作包中的唯讀inventory；取得結果後仍須Work查驗並
  另產生exact deployment批准文字，不能直接執行prepared deployment commands。
