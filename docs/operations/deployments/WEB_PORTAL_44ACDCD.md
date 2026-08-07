# Web Portal production deployment — 44acdcd

- 日期：2026-08-07（Asia/Taipei）
- 結果：成功；未需要 rollback
- Exact commit：`44acdcd1576be57fe2d9c08861872fa75146a2ef`
- Cloud Build：`e8534be4-cb7a-4efc-814d-ba4fa735ccf4`
- Previous／rollback revision：`web-portal-00039-87s`
- New revision：`web-portal-00040-wm9`
- Image digest：`sha256:1c4ec082515fd0369ead487ccf02137fa76b42fb666bf4fae47a90a78c6cf01c`

## 驗證

- `web-portal-00040-wm9` 為 Ready 並承接 100% traffic。
- `GET /` 為 200；`GET /demo/` 為 404。
- Runtime identity、三項既有 Secret references 與 public invoker boundary 通過 deployment wrapper／唯讀查核；
  未讀取 Secret value。
- `WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED` 不存在，依程式 default-off，未在部署中啟用。
- 新 revision 部署後 30 分鐘範圍內 ERROR log 為 0。
- 未人工登入或呼叫管理 POST，未讀寫 production DB、發送通知、修改 Secret／IAM／Scheduler／schema／RLS，
  也未部署其他服務。

## Rollback

本次未觸發 rollback。部署時已確認 `web-portal-00039-87s` Ready 且承接 100% traffic，並由 wrapper 在
切流量後失敗時自動回切；未來若要回切必須重新依當時 production 狀態取得授權。
