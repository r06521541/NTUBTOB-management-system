# 專案狀態

更新時間：2026-09-16（TASK-199 source-only account foundation 進行中）

維護角色：Main Work。當前 task／下一 actor 只看 [HANDOFF.yaml](HANDOFF.yaml)。
Git 基準 main：`d83bd4b1e64bad119f780344fbde6d57c378f308`（PR266）。
工作 branch／dirty state 必須由 Git 即時核對，不由本文件推定已整合。

## Current work and authority

- [TASK-199](tasks/TASK-199.md)：Owner 已批准四小時帳號基礎包，包含刪除**申請**、
  session/logout 競態回歸、隱私／SDK 事實與草稿、錯誤校名修正及狀態文件收斂。
  目前 source/test 整合中，尚未正式驗收或合併；不凍結 Flutter UX 或首版功能範圍。
- 本包不執行 deployment／migration、簽署／上傳／商店操作、真實刪除、provider／Secret／金鑰變動，
  也不碰正式資料。允許 source、離線／隔離假資料測試、唯讀查證與正常獨立 review／CI／PR／merge。
  既有 aggregate USD20 上限不重置；未知成本或私人輸入停止該 lane，不阻塞其他離線工作。
- IOS-TF-01 的歷史授權與剩餘目標仍在 [TASK-198](tasks/TASK-198.md)／
  [report](reports/TASK-198.md)／[review](reviews/TASK-198.md)。它不是本輪部署或重新簽署指令。
  不因 build2 本人驗收而宣稱所有 provider／privacy／公開發布 gate 已完成。

## Active role lanes

| lane | current actor_id | claim_id | lease_version | state |
| --- | --- | --- | --- | --- |
| `main-work` | `01a03587-d263-7e92-9965-54816f38b8a3`（runtime alias `/root`） | `main-work-20260825` | 17 | active |
| `domain-work:flutter` | `01a01212-72dc-7132-b2d7-dfaa2f97f184` | `flutter-domain-20260821` | 2 | active |

TASK-199 Main claim 為 `task-199-main-20260916` lease1，承載者是同一 Main，不是第二個 Main。
Writer／reviewer 的 task claim、owned paths、完成與撤回看 active task；未派任者 read-only。
輪替、ACK／heartbeat／主動完工通知依 [COLLABORATION](COLLABORATION.md) 第2節。

## Verified iOS delivery baseline

- App `tw.org.ntubtob.portal` 已循 GitHub hosted macOS native archive/export、原生上傳、
  App Store Connect 處理及 TestFlight 完成本人內測；不再標示為「尚未真實簽署／上傳」。
- Signing-only run34880271702 真實簽署／指定清理通過；不重跑成功基準或重建憑證。
  Build1 上傳 run34953146969；build2 上傳 run35048625677，native upload exit0。
- 目前本人手機為1.0.0(2)。Main 曾直接確認 build2 正在測試、僅既有 Owner Internal 群組1人、
  獨立測試者0；Owner 回報更新後正常進首頁。這是本人回報，非獨立裝置遙測。
- Build1 已獲 Owner 六項 smoke：Google login-to-home、連網冷啟免重登、離線唯讀、
  恢復連線免重登、賽事詳情、限定虛構比賽出席修改／重開／還原／重開。不要求重做。
- Build2 包含 Google503錯誤文案／恢復入口修正；未刻意在真機重現503。PR266 的支援入口
  source 已合併且 PR/main CI各7PASS／7scopeSKIP，但尚未更新至手機。
- 保留 build2 run35048625677/job104643922506 的 failure：native_sidefiles/
  EXTERNAL_METADATA_CHANGED；Logs新增1、Caches新增4／修改2，內容／原因未查證。
  指定 upload/signing audit 為 OWNED_PATHS_ABSENT／ABSENT、artifacts0，**不覆蓋整體
  cleanup=false**。Owner 已接受這一次披露的不確定供本人內測，不是所有未來錯誤豁免。
  不重送build2、不造build3追綠燈、不重填Secret。歷史細節保存在TASK198報告。
- Apple／LINE iPhone 登入、真機 logout／跨帳號資料隔離、其他裝置、正式 privacy／刪除與
  provider lifecycle 仍未全部驗收；不以 source tests 代替真實整合證據。

## Repository capabilities and unshipped work

### Identity, Web Portal and database

- PostgreSQL `ntubtob`：Phase C Person／Member／identity／qualification／audit、
  Person-based attendance、pending review lifecycle 已存在。
- 最近正式環境紀錄為 revision `0009_event_management_writes`；管理權仍為
  `WEB_PORTAL_ADMIN_MEMBER_IDS` runtime allowlist，非持久 Person role 切換成功。
  197位Member／Person、56組可靠LINE identity／active team-player關係及兩位管理者的
  受控啟用證據見 Phase C closeout；不是本輪即時資料清點。
