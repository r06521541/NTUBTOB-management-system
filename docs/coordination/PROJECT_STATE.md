# 專案狀態

更新時間：2026-09-16（1.0.0(2)本人更新進首頁通過；Main接續補登入前支援入口與清單校準，source未部署，不等於全IOS-TF-01或公開上架驗收）

維護角色：Main Work

目前 main 程式基準：`283c9c9e3de8f395728851d28039a7b2c46a1f24`（PR265）。
目前branch/dirty state由Git核對，next actor以HANDOFF為準。

Owner明確回覆「是」，接受run35048625677已披露的日誌／快取內容未明風險，允許既有1.0.0(2)僅本人內測；同一處置不再重問，不代表audit轉PASS、全機乾淨或未來新錯誤一律豁免。Owner另回報出口合規已完成，Main接續唯讀確認與本人群組範圍核對。
Owner完成新增後，Main直接確認1.0.0(2)「正在測試」；精確build detail只有既有Owner Internal群組、成員1、獨立測試者0。Owner再明確回覆「有 進首頁了」，確認TestFlight更新到1.0.0(2)後正常進首頁，記為本人回報實機update-to-home PASS，非Main獨立遙測、免重登入或所有provider／503失敗路徑均已驗證。本輪更新交付通過，無待Owner操作；整體provider／logout／privacy／device剩餘驗收仍由Main盤點。不重做build1六項smoke、無新增人員／重傳／公開發布。

保留run35048625677/job104643922506稽核事實：SIGNED_COPY_READY／signature／signing cleanup通過，native upload attempted=true／exit0／process stopped；primary null，但native_sidefiles/EXTERNAL_METADATA_CHANGED。Logs新增1、Caches新增4／修改2，內容及原因未查證。指定upload／signing清理audit各為OWNED_PATHS_ABSENT／ABSENT，artifacts0，不覆蓋整體cleanup=false或宣稱全機乾淨。後續Owner已接受本輪剩餘風險、完成合規與本人分發／更新如上；不重送build2、不另造build3試過關、不重填金鑰。Watch已結束。

