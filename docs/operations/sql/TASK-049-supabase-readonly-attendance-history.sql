-- TASK-049 attendance duplicate classification.
--
-- This read-only query returns aggregate counts only. It distinguishes state
-- changes from consecutive identical replies without exposing any member,
-- user, game, reply, or timestamp value.

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';

WITH grouped AS (
    SELECT game_id, member_id, count(*)::bigint AS group_size
    FROM ntubtob.game_attendance_replies
    GROUP BY game_id, member_id
),
ordered AS (
    SELECT
        game_id,
        member_id,
        user_id,
        reply,
        updated_at,
        row_number() OVER (
            PARTITION BY game_id, member_id
            ORDER BY updated_at, id
        ) AS version_number,
        lag(reply) OVER (
            PARTITION BY game_id, member_id
            ORDER BY updated_at, id
        ) AS previous_reply,
        lag(user_id) OVER (
            PARTITION BY game_id, member_id
            ORDER BY updated_at, id
        ) AS previous_user_id,
        lag(updated_at) OVER (
            PARTITION BY game_id, member_id
            ORDER BY updated_at, id
        ) AS previous_updated_at
    FROM ntubtob.game_attendance_replies
),
exact_duplicate_groups AS (
    SELECT game_id, member_id, user_id, reply, updated_at
    FROM ntubtob.game_attendance_replies
    GROUP BY game_id, member_id, user_id, reply, updated_at
    HAVING count(*) > 1
),
metrics AS (
    SELECT 'duplicate_member_game_groups'::text AS metric,
           count(*) FILTER (WHERE group_size > 1)::bigint AS value
    FROM grouped

    UNION ALL
    SELECT 'rows_in_duplicate_groups',
           coalesce(sum(group_size) FILTER (WHERE group_size > 1), 0)::bigint
    FROM grouped

    UNION ALL
    SELECT 'excess_rows_over_one_per_group',
           coalesce(sum(group_size - 1) FILTER (WHERE group_size > 1), 0)::bigint
    FROM grouped

    UNION ALL
    SELECT 'maximum_versions_in_one_group', coalesce(max(group_size), 0)::bigint
    FROM grouped

    UNION ALL
    SELECT 'consecutive_same_reply_transitions', count(*)::bigint
    FROM ordered
    WHERE version_number > 1 AND reply = previous_reply

    UNION ALL
    SELECT 'consecutive_changed_reply_transitions', count(*)::bigint
    FROM ordered
    WHERE version_number > 1 AND reply <> previous_reply

    UNION ALL
    SELECT 'same_timestamp_transitions', count(*)::bigint
    FROM ordered
    WHERE version_number > 1 AND updated_at = previous_updated_at

    UNION ALL
    SELECT 'user_changed_within_member_game_history', count(*)::bigint
    FROM ordered
    WHERE version_number > 1 AND user_id IS DISTINCT FROM previous_user_id

    UNION ALL
    SELECT 'exact_duplicate_groups', count(*)::bigint
    FROM exact_duplicate_groups

    UNION ALL
    SELECT 'attendance_member_disagrees_with_linked_user', count(*)::bigint
    FROM ntubtob.game_attendance_replies AS attendance
    JOIN ntubtob.line_users AS line_user ON line_user.id = attendance.user_id
    WHERE line_user.member_id IS DISTINCT FROM attendance.member_id
)
SELECT metric, value
FROM metrics
ORDER BY metric;

ROLLBACK;
