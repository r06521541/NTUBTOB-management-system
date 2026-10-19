# 專案狀態

更新時間：2026-10-19（TASK203接線續行，未上線）

維護角色：Main Work。當前 task／下一 actor 只看 [HANDOFF.yaml](HANDOFF.yaml)。
Git 基準 main：`2b8e93e9029ac9be924967696b9be544f377c456`（PR269）。
工作 branch／dirty state 必須由 Git 即時核對，不由本文件推定已整合。

## Current work and authority

- 最新2026-10-19：Owner核准TASK203-WIRE-01但新增費用額度0；優先現有資源，
  不明費用只阻擋該操作。非阻塞受理→fresh proof／封鎖→人工審查後固定履行scope
  的default-off source已完成並獨立ACCEPT，claims已釋放；最終27真PG16、舊相容168、
  重建shared428/Mobile113/Portal267/LINE26/notify11/broadcast28及quality48通過。
  日期factory43與重建Mobile113通過；180日截短誤報已撤回：兩個真PG回歸證明原程式
  存完整180日，第31天可查、第180天到期。新增0020仍為本機candidate，不代表線上migration。
  GitHub CLI登入／安全憑證庫及公開repo已核對，正進行整合與標準hosted CI；登入gate已解除。
  尚未部署或啟用正常App刪除；
  PG15／真provider／未結案180日延長與保留執行未驗收，不稱TASK203整包完成。

- 最新2026-09-30：candidate0017逐項履行紀錄、供應商防重派執行與可信證據補記已實作，
  局部獨立審查ACCEPT；外層Connection未提交P1已修。最新重建shared293/Mobile104/Portal261PASS；
  Flutter59PASS、八檔analyze clean，含站內確認流程、持久防重送與fresh restricted request。
  無active delegate；完整清除／人工共用文字處理／還原／原生接線未完成，全部default-off。
  無新Owner gate或線上變更；以下較早計數與active角色敘述不代表最新狀態。

- TASK203恢復in_progress：PG634PASS在最新bridge/pending修正前；Portal/bridge/pending局部獨立ACCEPT。
  Flutter狀態頁8PASS/analyze clean但未接線；較早installed shared261/Mobile102/Portal261PASS。
  最新fullPG649PASS、installed shared269/Mobile103/Portal261PASS；admin count/Mobile child獨立ACCEPT。
  真雙連線競態與新活動名單保護局部ACCEPT；Flutter收據adapter17PASS/analyze clean，審查中。
  正式App接線、完整履行仍未完成；全部仍default-off。
  無新政策gate、未整包驗收或部署；目前delegate與後續缺口以task/HANDOFF/report為準。

- TASK203最新：DEC-114解除共用文字政策gate；內容分類規則及Portal輸入提示已補。
  新增default-off取消申請／candidate0016不可逆dispatch fence；獨立局部審查ACCEPT、claims已釋放。
  本輪offline91PASS、service追加回歸11PASS；PG schema21PASS，但後續integration setup逾時，整批FAILED。
  integration3PASS屬較早run，非整批全綠；停止重試並正常停止測試庫，55484無回應確認。
  candidate0015整合readiness與隔離fixtures；LINE直接身分亦納入一致性範圍快照。
  前輪完整PG16為543PASS、installed147/99/261PASS，非本輪重跑；取消source已實作但未上線。
  續補未啟用的fresh-proof交易協調器及Mobile opt-in guard；combined44含真PG通過，
  重建隔離shared61／Mobile90／Portal261PASS。審查通知已處理／釋放；修正pending登入回歸。
  真provider／device驗證、其餘入口的交易內阻擋、取消與完整履行executor仍待接線。
  不可部署；下列歷史測試不是最新整包驗收。未有真實刪除或hosted CI證據。

- [TASK-203](tasks/TASK-203.md)：L3，同一delivery branch；首次Apple登入default-off及Portal人工核可
  source已分別由獨立advisor／Main驗收，兩個完工通知皆已收到、處理並釋放claim；非整包ACCEPT。
  新增LINE-only後端guard，避免Apple身分誤入legacy操作。重建隔離安裝後Mobile90／Portal260PASS；
  backend40PASS／44PostgreSQL SKIP；未有DB競態、真實刪除、migration、Flutter、CI／PR／部署證據。
  Owner以DEC-113核准保留共用LINE OA／群組公告並揭露另行封鎖／退出；個人化通知仍須停止。
  該Owner gate已解除，續離線履行準備；獨立訂閱與payload邊界待核對，不假稱刪除／合規已完成。
  已補唯讀legacy三鍵歸屬planner與一致性快照adapter（隔離PG16共12PASS）；無履行executor。
  未啟用0014 ledger基礎及獨立程序metadata檢查共14PASS；revision增量獨立ACCEPT。
  PG rewind與fixture修正已審查、實PG16順序95PASS；UTC完整PG套件432PASS零skip，hosted15/16未跑。
  最新shared95／Mobile90／Portal260PASS；非整包完成或CI-ready。Supabase登入已完成：兩專案Free Plan
  無方案內排程備份／PITR；Owner確認無另存手動備份，此輸入gate解除。供應商內部保留仍未知，
  不得當作零保留或自動升級；後續仍為離線實作，未部署。
  [report](reports/TASK-203.md)／[review](reviews/TASK-203.md)記錄修正與unknown-subject callback release blocker。