TASK198最新：PR261一次性設定已合併，CI34865517474成功16/16；native run34880271702真實簽署與清理通過。
Owner認可GitHub標準native路徑與一次性persistent Secrets custody，DEC-110明列範圍／風險。
Sign-only workflow已合併；舊workflow硬停用，舊日誌／資產保留。
已成功的signing-only基準不使用ASC／Apple登入p8，無Apple上傳／raw logs，不改production/provider。
既有真實憑證完成native archive/export/IPA檢查；固定結果SIGNED_BASELINE_VERIFIED、清理ABSENT、artifacts0。
Owner完成ios-native-signing三項Secret與五項Variables；Main核對名稱/設定與Owner reviewer/self-review/bypassfalse/main-only。
Main核對accepted runtime指紋、隔離staging ownership及無競爭run；舊job取消、無runner/steps，舊傳送Secret名稱皆無。
run34880271702：main/exact SHA、version1.0.0/build1/attempt1吻合；不重跑成功基準，後續建置重用已保存Secrets。
PR262已合併、CI16/16，真實altool help與新版收據讀取器通過；Owner已保存ASC Secret，Main唯讀確認存在／保護規則，不讀payload。
Main已實作opt-in native altool upload、簽署後交接、唯讀重複／自動分發檢查；獨立source ACCEPT。
本機direct79PASS1macOS SKIP＋inspector18PASS；PR263已合併、CI34935268030成功16/16，post-merge唯讀保護檢查通過。
Owner已手動啟動並核准run34953146969/job104328690147；本輪SIGNED_COPY_READY，原生上傳attempted=true／exit0。
Workflow失敗原因為native_sidefiles/EXTERNAL_METADATA_CHANGED；外部Logs/Caches變動內容與原因未知。
指定上傳暫存audit=OWNED_PATHS_ABSENT、簽署audit=ABSENT、artifacts0；不得推定所有位置皆無殘留。
Owner提供ASC Build Uploads截圖：1.0.0(1)綠色「完成」，已獲Owner Console接收／處理成功證據；非Main API驗證。
Owner確認既有內部群組只有本人，版本已加入，並回報從TestFlight安裝後成功進入iPhone歡迎畫面。
Owner後續截圖顯示登入頁有Apple／Google與圖示型LINE按鈕；UI顯示已確認，不等於登入或重啟測試成功。
Owner完成單次Google帳號選擇／授權，App顯示「資料格式異常」；Main核對20:22的Google exchange為503。
staging仍由mobile-api-staging-task157-47ccfb5f承接100%流量；DB readiness紀錄operational／none／tcp_ok。
不帶token的單次/me GET同樣503／DB readiness不可用；不是已證明的schema mismatch或Google帳號拒絕。
Google503誤導文案已合併PR264並隨build2更新到手機：嚴格契約且明確可重試才顯示恢復入口，不自動重送；196項本機測試、獨立ACCEPT與PR CI34976805878通過，真機未刻意重現503路徑。
Owner已回報Supabase Resume完成；20:44唯讀/me已回預期401／BEARER_REQUIRED，該請求DB guard通過。
Owner已回報Google登入後進首頁，記為本人實機login-to-home通過，非Main獨立裝置遙測或完整驗收。
Owner也確認連網且未登出時完全關閉重開，可直接回首頁；記為session恢復通過，不推定無限有效期或token內部狀態。
Owner確認斷網重開顯示離線唯讀，恢復網路再重開也能正常回首頁免登入；四項入口／連線smoke通過，非完整驗收。
Owner也確認賽事詳情正常；不推定已驗完整快取、寫入阻擋或不重開時自動復原。
Owner確認TASK198限定2035-02-01虛構對手甲／球場A的出席變更、重開保留、還原、再重開四步皆正確；回覆值已獲本人還原確認，不推定稽核／時間戳還原。
六項smoke不用重做；診斷本機133PASS3SKIP、lease11 ACCEPT，PR265已合併，PR CI34998337467／main CI34999512813皆16PASS。無金鑰version/find/help期間Caches仍變動，Logs未變；不等同金鑰殘留也不證明舊run乾淨。無待完成review/watch；最新剩餘風險處置已獲Owner批准。
不重送build1、不重填Secret；Owner已同意build2及原IOS-TF-01範圍後續版本的歷史風險處置，不等於宣稱舊run乾淨。每版仍需fresh preflight／既有Environment核准；新失敗或不確定仍停止、不自動重試。
目前source支援入口已接歡迎／登入前畫面，首頁離線仍可讀；本機111項測試與analyze通過，獨立lease12 ACCEPT／6項focused PASS，待hosted gate，不需新key／build3／手機操作。正式privacy URL／刪除流程仍缺，不以靜態說明冒充合規。
Main瀏覽器已恢復；build2合規／本人分發／更新完成，不重跑。staging Apple登入後端仍缺四項設定群組與schema readiness的fresh核對；暫不要求Owner測Apple。其後另補logout／provider／privacy真機證據。

## Active role lanes

| lane | current actor_id | claim_id | lease_version | state |
| --- | --- | --- | --- | --- |
| `main-work` | `01a03587-d263-7e92-9965-54816f38b8a3` | `main-work-20260825` | 17 | active |
| `domain-work:flutter` | `01a01212-72dc-7132-b2d7-dfaa2f97f184` | `flutter-domain-20260821` | 2 | active |

Lane 是長期責任邊界，不永久綁定厚重 session；輪替須先 revoke current actor，以 full HEAD、dirty state與完成／剩餘
事項交棒，再遞增 lease。沒有 active task claim 的其他 session 一律為 `advisor/read-only`。派工與回報使用
`COLLABORATION.md` 第 2 節 generic packet；訊息不取代 task claim、lane registry 或 HANDOFF。

## Current repository capabilities

### Identity, data and Web Portal

- PostgreSQL schema為`ntubtob`，production Alembic revision為`0009_event_management_writes`。Phase C Person／Member／
  auth identity／qualification／audit基礎、Person-based attendance與pending review lifecycle已存在。
- 197位Member／Person、56組可靠LINE identity／active team-player關係及兩位allowlist管理者已完成受控啟用；歷史
  mutation證據在Phase C closeout。Production管理權限仍只來自`WEB_PORTAL_ADMIN_MEMBER_IDS` runtime allowlist，
  Person role尚未取代它。
- Web Portal支援LINE登入、Person/identity管理、Game／attendance、Event／Activity read與allowlist-gated Event
  create/edit/publish/cancel。發布建立immutable invitee snapshot；管理寫入與通知分離。
