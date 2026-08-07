# TASK-070：完成 Phase C identity lifecycle、登入與 Person-based attendance

## 任務目標

以一個大型但可離線驗證的工作包，完成Phase C application bridge：讓LINE Login、Person、auth identity、
Member、qualification、核可對話與既有比賽出席在同一套明確規則下運作；管理mutation必須transactional、可稽核、
可重試且fail closed。

本任務包含repository migration與local PostgreSQL演練，但不執行production migration、不連Supabase、不部署、
不啟用production `WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED`，也不發真實LINE／Discord訊息。

## 已確認基準

- Base commit：`926a808dca2ce46f41be6dd4fb74a8059babf80b`。
- Production Phase A revision為`0003_legacy_bigint_activity_game`；Phase B已有197組Member／Person、56個linked
  LINE identities、56個active `team_player`及309筆append-only audits。
- TASK-069已部署default-off guard；production legacy match／ignore POST目前fail closed。
- 現行登入與attendance仍以legacy `line_users.member_id`／`game_attendance_replies.member_id`為核心；production
  attendance catalog顯示`member_id`可null，但目前ORM與analyzer仍假設它一定是Member。
- 現有Web Portal admin權限由`WEB_PORTAL_ADMIN_MEMBER_IDS` allowlist提供；People admin尚未成為授權來源。

## Owner核准的產品規則

### Person、identity與名稱

- 新LINE Login先建立pending identity，不在管理者核可前建立Person；不以nickname、頭貼、formal/display name自動
  配對。
- Person核可或Member配對本身即把合法Person設為active，不要求本人先從Portal登入。
- Person status優先於qualification：非active Person不能登入、查看受保護內容、回覆或參與，即使qualification仍active。
- UI用詞：Person `disabled`顯示「暫停參與」、Person `blocked`顯示「全域封鎖」；identity `disabled`顯示
  「停用登入方式」、identity `blocked`顯示「拒絕此登入帳號」。DB值暫不改名。
- Person停用／封鎖不自動撤銷qualification；永久取消資格必須另做明確mutation。只有active Person可進入disabled／
  blocked，解除後回active，不允許disabled與blocked直接互轉。
- 同一Person可有同provider多帳號；`provider + provider_subject`全域唯一。Identity停用／拒絕只影響該登入方式；
  Person停用／封鎖影響其全部identities。
- linked identity被disabled／blocked時保留person_id，解除後回linked；未連Person的pending identity被blocked後解除則
  回pending。任何identity恢復都不能繞過Person status。
- `display_name`必填、可重複，active Person可自行修改；不參與認證或授權。Admin可代改並填原因。
- 新增nullable `formal_name`與`admin_note`：Member正式姓名唯一來源仍是`members.name`，非Member才使用
  `people.formal_name`；`admin_note`只供admin，絕不進一般頁面、session、通知或audit全文。
- 所有active Person可在賽事頁切換display name／formal name；Member formal name取`members.name`，非Member取
  `people.formal_name`，缺少時fallback display name。通知／管理統計預設formal，缺少才fallback display。
- 不實作Person merge；核可前提供既有Member／Person搜尋與疑似重複警示，remap後保留無identity的舊Person。

### Qualification

- Active Person可沒有qualification，作為純檢視使用者。
- `affiliate`、`guest_player`、`staff`、`team_player`是參與資格，不授予Portal officer/admin權限；未來Event eligibility
  另案。`staff`保留但本輪不硬編碼活動權利。
- 只有allowlist admin可授予、撤銷、恢復qualification；每次需原因與audit。
- Member經LINE配對時若從未有`team_player`，預設授予；LINE只是預設觸發來源，不是持續保有資格的必要條件。
  Unlink／remap最後一個LINE identity也不自動撤銷`team_player`。
