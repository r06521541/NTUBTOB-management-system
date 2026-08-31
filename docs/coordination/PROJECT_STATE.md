# 專案狀態

更新時間：2026-08-31

維護角色：Main Work

Repository authority HEAD：`b05a6df3feeef6631dc8b3d95e42fb19a15a6087`

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
- Apple nonce-bound identity-token login/link repository slice已完成；verified stable`sub`是唯一identity key，不以
  email/name自動合併。Authorization-code validation、Apple refresh token、credential-state、server notification、
  revocation lifecycle、Apple Developer capability/profile、runtime binding與real-device/TestFlight仍未完成。

### Release and engineering

- Android repository release contract固定package`tw.org.ntubtob.portal`、API 36、Basic-only
  `android-closed + staging:real`、external signing、monotonic version與strict AAB inspection；production/mixed target
  fail closed。這是repository evidence，不是已上傳的store candidate。
- iOS有TestFlight/App Store fail-closed config與Sign in with Apple source contract；macOS/Xcode、signed archive、provider、
  capability/profile與real-device evidence仍是外部gate。
- CI對changed Python使用bounded pinned quality runner；text digest canonicalize LF，binary digest維持raw bytes；
  docs/archive與核准bootstrap wrapper可走quick gate，unknown/shared/workflow仍fail-safe full。

## Confirmed production state

- Web Portal：`web-portal-00054-rtp`，100% traffic；image tag commit
  `0d6efacac2f20fe1ff66f1aa9ae84fd888ab0961`。Identity maintenance為true，identity-link plain runtime config未完整啟用。
- LINE webhook：`line-webhook-handler-00013-yab`，100% traffic，公開入口仍驗證LINE signature。
- Notify cron：`notify-cronjob-service-00017-qms`，100% traffic並維持private。
- Web Portal與LINE webhook僅保留必要public ingress；四個既有Web Portal Secret references與runtime identity在最近部署
  post-check未漂移。LINE token／channel secret由Secret Manager version 2綁定，active env不保存plaintext。
- 已棄用LINE Notify API與legacy`line_notify_tokens`；LINE Official Account／Messaging API、LINE Login／webhook與
  Discord是不同能力。

## Active work and external gates

- TASK-169保留active：repository release-readiness已合併，但Android/iOS store、signing、provider、production backend、
  device與public-release gates仍是現在的release boundary。
- TASK-170保留active：repository Android candidate contract已通過review/CI；外部階段等待Owner Google Play developer-
  account verification。尚未建立Play app、產生／上傳exact Closed Testing AAB或完成store/device evidence。
- Production mobile deployment、Google production publishing/client migration、Apple provider lifecycle、iOS signing／
  TestFlight、Android public release、push/deep-link delivery與anonymous crash evidence都需未來exact Owner gate。
- Event attendance尚待production deployment；Event notification與guest-player管理仍未成為production capability。
- People role尚未cut over production admin allowlist；last-admin、self-lockout、audit atomicity仍是未來持久角色gate。
- Owner尚未完成一般browser與LINE in-app的production人工smoke；自然Scheduler與低流量長期observation不足，不能以
  缺少error log推定所有通知情境已驗證。

## Documentation lifecycle

- Completed TASK-142～168、171～173的原始task/report/review群組已由merged Git ancestry證據索引至
  `archive/phase-d/PHASE_D_CLOSEOUT.md`；archive只證明歷史，不授權現在操作。
- Active入口只保留TASK-169、170及其current evidence；目前沒有assigned active task。任何完成狀態不明或外部gate仍由
  該task承載的群組不得封存。
- 當前task與next actor只看`HANDOFF.yaml`；協作規則看`COLLABORATION.md`；長期決策看`DECISIONS.md`。

## Safety boundary

- Production固定採read-only discovery → Owner exact approval → one-shot execution → immediate post-check；結果不確定先
  read-only reconcile，不重送mutation。
- 不讀取或提交`envs/**/.env.yaml`、private env、credential、token、password或Secret payload。
- Store／provider／release signing／production／真實通知／正式資料與不可逆操作不得從staging、merge、archive或
  repository contract推定授權。
