# Agent 本機環境與已知陷阱

本文件記錄這個 repository 在 Windows／Codex workspace 已反覆遇到的環境限制。它不是 production runbook，也不
授權任何外部操作。

## 1. 基本原則

- 先執行 `git status --short`、`git branch --show-current`、`git rev-parse HEAD`。
- 既有變更屬於使用者或另一角色；不覆寫、不回復、不順手納入。
- 不在 `main`／default branch 建立工作 commit。
- 不手動把短 SHA 補成完整 SHA；一律由 Git 讀取。
- Tool 被取消、網路中斷或 timeout 後，先查本機與外部實際狀態，再決定是否重試。

## 2. PowerShell 與文字編碼

- PowerShell 讀取中文 Markdown 使用 `Get-Content -Encoding UTF8`；省略 encoding 曾造成 mojibake，不能把亂碼
  當成檔案內容損壞。
- 搜尋優先使用 `rg`／`rg --files`。
- 編輯使用 patch；bulk mechanical move／format 後必須重新檢查 diff。
- Windows checkout 可能使用 CRLF。不要因 Git 的 LF→CRLF warning 自動重寫無關檔案。

## 3. Python 版本與命令

- 專案正式相容基準是 Python 3.10。
- 這台 workspace 不保證有全域 `python`／`python3`；不要先失敗一次才尋找 runtime。
- 優先使用 workspace 提供的 dependency loader／bundled runtime。已知 bundled runtime 可能是 Python 3.12，適合
  本機工具與離線測試，但不能取代 hosted Python 3.10 相容性證據。
- Production operator 若在 checksummed launcher／runbook 中鎖定 exact Python 路徑與版本，必須照該 artifact，
  不得用一般本機慣例替換。

## 4. Make、shell 與 Black

- Makefiles 使用 `python3`、`sh`、`cp`、`rm`、`grep` 等 Unix 工具；純 Windows 環境缺少它們時，依 runbook 使用
  等價 Python unittest／tool command，不為跑測試修改 Makefile。
- 因 Windows 缺少 Unix make／sh 而設計性 skip，不等於產品測試失敗；交付時要明確標記。
- Python quality 工具固定由 `requirements-quality.txt` 安裝，版本與 `pyproject.toml` 的 Python 3.10／Black／isort
  設定由 repository 管理。不要另行全域安裝或從網路動態選版本。
- `python -m tools.repository_quality check --paths path/to/file.py` 會依序、逐檔、以 bounded timeout 執行 pinned
  isort／Black check；不使用 shell，也不回顯 formatter diff／source。`format --paths ...` 才會寫檔。
- CI 使用 classifier 已解析的 exact base/head SHA 與 `--git-diff`，以 NUL-delimited Git paths涵蓋每個新增／修改的
  `.py`，deleted path明確排除。任一路徑缺失、不安全或非 `.py` 的 explicit selection都會 fail closed。
- `make quality`／`make format` 會逐檔處理全部 tracked Python；新建但尚未納入 Git 的檔案應用 `--paths` 明確選取。
- Bundled Windows Python 的 broad／multi-file Black CLI 可能持續高 CPU 停滯；repository runner會逐檔終止 timeout
  process並繼續回報其他 selected files。終止舊 command 後仍須確認沒有殘留 process。

### Flutter 3.47／Dart 3.13 固定工具鏈

- Windows 不以 PATH 判定 Flutter 不可用。先執行
  `.\tools\Invoke-FlutterToolchain.ps1 status`；它只解析 TASK-113 核准的 Flutter 3.47／Dart 3.13 toolchain，不下載、
  安裝或修改全域 PATH。
- 若一般 `flutter` wrapper 在啟動前無輸出停滯，設定 `FLUTTER_ROOT` 後以該 root 的 Dart 執行
  `bin\cache\flutter_tools.snapshot`；repository入口為 `.\tools\Invoke-FlutterToolchain.ps1 flutter <args>`，dependency
  setup 使用 `.\tools\Invoke-FlutterToolchain.ps1 dart pub get --offline`。
- `dart format --output=none --set-exit-if-changed ...` 只檢查、不寫檔；需要套用格式時必須另執行 `dart format ...`，
  並只限 owned files。Hosted Flutter 3.47 是最終環境／build gate。

## 5. YAML 與 workflow

- Bundled runtime 過去沒有 PyYAML，環境也不保證有 `actionlint`。未實際使用 parser／actionlint 或 hosted GitHub
  parser前，不得宣稱 workflow YAML 已被解析接受。
- 不為單次純文件檢查臨時新增 production dependency。

## 6. Git、GitHub 與 clean-tree guard

- Push 前確認 exact origin。Sandbox 可能因 destination trust 拒絕 push；不要繞過，使用者確認 exact destination
  後再執行。
