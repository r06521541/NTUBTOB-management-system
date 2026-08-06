-- TASK-049 Supabase production schema inventory.
--
-- Safety contract:
--   * This transaction is explicitly read-only and always rolls back.
--   * The query reads PostgreSQL catalogs and metadata only.
--   * It never selects application row values from ntubtob tables.
--   * The output is one table: section, object_name, details.

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';

WITH inventory AS (
    SELECT
        '00_connection_context'::text AS section,
        'current_session'::text AS object_name,
        jsonb_build_object(
            'database', current_database(),
            'current_user', current_user,
            'server_version', current_setting('server_version'),
            'transaction_read_only', current_setting('transaction_read_only'),
            'search_path', current_setting('search_path')
        ) AS details

    UNION ALL

    SELECT
        '01_schema',
        n.nspname,
        jsonb_build_object('owner', pg_get_userbyid(n.nspowner))
    FROM pg_catalog.pg_namespace AS n
    WHERE n.nspname = 'ntubtob'

    UNION ALL

    SELECT
        '02_relation',
        format('%I.%I', n.nspname, c.relname),
        jsonb_build_object(
            'kind', CASE c.relkind
                WHEN 'r' THEN 'table'
                WHEN 'p' THEN 'partitioned_table'
                WHEN 'v' THEN 'view'
                WHEN 'm' THEN 'materialized_view'
                WHEN 'S' THEN 'sequence'
                ELSE c.relkind::text
            END,
            'owner', pg_get_userbyid(c.relowner),
            'estimated_rows', c.reltuples::bigint,
            'total_bytes', CASE
                WHEN c.relkind IN ('r', 'p', 'm')
                THEN pg_total_relation_size(c.oid)
                ELSE NULL
            END,
            'rls_enabled', c.relrowsecurity,
            'rls_forced', c.relforcerowsecurity
        )
    FROM pg_catalog.pg_class AS c
    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'ntubtob'
      AND c.relkind IN ('r', 'p', 'v', 'm', 'S')

    UNION ALL

    SELECT
        '03_column',
        format('%I.%I.%I', col.table_schema, col.table_name, col.column_name),
        jsonb_build_object(
            'ordinal_position', col.ordinal_position,
            'data_type', col.data_type,
            'udt_name', col.udt_name,
            'nullable', col.is_nullable,
            'default', col.column_default,
            'identity', col.is_identity,
            'generated', col.is_generated
        )
    FROM information_schema.columns AS col
    WHERE col.table_schema = 'ntubtob'

    UNION ALL

    SELECT
        '04_constraint',
        format('%I.%I.%I', n.nspname, rel.relname, con.conname),
        jsonb_build_object(
            'type', CASE con.contype
                WHEN 'p' THEN 'primary_key'
                WHEN 'u' THEN 'unique'
                WHEN 'f' THEN 'foreign_key'
                WHEN 'c' THEN 'check'
                WHEN 'x' THEN 'exclude'
                ELSE con.contype::text
            END,
            'definition', pg_get_constraintdef(con.oid, true),
            'validated', con.convalidated,
            'deferrable', con.condeferrable,
            'initially_deferred', con.condeferred
        )
    FROM pg_catalog.pg_constraint AS con
    JOIN pg_catalog.pg_class AS rel ON rel.oid = con.conrelid
    JOIN pg_catalog.pg_namespace AS n ON n.oid = rel.relnamespace
    WHERE n.nspname = 'ntubtob'

    UNION ALL

    SELECT
        '05_index',
        format('%I.%I.%I', schemaname, tablename, indexname),
        jsonb_build_object('definition', indexdef)
    FROM pg_catalog.pg_indexes
    WHERE schemaname = 'ntubtob'

    UNION ALL

    SELECT
        '06_trigger',
        format('%I.%I.%I', n.nspname, rel.relname, trg.tgname),
        jsonb_build_object(
            'enabled', trg.tgenabled,
            'definition', pg_get_triggerdef(trg.oid, true)
        )
    FROM pg_catalog.pg_trigger AS trg
    JOIN pg_catalog.pg_class AS rel ON rel.oid = trg.tgrelid
    JOIN pg_catalog.pg_namespace AS n ON n.oid = rel.relnamespace
    WHERE n.nspname = 'ntubtob'
      AND NOT trg.tgisinternal

    UNION ALL

    SELECT
        '07_function',
        format(
            '%I.%I(%s)',
            n.nspname,
            proc.proname,
            pg_get_function_identity_arguments(proc.oid)
        ),
        jsonb_build_object(
            'result_type', pg_get_function_result(proc.oid),
            'language', lang.lanname,
            'volatility', proc.provolatile,
            'security_definer', proc.prosecdef,
            'owner', pg_get_userbyid(proc.proowner)
        )
    FROM pg_catalog.pg_proc AS proc
    JOIN pg_catalog.pg_namespace AS n ON n.oid = proc.pronamespace
    JOIN pg_catalog.pg_language AS lang ON lang.oid = proc.prolang
    WHERE n.nspname = 'ntubtob'

    UNION ALL

    SELECT
        '08_rls_policy',
        format('%I.%I.%I', schemaname, tablename, policyname),
        jsonb_build_object(
            'permissive', permissive,
            'roles', roles,
            'command', cmd,
            'using_expression', qual,
            'check_expression', with_check
        )
    FROM pg_catalog.pg_policies
    WHERE schemaname = 'ntubtob'

    UNION ALL

    SELECT
        '09_current_role_privileges',
        format('%I.%I', n.nspname, rel.relname),
        jsonb_build_object(
            'select', has_table_privilege(rel.oid, 'SELECT'),
            'insert', has_table_privilege(rel.oid, 'INSERT'),
            'update', has_table_privilege(rel.oid, 'UPDATE'),
            'delete', has_table_privilege(rel.oid, 'DELETE'),
            'truncate', has_table_privilege(rel.oid, 'TRUNCATE'),
            'references', has_table_privilege(rel.oid, 'REFERENCES'),
            'trigger', has_table_privilege(rel.oid, 'TRIGGER')
        )
    FROM pg_catalog.pg_class AS rel
    JOIN pg_catalog.pg_namespace AS n ON n.oid = rel.relnamespace
    WHERE n.nspname = 'ntubtob'
      AND rel.relkind IN ('r', 'p', 'v', 'm')

    UNION ALL

    SELECT
        '10_migration_marker',
        format('%I.%I', table_schema, table_name),
        jsonb_build_object('exists', true)
    FROM information_schema.tables
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
      AND table_name IN ('alembic_version', 'schema_migrations', 'flyway_schema_history')
)
SELECT section, object_name, details
FROM inventory
ORDER BY section, object_name;

ROLLBACK;