- `team_player`只能授予已連Member的Person；非Member參賽使用`guest_player`。Revoked qualification不因配對自動恢復。
- `guest_player`必須有Asia/Taipei開始／結束日期，結束日整日包含、DB上限為隔日00:00 exclusive，最長5年；
  某場比賽是否可回覆依`valid_from <= game.start_datetime < valid_until`判斷，因此可提前回覆未來賽事。
- Revoked qualification立即阻止新增／修改回覆。資格縮短／撤銷不刪attendance：未來不合資格回覆標記無效且不計入
  有效名單，過去歷史保留；恢復後仍符合條件的未來回覆可重新有效。
- 同一場只要active `team_player`或有效`guest_player`任一成立，回覆即有效。

### Ignore、reject、unlink與remap

- Ignore只代表暫時不處理：legacy `ignored=true`、不建立Person、不授資格、不推導disabled／blocked；unignore回pending。
- Pending identity被「拒絕此登入帳號」時設blocked並同步legacy `ignored=true`作相容投影；解除後回pending且
  `ignored=false`。一般ignore則identity仍pending。
- 已配對帳號不能ignore，須走unlink、remap、identity停用或拒絕。
- Unlink把identity改回pending並清除legacy Member link；不刪Person、audit或qualification。
- Remap在單一transaction內把identity與legacy link移至另一既有Person／Member；target為disabled／blocked時拒絕，
  inactive合法target於核可後轉active。舊Person保留qualification，不自動合併或刪除。
- Revoked qualification、People status或identity security狀態不得由match／remap暗中恢復。

### 登入、session與權限過渡

- LINE callback以auth identity→Person為主要read boundary。Identity須linked、Person須active才登入；pending顯示等待
  核可，blocked／disabled拒絕。
- Session只保存`person_id`、`auth_identity_id`及相容期optional `member_id`；每個受保護request用單一有效查詢重新
  載入identity、Person、Member及qualification，不信任cookie內的status／role／qualification。
- 舊Member session只在Member→Person、active Person與linked LINE identity能唯一驗證時安全升級；否則清session並
  重新登入。Identity一旦存在，任何非linked狀態都不得fallback legacy繞過。
- 本輪唯一管理授權來源仍是admin Member allowlist；People `portal_access_level=admin`不單獨取得權限。Allowlist Member
  必須唯一映射Person作audit actor，但不要求People admin role。
- Admin不能停用／封鎖自己Person，也不能unlink／disable／reject／remap目前登入identity。處理另一allowlist admin時
  必須以advisory／row lock保證操作後至少仍有一位active且有linked login的allowlist admin。

### Pending核可對話

- 每個pending／ignored identity有一個私密核可對話串，只供該申請者與allowlist admin；自我介紹選填，不阻擋admin
  直接核可已知帳號。
- 申請者每24小時最多送一則1～1000字純文字；該訊息本身就是提醒，不另設空提醒按鈕。限制使用DB transaction／
  row lock與server time強制。
- 首次建立pending identity與每次合法申請訊息，皆在DB commit後通知Discord admin；重複登入不重複通知。
- Admin回覆不受24小時限制。LINE identity收到的外部提示只寫「Portal有新回覆」，不含回覆全文；delivery失敗不
  回滾Portal訊息。所有local tests必須mock通知。
- Ignored申請者仍可留言；不會自動unignore，但admin在ignored分頁看到未讀badge。Rejected identity不能再留言。
- 核可／reject後對話唯讀。Pending 30天無登入／訊息／admin回覆只標「久未處理」，不自動處分。
- 結案對話全文保留365天後redact，保留metadata與正式audit；本輪只建retention-ready schema、dry-run與local cleanup
  tests，不建立Scheduler、不執行production刪改。

### 既有比賽與attendance

- 所有active核可Person（含純檢視、affiliate、guest player、staff）可查看既有賽程及已回覆名單。
- 一般頁面只顯示尚未回覆人數，不列舉姓名；未來officer/admin高頻參加者洞察另案。
- 只有active `team_player`或比賽時間落在有效期間的active `guest_player`可由Portal或LINE webhook新增／修改回覆。
- Guest資格期間內可回覆所有現有比賽，不另建逐場邀請；沒有回覆的guest不算尚未回覆、不進回覆率分母、也不收
  既有截止提醒。Team player維持既有預期回覆語意。