- 一個包含多個外部步驟的命令可能在被取消前已完成前半段，例如 branch 已 push、PR 已建立。再次執行前先用
  `git branch -vv`、`gh pr list`／`gh pr view` 查證。
- Checksummed production launcher 常要求 clean tree。若只有 Work 明確擁有的未追蹤文件阻擋，先確認精確路徑與
  暫存目標，使用 `try/finally` 暫移並還原；不得藏匿、刪除或廣泛移動未知變更。
- Commit 前再次確認 branch，避免把工作 commit 留在 local `main`。若誤建但尚未 push，先把 commit 保留到新
  branch，再讓 local `main` 指回 `origin/main`；不要用 destructive reset 丟失 commit。

## 7. gcloud、Cloud Build 與 Cloud Run

- Windows 可能有 `gcloud.cmd` 但未以 `gcloud` 出現在 PATH；使用 repository wrapper 的 executable resolution，
  不硬編碼或據此誤判本機沒有 Cloud SDK。
- 執行任何 cloud command 前核對 account、project `ntubtob-schedule-405614`、region `asia-east1` 與 target。
- Regional Cloud Build submit 使用 machine-readable output 時必須抑制 streamed logs；resume describe 必須帶精確
  region。沿用 repository wrapper，不另寫臨時 parser。
- Cloud Run revision Ready、latest-created、latest-ready 與 traffic 是不同狀態。等待 control-plane 收斂，且 pinned
  traffic 必須在候選 revision 驗證後顯式 promotion。
- Cloud Run metadata 的 Secret reference 已確認為 `valueFrom.secretKeyRef.{key,name}`；不要猜成
  `{secret,version}`，也不要 resolve 或輸出 Secret payload。

## 8. Docker、PostgreSQL 與 psql

- 空 PostgreSQL container 不包含 legacy `ntubtob` schema。Portal-data migration integration 應使用既有
  `tools.setup_portal_data_legacy` 虛構 baseline，不自行猜 production schema。
- 依 runbook 使用 pinned PostgreSQL image／digest；production-shaped operator 常要求 `--pull never`、read-only
  workspace mount、private env-file 與 `PGOPTIONS=default_transaction_read_only=on`。
- 互動式 psql 必須 `\pset pager off`。曾因 `--More--` 等待超過 idle-in-transaction timeout，server 自動 rollback
  並中斷連線。
- PostgreSQL 16 `\bind` payload 使用 runbook 指定的 bare psql variables，例如
  `\bind :admin_member_ids :mutation_request_id :recovery_request_id \g`；`:'value'` 會把 SQL literal quoting 帶入
  bind payload，可能造成 bigint／UUID cast 失敗。
- Production SQL Editor／psql 的 logging、RLS bypass、owner privilege 與 transaction read-only 必須依當次受控
  preflight，不從舊 transcript 推論。

## 9. Canonical checksum

- 新文字 artifact 使用 `python -m tools.artifact_digest digest --text PATH`：只將 CRLF 正規化為 LF後計算 SHA-256。
- Binary artifact 必須明確使用 `digest --binary PATH`，hash raw bytes；helper不從副檔名推論text／binary。
- 新 checksum manifest 可用 `python -m tools.artifact_digest parse-manifest PATH` 做ASCII、大小、entry數、lowercase
  SHA-256、safe relative name與duplicate檢查。`.sha256`及checksum-owned text classes固定LF。
- 本任務不遷移現有 production launcher／manifest／歷史 artifact；它們仍沿用原本受測試保護的 verifier，且不得以
  `Get-FileHash` 重產文字 checksum。APK及既有gcloud binary digest等raw-byte用途不改。
- Artifact、checksum、validator 或 runbook順序改變時，舊 production 批准必須 fail closed並重新驗收。

## 10. Production 不確定狀態

- Production 固定採 discovery → Owner 精確批准 → execute → post-check。
- 不把 read-only discovery 與 mutation 綁在同一次 Owner 看不到 count／target 的呼叫中。
- Mutation 中斷、連線消失或輸出不完整時不得重跑；先用獨立 read-only recovery diagnostic 判定 zero／applied／
  ambiguous。
- 自然流量低時，不用固定等待時間假裝有 observation 證據；改用 revision／traffic／flag、健康檢查、去識別化
  error classification與下一次自然排程結果。

## 11. 專案特定語意提醒

- Production admin authority 目前來自 `WEB_PORTAL_ADMIN_MEMBER_IDS` runtime allowlist，不是 Person role。
- 已棄用的是 LINE Notify API 與 legacy `line_notify_tokens`；LINE Official Account／Messaging API、LINE Login／
  webhook 與 Discord 仍是不同能力，caller、credential 與副作用邊界必須分開查證。
- Identity maintenance flag 目前仍為 false；Phase C 完成不代表所有 pending identity 管理操作已開放。
- 歷史 Phase C 文件已封存，平常先讀 closeout 與 `PROJECT_STATE.md`，不要掃讀整個 archive。
