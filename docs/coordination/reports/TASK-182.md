# TASK-182 本機工具穩定化

## Delta / diagnosis

- Black24.4.2 CLI的bounded stack停在cache暫存檔建立；相同CLI使用隔離cache成功。
  runner為每次Black subprocess建立自動清理cache，不改全域ACL/cache、不換API、不失敗後重試。
- 現有PowerShell helper修正empty argument丟失並明確UTF-8 decoding；保留exit code/timeout判斷。
- quality失敗增加固定stage/source_mutation/next_action；format失敗明示可能已局部改檔，不推定runtime結果。
- Windows新增虛構process測試：empty/quote/space/Unicode、INFO stderr、exit7、timeout與mock serial0/1/many。
- 同一既有launcher test檔有少量Black正規化；未改既有測試語意。

## Evidence checkpoint

- 先重現cache isolation test與argument round-trip失敗，再修正；最初診斷CLI有5秒timeout，未宣稱成功。
- 修正後quality CLI format/check三個owned Python檔皆通過，不再需要API fallback。
- quality＋launcher suite沙箱執行82 tests：79 passed，3因PowerShell.Security模組載入失敗。
  相同suite重跑仍失敗；進一步定位Python child繼承的module搜尋路徑／大小寫重複環境鍵。
- harness固定Windows PowerShell child的內建Modules路徑，不改全域設定；新增bootstrap regression。
  修正後同一完整quality＋launcher suite 83 tests全部PASS（52秒，無skip），含原3項安全測試。
- `test_ci_*.py`：35 tests（34 passed，1既有本機Bash skip）；`quality check --working-tree`三檔真實CLI PASS；diff check PASS。
- 前 TASK-181 post-merge run 34075755442 已確認success。
- reviewer `/root/task181_review` lease1接受核心（21項独立測試PASS），lease2接受harness增量
  （bootstrap＋3項private fake tests全PASS）；Main已收到且接受completion，無blocking findings。
- hosted CI待本包單一ready PR；本次無runtime inventory、部署、DB、provider、signing／store操作。

## Limits

本次定位的是一種cache阻塞，不保證所有formatter timeout根因相同。cache建立/清理失敗仍報failure。
PowerShell helper caller的文字輸出須UTF-8或ASCII；未宣稱支援任意legacy code page。
沒有提供通用自動重試，未改既有one-shot approval／Secret處理；新版launcher不得重用舊exact approval。
此為pre-PR checkpoint；本branch的Git／PR為後續merge與required checks證據，不另開純狀態PR。
