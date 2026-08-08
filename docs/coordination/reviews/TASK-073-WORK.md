# TASK-073 Work production migration review

## 結論

結果：`accepted`

2026-08-08 production Phase C schema migration已依批准範圍從
`0003_legacy_bigint_activity_game`一次transaction升級為`0004_phase_c_identity_lifecycle`。Fresh inventory、
strict post-check及pair comparison皆通過；結果為`pass`。本結論只關閉schema migration，不代表application
deployment、runtime flag enablement或identity maintenance activation。

## 鎖定證據

- Reviewed source commit：`5a63a0c77e2725c828b17b784680b90a6cffb03f`
- Inventory SHA-256：`9dc3d2e589ca298e40a9bf529d5801e6b7081016547996bbd5010df7adae2d46`
- Migration SHA-256：`67ea4490a1e3459221f440ae280e95f3be5a868ad2c37c78ae3519073e7d1f91`
- Post-check SHA-256：`6de46c7c46c5ea1dd75e0172a1369368c3d3d4ec7f1ddf8077afe4bcec613166`
- Inventory export：2026-08-08 14:36 Asia/Taipei
- Post-check export：2026-08-08 14:50 Asia/Taipei
- CSV為repository外的sanitized evidence，不提交repository。

## Pre-check

- 51列固定六欄CSV通過strict inventory validation。
- Revision為`0003_legacy_bigint_activity_game`。
- 38個required gates全通過。
- Phase C table與column collisions皆為0。
- Session不是superuser；`BYPASSRLS=true`由Owner另行明確接受本次bounded transaction風險。
- 既有production logical backup及isolated restore rehearsal證據仍保留。

## Migration與post-check

- Owner回報完整migration SQL第一步成功；未回報timeout、SQL error或ambiguous connection outcome。
- Post-check 55列、44個required gates通過。
- Revision為`0004_phase_c_identity_lifecycle`。
- 精確Phase C fingerprints：2 tables、19 columns、15 constraints、3 indexes。
- `python -m tools.portal_data_phase_c_readiness validate --kind postcheck <csv>`：passed。
- `python -m tools.portal_data_phase_c_readiness compare <inventory.csv> <postcheck.csv>`：`pass`。
- 10個compare metrics在migration前後一致。

## 保留邊界

- `PORTAL_DATA_PHASE_C_ENABLED`與identity maintenance仍保持關閉。
- 尚未部署Web Portal、LINE webhook、notify cron或其他服務。
- 尚未修改Secret、IAM、Scheduler、RLS policies、grants或API exposure。
- 不執行downgrade、drop、cleanup、restore或額外production SQL。
- 下一步必須另立application rollout與feature activation task，並由Owner另行批准production deployment。