- Portal 支援 LINE登入、人員／identity、Game出席、Event/Activity read 及 allowlist-gated
  Event create/edit/publish/cancel；發布採 immutable invitee snapshot，寫入與通知分離。
- Repository main 已有 linear0012 persistent admin authority、Event通知／guest-player。
  尚未在production seed、migration、mode flip或部署；相關 exact operator 授權不自動擴張。
- TASK199新增 additive0013 帳號刪除申請收據（source-only），不刪除 Person／Member／session，
  不撤銷provider、不啟用normal bootstrap；downgrade保留收據。尚非正式環境schema。
- Event／一般Activity為三態出席；linked Game沿用五態單一來源。此source交付未部署production。
- Desktop LINE登入保持callback origin、same-browser initiation、state／nonce／TTL／safe return；
  LINE內建瀏覽器路徑維持安全邊界。

### Flutter and Mobile API

- Basic real client：LINE／Google與iOS Apple入口、server-owned session、identity recovery、
  games／attendance、Event／Activity、通知、帳號狀態、support與bounded Officer foundation。
  Offline只讀，mutation須online；fake mode是fictional、deterministic、network-free。
- TASK199新增可注入的刪除申請狀態／站內確認UI，僅fake demo啟用；real app不展示假可用按鈕。
  真正受理／履行、pending或restricted帳號管道、資料保留及對外聯絡方式待Owner與rollout決策。
- Apple repository foundation包含nonce／single-use code exchange、encrypted provider credentials、
  notification receipt/revocation與明確revision allowlist；只以verified stable subject識別，
  不以email/name自動合併。Source存在不等於live Apple lifecycle可用。
- [MOBILE_PRIVACY_DRAFT](../releases/MOBILE_PRIVACY_DRAFT.md) 區分first-party source、
  vendor SDK聲明與archive/runtime未知；不是已發布privacy policy或已完成App Privacy／Data Safety。
- 匿名crash foundation仍default-off、local-only；無真實collector／endpoint或upload receipt。
  Push／deep-link delivery、production mobile backend與provider publishing仍保留外部gate。

## Last recorded external state (not a fresh inventory)

- Isolated staging：`ntubtob-mobile-staging`／`mobile-api-staging`，最近記錄DB revision0008、
  revision `mobile-api-staging-task157-47ccfb5f`100% traffic。Owner恢復Supabase後，
  無token /me曾回401／BEARER_REQUIRED；不能由此推論Apple設定或schema完整。
- 2026-09-16 TASK199唯讀metadata確認同一staging revision仍100%，四項Apple lifecycle設定
  名稱均缺（只查env.name，不讀值／Secret）。DB schema仍未fresh查證，不能把舊0008當即時值。
  未要求Owner在未ready時測Apple。
  Shared Google provider仍External／Testing；staging成功不等於production publishing。
- Production Web Portal `web-portal-00054-rtp`100%，image commit
  `0d6efacac2f20fe1ff66f1aa9ae84fd888ab0961`；identity maintenance=true，
  identity-link plain runtime config未完整啟用。
- LINE webhook `line-webhook-handler-00013-yab`100%，公開入口驗證signature；
  notify cron `notify-cronjob-service-00017-qms`100%，private。
  最近紀錄四個Portal Secret references與runtime identity未漂移；不讀payload。
- 棄用的是 LINE Notify API／legacy line_notify_tokens，不是Messaging API／LINE Login／webhook。

## Remaining release gates and decisions

- iOS：Apple backend/config及真機provider/logout驗收；正式privacy/support URL、資料保留／刪除履行、
  SDK/archive privacy manifests與商店揭露；公開候選與production backend/provider尚待獨立決策。
- Android：Play app NTUBTOB／tw.org.ntubtob.portal已建立；尚未有真實Closed Testing AAB上傳、
  signing/store/device完整證據。維持API36、android-closed＋staging:real的source邊界。
- 不因Owner尚未決定Flutter UX便擅自凍結、重設計或刪減首版；功能與體驗清單另待Owner回來確認。
- 正式Event attendance／notification／guest-player與persistent admin rollout、自然Scheduler與
  長期低流量觀察仍未完成；缺error log不等於所有情境通過。

## Documentation and safety

Completed TASK142–168、171–173歷史索引見 archive/phase-d/PHASE_D_CLOSEOUT.md；archive不授權現在操作。
TASK169/170/174及後續release tasks的外部gate未因本輪文件收斂而撤回。現在能力看本文件，
歷史嘗試看task/report/review，決策看DECISIONS，HANDOFF只承載singleton，避免互相矛盾的流水帳。

Production與不可逆操作仍需exact target／approval／one-shot／post-check；結果不確定先read-only reconcile。
不得讀取／提交private env、credential、token、password或Secret payload；merge不代表deploy或release。