- Repository已合併persistent admin authority與linear `0012` capability；production仍維持runtime allowlist及revision
  `0009`，尚未執行seed、migration、mode flip或部署。
- Event與一般Activity採三態attendance；linked Game在同一Event surface重用既有Game五態且不重複儲存。此
  repository delivery尚未部署至production。
- Desktop LINE login以固定callback origin及短效same-browser initiation維持session continuity；state、nonce、TTL、
  safe return與LINE in-app路徑維持fail closed。

### Flutter and Mobile API

- Flutter real composition提供Basic client、LINE／Google登入、server-owned session、跨provider identity recovery、
  games／attendance、Event／Activity、通知中心、帳號資料狀態、support資訊與bounded Officer read/publishing foundation。
  Offline只讀且mutation需online；development fake為deterministic、fictional、network-free。
- Isolated fictional staging已完成Mobile API、DB revision`0008`、LINE／Google real-provider smoke與session/linking驗證。
  Shared primary Google provider仍為External／Testing，runtime/data固定在`ntubtob-mobile-staging`；staging成功不代表
  production provider publishing或deployment。
- Apple nonce-bound identity-token、single-use authorization-code exchange、加密provider credential、server notification
  receipt/revocation與explicit revision allowlist已完成repository foundation；verified stable`sub`仍是唯一identity key，
  不以email/name自動合併。Apple Developer capability/profile、真實client secret/Secret binding、credential-state實測、
  active token revocation、runtime deployment與real-device/TestFlight仍未完成。

### Release and engineering

- Android repository release contract固定package`tw.org.ntubtob.portal`、API 36、Basic-only
  `android-closed + staging:real`、external signing、monotonic version與strict AAB inspection；production/mixed target
  fail closed。這是repository evidence，不是已上傳的store candidate。
- iOS有TestFlight/App Store fail-closed config與Sign in with Apple source contract；hosted macOS/Xcode已驗證
  staging:real Release source可no-codesign編譯。Signed archive、provider、capability/profile與real-device evidence仍是外部gate。
- TASK-183新增secret-free cloud rehearsal與artifact-only IPA inspection；後者不授權upload/release，default readiness
  gate不變。Owner回報App ID/capability與App Store Connect record已建立，未於本task獨立查證；真實憑證與store操作未做。
- Owner回報上傳API key已私人保存；另於TASK-185 merged SHA完成CSR／加密PKCS8建立，Apple Distribution憑證已簽發下載。
  未讀取或獨立驗證實際檔案，不再依據較早的Certificates空白狀態建立替代憑證。
- TASK-185純記憶體配對工具已由PR240合併且完整CI成功；配對不等於Apple信任或簽章授權。
- TASK-186已合併；Owner於exact批准後回報加密PKCS12轉檔confirmed_success，另已下載App Store Connect profile。
  不重做轉檔；profile可信CMS、Team/App配對及macOS native import尚未驗證。
- TASK-187已合併純記憶體profile內容配對核心；配對成功仍非CMS可信、私鑰持有或簽章授權，不讀Owner檔案。
- TASK-188已由PR243合併；完整CI與macOS15+虛構PKCS12純記憶體原生import通過，不代表Owner資產已驗證。
- TASK-189已由PR244合併；CMS預檢／原生驗簽／受限Apple信任鏈及虛構macOS正反向演練通過完整CI。
  不代表Owner資產已驗證；不授權真實簽章／上傳，revocation仍未驗證。
- TASK-190已由PR245合併，完整CI與macOS虛構演練PASS。Owner完成Environment設定後，唯讀查驗確認保護規則
  及目標Secret不存在；API有回傳禁止管理員略過欄位，不再是未解相容性疑慮。
