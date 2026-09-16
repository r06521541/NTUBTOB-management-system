# iOS App Store Connect preparation

狀態日期：2026-09-16。這是`NTUBTOB`的`staging + real + Basic-only` TestFlight candidate的repository
準備契約，不是App Store Connect已填寫、Apple審核、signed archive或發布證據。Apple Console當下若出現不同問題，停止
並依當下官方說明重新分類，不用舊答案硬填。

已完成的真實簽署、本人TestFlight安裝／更新與Google核心smoke見[TASK-198 report](../coordination/reports/TASK-198.md)。
下列manifest仍是準備契約，不是live進度表；不把`required`／`blocked`值當作重做已接受步驟的指令。

## 固定candidate範圍

- 只連隔離staging runtime與測試資料，不連production資料。
- 只提供Basic會員能力；不宣稱Officer／Admin、push、deep link或crash upload。
- 支援iOS 15以上；TestFlight source vector為`staging + real + Release + testflight`。
- LINE／Google／Apple登入的provider限制與不可用情境必須在測試說明中明列，不得以repository測試代替真機證據。
- 機器可讀草稿位於[`ios-testflight-preparation.json`](ios-testflight-preparation.json)，只可輸出
  `PREPARATION_ONLY`，不得輸出帳號、URL、provider或簽章識別資料。

## 可預先貼入的繁體中文草稿

下列文字已受repository validator檢查長度與禁止識別資料，但名稱／副標仍需Owner在建立App record前確認。

| 欄位 | 草稿 |
| --- | --- |
| App name | `NTUBTOB` |
| Subtitle | `台大棒球校友隊平台` |
| Primary language | Traditional Chinese (`zh-Hant`) |
| Category | 建議`Sports`；建立record前由Owner確認，不把建議當已核准值 |
| Pricing | 免費；沒有IAP或訂閱 |
| Beta description | `NTUBTOB 是台大棒球校友隊的隊務與賽事資訊平台。本 TestFlight 版本僅供受邀測試者使用，連接隔離的測試環境與測試資料，不會存取正式環境資料。` |
| What to test | `請測試安裝、冷啟動、登入與登出、工作階段延續、賽程與活動瀏覽、出席回覆、離線唯讀及重新連線。此版本不提供推播、deep link 或 crash report 上傳；請勿在回報中附上帳號、權杖、裝置識別碼或其他個人資料。` |

Feedback email是TestFlight外部測試必填資料，但不得寫進repository；Owner在Console用實際支援信箱填寫。
Beta App Review的聯絡資料、測試登入方式與必要review notes也只在Owner可見的Console填寫；repository只保存去識別化
完成狀態。商店screenshots須由exact candidate與支援iPhone產生，不能用mock／舊版畫面冒充。

## App Privacy事實盤點

這是exact Basic candidate的repository事實，不是Apple questionnaire已送出答案。Apple要求同時涵蓋App與整合的第三方
SDK；最終資料類型名稱與「收集」定義須在App record建立後依Console當下文字逐項確認。

| Repository事實類別 | 收集 | 與使用者連結 | Tracking | 目的／限制 |
| --- | --- | --- | --- | --- |
| provider帳號識別 | 是 | 是 | 否 | 登入、identity linking與帳號安全；不以email/name自動合併 |
| Person顯示名稱 | 是 | 是 | 否 | 顯示帳號與隊務資料，可由使用者更新 |
| 出席與隊務互動 | 是 | 是 | 否 | 賽程／Event出席及隊務核心功能 |
| 安裝識別 | 是 | 是 | 否 | session、refresh、防重與安全；server保存hash類別 |
| crash diagnostics upload | 否 | 否 | 否 | candidate不安裝upload provider；local opt-in queue不等於server收集 |
| notification device token | 否 | 否 | 否 | Basic candidate不啟用push delivery |

尚未可定案：LINE、Google、Apple與其transitive SDK的App Privacy揭露、archive內`PrivacyInfo.xcprivacy`聚合結果，以及
App Store Connect當下對各資料類別的精確映射。三者未完成前不得發布App Privacy答案。

## 現在必須保持BLOCKED的項目

1. **公開URL與App內入口**：privacy policy與support URL尚未由公開、匿名可達的exact頁面證明；App內目前也沒有可點擊的
   正式privacy policy入口。source已補歡迎／登入前的靜態支援與資料使用說明，尚未部署到build2；不等於公開policy或其連結，
   也不猜URL。公開頁與App內正式policy入口仍是分開的gate。
2. **帳號刪除**：TASK199新增source-only申請／查詢、站內確認及離線／未知結果語意；real bootstrap未啟用，
   只在fictional demo展示，已安裝版本仍只有文字說明。這不是完整刪除，hard blocker維持；正式受理、
   保留／履行／provider撤銷、pending或restricted帳號管道與runtime驗收尚待決策。
3. **年齡分級**：必須依App Store Connect當下questionnaire回答。Repository只證明本candidate沒有廣告、賭博、IAP、
   聊天或一般使用者公開內容；不可直接宣稱最終rating。
4. **出口合規**：App使用HTTPS、Keychain／secure storage與nonce hashing。是否可宣告exempt及是否寫入
   `ITSAppUsesNonExemptEncryption`仍須依exact archive依賴與Owner法律責任確認，本task不修改`Info.plist`。
5. **Apple登入runtime與公開版**：TASK-198已有native簽署、Apple處理及本人TestFlight證據，不重建既有資源；但staging Apple
   後端設定與真機登入未完成，也未驗證公開版provider lifecycle。候選sidefile audit限制仍見原run紀錄，不改成PASS。
6. **公開發行選項**：content rights、distribution regions、EU DSA status與商店screenshots仍需Owner依實際權利與發行
   地區確認；TestFlight準備不代替這些公開版決策。

## Repository preflight

```powershell
py -3.10 -m tools.ios_store_readiness
```

成功只代表manifest完整且仍正確維持`PREPARATION_ONLY`；它不連網、不登入Apple、不建立資源，也永遠不能將目前狀態
轉成release ready。實際signed IPA仍須依[`IOS_TESTFLIGHT_CHECKLIST.md`](IOS_TESTFLIGHT_CHECKLIST.md)檢查。
