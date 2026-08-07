# TASK-049 Supabase catalog（去識別化）

本文件保存 Owner 於 2026-08-06 在 Supabase SQL Editor 執行 TASK-049 read-only catalog
query 後取得的 production schema 證據。原始結果經 Work 去識別化，只保留下列 migration
rehearsal 必要 metadata：

- table names 與 RLS flags
- column names、types、nullable、defaults、identity、generated
- primary key 與 foreign key constraints

已移除 database、current user、owner、table privileges、sizes、row estimates 及 connection
context。這份證據不包含 application row values、姓名、LINE ID、token、webhook identifier、
Secret 或 connection string。Catalog 當時沒有回傳 `ntubtob` RLS policy rows、custom triggers
或 custom functions；這只代表查詢當時的 metadata evidence，不授權 production 變更。

## Tables and RLS flags

| table | RLS enabled | RLS forced |
| --- | --- | --- |
| attendance_reply_types | true | false |
| ballparks | true | false |
| cancellations | true | false |
| discord_webhooks | true | false |
| game_attendance_replies | true | false |
| games | true | false |
| line_groups | true | false |
| line_notify_tokens | true | false |
| line_users | true | false |
| members | true | false |

## Columns

| table.column | data type | UDT | nullable | default | identity | generated |
| --- | --- | --- | --- | --- | --- | --- |
| attendance_reply_types.description | character varying | varchar | NO | NULL | NO | NEVER |
| attendance_reply_types.id | bigint | int8 | NO | NULL | YES | NEVER |
| ballparks.city_name | character varying | varchar | YES | NULL | NO | NEVER |
| ballparks.city_weather_code | character varying | varchar | YES | NULL | NO | NEVER |
| ballparks.district_name | character varying | varchar | YES | NULL | NO | NEVER |
| ballparks.id | bigint | int8 | NO | NULL | YES | NEVER |
| ballparks.name | character varying | varchar | NO | NULL | NO | NEVER |
| cancellations.announced | boolean | bool | YES | NULL | NO | NEVER |
| cancellations.cancellation_time | timestamp with time zone | timestamptz | NO | NULL | NO | NEVER |
| cancellations.game_id | bigint | int8 | NO | NULL | NO | NEVER |
| cancellations.id | bigint | int8 | NO | NULL | YES | NEVER |
| discord_webhooks.created_at | timestamp with time zone | timestamptz | YES | NULL | NO | NEVER |
| discord_webhooks.description | character varying | varchar | YES | NULL | NO | NEVER |
| discord_webhooks.id | bigint | int8 | NO | NULL | YES | NEVER |
| discord_webhooks.webhook_identifier | character varying | varchar | NO | NULL | NO | NEVER |
| game_attendance_replies.game_id | bigint | int8 | NO | NULL | NO | NEVER |
| game_attendance_replies.id | bigint | int8 | NO | NULL | YES | NEVER |
| game_attendance_replies.member_id | bigint | int8 | YES | NULL | NO | NEVER |
| game_attendance_replies.reply | smallint | int2 | NO | NULL | NO | NEVER |
| game_attendance_replies.updated_at | timestamp with time zone | timestamptz | NO | now() | NO | NEVER |
| game_attendance_replies.user_id | bigint | int8 | YES | NULL | NO | NEVER |
| games.away_team | character varying | varchar | YES | NULL | NO | NEVER |
| games.cancellation_announcement_time | timestamp with time zone | timestamptz | YES | NULL | NO | NEVER |
| games.cancellation_time | timestamp with time zone | timestamptz | YES | NULL | NO | NEVER |
| games.duration | smallint | int2 | YES | NULL | NO | NEVER |
| games.home_team | character varying | varchar | YES | NULL | NO | NEVER |
| games.id | bigint | int8 | NO | NULL | YES | NEVER |
| games.invitation_time | timestamp with time zone | timestamptz | YES | NULL | NO | NEVER |
| games.location | character varying | varchar | YES | NULL | NO | NEVER |
| games.season | smallint | int2 | YES | NULL | NO | NEVER |
| games.start_datetime | timestamp with time zone | timestamptz | YES | NULL | NO | NEVER |
| games.year | smallint | int2 | YES | NULL | NO | NEVER |
| line_groups.created_at | timestamp with time zone | timestamptz | NO | now() | NO | NEVER |
| line_groups.description | character varying | varchar | YES | NULL | NO | NEVER |
| line_groups.id | bigint | int8 | NO | NULL | YES | NEVER |
| line_groups.is_broadcast_enabled | boolean | bool | NO | false | NO | NEVER |
| line_groups.line_group_id | character varying | varchar | YES | NULL | NO | NEVER |
| line_notify_tokens.description | character varying | varchar | YES | NULL | NO | NEVER |
| line_notify_tokens.id | bigint | int8 | NO | NULL | YES | NEVER |
| line_notify_tokens.token | character varying | varchar | NO | NULL | NO | NEVER |
| line_users.has_replied | boolean | bool | NO | false | NO | NEVER |
| line_users.id | bigint | int8 | NO | NULL | YES | NEVER |
| line_users.ignored | boolean | bool | NO | false | NO | NEVER |
| line_users.line_user_id | character varying | varchar | NO | NULL | NO | NEVER |
| line_users.member_id | bigint | int8 | YES | NULL | NO | NEVER |
| line_users.nickname | character varying | varchar | NO | NULL | NO | NEVER |
| line_users.submit_time | timestamp with time zone | timestamptz | YES | `(now() AT TIME ZONE 'CCT'::text)` | NO | NEVER |
| members.enroll_year | smallint | int2 | YES | NULL | NO | NEVER |
| members.id | bigint | int8 | NO | NULL | YES | NEVER |
| members.major | character varying | varchar | YES | NULL | NO | NEVER |
| members.name | character varying | varchar | NO | NULL | NO | NEVER |
| members.number | smallint | int2 | YES | NULL | NO | NEVER |
| members.positions | character varying | varchar | YES | NULL | NO | NEVER |

