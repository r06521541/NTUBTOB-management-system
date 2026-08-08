# TASK-078：準備 Phase C feature-off production deployment 工作包

## 任務目標

以已合併的TASK-077 commit `1838ec6fc77a74e23700f9cd29b8ea910c0a29fb`為唯一source，為Web Portal、LINE
webhook與notify cron建立可重現的feature-off production deployment工作包。三個新revision部署後仍必須保持Phase C、
rollout freeze及identity maintenance關閉；本task先完成artifact、現況盤點、精確命令、驗證與rollback證據，交由
Owner批准後才可真正部署。

## Owner授權與停止點

- Owner已要求修訂Windows Black規範並直接繼續下一個task；一般Git／PR工作可依standing authorization自行處理。
- 本階段允許repository／local-only操作，以及對既有GCP資源執行唯讀`gcloud ... describe`／`list`取得服務、revision、
  traffic、runtime env key存在性與Scheduler target metadata；不得顯示任何secret value。
- 本階段不授權Cloud Build、image build／push、deploy、revision建立、traffic或env mutation、production endpoint invoke、
  Scheduler pause／resume／run、Secret／IAM、DB、LINE／Discord通知。
- 工作包完成後HANDOFF必須為`awaiting_owner_approval / owner`。未取得Owner對exact source commit、三個target、
  current／rollback revisions、artifact fingerprints、flags與rollback traffic mutation的明確批准，不得進入部署。

## Base與目標

- Base／source commit：`1838ec6fc77a74e23700f9cd29b8ea910c0a29fb`
- GCP project／region必須從現有deployment設定與目前CLI唯讀查驗交叉確認，不可只沿用記憶。
- Targets：Cloud Run Web Portal、Cloud Functions Gen2 LINE webhook、Cloud Run notify cron。
- `game_broadcast_service`與`update_game_schedule`不是本task target。

## 必做工作

### 1. Source與artifact鎖定

- 確認branch source與merged commit一致，工作樹既有變更分流保留。
- 依TASK-077 runbook重建shared sdist，將同一exact artifact放入三個deployment contexts。
- 執行三份offline artifact／build-context preflight，記錄shared source fingerprint、各artifact SHA-256、requirements與
  sensitive-file exclusions。
- 不執行Cloud Build或container image build。

### 2. Production唯讀現況盤點

- 確認目前gcloud account、project與region；只在目標明確吻合時繼續唯讀查驗。
- 記錄三個target目前Ready revision／function、traffic vector、image／source metadata、runtime、ingress與authentication
  classification。
- 只記錄下列非機密env keys的存在與exact非機密值，不得輸出其他env或secret values：
  `PORTAL_DATA_PHASE_C_ENABLED`、`PORTAL_DATA_ROLLOUT_FREEZE_ENABLED`，以及僅Web Portal使用的
  `WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED`。
- 查明notify相關Scheduler job的target與啟用狀態，只讀不改；LINE webhook不做production invoke。
- 若任何target、project、region、revision、traffic或flag無法確定，停止並列為blocking finding。

### 3. Feature-off部署命令與env preservation

- 產生精確但不執行的三服務build／deploy命令，所有source都鎖定本task commit與artifact fingerprints。
- 證明deployment wrapper不會刪除未列出的runtime env／Secret bindings；明確設定或保存三個新旗標為`false`。
- 不得把真實secret寫入命令、文件、log或build context。
- 對Gen2 function說明可重現的rollback方式；若rollback target無法精確重建，不得假稱已具備rollback。

### 4. 驗證、觀察與rollback計畫

- 為每個target列出部署後唯讀驗證：Ready、traffic、revision env key classification、IAM／ingress未退化、error logs。
- Web Portal可規劃安全GET smoke；notify／webhook不得人工invoke具副作用endpoint。
- 設定明確停止條件與rollback順序；任一服務失敗時不得前進到下一服務。
- Rollback只回復artifact／revision與100% traffic；不得降schema 0004、變更Secret／IAM／Scheduler或清理production data。
- 工作包需明確說明部署完成仍是all Phase C off／all freeze off，不等於Phase C activation。

## 必要驗證

- TASK-077三份artifact／build-context offline preflight。
- Deployment wrapper完整dry-run／contract tests。
- Transition controller以production盤點vector驗證起點必須是合法all-off／unfrozen；資料不足時fail closed。
- 受影響deployment tools tests、`compileall`、isort（若Python有變更）、Windows Black formatter API（僅Python變更檔）、
  `git diff --check`與`git status --short`。
- 本task若只有文件、artifact與既有工具輸出，不另建PR或觸發hosted CI；若實際修改可執行deployment code／workflow，
  才依變更範圍建立唯一ready PR。

## 交付成果

- `docs/operations/deployments/PHASE_C_FEATURE_OFF_1838EC6.md`：精確部署工作包與去機密唯讀證據。
- `docs/coordination/reports/TASK-078-CODEX.md`：實際命令、結果、限制與變更檔案。
- 更新`HANDOFF.yaml`為`awaiting_owner_approval / owner`；工作包不得自行執行。

## 完成定義

- 三個target、current／rollback revisions、traffic、non-secret flag vector與artifact fingerprints均可重現。
- 三份部署命令與驗證／rollback命令經dry-run或靜態contract驗證，但沒有被執行。
- 工作包不含secret、不讀production data、不invoke服務、不改任何external state。
- Work能依實際repository與唯讀production evidence驗收，Owner能用一段精確批准文字授權或拒絕部署。
