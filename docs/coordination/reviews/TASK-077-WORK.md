# TASK-077 Work review

## 驗收結論

結論：`accepted_pending_hosted_ci`

Work 已查驗 branch `codex/phase-c-activation-freeze`、implementation commit
`d02e0a31e2ac44491fa81bc9d07db38f511a7099`、completion commit
`0093875b5c97aee2a77b953af8b6e77c49d03d2e`、實際 diff、Codex report與本機測試。
freeze runtime、三服務副作用邊界與離線transition controller整體方向正確。首次驗收發現的CI change classifier
blocking finding已由`9d46aa3357734e2c5853a613ccfd860d5a16cb8e`修正並通過第二輪驗證；待唯一ready PR的
hosted Python 3.10 final gate成功後可依standing Git授權squash merge。

## Blocking finding

### CI會漏跑共用runtime的三個直接consumer suites

`tools/ci_change_classifier.py`目前將
`shared_lib/shared_module/portal_data/runtime.py`單獨分類為`deployment_tools`。因此未來若只修改共用Phase C／freeze
runtime，CI只會跑deployment tools，不會跑Web Portal、LINE webhook與notify cron；這三個服務卻都直接import並依賴
該runtime。現有classifier test還把這個漏測行為固定成預期值。

Codex需做最小修正：

- 讓`runtime.py`單獨變更時同時選取`deployment_tools`、`web_portal`、`line_webhook`、`notify_cron`。
- 維持不選取`portal_data`，避免本任務無schema／model／SQL變更卻觸發PostgreSQL matrix。
- 新增精準regression test，分別證明runtime單檔的多scope結果，以及controller／preflight等純部署工具仍只選
  `deployment_tools`。
- 不擴張至workflow重寫或其他服務。

修正結果：以上四項均已完成。`runtime.py`單檔目前選取`deployment_tools`、`web_portal`、`line_webhook`及
`notify_cron`，不選取`portal_data`；controller／preflight仍只選`deployment_tools`。

## Work獨立驗證

使用Codex Desktop bundled Python執行：

```text
python -m unittest \
  tools.tests.test_ci_change_classifier \
  tools.tests.test_deploy_phase_c_runtime \
  tools.tests.test_deploy_phase_c_transition_controller -v
```

首次結果：32／32通過；同時確認原有測試確實把`runtime.py`誤分類為僅`deployment_tools`。

修正後重跑同一命令：33／33通過。另查驗`0093875..0a95cec`實際diff只包含classifier、regression tests、Codex
report與handoff；`git diff --check 43eb67c..HEAD`通過。

## 邊界

- 本輪沒有部署、production flags／traffic／database mutation、Scheduler、Secret／IAM、production invoke或通知。
- Hosted Python 3.10與final gate留待唯一ready PR補證據。
- 接受結論不包含deployment或production runtime flag啟用；後續仍須TASK-078／079各自的精確操作包與Owner部署批准。