- Attendance以Person為主體；Member回覆保留legacy member_id，guest member_id為null，不建立假Member。
- Notify cron、LINE webhook及Web Portal共用Person-aware analyzer。Guest回覆納入有效名單並以formal name fallback
  display name呈現；需能標示guest資格。

## Repository migration範圍

新增下一個單一Alembic head（不得改寫0001～0003），至少包含：

- `people.formal_name`、`people.admin_note` nullable及合理長度constraint。
- 擴充`access_audit.action`，為ignore／unignore、unlink／remap、identity disable／enable／reject／unblock、Person profile
  及核可生命週期提供明確action，不用generic action掩蓋語意。
- Pending review threads／messages／notification throttle／closed／retention-redaction所需最小tables、FK、indexes、
  constraints與RLS enabled／zero-policy邊界。
- `game_attendance_replies.person_id` nullable FK/index；以Member.person_id backfill既有rows，驗證0 unresolved後才建立新
  application contract。保留legacy member_id nullable相容性。
- 所有expand／backfill步驟須可由舊版application安全共存；upgrade、pre/post evidence、checksum與local downgrade／
  forward-recovery界線需明說。不得假設production已執行。

若完整設計需要額外欄位或table，Codex可採最小正規化方案，但不得改變上述產品語意、加入活動eligibility或建立
production操作。

## 程式與UI範圍

1. 建立可注入同一Session的identity lifecycle service／repository operations；legacy與portal writes、qualification及
   audits須在單一transaction。不得串接會各自commit的現有methods假裝原子操作。
2. LINE callback建立／重用pending identity與必要legacy candidate row；不建立Person、不自動匹配。接上新principal
   resolution、pending／rejected UX及安全session升級。
3. 將`/match-member`演進為mobile-first「身分與存取管理」：pending／ignored、Person、identities、qualification、
   status、unlink／remap、admin-only audit timeline與核可對話。所有mutation需admin、CSRF、原因、確認與server-side
   revalidation；不提供Person／identity刪除或People role編輯。
4. 個人頁允許active Person修改display name；formal name／admin note只由admin改。一般Person只看目前狀態／資格，
   audit timeline僅admin分頁查看且不得顯示raw JSON、provider subject或敏感內容。
5. Attendance及analyzer改為Person-aware；Web Portal與LINE webhook使用相同eligibility，notify cron相容guest顯示與
   回覆統計。既有Member行為與LINE interaction須回歸保護。
6. Local demo以虛構資料呈現所有身份、對話、管理mutation、姓名切換、guest有效期與attendance；不得連DB、LINE、
   Discord或其他外部服務，production demo仍default-off。
7. 更新drift inventory／checksum／strict validator，接受精確runtime audit／attendance contract，拒絕malformed actor、
   target、identity、action、state、qualification、session或cross-model drift；輸出仍只可為固定aggregate evidence。

## Transaction、競爭與通知要求

- Match／approve／ignore／unignore／reject／unblock／unlink／remap、Person／identity status、qualification與對話節流皆需
  row locks、optimistic/domain checks及明確idempotency。
- 同目標安全重送不得新增audit、qualification或通知；不同目標競爭只能一筆成功且其他fail closed。
- DB commit後才呼叫Discord／LINE helper；delivery失敗不得rollback committed state，亦不得在HTTP retry造成重複DB
  mutation。外部錯誤訊息不得包含subject、姓名、DB row、token或response body。
- Append-only audit不得update/delete；對話retention redaction是獨立受控資料生命週期，不得關閉audit trigger。

## 非目標與安全邊界

