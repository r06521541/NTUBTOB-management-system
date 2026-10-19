# Apple 首次登入與帳號刪除：核准方向及實作邊界

2026-09-17，Owner已批准方向，見DEC-112。**本文件不是已實作或已上線證明。**
延伸[刪除設計](ACCOUNT_DELETION_DESIGN.md)；[適用性盤點](ACCOUNT_CREATION_APPLICABILITY.md)
保留作歷史依據，不再以取得login-only豁免作為工作的前置條件。

## TASK203-WIRE-01：正式接線核准包（2026-10-19，費用修正版）

Owner於2026-10-19核准本包其餘建議並要求繼續；**未批准任何新增費用**。
本次明確限制優先於下方舊文字／先前費用提案；下方2026-09原始規劃不是即時缺口清單。
Main只維持TASK203同一delivery group，不另開產品／測試框架／一般基礎建設支線。
建議終點：真實staging接線、專用測試帳號完整履行、僅Owner TestFlight驗收。
不是production全員啟用、公開商店發布，也不刪除Owner或其他隊員的既有真實隊務帳號。

### 一次選定的產品與營運規則

| 決策 | 建議採用 | 代價／風險及邊界 |
| --- | --- | --- |
| 刪除範圍 | 沿DEC112/114：同一服務帳號全部provider、登入/session、個人映射及應刪內容；Person僅可留下無法回連的必要技術支點 | 不保證保留具名歷史；不刪整場活動或他人內容，不等同實體退隊 |
| 受理／人工例外 | App先受理並回收據；新鮮本人驗證後封鎖一般存取。可明確判定者自動處理，共用／歧義文字由Owner授權審查，唯獨最後管理員處置走獨立操作身分 | 不要求使用者寄信或等待人工審好才能提出申請；缺審查不能偽造空白批准 |
| 處理目標 | 自受理起30日內履行線上範圍；到期未完成須明示逾期／原因並升級處理，不假稱成功 | 這是提議的服務目標，不是法定期限／Apple指定天數；staging驗證可履行後才能對外公布 |
| 收據與工作資料 | 收據初始存取期限自受理180日；未結案須在到期前依原job／本人證明受控延長或提供等價安全查詢，不得迫使用戶重申請。額外審查原文、可識別sealed plan在線上履行後30日內清除，最小處置紀錄自受理180日檢查清除條件 | 現有immutable evidence不可直接刪；先實作／驗證受控清除及必要延長，再啟用，不把expires欄位偷偷當提醒 |
| 備份／抑制證據 | 最小抑制binding及必要key必須跨越最後可還原副本的驗證失效，再完成抑制驗證才能清除；每30日檢查 | provider保留未知不等於0；不自動在180日刪除或默認永久保留。每job自受理起第150日仍無法界定，停止新不可逆履行／啟用擴張，保留受理、收據查詢及既有未結案證據，提出具體例外決策；不得標completed |
| Provider | Apple／Google／LINE都納入同一服務範圍；只接受可驗證的fresh proof，Google缺nonce契約須在包內補齊或提供等價已review方案 | 不以綁另一provider作刪除前提，不弱化驗證或把普通Google登入token當fresh proof；未知撤銷不盲重送 |
| 最後管理員 | Owner為操作負責人；以獨立DB operator的exact job/gen/epoch批准與管理寫入暫停來履行 | 不自動升權／恢復管理、不走allowlist；保持最後管理員可刪除，異常不因保住管理員而假稱完成 |
| Migration復原 | 若既有staging含不能丟棄資料，允許且要求單次受限加密的migration前備份與隔離還原驗證；成功rollout及恢復驗證後7日內刪備份的活動副本 | 僅同包的可復原性措施，不是長期備份產品；soft-delete等副本及刪除抑制也須查證，程式rollback不能撤銷已完成的刪除 |

人工review來源：先採受保護的內部操作流程，不建通用審查平台。核實操作身分／權限，
將處置綁定row/version/hash與job/generation；唯讀callback只消費已批准資料，不在鎖內等人或聯網。
現有builder在初次request插入前要求review，不能直接當作已完成以上非阻塞受理設計；
本包包含必要且最小的受理／審查階段分離、期限／受控清除相容修正及回歸，不能只換文案。
主責Owner每工作日至少檢視待辦；最後管理員或本人案件由獨立操作憑證確認，不代表自行豁免內容規則。