## Primary and foreign key constraints

| table.constraint | type | definition | validated |
| --- | --- | --- | --- |
| attendance_reply_types.attendance_reply_types_pkey | primary_key | PRIMARY KEY (id) | true |
| ballparks.ballparks_pkey | primary_key | PRIMARY KEY (id) | true |
| cancellations.cancellations_pkey | primary_key | PRIMARY KEY (id) | true |
| cancellations.ntubtob_cancellations_game_id_fkey | foreign_key | FOREIGN KEY (game_id) REFERENCES ntubtob.games(id) | true |
| discord_webhooks.discord_webhooks_pkey | primary_key | PRIMARY KEY (id) | true |
| game_attendance_replies.game_attendance_reply_pkey | primary_key | PRIMARY KEY (id) | true |
| game_attendance_replies.ntubtob_game_attendance_replies_reply_fkey | foreign_key | FOREIGN KEY (reply) REFERENCES ntubtob.attendance_reply_types(id) | true |
| game_attendance_replies.ntubtob_game_attendance_reply_game_id_fkey | foreign_key | FOREIGN KEY (game_id) REFERENCES ntubtob.games(id) | true |
| game_attendance_replies.ntubtob_game_attendance_reply_member_id_fkey | foreign_key | FOREIGN KEY (member_id) REFERENCES ntubtob.members(id) | true |
| game_attendance_replies.ntubtob_game_attendance_reply_user_id_fkey | foreign_key | FOREIGN KEY (user_id) REFERENCES ntubtob.line_users(id) | true |
| games.games_pkey | primary_key | PRIMARY KEY (id) | true |
| line_groups.line_groups_pkey | primary_key | PRIMARY KEY (id) | true |
| line_notify_tokens.line_notify_tokens_pkey | primary_key | PRIMARY KEY (id) | true |
| line_users.line_users_pkey | primary_key | PRIMARY KEY (id) | true |
| line_users.ntubtob_line_users_member_id_fkey | foreign_key | FOREIGN KEY (member_id) REFERENCES ntubtob.members(id) | true |
| members.members_pkey | primary_key | PRIMARY KEY (id) | true |

## Evidence boundary

- Confirmed facts are limited to the catalog snapshot above and TASK-049 aggregate review.
- `RLS enabled=true` with no returned policy rows does not prove any particular runtime access path.
- Identity columns are recorded as catalog metadata; sequence names and current values are intentionally omitted.
- This file is suitable for local fake-fixture fidelity and migration review only. It is not executable SQL and
  does not authorize production access, stamp, DDL, backfill or deployment.
