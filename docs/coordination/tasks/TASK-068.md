# TASK-068：建立 Phase C identity drift detector與配對維護閘門

## 任務目標

在Phase B已commit、Phase C尚未接線的過渡期，防止Web Portal既有Member配對／ignore routes繼續只修改legacy
`line_users`而使Person／identity／qualification漂移；同時建立固定、去識別化、唯讀的identity reconciliation
inventory與strict validator。此任務不實作dual-write、不修改正式schema、不部署。

## 已確認現況

- Production已有197 People/member links、56 LINE identities、56 team_player及309 audits。
- Web Portal `POST /match-member/match`目前只呼叫`LineUser.update_member_id()`並各自commit。
- `POST /match-member/ignore`目前只呼叫`LineUser.update_as_ignored()`並各自commit。
- 現行管理頁只列`member_id IS NULL AND ignored=false`，沒有remap或unlink UI。
- 新LINE user仍可能由既有webhook新增為unlinked legacy row；這類row應被分類為pending candidate，不可被當成
  已損壞資料。
- 既有People為inactive；何時因登入轉active屬後續Phase C login task，本任務不得改變。
- ignored identity未核准映射為blocked或disabled，本任務不得替Owner決定。

## 使用者價值

- 在新舊模型過渡期間，避免管理員一次正常配對造成不可見資料漂移。
- 讓Work能以aggregate evidence區分正常pending／ignored candidates與真正不一致。
- 為後續transactional dual-write建立可測試的pre/post contract，而不急著切換production auth。

## 實作範圍

### A. Fail-closed maintenance guard

1. 建立集中設定，例如`WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED`，只接受明確安全boolean；缺少、空白、未知值
   一律視為false。
2. Production的Member match與ignore POST routes在guard為false時，必須在任何DB lookup／write及Discord通知前
   回傳固定503 maintenance response。
3. GET管理頁可繼續讓admin唯讀查看pending rows，但需清楚顯示維護暫停；表單按鈕disabled且不得形成可繞過
   server-side guard的假安全。
4. Demo mode不得因新env取得production route或DB能力。
5. 不讀取或修改真實`envs/**/.env.yaml`；只更新example／README key與安全預設。

本任務不部署，因此production在deployment前仍依人工freeze；不得宣稱guard已在線上生效。

### B. 去識別化 drift inventory與validator

建立checksummed read-only SQL artifact與strict validator，只輸出固定六欄boolean/count/revision，至少分類：

- Phase A revision、13 tables、RLS/policy/trigger boundary；
- Member/Person link完整性與People basic/inactive counts；
- reliable linked LINE rows與linked auth identities數量；
- 正常unlinked non-ignored pending candidates；
- 正常ignored legacy candidates（不自動建立identity）；
- missing identity、wrong Person link、identity without reliable legacy link；
- team_player missing／extra／revoked mismatch；
- duplicate provider subject、orphan Member link；
- unexpected/inconsistent access audit只作aggregate gate，不輸出request ID或row value。

Validator須固定每個metric的section/name/status/value field/gate，拒絕missing、extra、duplicate、reordered、型別錯誤、
非零unsafe counts及敏感值。Pending／ignored counts是資訊，不得因非零自動fail。

### C. Local reconciliation contract

以明顯虛構PostgreSQL fixtures覆蓋：

- Phase B exact consistent state；
- 新unlinked non-ignored LINE user被分類pending且整體仍safe；
- ignored legacy row被分類ignored且不自動產生blocked／disabled identity；
- legacy match後缺identity、identity指錯Person、qualification缺少／多餘、duplicate subject及orphan全部fail closed；
- guard關閉時match／ignore零DB lookup、零write、零Discord；guard開啟時保留目前legacy behavior，明確標記仍只供
  local compatibility test，不代表可部署啟用。

## 設計決策

- 本輪guard是過渡安全措施，不是長期feature flag；後續只有transactional dual-write通過並取得部署批准，才能
  決定是否開啟。
- 不把ignored自動變成blocked／disabled；不建立identity、不撤銷資格、不改People status。
- 不以姓名、nickname或display name比對。
- 不讓drift detector自動修資料；只輸出sanitized分類及stop decision。
- 不把production aggregate counts硬編碼為永久產品常數；若未來production execution使用，須另案fresh evidence。

## 非目標

- 不實作legacy／portal transactional dual-write、remap、unlink、ignore reconciliation或first-login activation。
- 不切換LINE login、session、role/capability或attendance讀取來源。
- 不修改schema、migration、RLS policy、grant、role、Secret、IAM、Scheduler或cloud resources。
- 不連線／查詢／寫入production，不部署、不通知、不人工invoke服務。
- 不修改其他apps/functions或順手重構legacy ORM。

## 驗收條件

1. Guard預設false且fail closed；match／ignore在任何副作用前回503，GET頁有一致maintenance UI。
2. 明確true才能進入既有route，錯誤／未知值不得fail open。
3. Checksummed read-only inventory及strict validator完全去識別化並通過local PostgreSQL fixtures。
4. Pending與ignored candidates正確分類，真正cross-model drift全部fail closed。
5. Python 3.10相容，外部請求皆mock；不需production DB／secret即可執行測試。
6. `git diff --check`、受影響Web Portal tests、portal_data tests、compile及artifact verifier通過。
7. Report明確說明guard尚未部署、production freeze仍有效、dual-write與activation仍待後續任務。

## 建議驗證命令

```powershell
python -m unittest discover -s apps/web_portal/tests -v
python -m unittest discover -s tests/portal_data -v
python -m compileall -q apps/web_portal shared_lib tools tests/portal_data
git diff --check
git status --short
```

PostgreSQL integration tests使用既有local-only Compose fixture，完成後停止container/network並保留既有專用volume。

## 停止條件

- 需要決定ignored映射、Person activation、remap/unlink或qualification撤銷政策。
- 需要直接修改production env、DB、schema、RLS、Secret或deployment。
- Guard無法在DB lookup／Discord前集中阻擋，或必須大幅重寫`app.py`。
- Drift evidence無法在不輸出identity／Member row values下形成strict contract。

## 交付物

- Web Portal maintenance guard、唯讀GET提示與tests。
- Checksummed identity drift inventory SQL、validator、local fixtures/tests及操作文件。
- 更新`.env_example`／README（只記key與安全預設）。
- `docs/coordination/reports/TASK-068-CODEX.md`與HANDOFF。

## Base commit

`f1df7e3`