### 環境、保管、權限與費用

- 唯一DB目標：Supabase ntubtob-mobile-staging / nmjfnhalsabszpfvjale。
  唯一既有服務目標：GCP ntubtob-mobile-staging / asia-east1 / mobile-api-staging；
  先唯讀核對實際DB/Secret reference/traffic。舊wrapper有production project常數，禁止直接沿用。
- 修正先前判斷：已看到Editor的是ntubtob-schedule-405614，不是已證明staging具有同樣IAM。
  先檢查並優先重用既有獨立staging project；不以舊專案Editor直接推導必須新建第三個project。
- 擬定專用bucket：ntubtob-erasure-stg-405614，asia-east1、Standard、uniform access、
  public-access prevention；獨立於DB還原，不放姓名/email/原文。名稱須先確認可用及歸屬。
  無保留鎖、無自動到期刪抑制證據；soft-delete/versioning的額外副本亦納入清除庫存。
  必要migration備份另限ntubtob-erasure-stg-preflight-405614獨立private bucket與專用
  privacy操作身分；一般runtime/custody writer不能讀取。兩bucket皆須在同一核准custody project。
- 若既有staging繼承權限無法達成隔離，本次可條件式建立唯一custody project
  ntubtob-erase-stg-405614，仍只含上述bucket／必要key與專用身分；不開一般雲端遷移支線。
  若project/bucket名稱不可用，或需改billing account／organization／region，停止，不自選其他目標。
- 核准的最小權限差異：DB schema owner／executor／recovery operator分離；
  runtime不持有schema owner、BYPASSRLS或recovery批准權。custody writer僅create/get，
  restore reader僅get/list；真正清除交由獨立有審核的privacy操作身分，不給一般runtime刪證據權。
  同時檢查繼承IAM及SET ROLE；不移除舊服務Editor、不改production任何IAM。
- 允許本包四項獨立用途key（receipt、proof、plan、restore-binding）的建立／版本，依用途
  僅授相應API／executor／restore驗證身分，不對所有runtime一律授權。
  必要備份另用第五把backup加密key，僅受控backup/restore操作身分可存取；一般App/runtime/
  custody writer均無此key權限。全部使用Secret Manager，拒絕公開／長期SA key下載。
  舊登入/provider/signing key不輪替。
  owner帳號憑證不進chat/repo/log；登入/MFA及不可代辦的consent才交Owner操作。
- 費用授權：**新增費用額度為0；原一次性US$20＋US$5/月提案未獲核准，不得執行。**
  優先現有資源／可確認的既有配額；不能把Free標籤或舊IOS-TF-01預算當新增費用授權。
  新資源／Secret versions／CI／建置／部署／簽署即使技術上已核准，仍須先確認不新增費用；
  無法確認者只暫停該操作，source、離線驗證及其他不花錢的接線工作繼續。
  確需付費時一次列SKU／用量／一次性及持續估價／替代方案／不採用代價，再請Owner批准。
  不建立收費備用專案／啟用billing／繞用其他帳號，不以自動刪必要證據或降低安全性省費用。
  本包只採alerts，不宣稱硬cap；不能為省費用刪仍必要的證據或關掉整個project。
  未用付費Supabase升級/PITR、常駐VM、額外SaaS、長期備份服務或公開bucket。

### 執行授權與完成條件

Owner已核准同一任務內最小實作、獨立review、commit/push/單一final PR/必要CI、
staging資料庫唯讀preflight及已測試exact migration、必要上述資源／Secret bindings／IAM、
既有staging服務部署與rollback，以及沿既有簽署路徑更新僅Owner TestFlight。
上述權限全部受「不批准新增費用」限制；不得推定任何雲端或hosted操作免費。
不因commit SHA／同範圍confirmed-zero修正反覆要求核准；不重造controller或一般框架。
所有變更仍須經repository-owned reviewed操作路徑與精確artifact/identity/target檢查。

