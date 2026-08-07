# TASK-065 Work 驗收

## 結論

`accepted`。Phase B repository-only工作包已將永久Member、LINE identity與`team_player`資格分離，並以
去識別化inventory、inventory-bound deterministic backfill、post-check及本機PostgreSQL演練固定安全邊界。
本驗收不授權或執行production inventory、DML/backfill、rollback、Phase C或deployment。

## 實際查驗

- Branch／HEAD：`main`／`04a10787d500793a43a41d93e902b2a41f64fcc6`（implementation head；其後僅handoff）。
- 實際檢查base `26c228a`後所有implementation、修正commit、SQL artifacts、checksums、tests、report與handoff。
- Work第一輪發現required integer非零仍通過、Phase A boundary與approved inventory binding不足，退回修正。
- Work第二輪以partial mapping、wrong revision及nonzero precondition直接重現public renderer bypass，退回修正。
- 最終負測中，相同partial/wrong mapping由`render_backfill`以`PhaseBEvidenceError`拒絕。
- `git diff --check d33a42a..e020897`：通過。
- `python -m tools.portal_data_phase_b verify`：通過。
- `python -m compileall -q shared_lib tools tests/portal_data`：通過。
- `python -m unittest tests.portal_data.test_phase_b_artifacts.PhaseBArtifactStaticTests -v`：6/6通過。
- local-only PostgreSQL 16：`python -m unittest discover -s tests/portal_data -v`，121/121通過。
- PostgreSQL container/network於驗收後停止並移除；既有專用local volume保留。

第一次Work嘗試因sandbox無權存取Windows Docker named pipe，container未啟動且integration tests連線失敗；取得
本機Docker權限後以相同local-only fixture重跑，121/121通過。此為驗收環境限制，不是產品或測試失敗。

## 已確認行為

- 每位Member依primary key建立唯一`basic/inactive` Person，不以姓名或LINE display name合併。
- 只有non-ignored且已有可靠legacy Member FK的LINE rows建立linked identity；只有這些Member取得active
  `team_player`。
- 同一Member可有多個LINE accounts並形成多identity，但僅一個`team_player` qualification。
- Inventory固定revision、13 portal tables、13 RLS enabled、0 forced、0 policies、2 append-only triggers、
  zero portal application rows與legacy aggregate counts。
- Public renderer要求完整inventory schema並重套所有metric gates；partial、unknown、wrong revision與nonzero
  safety mapping均被拒絕。
- Rendered mutation在首次寫入前重驗approved counts、RLS/policy/trigger及identity/orphan boundary；漂移時
  transaction零寫入失敗。
- Post-check拒絕unexpected或relationship-inconsistent audits，並比對People、identity、qualification與audit
  expected counts。
- 相同batch可安全重跑；commit前以完整transaction rollback回到exact pre-state。

## Recovery限制

Phase A的audit tables為append-only。Backfill一旦commit，不得停用trigger或刪除audit來宣稱exact rollback；
正式execution task只能定義保留audit的forward compensation。Phase C開始後亦不得使用pre-commit rollback說法。

## 尚未執行

- 未執行production inventory SQL，沒有production CSV或fresh expected counts。
- 未連線或修改Supabase，未執行backfill／rollback／Phase C。
- 未讀Secret/env，未修改RLS policy、IAM、Scheduler或cloud resources，未部署或通知。

## 驗收判定

沒有blocking finding。TASK-065 repository-only範圍接受；下一步應先取得fresh sanitized production inventory，
再建立exact execution package並另向Owner取得production DML批准。
