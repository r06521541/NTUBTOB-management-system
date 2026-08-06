-- TASK-049 Supabase production aggregate data-quality inventory.
--
-- Prerequisite: the catalog inventory confirmed the exact legacy tables and
-- columns referenced below. This query returns counts only. It never selects
-- names, LINE user IDs, tokens, webhook identifiers, or application rows.

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';

WITH metrics AS (
    SELECT '00_table_rows'::text AS section,
           'attendance_reply_types'::text AS metric,
           count(*)::bigint AS value
    FROM ntubtob.attendance_reply_types

    UNION ALL
    SELECT '00_table_rows', 'ballparks', count(*)::bigint
    FROM ntubtob.ballparks

    UNION ALL
    SELECT '00_table_rows', 'cancellations', count(*)::bigint
    FROM ntubtob.cancellations

    UNION ALL
    SELECT '00_table_rows', 'discord_webhooks', count(*)::bigint
    FROM ntubtob.discord_webhooks

    UNION ALL
    SELECT '00_table_rows', 'game_attendance_replies', count(*)::bigint
    FROM ntubtob.game_attendance_replies

    UNION ALL
    SELECT '00_table_rows', 'games', count(*)::bigint
    FROM ntubtob.games

    UNION ALL
    SELECT '00_table_rows', 'line_groups', count(*)::bigint
    FROM ntubtob.line_groups

    UNION ALL
    SELECT '00_table_rows', 'line_notify_tokens', count(*)::bigint
    FROM ntubtob.line_notify_tokens

    UNION ALL
    SELECT '00_table_rows', 'line_users', count(*)::bigint
    FROM ntubtob.line_users

    UNION ALL
    SELECT '00_table_rows', 'members', count(*)::bigint
    FROM ntubtob.members

    UNION ALL
    SELECT '01_members', 'blank_name_rows', count(*)::bigint
    FROM ntubtob.members
    WHERE btrim(name) = ''

    UNION ALL
    SELECT '01_members', 'duplicate_normalized_name_groups', count(*)::bigint
    FROM (
        SELECT lower(btrim(name))
        FROM ntubtob.members
        GROUP BY lower(btrim(name))
        HAVING count(*) > 1
    ) AS duplicate_member_names

    UNION ALL
    SELECT '01_members', 'rows_in_duplicate_normalized_name_groups',
           coalesce(sum(group_size), 0)::bigint
    FROM (
        SELECT count(*)::bigint AS group_size
        FROM ntubtob.members
        GROUP BY lower(btrim(name))
        HAVING count(*) > 1
    ) AS duplicate_member_names

    UNION ALL
    SELECT '02_line_users', 'linked_rows', count(*)::bigint
    FROM ntubtob.line_users
    WHERE member_id IS NOT NULL

    UNION ALL
    SELECT '02_line_users', 'unlinked_rows', count(*)::bigint
    FROM ntubtob.line_users
    WHERE member_id IS NULL

    UNION ALL
    SELECT '02_line_users', 'ignored_rows', count(*)::bigint
    FROM ntubtob.line_users
    WHERE ignored IS TRUE

    UNION ALL
    SELECT '02_line_users', 'unlinked_not_ignored_rows', count(*)::bigint
    FROM ntubtob.line_users
    WHERE member_id IS NULL AND ignored IS FALSE

    UNION ALL
    SELECT '02_line_users', 'duplicate_line_subject_groups', count(*)::bigint
    FROM (
        SELECT line_user_id
        FROM ntubtob.line_users
        GROUP BY line_user_id
        HAVING count(*) > 1
    ) AS duplicate_line_subjects

    UNION ALL
    SELECT '02_line_users', 'rows_in_duplicate_line_subject_groups',
           coalesce(sum(group_size), 0)::bigint
    FROM (
        SELECT count(*)::bigint AS group_size
        FROM ntubtob.line_users
        GROUP BY line_user_id
        HAVING count(*) > 1
    ) AS duplicate_line_subjects

    UNION ALL
    SELECT '02_line_users', 'members_with_multiple_line_accounts', count(*)::bigint
    FROM (
        SELECT member_id
        FROM ntubtob.line_users
        WHERE member_id IS NOT NULL
        GROUP BY member_id
        HAVING count(*) > 1
    ) AS members_with_multiple_accounts

    UNION ALL
    SELECT '02_line_users', 'orphan_member_references', count(*)::bigint
    FROM ntubtob.line_users AS line_user
    WHERE line_user.member_id IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM ntubtob.members AS member
          WHERE member.id = line_user.member_id
      )

    UNION ALL
    SELECT '03_games', 'rows_with_missing_schedule_fields', count(*)::bigint
    FROM ntubtob.games
    WHERE year IS NULL
       OR season IS NULL
       OR start_datetime IS NULL
       OR duration IS NULL
       OR location IS NULL
       OR home_team IS NULL
       OR away_team IS NULL

    UNION ALL
    SELECT '03_games', 'duplicate_natural_key_groups', count(*)::bigint
    FROM (
        SELECT year, season, start_datetime, home_team, away_team
        FROM ntubtob.games
        GROUP BY year, season, start_datetime, home_team, away_team
        HAVING count(*) > 1
    ) AS duplicate_games

    UNION ALL
    SELECT '03_games', 'invited_rows', count(*)::bigint
    FROM ntubtob.games
    WHERE invitation_time IS NOT NULL

    UNION ALL
    SELECT '03_games', 'cancelled_rows', count(*)::bigint
    FROM ntubtob.games
    WHERE cancellation_time IS NOT NULL

    UNION ALL
    SELECT '04_game_attendance', 'null_member_rows', count(*)::bigint
    FROM ntubtob.game_attendance_replies
    WHERE member_id IS NULL

    UNION ALL
    SELECT '04_game_attendance', 'null_user_rows', count(*)::bigint
    FROM ntubtob.game_attendance_replies
    WHERE user_id IS NULL

    UNION ALL
    SELECT '04_game_attendance', 'orphan_game_references', count(*)::bigint
    FROM ntubtob.game_attendance_replies AS reply
    WHERE NOT EXISTS (
        SELECT 1 FROM ntubtob.games AS game WHERE game.id = reply.game_id
    )

    UNION ALL
    SELECT '04_game_attendance', 'orphan_member_references', count(*)::bigint
    FROM ntubtob.game_attendance_replies AS reply
    WHERE reply.member_id IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM ntubtob.members AS member WHERE member.id = reply.member_id
      )

    UNION ALL
    SELECT '04_game_attendance', 'orphan_user_references', count(*)::bigint
    FROM ntubtob.game_attendance_replies AS reply
    WHERE reply.user_id IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM ntubtob.line_users AS line_user WHERE line_user.id = reply.user_id
      )

    UNION ALL
    SELECT '04_game_attendance', 'invalid_reply_type_references', count(*)::bigint
    FROM ntubtob.game_attendance_replies AS reply
    WHERE NOT EXISTS (
        SELECT 1
        FROM ntubtob.attendance_reply_types AS reply_type
        WHERE reply_type.id = reply.reply
    )

    UNION ALL
    SELECT '04_game_attendance', 'duplicate_game_member_groups', count(*)::bigint
    FROM (
        SELECT game_id, member_id
        FROM ntubtob.game_attendance_replies
        WHERE member_id IS NOT NULL
        GROUP BY game_id, member_id
        HAVING count(*) > 1
    ) AS duplicate_game_member_replies

    UNION ALL
    SELECT '04_game_attendance', 'duplicate_game_user_groups', count(*)::bigint
    FROM (
        SELECT game_id, user_id
        FROM ntubtob.game_attendance_replies
        WHERE user_id IS NOT NULL
        GROUP BY game_id, user_id
        HAVING count(*) > 1
    ) AS duplicate_game_user_replies

    UNION ALL
    SELECT '05_cancellations', 'orphan_game_references', count(*)::bigint
    FROM ntubtob.cancellations AS cancellation
    WHERE NOT EXISTS (
        SELECT 1 FROM ntubtob.games AS game WHERE game.id = cancellation.game_id
    )

    UNION ALL
    SELECT '05_cancellations', 'games_with_multiple_cancellation_rows', count(*)::bigint
    FROM (
        SELECT game_id
        FROM ntubtob.cancellations
        GROUP BY game_id
        HAVING count(*) > 1
    ) AS duplicate_cancellations
)
SELECT section, metric, value
FROM metrics
ORDER BY section, metric;

ROLLBACK;