真實provider I/O只准明確記錄的專用測試identity，且須證明不影響既有production登入。
若共用channel/client造成跨環境撤銷影響，先隔離測試設定；不得拿Owner真實隊務identity試刪。
對不可逆UI動作仍遵守action-time確認；Owner登入/MFA/consent與本人實機驗收無法由預批保證免除。
不發訊息給真實LINE/Discord用戶，不對production DB/traffic/公開App Store發版作任何mutation。

執行順序固定：唯讀環境／角色／資料／備份庫存 -> 檢查點與隔離恢復演練 -> 最小接線／review ->
CI與staging migration/deploy -> 專用pending／linked／blocked與provider/unknown/restore/last-admin情境 ->
Owner安裝驗收。staging測試不擴到真實隊員；所有變更仍維持單一delivery group。
正常驗收恢復副本僅含新建虛構fixture。只有必要的migration前復原副本可包含上述exact
staging DB的既有ntubtob資料（含個資與既有加密credential），不含production或env/Secret payload。
採標準工具與已review薄操作路徑，外層加密後才可落入受限暫存／指定backup bucket，
只可還原到受限隔離測試環境、不對外服務、不輸出資料原文；不能將抑制bucket誤稱DB備份。
發現明文credential或無法安全隔離／還原時停止；不為通過migration而跳過備份或恢復驗證。

完成須有：App送出／fresh proof／存取封鎖／實際限定清理／重啟收據／無重派／他人不受影響，
三provider均可用或以獨立已驗證且不要求額外provider的本人驗證路徑履行；手機實測與rollback證據。
online_completed與備份/provider未完成分開顯示；抑制完成不等於副本已清除，不保證Apple一定過審。

只在新事實需擴權、超額費用、隔離不足、未知不可逆效果、還原失敗、期限/保留無法履行、
或scope必須大改時停止，帶exact stage/check/已知副作用/單一下一步回報，不重複盲試。
production全員開放／真隊員刪除／公開政策發布及公開商店上線不包含在本包。