- 不讓People admin/officer成為production授權來源，不修改env allowlist內容。
- 不實作Person merge、Member解除、活動eligibility、Event production UI、Google／Apple OAuth或使用者自行綁新identity。
- 不修改Secret、IAM、Scheduler、Cloud Run／Functions config或其他cloud resources。
- 不讀`envs/**/.env.yaml`或Secret，不連／查／寫production DB，不執行production migration／cleanup，不部署。
- 不發真實LINE／Discord、不人工invoke production、不修改正式資料或enable maintenance flag。
- 不進行無關服務重構；shared library變更須搜尋並驗證所有direct callers。

## 必要測試與驗收

### Local PostgreSQL 16

- 由0003升級新head、fresh install、attendance backfill、RLS／constraint／index／single-head、pre/post evidence及必要
  recovery rehearsal全部通過。
- 完整identity狀態矩陣、多人／多identity、same-provider多帳號、last-admin concurrency、retry與failure injection證明
  transaction atomicity。
- Qualification日期、5年上限、revocation／restoration、未來／過去attendance有效性及guest不進未回覆分母。
- Pending對話24小時節流、ignore/reject差異、365天redaction dry-run及零production副作用。
- Drift validator接受合法Phase B＋Phase C資料並拒絕每種tampering／cross-model drift。

### Application suites

- Web Portal：auth callback、principal refresh、session upgrade、admin/CSRF/guard、管理UI、profile、name toggle、pending
  conversation、attendance及demo完整回歸。
- LINE webhook：Member與有效guest成功、其他資格／時間／status失敗、無真實reply／push。
- Notify cron：Person-aware attendance統計、formal/display fallback、guest呈現、health/import無副作用。
- Shared library重建並安裝sdist；執行所有直接受影響apps/functions tests、Python 3.10 compile/import及artifact verifier。
- 外部HTTP／LINE／Discord全部mock；不得因測試讀取production env或網路。

建議至少執行：

```powershell
python -m unittest discover -s apps/web_portal/tests -v
python -m unittest discover -s functions/line_webhook_handler/tests -v
python -m unittest discover -s apps/notify_cronjob_service/tests -v
python -m unittest discover -s tests/portal_data -v
python -m compileall -q apps/web_portal apps/notify_cronjob_service functions/line_webhook_handler shared_lib tools tests/portal_data
git diff --check
git status --short
```

Hosted PR CI必須使用Python 3.10並跑完整required suites。Windows缺少`make/sh`時使用bundled／launcher Python執行等價
命令，不修改Makefile規避環境問題。

## 停止條件

- 需要production DB／migration、Secret、IAM、Scheduler、deployment或真實通知才能繼續。
- 無法讓舊版application與expand migration安全共存，或attendance backfill有unresolved Person。
- 必須改變Owner已核准的status、qualification、可見性、對話、姓名或admin授權語意。
- 需要Person merge、Member解除、Event eligibility或People role正式切換。
- Audit／error／notification必須曝露provider subject、admin note、Secret或不必要個資。
- 主要架構無法在Python 3.10、Flask/Jinja及既有SQLAlchemy/Alembic邊界安全延伸而需大型重寫。

## 交付物

- 下一個Alembic migration、checksummed pre/post evidence與local rehearsal。
- Identity lifecycle／principal／pending conversation／attendance domain與repository實作。
- Web Portal、LINE webhook、notify cron及demo接線與tests。
- 更新README／local migration runbook／drift validator。
- `docs/coordination/reports/TASK-070-CODEX.md`與最終`HANDOFF.yaml`。

## 授權

Owner已逐項核准上述產品規則、local implementation及一般Git／PR工作包。依長期授權，可在實際diff、required CI與
Work驗收無blocking finding後自行commit、push、建立／ready PR及squash merge。此授權不包含production migration／
data operation、deployment、maintenance flag、Secret／IAM／Scheduler、真實通知或範圍擴張。

## Base commit

`926a808dca2ce46f41be6dd4fb74a8059babf80b`
