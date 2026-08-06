# 多元活動與複合行程產品方向

更新時間：2026-08-05
狀態：`approved_concept_model`
維護角色：Work

## Owner願景

系統未來除了聯盟比賽，也要支援幹部自行建立：

- 聚餐
- 旅遊／移地活動
- 友誼賽、OB賽等非聯盟比賽
- 一次活動包含多個項目，例如週末旅遊中包含三場比賽、住宿、交通與聚餐

上述活動由具幹部資格的成員建立與管理。

## 初步產品方向

採「Event活動容器＋Activity行程項目」概念：

- Event代表一次完整活動，例如「台中週末移地賽」。
- Activity代表活動內的比賽、聚餐、交通、住宿或其他行程。
- 單場比賽或單次聚餐也可以是簡單Event。
- 比賽來源需區分聯盟匯入與幹部手動建立，避免crawler覆蓋手動內容。
- 出席未來可能分為整體Event與個別Activity兩層，並提供全部參加後個別調整的快速操作。
- Event 依 `person_qualifications` eligibility rules 選人；publish 時產生不可被後續資格變化暗改的 `event_invitees` 快照。
- 管理員可對個人作 manual include/exclude override，但必須保存 actor、reason 與差異。
- Attendance、roster、statistics 明確區分正式 `team_player` 與 `guest_player`。

## 尚未決定

- 哪些 officer/admin capabilities 可以建立、發布、修改或取消活動。
- 活動發布是否需第二位幹部確認，以及發布與通知是否分開。
- 出席採整體、逐項或兩層模式；住宿、交通等是否另有回覆欄位。
- 聯盟匯入賽事如何加入旅遊Event，以及重複賽事辨識規則。
- 異動、取消、通知、稽核與個資可見範圍。

## 建議下一步

另立discovery任務盤點現有`games`、出席、crawler、通知與所有callers，產出：

1. 產品規則與角色權限矩陣。
2. Event／Activity概念模型與相容方案。
3. Migration、backfill、rollout與rollback草案。
4. 可離線操作的Event Builder prototype範圍。

在後續 migration 任務取得 Owner 明確批准前，不修改 Supabase schema、不執行 DDL，也不把多元活動硬塞進既有 `games` 欄位。

TASK-047 已核准 Person access、qualification、Event／Activity、invitee snapshot、既有 Game 相容、兩層出席、migration、rollback 與 local integration 的概念模型，見
[`ROLE_PERSISTENCE_PLAN.md`](ROLE_PERSISTENCE_PLAN.md)。仍不授權 schema 或 production 變更。
