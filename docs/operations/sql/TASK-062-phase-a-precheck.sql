-- TASK-062 Phase A execution-time pre-check. Sanitized aggregates only.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';

WITH legacy_tables(table_name) AS (VALUES
  ('attendance_reply_types'), ('ballparks'), ('cancellations'), ('discord_webhooks'),
  ('game_attendance_replies'), ('games'), ('line_groups'), ('line_notify_tokens'),
  ('line_users'), ('members')
), relations AS (
  SELECT c.oid,c.relname,c.relowner,c.relrowsecurity,c.relforcerowsecurity
  FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='ntubtob' AND c.relkind IN ('r','p')
), session_role AS (
  SELECT oid FROM pg_catalog.pg_roles WHERE rolname=CURRENT_USER
), legacy_table_fingerprint AS (
  SELECT md5(string_agg(r.relname||'|'||r.relrowsecurity::text||'|'||r.relforcerowsecurity::text,E'\n' ORDER BY r.relname)) value
  FROM relations r JOIN legacy_tables e ON e.table_name=r.relname
), legacy_column_fingerprint AS (
  SELECT md5(string_agg(c.table_name||'.'||c.column_name||'|'||c.data_type||'|'||c.udt_name||'|'||c.is_nullable||'|'||coalesce(c.column_default,'NULL')||'|'||c.is_identity||'|'||c.is_generated,E'\n' ORDER BY c.table_name,c.column_name)) value
  FROM information_schema.columns c JOIN legacy_tables e ON e.table_name=c.table_name WHERE c.table_schema='ntubtob'
), legacy_constraint_fingerprint AS (
  SELECT md5(string_agg(r.relname||'.'||c.conname||'|'||CASE c.contype WHEN 'p' THEN 'primary_key' WHEN 'f' THEN 'foreign_key' ELSE c.contype::text END||'|'||pg_catalog.pg_get_constraintdef(c.oid,true)||'|'||c.convalidated::text,E'\n' ORDER BY r.relname,c.conname)) value
  FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_class r ON r.oid=c.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=r.relnamespace JOIN legacy_tables e ON e.table_name=r.relname WHERE n.nspname='ntubtob' AND c.contype IN ('p','f')
), evidence(section, metric, status, boolean_value, integer_value, text_value) AS (
  SELECT '00_session', 'transaction_read_only', 'required', current_setting('transaction_read_only') = 'on', NULL::bigint, NULL::text
  UNION ALL SELECT '01_legacy', 'legacy_table_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN legacy_tables e ON e.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relkind IN ('r','p')
  UNION ALL SELECT '01_legacy', 'legacy_table_fingerprint_matches', 'required', coalesce(value='210bc2099cf9e95bac888a69d0c1a82c',false), NULL, NULL FROM legacy_table_fingerprint
  UNION ALL SELECT '01_legacy', 'legacy_column_fingerprint_matches', 'required', coalesce(value='e7bae24dd9d7376be662fa4e33462185',false), NULL, NULL FROM legacy_column_fingerprint
  UNION ALL SELECT '01_legacy', 'legacy_constraint_fingerprint_matches', 'required', coalesce(value='0a1b070c6f8d607b118e6b3acf7c2467',false), NULL, NULL FROM legacy_constraint_fingerprint
  UNION ALL SELECT '01_legacy', 'legacy_rls_enabled_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN legacy_tables e ON e.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relrowsecurity
  UNION ALL SELECT '01_legacy', 'legacy_rls_forced_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN legacy_tables e ON e.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relforcerowsecurity
  UNION ALL SELECT '01_legacy', 'legacy_policy_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_policies p JOIN legacy_tables e ON e.table_name=p.tablename WHERE p.schemaname='ntubtob'
  UNION ALL SELECT '02_gate', 'alembic_version_exists', 'stop_if_true', to_regclass('ntubtob.alembic_version') IS NOT NULL, NULL, NULL
  UNION ALL SELECT '02_gate', 'portal_table_count', 'stop_if_nonzero', NULL, count(*), NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='ntubtob' AND c.relname IN ('access_audit','activities','activity_attendance_replies','auth_identities','event_attendance_replies','event_audit','event_eligibility_rules','event_invitee_overrides','event_invitees','event_managers','events','people','person_qualifications') AND c.relkind IN ('r','p')
  UNION ALL SELECT '02_gate', 'members_person_id_exists', 'stop_if_true', EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='ntubtob' AND table_name='members' AND column_name='person_id'), NULL, NULL
  UNION ALL SELECT '06_access', 'ntubtob_exists', 'required', EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname='ntubtob'), NULL, NULL
  UNION ALL SELECT '06_access', 'schema_owned_by_session', 'required', coalesce((SELECT n.nspowner=s.oid FROM pg_catalog.pg_namespace n CROSS JOIN session_role s WHERE n.nspname='ntubtob'),false), NULL, NULL
  UNION ALL SELECT '06_access', 'session_has_usage', 'required', coalesce((SELECT pg_catalog.has_schema_privilege(n.oid,'USAGE') FROM pg_catalog.pg_namespace n WHERE n.nspname='ntubtob'),false), NULL, NULL
  UNION ALL SELECT '06_access', 'session_has_create', 'required', coalesce((SELECT pg_catalog.has_schema_privilege(n.oid,'CREATE') FROM pg_catalog.pg_namespace n WHERE n.nspname='ntubtob'),false), NULL, NULL
  UNION ALL SELECT '06_access', 'legacy_owned_by_session_count', 'required', NULL, count(*), NULL FROM relations r JOIN legacy_tables e ON e.table_name=r.relname CROSS JOIN session_role s WHERE r.relowner=s.oid
  UNION ALL SELECT '06_access', 'legacy_owned_by_other_count', 'required', NULL, count(*), NULL FROM relations r JOIN legacy_tables e ON e.table_name=r.relname CROSS JOIN session_role s WHERE r.relowner<>s.oid
  UNION ALL SELECT '06_access', 'legacy_session_named_grant_count', 'required', NULL, count(*), NULL FROM information_schema.table_privileges t JOIN legacy_tables e ON e.table_name=t.table_name WHERE t.table_schema='ntubtob' AND t.grantee=CURRENT_USER
  UNION ALL SELECT '06_access', 'legacy_visible_write_grant_count', 'required', NULL, count(*), NULL FROM information_schema.table_privileges t JOIN legacy_tables e ON e.table_name=t.table_name WHERE t.table_schema='ntubtob' AND t.privilege_type IN ('INSERT','UPDATE','DELETE','TRUNCATE')
  UNION ALL SELECT '06_access', 'legacy_public_grant_count', 'required', NULL, count(*), NULL FROM information_schema.table_privileges t JOIN legacy_tables e ON e.table_name=t.table_name WHERE t.table_schema='ntubtob' AND t.grantee='PUBLIC'
  UNION ALL SELECT '06_access', 'legacy_other_visible_grant_count', 'required', NULL, count(*), NULL FROM information_schema.table_privileges t JOIN legacy_tables e ON e.table_name=t.table_name WHERE t.table_schema='ntubtob' AND t.grantee NOT IN ('PUBLIC',CURRENT_USER)
  UNION ALL SELECT '06_access', 'nonowner_default_table_grant_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_default_acl d JOIN pg_catalog.pg_namespace n ON n.oid=d.defaclnamespace CROSS JOIN LATERAL pg_catalog.aclexplode(coalesce(d.defaclacl,pg_catalog.acldefault(d.defaclobjtype,d.defaclrole))) a WHERE n.nspname='ntubtob' AND d.defaclobjtype='r' AND a.grantee<>d.defaclrole
  UNION ALL SELECT '90_counts', 'attendance_reply_types', 'compare', NULL, count(*), NULL FROM ntubtob.attendance_reply_types
  UNION ALL SELECT '90_counts', 'ballparks', 'compare', NULL, count(*), NULL FROM ntubtob.ballparks
  UNION ALL SELECT '90_counts', 'cancellations', 'compare', NULL, count(*), NULL FROM ntubtob.cancellations
  UNION ALL SELECT '90_counts', 'discord_webhooks', 'compare', NULL, count(*), NULL FROM ntubtob.discord_webhooks
  UNION ALL SELECT '90_counts', 'game_attendance_replies', 'compare', NULL, count(*), NULL FROM ntubtob.game_attendance_replies
  UNION ALL SELECT '90_counts', 'games', 'compare', NULL, count(*), NULL FROM ntubtob.games
  UNION ALL SELECT '90_counts', 'line_groups', 'compare', NULL, count(*), NULL FROM ntubtob.line_groups
  UNION ALL SELECT '90_counts', 'line_notify_tokens', 'compare', NULL, count(*), NULL FROM ntubtob.line_notify_tokens
  UNION ALL SELECT '90_counts', 'line_users', 'compare', NULL, count(*), NULL FROM ntubtob.line_users
  UNION ALL SELECT '90_counts', 'members', 'compare', NULL, count(*), NULL FROM ntubtob.members
)
SELECT section, metric, status, boolean_value, integer_value, text_value FROM evidence ORDER BY section, metric;
ROLLBACK;
