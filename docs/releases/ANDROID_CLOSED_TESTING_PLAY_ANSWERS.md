# Android Closed Testing Play answers

狀態日期：2026-09-02。這是 `NTUBTOB`／`tw.org.ntubtob.portal` 第一個 Basic-only Closed Testing candidate 的
回答契約；不是 Console 已填寫或送審證據。Console 當下若出現不同問題、公開／production範圍或未知法規聲明，停止而不猜。

## 固定產品範圍

- 應用程式：`NTUBTOB`；預設語言：繁體中文（台灣）；類型：應用程式；定價：免費。
- 發布範圍：Closed Testing only；不啟用 open testing、production rollout或tester通知。
- Runtime：isolated staging、real provider、fictional/test accounts與資料；不存取production資料。
- Candidate：Basic-only。沒有Officer/Admin、push delivery、deep-link delivery或anonymous crash upload。
- 登入：LINE與Google；provider步驟若因測試帳號限制不可安全執行，tester notes明列 unavailable，不假稱通過。
- 帳號資料：App內提供帳號資料來源／狀態與帳號刪除申請入口；實際privacy、support、deletion URL必須從已部署公開頁面
  read-only確認後再填，本文不記錄或猜測URL。

## Data Safety 回答原則

- 只依 exact candidate 的實際網路與server contract回答，不以未啟用的roadmap功能作答。
- 登入識別資料與使用者在隊務系統中的必要帳號／出席資料，屬提供核心功能所需；不得宣稱完全不收集資料。
- 不販售資料；不為廣告用途分享；傳輸使用HTTPS。是否屬「分享」及各資料類型的retention/deletion選項，以Console當下
  定義和公開privacy/deletion內容逐項核對。
- 不宣稱push、deep-link delivery或crash reporting，因本candidate均未啟用。

## Tester notes 必含

- 這是台大棒球校友隊平台的封閉測試版，只連接隔離staging環境與虛構／測試資料。
- 僅含Basic會員功能；Officer/Admin功能不在此版。
- 此版不提供push通知、deep-link delivery或crash report upload。
- LINE／Google登入需要事先核准的測試帳號；無法安全執行的provider情境會明列，不代表產品已通過該情境。
- 測試 install／upgrade／cold start／refresh／logout／schedule、Event與attendance／offline；回報時不要附帳號、client ID、
  endpoint、裝置識別碼或Secret。

## 尚待 Owner 可見外部確認

1. Closed Testing track確實沒有既有version（首次上傳才可用previous version code `0`）。
2. 公開privacy、support與account-deletion URL均可匿名存取且內容符合exact candidate。
3. Console當下Data Safety、內容分級、目標對象、廣告、政府／新聞等問題的實際題目與必填範圍。
4. Upload key建立、離線備份與Play App Signing enrollment；這些不由repository operator代辦。
5. Exact AAB完成Android 15實機矩陣後，才可上傳Closed Testing；處理中／拒絕／不明狀態不可填PASS。
