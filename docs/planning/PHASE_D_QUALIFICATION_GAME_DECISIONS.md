# Phase D Qualification／Game 決策紀錄

用途：提供主 Work session 作為 `phase-d-qualification-and-game-operations` 的產品規格輸入。

## Qualification 語意

- 正式 Member 自動具備 `team_player`。
- `team_player` 與其他 qualification 互斥；`guest_player`、`affiliate`、`staff` 可彼此並存。
- inactive Member 保留歷史 `team_player`，但不自動進入新 Game 邀請／roster／出席候選名單；歷史 Game roster、出席、統計仍顯示。
- `guest_player` 只能由 Officer／Admin 明確授予，可參加所有 Game，直到撤銷或到期。
- `affiliate`／`staff` 不自動出現在 Game 邀請候選名單，也不能以 Game-specific override 參加 Game。
- 資格撤銷保留歷史與 audit，不再進入新候選名單。
- 只有 guest_player 需要有效期間；到期只影響未來 Game，既有 Game 永遠保留。
- 授予／撤銷 guest_player、affiliate、staff 都需要 reason 與 audit。
- Officer 可授予 guest_player、affiliate、staff；team_player 由 Member 自動產生。

## Person 狀態與資格

- Admin 新增 Member 時建立 inactive Person，並自動具備 team_player。
- Officer／Admin 可將 Person 啟用為 active；合法途徑是連結正式 Member 或授予其他有效資格。
- 授予有效資格給 inactive Person 時自動轉 active。
- Person 沒有 Member 且所有非 team_player 資格撤銷時，轉為 pending。
- pending 使用 `pending_reason`／substatus 區分 `identity_review`、`qualification_review`、`member_link_required`。
- pending Person 保留完整 qualification、Game roster、出席與統計歷史；停止新的登入／邀請／roster 候選資格。
- pending 不出現在 Basic 一般 Person 列表，只由 Officer／Admin 管理。

## Game 邀請、Roster 與統計

- Game 邀請／roster 在建立或發布時保存資格來源快照；後續資格變更不自動改寫原快照。
- 沒有適用資格者不能直接加入 Game；必須先建立相應長期 qualification。
- 已發布 Game 的新增／重新加入使用明確 roster override，保存加入時間、操作者與來源。
- 重新加入不需新 reason／audit，但仍須確認目前有有效資格。
- 資格撤銷後，既有 Game 是否保留由 Officer／Admin 個別決定；保留／移除都必須 audit。
- guest_player 出席與表現保留，但預設不計入正式隊員統計；報表可切換 guest 維度。
- 從 roster 移除者保留出席歷史並標記已移出；移除需 reason／audit。
- 移除後重新加入的有效資格檢查仍不可省略。
- Game 出席／統計人工修正由 Officer／Admin 執行，需 reason／audit。
- 過去 Game roster 顯示目前最新球員資料；資格標示也顯示目前最新資格。
- affiliate／staff 不得參加 Game。

## 球員資料

- Basic 可查看球衣背號、守位、打擊／投球資料。
- 球衣背號只有 Officer／Admin 可修改；guest 背號可重複，正式 team_player 的目前背號不可重複。
- 球衣背號只保留目前值，不保存歷史變更；修改需要 audit。
- 其他球員欄位本人、Officer、Admin 都可修改；不要求 audit。
- 守位採結構化資料：一個主要守位、多個次要守位，支援具體守位與「內野／外野」等籠統選項。
- 慣用打擊手：右／左／左右開弓／未提供。
- 慣用投球手：右／左／不投球／未提供。

## Person 列表與可見性

- Basic Person 列表只提供低敏資料；電話、醫療、私人備註、完整 provider subject 不可見。
- 列表預設只顯示目前正式 team_player；可切換查看歷史 team_player。
- guest_player 使用獨立篩選，不混入目前正式球員篩選。
- 可提供目前正式球員、Guest player、歷史正式球員、Staff、Affiliate 篩選。
- Staff／Affiliate 篩選：Basic 只看低敏摘要；Officer／Admin 可看較完整資料。
- inactive team_player 個人小卡不特別強調 inactive；列表提供「只顯示目前球員」切換。

## 尚待後續補定

- 目前缺少的球員欄位與正式資料來源。
- Person pending reason 的精確轉移矩陣與 UI 文案。
- Game roster 快照的 schema／read model 及歷史資格顯示細節。
- 球衣背號的「目前有效 team_player」唯一性範圍。
- Staff／Affiliate 的完整資料可見欄位清單。

## Game 管理與異動

- Officer／Admin 都可建立、編輯、取消 Game。
- 聯盟匯入 Game 可由 Officer／Admin 人工覆寫；覆寫需 reason／audit，且 crawler 不得覆蓋人工值。
- 提供「還原匯入值」操作；Officer／Admin 可執行，但需確認、reason／audit。
- Game 日期不可直接修改；改期採系統化流程：原 Game 標記 cancelled、建立新 Game、保留新舊關聯與歷史。
- 球場可直接修改，保留原 Game／roster／出席，並通知出席／待確認者。
- 對手可直接修改，保留原 Game／roster／出席，但不自動通知。
- 取消 Game 保留邀請、roster、出席與統計歷史，並通知所有原邀請者。
- 日期改期建立新 Game 時，通知原 Game 的所有邀請者。
- Game 時間／球場必要異動的自動通知目前採 LINE＋Discord 雙渠道。
- LINE／Discord 分開處理；一渠道失敗不阻塞另一渠道，失敗留下紀錄。
- 自動通知至少具備基本發送紀錄與重複防護；不要求每次人工二次確認。
- 自動通知目前只針對時間與球場異動；日期改由改期流程通知，對手變更不通知。

## Game 顯示與資料原則

- Game roster／統計中的球員資料顯示目前最新值，不保存球員欄位歷史快照。
- Game roster／統計中的資格顯示目前最新資格。
- 已過期 guest_player 只在 Officer／Admin 畫面標示資格已到期，Basic 不特別顯示。
- `affiliate`／`staff` 不得參加 Game。
