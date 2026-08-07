-- TASK-052 Supabase access-boundary inventory.
-- REVIEWED QUERY ONLY: Owner execution requires separate explicit approval.
-- Output is deliberately limited to generic flags, counts and a major version.

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';

WITH legacy_tables(table_name) AS (
    VALUES
        ('attendance_reply_types'), ('ballparks'), ('cancellations'),
        ('discord_webhooks'), ('game_attendance_replies'), ('games'),
        ('line_groups'), ('line_notify_tokens'), ('line_users'), ('members')
),
portal_tables(table_name) AS (
    VALUES
        ('access_audit'), ('activities'), ('activity_attendance_replies'),
        ('auth_identities'), ('event_attendance_replies'), ('event_audit'),
        ('event_eligibility_rules'), ('event_invitee_overrides'),
        ('event_invitees'), ('event_managers'), ('events'), ('people'),
        ('person_qualifications')
),
relations AS (
    SELECT c.oid, c.relname, c.relowner, c.relrowsecurity, c.relforcerowsecurity
    FROM pg_catalog.pg_class AS c
    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'ntubtob' AND c.relkind IN ('r', 'p')
),
session_role AS (
    SELECT r.oid, r.rolsuper, r.rolbypassrls, r.rolcreaterole, r.rolcreatedb
    FROM pg_catalog.pg_roles AS r
    WHERE r.rolname = CURRENT_USER
),
table_fingerprint AS (
    SELECT md5(string_agg(
        r.relname || '|' || r.relrowsecurity::text || '|' || r.relforcerowsecurity::text,
        E'\n' ORDER BY r.relname
    )) AS value
    FROM relations AS r
    JOIN legacy_tables AS expected ON expected.table_name = r.relname
),
column_fingerprint AS (
    SELECT md5(string_agg(
        col.table_name || '.' || col.column_name || '|' || col.data_type || '|' ||
        col.udt_name || '|' || col.is_nullable || '|' ||
        COALESCE(col.column_default, 'NULL') || '|' || col.is_identity || '|' ||
        col.is_generated,
        E'\n' ORDER BY col.table_name, col.column_name
    )) AS value
    FROM information_schema.columns AS col
    JOIN legacy_tables AS expected ON expected.table_name = col.table_name
    WHERE col.table_schema = 'ntubtob'
),
constraint_fingerprint AS (
    SELECT md5(string_agg(
        rel.relname || '.' || con.conname || '|' ||
        CASE con.contype WHEN 'p' THEN 'primary_key' WHEN 'f' THEN 'foreign_key' ELSE con.contype::text END || '|' ||
        pg_catalog.pg_get_constraintdef(con.oid, true) || '|' || con.convalidated::text,
        E'\n' ORDER BY rel.relname, con.conname
    )) AS value
    FROM pg_catalog.pg_constraint AS con
    JOIN pg_catalog.pg_class AS rel ON rel.oid = con.conrelid
    JOIN pg_catalog.pg_namespace AS n ON n.oid = rel.relnamespace
    JOIN legacy_tables AS expected ON expected.table_name = rel.relname
    WHERE n.nspname = 'ntubtob' AND con.contype IN ('p', 'f')
),
inventory(section, metric, status, boolean_value, integer_value, text_value) AS (
    SELECT '00_session', 'transaction_read_only', 'required',
           current_setting('transaction_read_only') = 'on', NULL::bigint, NULL::text
    UNION ALL SELECT '00_session', 'server_major', 'info', NULL,
           current_setting('server_version_num')::integer / 10000, NULL
    UNION ALL SELECT '00_session', 'session_is_superuser', 'risk', sr.rolsuper, NULL, NULL
           FROM session_role AS sr
    UNION ALL SELECT '00_session', 'session_bypasses_rls', 'risk', sr.rolbypassrls, NULL, NULL
           FROM session_role AS sr
    UNION ALL SELECT '00_session', 'session_can_create_role', 'risk', sr.rolcreaterole, NULL, NULL
           FROM session_role AS sr
    UNION ALL SELECT '00_session', 'session_can_create_database', 'risk', sr.rolcreatedb, NULL, NULL
           FROM session_role AS sr

    UNION ALL SELECT '01_schema', 'ntubtob_exists', 'required',
           EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = 'ntubtob'), NULL, NULL
    UNION ALL SELECT '01_schema', 'session_has_usage', 'info',
           COALESCE((SELECT pg_catalog.has_schema_privilege(n.oid, 'USAGE')
                     FROM pg_catalog.pg_namespace AS n WHERE n.nspname = 'ntubtob'), false), NULL, NULL
    UNION ALL SELECT '01_schema', 'session_has_create', 'risk',
           COALESCE((SELECT pg_catalog.has_schema_privilege(n.oid, 'CREATE')
                     FROM pg_catalog.pg_namespace AS n WHERE n.nspname = 'ntubtob'), false), NULL, NULL
    UNION ALL SELECT '01_schema', 'schema_owner_relation', 'info', NULL, NULL, COALESCE((
           SELECT CASE WHEN n.nspowner = sr.oid THEN 'same' ELSE 'different' END
           FROM pg_catalog.pg_namespace AS n CROSS JOIN session_role AS sr
           WHERE n.nspname = 'ntubtob'
           ), 'unknown')

    UNION ALL SELECT '02_catalog', 'legacy_table_count', 'required', NULL, count(*), NULL
           FROM relations AS r JOIN legacy_tables AS e ON e.table_name = r.relname
    UNION ALL SELECT '02_catalog', 'legacy_table_fingerprint_matches', 'required',
           COALESCE(tf.value = '210bc2099cf9e95bac888a69d0c1a82c', false), NULL, NULL FROM table_fingerprint AS tf
    UNION ALL SELECT '02_catalog', 'legacy_column_fingerprint_matches', 'required',
           COALESCE(cf.value = 'e7bae24dd9d7376be662fa4e33462185', false), NULL, NULL FROM column_fingerprint AS cf
    UNION ALL SELECT '02_catalog', 'legacy_constraint_fingerprint_matches', 'required',
           COALESCE(cf.value = '0a1b070c6f8d607b118e6b3acf7c2467', false), NULL, NULL FROM constraint_fingerprint AS cf
    UNION ALL SELECT '02_catalog', 'alembic_version_exists', 'stop_if_true',
           EXISTS (SELECT 1 FROM relations WHERE relname = 'alembic_version'), NULL, NULL
    UNION ALL SELECT '02_catalog', 'new_portal_table_count', 'stop_if_nonzero', NULL, count(*), NULL
           FROM relations AS r JOIN portal_tables AS p ON p.table_name = r.relname

    UNION ALL SELECT '03_owner', 'legacy_owned_by_session_count', 'risk', NULL, count(*), NULL
           FROM relations AS r JOIN legacy_tables AS e ON e.table_name = r.relname
           CROSS JOIN session_role AS sr WHERE r.relowner = sr.oid
    UNION ALL SELECT '03_owner', 'legacy_owned_by_other_count', 'info', NULL, count(*), NULL
           FROM relations AS r JOIN legacy_tables AS e ON e.table_name = r.relname
           CROSS JOIN session_role AS sr WHERE r.relowner <> sr.oid

    UNION ALL SELECT '04_privilege', 'legacy_selectable_count', 'info', NULL, count(*), NULL
           FROM relations AS r JOIN legacy_tables AS e ON e.table_name = r.relname
           WHERE pg_catalog.has_table_privilege(r.oid, 'SELECT')
    UNION ALL SELECT '04_privilege', 'legacy_insertable_count', 'risk', NULL, count(*), NULL
           FROM relations AS r JOIN legacy_tables AS e ON e.table_name = r.relname
           WHERE pg_catalog.has_table_privilege(r.oid, 'INSERT')
    UNION ALL SELECT '04_privilege', 'legacy_updatable_count', 'risk', NULL, count(*), NULL
           FROM relations AS r JOIN legacy_tables AS e ON e.table_name = r.relname
           WHERE pg_catalog.has_table_privilege(r.oid, 'UPDATE')
    UNION ALL SELECT '04_privilege', 'legacy_deletable_count', 'risk', NULL, count(*), NULL
           FROM relations AS r JOIN legacy_tables AS e ON e.table_name = r.relname
           WHERE pg_catalog.has_table_privilege(r.oid, 'DELETE')
    UNION ALL SELECT '04_privilege', 'legacy_truncatable_count', 'risk', NULL, count(*), NULL
           FROM relations AS r JOIN legacy_tables AS e ON e.table_name = r.relname
           WHERE pg_catalog.has_table_privilege(r.oid, 'TRUNCATE')
    UNION ALL SELECT '04_privilege', 'public_grant_count', 'risk', NULL, count(*), NULL
           FROM information_schema.table_privileges AS tp
           JOIN legacy_tables AS e ON e.table_name = tp.table_name
           WHERE tp.table_schema = 'ntubtob' AND tp.grantee = 'PUBLIC'
    UNION ALL SELECT '04_privilege', 'session_named_grant_count', 'info', NULL, count(*), NULL
           FROM information_schema.table_privileges AS tp
           JOIN legacy_tables AS e ON e.table_name = tp.table_name
           WHERE tp.table_schema = 'ntubtob' AND tp.grantee = CURRENT_USER
    UNION ALL SELECT '04_privilege', 'other_visible_grant_count', 'risk', NULL, count(*), NULL
           FROM information_schema.table_privileges AS tp
           JOIN legacy_tables AS e ON e.table_name = tp.table_name
           WHERE tp.table_schema = 'ntubtob' AND tp.grantee NOT IN ('PUBLIC', CURRENT_USER)
    UNION ALL SELECT '04_privilege', 'visible_write_grant_count', 'risk', NULL, count(*), NULL
           FROM information_schema.table_privileges AS tp
           JOIN legacy_tables AS e ON e.table_name = tp.table_name
           WHERE tp.table_schema = 'ntubtob'
             AND tp.privilege_type IN ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')

    UNION ALL SELECT '05_rls', 'legacy_rls_enabled_count', 'required', NULL, count(*), NULL
           FROM relations AS r JOIN legacy_tables AS e ON e.table_name = r.relname
           WHERE r.relrowsecurity
    UNION ALL SELECT '05_rls', 'legacy_rls_forced_count', 'info', NULL, count(*), NULL
           FROM relations AS r JOIN legacy_tables AS e ON e.table_name = r.relname
           WHERE r.relforcerowsecurity
    UNION ALL SELECT '05_rls', 'policy_count', 'info', NULL, count(*), NULL
           FROM pg_catalog.pg_policies WHERE schemaname = 'ntubtob'
    UNION ALL SELECT '05_rls', 'public_policy_count', 'risk', NULL, count(*), NULL
           FROM pg_catalog.pg_policies WHERE schemaname = 'ntubtob' AND 'public' = ANY(roles)
    UNION ALL SELECT '05_rls', 'write_policy_count', 'risk', NULL, count(*), NULL
           FROM pg_catalog.pg_policies WHERE schemaname = 'ntubtob' AND cmd IN ('ALL', 'INSERT', 'UPDATE', 'DELETE')
    UNION ALL SELECT '05_rls', 'policy_expression_present_count', 'info', NULL, count(*), NULL
           FROM pg_catalog.pg_policies WHERE schemaname = 'ntubtob' AND (qual IS NOT NULL OR with_check IS NOT NULL)
)
SELECT section, metric, status, boolean_value, integer_value, text_value
FROM inventory
ORDER BY section, metric;

ROLLBACK;
