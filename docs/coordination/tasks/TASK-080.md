# TASK-080：notify cron Phase C feature-off production deployment

## 目標

將已通過 hosted CI 的 `main` commit
`d9213acea1708f051fc457753b3b941dbad305f6` 部署到 production
`notify-cronjob-service`，使其取得已合併的 Phase C compatibility／freeze 程式碼，但所有 Phase C 功能仍明確維持關閉。

這是一次 Cloud Run source deployment；不是 Phase C activation。不得部署其他服務或開啟任何功能旗標。

## 已確認事實

- `d9213ac` 是 TASK-079 的 squash merge commit；其 hosted CI 已成功，並將未來 deployment contract 固定為
  `CHANNEL_ACCESS_TOKEN:2`。
- production notify 的現行 serving revision 曾在 credential rotation 後更新為
  `notify-cronjob-service-00012-gfm`，但它尚未取得 TASK-077 的 feature-off application source。此值只能作為
  準備時的候選 rollback baseline；執行前必須用唯讀 Cloud Run metadata 重新確認。
- Phase C schema 0004 已存在於 production；Phase C 與 rollout-freeze runtime flags 的安全預設均為 `false`。
- notify 的 POST routes 可能觸發 Discord／LINE 通知；部署驗證不得人工呼叫 POST route 或 Scheduler。

## 請求 Owner 批准的精確範圍

若 Owner 接受本工作包，批准下列行為且僅限下列行為：

1. 以 `d9213acea1708f051fc457753b3b941dbad305f6` 建置並部署 production `notify-cronjob-service`。
2. 以唯讀 metadata 檢查部署身分／project／region、現行 serving revision／traffic、private IAM boundary、
   新 revision Ready、image digest、runtime Secret binding 名稱與版本，以及 Phase C／freeze flag 的非機密值。
3. 明確保留／設定：
   - `CHANNEL_ACCESS_TOKEN` 綁定 `CHANNEL_ACCESS_TOKEN:2`；
   - `PORTAL_DATA_PHASE_C_ENABLED=false`；
   - `PORTAL_DATA_ROLLOUT_FREEZE_ENABLED=false`。
4. 新 revision Ready 且所有 contract 驗證通過後，將 100% traffic 切至該新 revision。
5. 若 build、revision、digest、private boundary、secret binding、flag vector 或 traffic verification 任一失敗，將 100%
   traffic rollback 至執行前唯讀確認的 exact healthy revision；不自行重建舊 image。
6. 允許既有 Scheduler 在原排程自然呼叫新 revision；不人工 invoke、pause/resume 或修改 Scheduler。

## 明確不包含

- 不部署 Web Portal、LINE webhook、game broadcast 或 update-game-schedule。
- 不開啟 Phase C、freeze、identity maintenance 或其他 runtime flag。
- 不建立、讀取 payload、輪替、停用或刪除任何 Secret；只允許核對名稱／版本／binding metadata。
- 不修改 IAM、Scheduler、資料庫、schema、RLS、traffic policy 以外的資源設定，亦不做 Cloud Run POST smoke test。
- 不發送人工 LINE／Discord 通知、不連 production DB、不執行 DDL/DML。

## 執行前停止條件

任一情況立即停止，不 build/deploy：

- `main` HEAD 不是指定 full SHA，或工作樹不乾淨。
- gcloud account、project `ntubtob-schedule-405614`、region `asia-east1` 或 target service 不精確吻合。
- 無法確認現行 100% serving／healthy rollback revision。
- 新／現有 runtime binding 不為 `CHANNEL_ACCESS_TOKEN:2`，或 flag 非明確 `false`。
- service 不再是 private、runtime／build context 出現 secret plaintext，或 metadata 輸出範圍無法安全限制。

## 驗證與完成條件

- deployment wrapper 的 clean checkout／approved SHA／temporary env cleanup contract 生效。
- Cloud Build 成功、新 image digest 與新 revision digest 一致、新 revision Ready、且新 revision承接 100% traffic。
- runtime metadata 證明 service 維持 private、LINE token binding 為 version 2、兩個 feature flags 為 false。
- 不做 endpoint invoke；只查 startup／近期 error logs 與 control-plane metadata，且不記錄 env values、token 或個資。
- 失敗時的 rollback command、實際 revision、traffic 結果及未驗證線上業務流程寫入 deployment report。

## 授權後的執行入口

以 Windows configured Python 執行：

```powershell
python tools/deploy_scheduled_service.py notify-cronjob-service --execute `
  --approved-commit d9213acea1708f051fc457753b3b941dbad305f6 `
  --rollback-revision <EXECUTION_TIME_EXACT_HEALTHY_REVISION>
```

其中 rollback revision 必須是執行前唯讀盤點所得，不能預先猜測。執行前的 runtime non-secret flag metadata 應由 Owner
維護的 non-secret env source 提供；若缺少任一 required false key，依本 task 停止。

## 狀態與下一步

本文件只建立部署工作包，尚未取得本次 production deployment 明確批准。等待 Owner 以本文件的 six-point scope
批准後，Work 才可執行。
