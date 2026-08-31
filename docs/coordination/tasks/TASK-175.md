# TASK-175：Event Notification and Guest-Player Lifecycle

## Task metadata

- task_type: `delivery`
- delivery_group: `task-175-event-guest-lifecycle`
- requires_independent_pr: `true`
- acceptance_level: `L3`（schema／notification／authorization；repository-only）
- base: `ccc5f596dc9560d713dbf93a305c64d2d1642927`
- branch: `codex/task-175-event-guest-lifecycle`
- owner_approved: 2026-09-01

## Product outcome

將已完成的Event／Activity管理與attendance補成可用的內部通知與guest-player管理閉環。Event發布、編輯、取消
仍不自動發通知；Officer／Admin必須從immutable invitee snapshot預覽exact recipient count，以typed confirmation與
idempotency key明確建立durable in-app notification。本任務不接真實push、LINE、Discord或provider delivery。

Guest-player管理只涵蓋stable Person的bounded `guest_player` qualification：授予／延長／撤銷、有效／已過期分類、
reason與append-only audit，以及Event eligibility／immutable invitee snapshot的team／guest分流。不新增無Person的同行者、
不從名字自動配對identity，不將guest計入正式隊員統計。

## Required behavior

1. 新Event notification必須是發布後的獨立操作；preview與confirm都重讀active Officer／Admin、published／
   cancelled state、immutable included invitees與exact event version。預覽變動、snapshot缺失、空或超界audience一律停止。
2. 第一版只建立durable in-app history，destination可回到Event detail。Publish／update／cancel notification type必須
   schema-bounded，recipient rows與publish audit在同transaction建立，同session／idempotency key及同request安全重試，
   conflict或unknown不自動重送。External delivery outbox不建立可發送工作。
3. 收件者只能來自該Event已發布的included invitee snapshot；不依當前qualification重算，不將manual exclude、
   inactive／disabled／blocked Person或其他Event混入。歷史notification保留發送當下的recipient snapshot。
4. Guest-player mutation只對active Person，必須Asia/Taipei-aware bounded period，最長五年、reason、request ID、
   CSRF／server authorization與audit。延長與撤銷重讀actor／target／version；失敗不部分改寫。
5. Web Portal預設顯示active guest，可切換expired／revoked；明確顯示期限、與Member／team-player分類，
   並提供授予／延長／撤銷確認。不顯示provider subject、原始identity或非必要個資。
6. Mobile/Web Event read可安全顯示team／guest分類與in-app notification destination；Basic不取得管理預覽、
   未回覆全名單或qualification mutation capability。
7. Additive migration需與0010 runtime安全共存；新Event notification寫入只在exact new head啟用，舊版LINE／Google／
   Apple login、Game notification與Event attendance不得因migration ordering失效。Downgrade不刪除notification／audit evidence。

## Advisor claims

### Notification/Data advisor

- actor_id: `/root/task170_play_evidence_writer`
- role: `advisor/read-only`
- claim_id: `task-175-event-notification-discovery-20260901`
- lease_version: 1
- scope: 盤點Event snapshot、notification schema/service、Web/Mobile callers與minimal migration/test boundary
- write: `read-only`
- report_to: `/root`

### Guest/Auth advisor

- actor_id: `/root/task170_android_candidate_writer`
- role: `advisor/read-only`
- claim_id: `task-175-guest-auth-discovery-20260901`
- lease_version: 1
- scope: 盤點guest qualification現況、UI gap、authorization/audit/concurrency與minimal tests
- write: `read-only`
- report_to: `/root`

Advisor不得修改working tree、commit、push、PR或外部狀態；完成時必須主動送回full HEAD、findings、
recommended owned paths、tests、limits與external mutations。

## Accepted discovery and writer claim

- Event notification 使用專用 preview／confirm service，不擴張會建立 `push=pending` 的 generic publisher。
- 同一線性 additive `0011` 同時承載 Event notification destination／audit／recipient immutability 與
  guest qualification version／extended audit；不建立 parallel migration head。
- Guest lifecycle 固定為 `scheduled`／`active`／`expired`／`revoked`；Event eligibility 以 Event `start_at` 判定。
- Guest manager 使用狹義 projection／route，不放寬 broad `admin_dashboard`；active persisted Officer 與 active
  allowlisted Member admin 可管理，persisted Admin 本身不足以越過 DEC-082。
- Mobile 本任務只讀 Event 通知／own snapshot category，不新增 guest mutation endpoint。

### Sole writer

- actor_id: `/root/task174_apple_lifecycle_writer`
- role: `codex-writer`
- claim_id: `task-175-event-guest-writer-20260901`
- lease_version: 1
- assigned_head: `82bdb7956d4b8f1a6ef35292779c772e40235c07`
- owned_paths: `migrations/versions/0011_event_notification_guest_lifecycle.py`, Event／notification／qualification related
  sections in `shared_lib/shared_module/**`, `apps/web_portal/**`, `apps/mobile_api/**`, `clients/flutter_app/**`, focused tests,
  `docs/coordination/reports/TASK-175.md`, and this task／HANDOFF status only
- forbidden_paths: broker fixture／adapter, deployment／cloud／Secret／provider operators, unrelated services, archive
- report_to: `/root`

Writer must immediately ACK the exact claim and report target, send a heartbeat every 10–15 minutes, and proactively deliver full
commit SHA／tests／dirty paths／findings／limits／external mutations to Main. One writer owns all shared/schema paths until immutable
handoff; no second writer may edit this branch concurrently.

## Verification budget

- Test-first repository／service／Web／Mobile focused suites。
- PostgreSQL 15.8／16.4 additive migration matrix。
- Web Portal full、Mobile API affected-full、shared callers／OpenAPI／Flutter notification/event focused tests。
- 一位Data／Authorization targeted reviewer與Main diff/scope review。
- 一個ready PR；required hosted CI全綠才可merge。

## Stop conditions

- 需發送真實LINE／push／Discord／email、讀取Secret payload、新provider／IAM／cloud／production／真實使用者或資料mutation。
- 需將Event publish改為自動通知、重算published invitee snapshot、接受client提供recipient IDs或放寬Officer／Admin授權。
- 需新增無Person的guest companion、將guest自動轉Member／team_player、或修改crawler／linked Game ownership。
- dirty paths超出active writer owned paths，或base／branch／claim不一致。

## External boundary

本任務只授權repository branch／commit／push／PR／CI／merge。Production schema／runtime／deployment、真實notification與
guest資料mutation是完成repository delivery後的獨立Owner gate。