- Owner於exact批准後執行profile intake，回報本機input階段INPUT_REJECTED、run_id=null；未到dispatch。
  TASK-191已合併且full CI通過；Owner批准並執行local-only診斷，回報CMS_ALGORITHM_REJECTED，其他四項PASS。
  TASK-192已合併，Owner用完一次完整診斷：五項digest／attribute限制不符，其餘predicate通過；仍未證實真實信任。
  TASK-194已由PR248合併，full CI及macOS408個虛構CMS案例／runner演練通過；原生驗簽及Apple信任鏈保留。
  Owner另批准exact merged SHA真實驗證，仍於input回報INPUT_REJECTED、未到dispatch；子程序已結束。
  真實profile驗證尚未完成。TASK195公開資料架構審查已ACCEPT：建議轉為Xcode-led archive/export與分層Apple驗證；
  既有outerCMS/XML檢查不代表modern DER profile平台權威。Owner已批准架構；TASK196純虛構可行性實作已合併。
  現行程式/gate未改；不重試或第三次診斷、不推定演算法、不重建憑證；未授權新private custody/signing。
  TASK196已由PR249合併，完整run34603603901共16工作PASS：無私鑰archive、虛構Keychain正反向案例／清理，
  以及缺虛構profile時的預期匯出拒絕均驗證。原問題是分類漏認Xcode措辭，已以固定selector整行判定修正。
  真實資產與簽署未動用；positive export、真實profile、候選簽署／TestFlight仍是後續獨立gate。
  TASK197：run34608233601已驗證實際Flutter未簽署archive；PR250後由TASK198收斂並合併。
  虛構codesign出現identity查找訊息、cleanup成功；根因不足以支持修正，有限診斷已停。
run34610163522唯讀診斷查得target憑證／identity且DER符合；cleanup成功、codesign未執行。
run34614766702單次parent/child診斷完成：均找到相符identity/key、typed canSign=true，cleanup成功。
原生policy NOT_EVALUATED、codesign未執行；不再把虛構codesign成功當真實發布前提，根因不冒稱解決。
- TASK-177 repository delivery已通過獨立Privacy／Security review與hosted CI：Flutter匿名crash foundation固定
  default-off、local-only、provider-neutral與嚴格去識別化；尚無provider／endpoint、真實上傳或receipt evidence。
- CI對changed Python使用bounded pinned quality runner；text digest canonicalize LF，binary digest維持raw bytes；
  docs/archive與核准bootstrap wrapper可走quick gate，unknown/shared/workflow仍fail-safe full。

## Last recorded production state

以下是既有部署／查證紀錄，不是本次即時雲端盤點；執行外部操作前必須重新核對 exact target/state。

- Web Portal：`web-portal-00054-rtp`，100% traffic；image tag commit
  `0d6efacac2f20fe1ff66f1aa9ae84fd888ab0961`。Identity maintenance為true，identity-link plain runtime config未完整啟用。
- LINE webhook：`line-webhook-handler-00013-yab`，100% traffic，公開入口仍驗證LINE signature。
- Notify cron：`notify-cronjob-service-00017-qms`，100% traffic並維持private。
- Web Portal與LINE webhook僅保留必要public ingress；四個既有Web Portal Secret references與runtime identity在最近部署
  post-check未漂移。LINE token／channel secret由Secret Manager version 2綁定，active env不保存plaintext。
- 已棄用LINE Notify API與legacy`line_notify_tokens`；LINE Official Account／Messaging API、LINE Login／webhook與
  Discord是不同能力。

## Active work and external gates

- IOS-TF-01／TASK-198 active：Owner已批准既有資產真實簽署、必要staging操作與僅本人TestFlight，新增成本上限USD20。
  PR251已合併，CI34688813903全16項成功；clean-main preflight通過，尚未真實簽署上傳。
  Windows operator／sanitized journal／GET復原已整合；新保護環境與staging retained-binding已唯讀驗證，舊環境不變。
  DEC-109取代包內逐次批准與TASK197單次診斷限制；不含production／公開版／新憑證。現有P12/profile/cert檔存在，
  未讀payload或驗證有效性；live staging Ready但四項Apple設定key皆缺，private intake／實機仍待必要Owner參與。
  First slice由PR250合併且16項CI全綠；Apple登入完成，App capability／憑證／profile／ASC上傳key皆已唯讀確認存在。
  Owner已建立並下載僅綁現有App、由staging使用的登入key，portal狀態已確認；未讀payload或驗證本機custody。
  私密材料驗證模組離線測試及獨立review通過；Owner已新增一個iOS client，唯讀確認類型/名稱/Bundle相符，既有Android/Web不動；真實簽署adapter準備中。
  Owner內部群組已建立：1位本人測試者、0版本、手動分發。輸入拒絕後唯讀確認runs0／secrets0／journal不存在。
  Main修正成對引號與同欄位格式重填；依Owner新要求新增受保護本機JSON保存六欄metadata，密碼與key內容不保存。
  PR252已合併且CI34693162874全16項成功；Owner已填JSON，語法通過但ASC来源資料夾繼承ACL不合原custody規則。
  Owner批准只複製JSON指定ASC key到既有受保護目錄、自動改path、原檔/另把key與其他五欄不動。
  Writer17完成單檔匯入；Main提前檢查四個資產權限，補上完成狀態私鑰格式重驗；Security31已ACCEPT。
  PR253已合併且CI34696846257全16項成功；預檢READY，實際匯入在KEY_REJECTED停下、尚未copy/backup/update。
  已用假key重現有限PKCS8等價編碼被serializer比對誤拒；修正不改key原bytes、不放寬曲線/extra資料檢查。
  Security33 ACCEPT、本機218tests214PASS4skips；待正常CI/merge後fresh預檢/單次import，不需Owner重填六欄。