官方依據（2026-10-16查閱，非平台驗收）：
[Apple帳號刪除](https://developer.apple.com/help/app-review/guideline-reference/5-1-1-account-deletion)
允許合理人工處理時間，但App內須可發起、不可強制客服往返；
[Supabase備份](https://supabase.com/docs/guides/platform/backups)不證明Free provider內部零保留；
[GCS計價](https://cloud.google.com/storage/pricing)含操作／網路／保留副本等成本；
[Billing預算](https://docs.cloud.google.com/billing/docs/how-to/budgets)區分alerts與spend cap。

有效Owner指示：「先不批准新增費用，其餘照建議核准並繼續做，優先用現有資源。
真的需要花錢再一次整理具體估價，不要因此卡住其他工作。」不含production全員開放或真隊員刪除。

## 使用者流程

1. 以Apple首次登入，完成provider驗證。只以verified subject識別，不把姓名或email當配對證明。
2. 已linked且active：沿用正常登入；既有blocked／revoked／刪除中身分不得被當陌生人重建。
3. 真正新subject：建立唯一pending identity與審核thread，不建有權限的Person或一般session。
4. 待審畫面提供兩條清楚路徑：「連結我已有的帳號」及「申請管理員配對／核准」。
   前者保留不同provider既有帳號proof，後者不要求先註冊LINE；均不能讀取完整隊員下拉名冊。
5. 管理員在受保護介面確認身分及目標，配對既有Person或明確核准新身分。
   對應provider、資格、操作影響須可見；不能拿LINE legacy row作Apple批准前提。
6. 核准後使用者重新驗證／重新整理狀態取得正常session；待審credential本身永不升為一般access token。
7. 待審、受限與正常帳號皆可透過本人驗證發起刪除；未持有一般session不得成为永久阻擋理由。

## 原始程式缺口（2026-09-17；即時現況以TASK203 report為準）

- `AppleLifecycleAuthService.exchange`對未知subject回AccountUnavailable；不能只在Flutter改文案。
- `ensure_apple_link_candidate`已有pending primitive，但目前用途是self-link；首次加入意圖與audit原因需明確。
- Apple code是single-use；先驗assertion、一次exchange，確定結果後原子保存必要provider credential／pending狀態。
  DB或網路結果未知不得重送Apple code；錯誤須區分provider交換與本服務保存，不讓使用者反覆盲試。
- 管理員pending列表／approve_member目前限LINE，approve_non_member也依legacy LINE row。
  需抽出provider-neutral批准核心，保留LINE相容adapter與既有權限、maintenance及鎖順序。
- 0013刪除收據只支援Person及active session，且沒有履行；不適用尚無Person的pending identity。
  不能为了使用舊收據而先給pending建立active Person。需另設最小本人證明與subject scope契約。
- 完整帳號刪除牽涉Portal／LINE及背景工作guard，不可只在Mobile封鎖。

## 分段實作、同一上線範圍

| 工作段 | 可離線交付 | 啟用條件 |
| --- | --- | --- |
| A 身分契約與資料盤點 | pending／existing／restricted矩陣、caller與個資儲存清單、虛構fixture | 不改runtime |
| B Apple首次登入及管理核准 | API／repository／Flutter／Portal與race、安全回歸 | 不單獨部署開放新註冊 |
| C 刪除受理與履行 | pending與Person target、有限proof、ledger、共用guard、provider與purge adapter | 所有caller相容，政策與保存範圍可履行 |
| D 整合候選 | 隔離DB／mock provider整合、不可逆步驟dry-run與post-check、獨立review | exact候選與部署計畫核准 |

不為每段增加獨立PR、簽署或Owner重輸入。共用delivery group建議
`apple-onboarding-account-lifecycle`，L3，不適用Flutter UI孵化豁免。
新增schema前須提出additive migration、向後相容與rollback；不先分配revision號。

## 五行execution checkpoint（source實作前更新exact task／paths）

1. 目標：Apple新用戶能受理、被核准或刪除，不能繞過隊務授權。
2. 核心：mobile_api／identity_lifecycle／account_deletion、Portal管理頁、Flutter待審與帳號頁及測試。
3. Invariant：既有人不被合併或登出；pending無業務權限；刪除不波及他人；不復活已刪帳號。
4. 測試：先失敗回歸，再affected auth suites、DB15/16、Flutter focused/analyze及獨立安全review。
5. 邊界：不碰真資料／provider／部署；保存期限及具名名冊例外不能由工程師冒充已核准政策。

## 必測情境

- 未知Apple subject→pending；重複／併發登入最多一identity，無Person／一般session／越權名冊曝光。
- 無效assertion、subject不符、過期nonce、code重放／timeout不得建可用帳號或自動重試外部mutation。
- linked active維持原帳號；inactive／blocked／revoked／deleting不得走新加入繞過限制。
- 同email不同subject不自動合併；兩個陌生provider無法充當existing proof；proof不同人／過期拒絕。
- 管理員新建／既有配對均有明確確認、CSRF與mutation-time重查；與link／刪除競態不重複Person。
- pending刪除限本人identity；linked刪除涵蓋其服務帳號，不只Apple；刪除證明不能讀取業務資料。
- 最後管理員、缺Apple token、provider未知結果、DB回應遺失、離線cache均有真實而不誇大的結果。
- 不刪整場比賽、他人出席或整批通知；舊session／Portal／LINE／outbox無法繞過刪除guard。

## 尚未批准的營運數字

2026-09-18補充DEC-113：共用LINE OA／群組公告維持既有受眾，帳號刪除仍停止個人化通知。
刪除確認與完成頁須說明封鎖OA／退出群組的獨立操作，不能要求先完成這些操作才刪帳。
不得為維持公告而保留登入subject／個人受眾映射；公告按鈕也不能讓已刪帳號恢復存取。
以實際payload／caller查證共用邊界，不以API名稱自動豁免。此決策不是合規或啟用證明。

不把先前建議的30／90日等期限當成這次默認批准。實作可先做fixture、契約及不啟用的基礎；
在對外承諾期限／啟用不可逆履行前，再一次提供實際庫存支持的保存方案供Owner選定。
沒有充分依據，不採「刪帳號但仍保留全部具名歷史」例外。公開政策、真實刪除與上架仍分別驗收。
