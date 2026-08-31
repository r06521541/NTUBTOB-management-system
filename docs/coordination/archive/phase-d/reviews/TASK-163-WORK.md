# TASK-163 Main Work Review

## Verdict

`accepted_merged`

## Accepted behavior

- Active Officer／Admin 可管理 Event draft、Activity itinerary、eligibility preview、manual override、publish與cancel；basic／inactive／typed-key mismatch在service mutation前fail closed。
- Publish與qualification／override共用序列化邊界，建立immutable invitee snapshot；InMemory以local-copy atomic commit避免failure留下partial audit／snapshot。
- Published edit不重算snapshot；edit／cancel有append-only audit且不觸發notification或Game write。
- Mutation request ID綁exact operation／target／payload／optimistic version；cross-operation與不同payload碰撞拒絕，Activity boundary no-op仍先驗replay。
- Web使用session CSRF、server-owned actor、canonical typed keys、Taipei-aware input、PRG及初始化完成前disabled的站內確認。
- Manager selector只投影display name與opaque person key，不投影contact／provider identity。

## Evidence

- Writer：repository／migration 22 passed；PostgreSQL 19 skipped（本機無isolated DB）；Web Portal 221/221 passed；compile、Node syntax、formatter API與`git diff --check` passed。
- Independent Data／Authorization review：correction round 2 final `ACCEPT`；snapshot atomicity／serialization、typed key、exact replay及minimal manager projection均無剩餘blocker。
- Main focused：2項request replay／boundary regressions與2項Web confirmation/static contract passed；首次直接module命令因class name／Web test cwd錯誤未啟動測試，改用supported exact targets後通過。
- Hosted run `33075904432`：PostgreSQL 15／16未通過；failure限定於三個upgrade-to-head assertion仍期待`0008`，以及Phase C reset以`head -> downgrade 0003`碰到`0009`刻意保留的audit constraint。Writer correction改為current head `0009` assertion與真正重建isolated legacy schema；此紀錄不是hosted acceptance。
- Final hosted run `33077406624`：PostgreSQL 15／16及全部selected gates passed；PR #209 conflict-free merged as `c1dd1e3e75e373da6991748b8e34ab63d86b1c25`。

## Remaining gates and limits

- Repository delivery已完成；run `33075904432` 維持failed evidence，final acceptance以run `33077406624`為準。
- Merge不授權production schema rollout、deployment、real data、notification、Secret、IAM或cloud mutation。