- TASK-175與TASK-176 repository delivery已合併；Event通知／guest-player與persistent admin仍未部署、未遷移或切換
  production，外部mutation維持獨立Owner gate。
- TASK-174 repository delivery已由PR #227合併，其Apple provider lifecycle foundation只是repository capability；不授權
  Apple provider、Secret、signing、runtime、production或TestFlight操作。
- TASK-169保留active：repository release-readiness已合併，但Android/iOS store、signing、provider、production backend、
  device與public-release gates仍是現在的release boundary。
- TASK-170 repository delivery已由PR #232合併；Play app `NTUBTOB`／`tw.org.ntubtob.portal` 已建立，但尚未建立真實
  upload key、產生／上傳exact Closed Testing AAB或完成store/device evidence；open／production／公開發布皆未執行。
- TASK-178 repository delivery已通過獨立Release／Security review及hosted CI：iOS staging TestFlight source與原生Apple
  bridge可在Release/no-codesign向量編譯；仍不構成signing、provider、TestFlight或公開版ready。
- TASK-179已由PR #234合併：signed IPA離線fail-closed inspector與TestFlight evidence checklist已進repository；尚無真實
  signed IPA，Apple readiness marker仍使actual inspection維持blocked。
- TASK-180 repository delivery已合併至上述固定Git基準：TestFlight metadata、privacy fact與外部gate
  manifest／validator維持fail closed；現有「聯絡管理員」帳號刪除文字仍是hard blocker；不推定外部gate完成。
- TASK-181已合併：文件校正、local quality selection、未生效流程／CI提案；不改CI規則或授權。
- TASK-182為local工具穩定化：Black cache隔離、PowerShell process helper及離線回歸；不執行runtime／store操作。
- TASK-177 repository foundation已由PR #231合併；external crash collection仍未啟用。
- Production mobile deployment、Google production publishing/client migration、Apple provider lifecycle、iOS signing／
  TestFlight、Android public release、push/deep-link delivery與anonymous crash evidence都需未來exact Owner gate。
- Event attendance尚待production deployment；Event notification與guest-player管理仍未成為production capability。
- People role尚未cut over production admin allowlist；last-admin、self-lockout、audit atomicity仍是未來持久角色gate。
- Owner尚未完成一般browser與LINE in-app的production人工smoke；自然Scheduler與低流量長期observation不足，不能以
  缺少error log推定所有通知情境已驗證。

## Documentation lifecycle

- Completed TASK-142～168、171～173的原始task/report/review群組已由merged Git ancestry證據索引至
  `archive/phase-d/PHASE_D_CLOSEOUT.md`；archive只證明歷史，不授權現在操作。
- Active入口保留TASK-169、170、174及其current/external-gate evidence；TASK-178保留本次repository delivery evidence。
  任何完成狀態不明或外部gate仍由該task承載的群組不得封存。
- 當前task與next actor只看`HANDOFF.yaml`；協作規則看`COLLABORATION.md`；長期決策看`DECISIONS.md`。

## Safety boundary

- Production固定採read-only discovery → Owner exact approval → one-shot execution → immediate post-check；結果不確定先
  read-only reconcile，不重送mutation。
- 不讀取或提交`envs/**/.env.yaml`、private env、credential、token、password或Secret payload。
- Store／provider／release signing／production／真實通知／正式資料與不可逆操作不得從staging、merge、archive或
  repository contract推定授權。