- [TASK-202](tasks/TASK-202.md)：planning，branch `codex/task-202-privacy-retention-plan`；
  Main已把Owner確認的個人陳柏安、公開信箱與第一方隊務限定／不廣告不出售寫入未發布草稿。
  Owner追加要求[帳號／隊務分離詳細草案](../planning/ACCOUNT_DELETION_DESIGN.md)，Main lease2已交規劃；
  解除Apple與完整帳號刪除分開，Person技術鍵不構成個資豁免。具名名冊保留及方案A期限均未核准。
  Advisor `task-202-deletion-design-review` lease2主動回報設計ACCEPT，Main已處理並釋放；無source／runtime mutation。
  缺Apple token不阻本服務清理；callback綁intent/generation；standalone unlink另有平台gate。不是合規／實作驗收。
  本機quick contract41項為40PASS／1SKIP；planning文件留本機，不建單獨PR或重跑建置。
  [適用性盤點](../planning/ACCOUNT_CREATION_APPLICABILITY.md)區分source／build2／歷史runtime；
  既有proof連結不建Person，但有pending與LINE人工建Person能力，不能籠統宣稱login-only。
  Main已收取並處理advisor主動完工；Apple詢問僅草稿未送，未改產品範圍或實作刪除。
  最新DEC-112選定Apple可首次登入，pending不等於隊員權限；不再等待login-only豁免。
  [同一交付範圍](../planning/APPLE_ONBOARDING_DELIVERY.md)涵蓋首次登入、跨provider批准與真實刪除；
  Main lease4已固化決策及設計，規劃交棒TASK203；TASK202本身未改程式，保留期限仍待決。
- [TASK-201](tasks/TASK-201.md)：Owner要求繼續至需介入；Main核對native privacy resource／package
  exact-name對照及App第一方宣告依據。保持未知與政策決策邊界；不自行新增不實manifest或商店答案。
  Main claim `task-201-main-20260917` lease1；advisor `/root/privacy_foundation`
  claim `task-201-privacy-review` lease2已主動回報source ACCEPT；lease1設計ACCEPT亦已收到。
  本機95tests為93PASS／2WindowsSKIP；獨立64tests為62PASS／2WindowsSKIP。
  Accepted source eeb49465ebf3ff9f7e01e5d0c0d8c5252f2a4c0b已push；PR269/run35131673831全部16PASS。
  已guarded merge且main tree相同；main/run35132747553也全部16PASS，兩輪盤點摘要一致。
  實際unsigned盤點unknown alias7→1、lock unknown2→0，新增AppCheck11.3.2／Interop101.0.0；
  manifest／lock內容不變，非SDK升級、signed build2或合規證明。
  Task Main／advisor claims已釋放；六份收尾文件留本機待下次實質PR，不另開狀態PR。
  公開營運主體／名稱、支援／隱私聯絡信箱與第一方用途已由Owner確認並記入TASK202；
  保存／刪除期限及SDK／雲端runtime仍須另行核對，禁止自行填商店答案或發布政策。
- [TASK-200](tasks/TASK-200.md)：Owner要求接著做，Main補上既有unsigned fictional iOS CI成品的
  privacy manifest／native dependency盤點。獨立設計ACCEPT後實作與隔離測試，不另造release controller、
  不再簽署／上傳、不讀private artifact、不猜商店答案。正常source review／CI／單一PR沿用standing authority。
  Source0832b7110b390dac444b759e6b04b1c631703e02已ACCEPT、fourhashes綁定。公開push曾在執行前被auto-review
  攔下；Owner2026-09-17明確確認15檔payload139e4cda32b3203050b7f3891fbb00785694b518可公開，
  PR268/run35126415121及main/run35127733708各16PASS，local main已同步且tree一致，task交付完成。
  真實unsigned CI盤點13份manifest、root缺席、7個未知alias，兩個SPM lock一致、各2個未知identity；
  GoogleSignIn9.2.0／LINE5.17.0等7個原生版本已取得，不等於signed build2、SDK完整coverage或合規。
  PR／main盤點摘要相同，Mac直接21項inventory測試全通過。六份Main-owned收尾／證據文件已隨TASK201實質PR合併。
- [TASK-199](tasks/TASK-199.md)：Owner 已批准四小時帳號基礎包，包含刪除**申請**、
  session/logout 競態回歸、隱私／SDK 事實與草稿、錯誤校名修正及狀態文件收斂。
  Source已獨立ACCEPT，本機Flutter395PASS／analyze無問題。Owner明確確認本次45檔公開
  payload後推送成功；PR267/run35103422322全部16PASS（含hosted15/16）後已合併。
  合併tree與PR相同；main/run35104479236也全部16PASS，本包source交付完成且本機main已同步。
  未部署，不凍結 Flutter UX 或首版範圍。五份Main-owned closeout文件已隨TASK200實質PR合併。
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

TASK-199 Main claim `task-199-main-20260916` lease1已完成並釋放；全域Main角色不變。
TASK-200 Main claim `task-200-main-20260916` lease1及advisor lease2完成並釋放；全域Main不變。
TASK-201 Main claim `task-201-main-20260917` lease1及advisor lease2完成並釋放；全域Main不變。
TASK-202 Main claim `task-202-main-20260917` lease4記錄核准方向；advisor `task-202-account-applicability` lease1完成／釋放。
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
  第一方privacy宣告、SDK未知對照、signed candidate／Xcode privacy report與商店揭露；
  TASK200只有unsigned CI盤點。公開候選與production backend/provider尚待獨立決策。
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
