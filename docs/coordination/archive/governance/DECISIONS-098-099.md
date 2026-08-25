# DEC-098～099 歷史原文

本檔保存被 DEC-100 取代的原始決策，只證明當時的授權演進，不構成現行操作授權。現行規則以
`../../DECISIONS.md` 為準。

封存原因：DEC-098與DEC-099已於2026-08-25被DEC-100整併取代。

## DEC-098：隔離 staging fictional environment 採 agent autonomy

- 狀態：`active`
- 生效：2026-08-20
- 來源：Owner 對 TASK-113～118 實際 activation／Emulator 流程的檢討與明確長期授權
- Supersedes：DEC-096 中「staging deployment 一律另案逐步批准」的 staging fictional 部分；production promotion 仍保留
- 決策：在 project、database identity、cost ceiling、runtime service account、Secret references、public boundary 與 rollback
  已由 Owner 核准且持續一致時，Main Work 可自主完成 staging fictional build、candidate、traffic、data repair／test mutation、
  rollback、Emulator／ADB 驗收與 task-specific cleanup。一般低敏操作使用 `operator=agent`，不建立儀式性 Owner gate。
- Invariants：production、真實使用者／資料／通知、Secret payload、付費或公開權限擴張、release signing／store、資源／DB／
  Secret version 的不可逆刪除仍為 Owner gate。未知外部結果先唯讀 reconcile；unknown drift、identity mismatch 或安全邊界
  放寬立即停止。Domain Work 必須主動 heartbeat 並向 Main Work 交回，不得在自己的 session 靜默等待。
- Non-goals：不授權 production promotion、正式 schema／資料操作、LINE／Google／Apple Console policy、建立新付費資源、
  提高成本上限或刪除既有 cloud resource；也不允許 agent 代替 Owner 輸入帳密、掃碼或 consent。

## DEC-099：Checksummed staging target 與分層 agent autonomy

- 狀態：`active`
- 生效：2026-08-25
- 來源：Owner 對 Main Work 外部唯讀與隔離 staging 操作邊界的明確長期授權
- Supersedes：無；補充 DEC-098 的 target resolution 與操作分層
- 決策：Repository 中通過既有 verifier 的 checksummed staging artifact 所指向之 project、region、service、revision
  與 resource alias，視為既有核准的 isolated fictional staging target。即使其 project 不同於本機 default config，
  Main Work 仍可用每個命令顯式 target 執行 sanitized `list/get/describe`，不得因此切換預設帳號或修改 gcloud config。
- Repository autonomy：Work／Codex可依 DEC-076 完成 branch、commit、push、PR、CI與merge；一般 coordination payload
  的 repository push 已獲 Owner 明確授權，仍不得提交 Secret、credential或受限制的 provider identifier。
- Read-only autonomy：可查 Cloud Run revision／traffic／runtime key存在性、Secret reference metadata與version存在性、
  IAM結構、OAuth client類型／callback匹配狀態、build／health／audit metadata。輸出只保留
  `confirmed／missing／inconsistent／blocked` 或布林值；不得輸出account、client ID、callback值、Secret名稱、
  fingerprint、IAM member identity或Secret payload。
- Reversible staging autonomy：確認 exact target、runtime identity、cost ceiling、public boundary與rollback一致後，agent
  可在既有工具邊界內建立無traffic candidate、執行health check及可復原rollback，並沿用既有Secret references；
  未知結果先唯讀reconcile，不得盲目重送。
- Owner gates：OAuth client建立／刪除、callback修改、Secret payload／version建立或輪替、IAM binding、public access、
  runtime identity、traffic promotion、signing、帳密／登入／consent、store、production、真實資料／通知、新付費資源與
  不可逆刪除仍需精確逐案批准。Main Work應先提供一次完整批准包，不為同一已核准原子操作逐命令重問。
- Stop conditions：artifact verifier失敗、target無法唯一解析、active identity或cost／public／rollback boundary漂移、
  network/auth failure、輸出無法安全去識別、外部結果不確定或需要任何未核准mutation時立即停止。
