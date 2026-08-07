-- TASK-062 Phase A execution-time post-check. Sanitized aggregates only.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';

WITH legacy_tables(table_name) AS (VALUES
  ('attendance_reply_types'), ('ballparks'), ('cancellations'), ('discord_webhooks'),
  ('game_attendance_replies'), ('games'), ('line_groups'), ('line_notify_tokens'),
  ('line_users'), ('members')
), portal_tables(table_name) AS (VALUES
  ('access_audit'),('activities'),('activity_attendance_replies'),('auth_identities'),
  ('event_attendance_replies'),('event_audit'),('event_eligibility_rules'),
  ('event_invitee_overrides'),('event_invitees'),('event_managers'),('events'),('people'),
  ('person_qualifications')
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
), portal_columns AS (
  SELECT md5(string_agg(c.table_name||'.'||c.column_name||'|'||c.data_type||'|'||c.udt_name||'|'||c.is_nullable||'|'||coalesce(c.column_default,'NULL')||'|'||c.is_identity||'|'||c.is_generated, E'\n' ORDER BY c.table_name,c.ordinal_position)) value
  FROM information_schema.columns c JOIN portal_tables p ON p.table_name=c.table_name WHERE c.table_schema='ntubtob'
), portal_constraints AS (
  SELECT md5(string_agg(r.relname||'.'||c.conname||'|'||c.contype::text||'|'||pg_catalog.pg_get_constraintdef(c.oid,true)||'|'||c.convalidated::text, E'\n' ORDER BY r.relname,c.conname)) value
  FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_class r ON r.oid=c.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=r.relnamespace JOIN portal_tables p ON p.table_name=r.relname WHERE n.nspname='ntubtob'
), portal_indexes AS (
  SELECT md5(string_agg(indexname||'|'||indexdef, E'\n' ORDER BY indexname)) value
  FROM pg_catalog.pg_indexes WHERE schemaname='ntubtob' AND indexname IN ('ix_auth_identities_person','ix_person_qualifications_active','ix_event_invitees_event_included')
), portal_triggers AS (
  SELECT md5(string_agg(t.tgname||'|'||pg_catalog.pg_get_triggerdef(t.oid,true), E'\n' ORDER BY t.tgname)) value
  FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='ntubtob' AND t.tgname IN ('access_audit_append_only','event_audit_append_only') AND NOT t.tgisinternal
), evidence(section, metric, status, boolean_value, integer_value, text_value) AS (
  SELECT '00_session', 'transaction_read_only', 'required', current_setting('transaction_read_only')='on', NULL::bigint, NULL::text
  UNION ALL SELECT '01_legacy', 'legacy_table_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN legacy_tables e ON e.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relkind IN ('r','p')
  UNION ALL SELECT '01_legacy', 'legacy_table_fingerprint_matches', 'required', coalesce(value='210bc2099cf9e95bac888a69d0c1a82c',false), NULL, NULL FROM legacy_table_fingerprint
  UNION ALL SELECT '01_legacy', 'legacy_column_fingerprint_matches', 'required', coalesce(value='311f00b66a15cb90ff00caffae46bac3',false), NULL, NULL FROM legacy_column_fingerprint
  UNION ALL SELECT '01_legacy', 'legacy_constraint_fingerprint_matches', 'required', coalesce(value='7e9be5ea877337844a60410a1340821b',false), NULL, NULL FROM legacy_constraint_fingerprint
  UNION ALL SELECT '01_legacy', 'legacy_rls_enabled_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN legacy_tables e ON e.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relrowsecurity
  UNION ALL SELECT '01_legacy', 'legacy_rls_forced_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN legacy_tables e ON e.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relforcerowsecurity
  UNION ALL SELECT '01_legacy', 'legacy_policy_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_policies p JOIN legacy_tables e ON e.table_name=p.tablename WHERE p.schemaname='ntubtob'
  UNION ALL SELECT '02_revision', 'revision_matches', 'required', (SELECT count(*)=1 AND min(version_num)='0003_legacy_bigint_activity_game' FROM ntubtob.alembic_version), NULL, NULL
  UNION ALL SELECT '03_catalog', 'portal_table_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN portal_tables p ON p.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relkind IN ('r','p')
  UNION ALL SELECT '03_catalog', 'portal_column_count', 'required', NULL, count(*), NULL FROM information_schema.columns c JOIN portal_tables p ON p.table_name=c.table_name WHERE c.table_schema='ntubtob'
  UNION ALL SELECT '03_catalog', 'portal_column_fingerprint_matches', 'required', coalesce(value='1ca150c6a5de398e49b34b1ccf3f5599',false), NULL, NULL FROM portal_columns
  UNION ALL SELECT '03_catalog', 'portal_constraint_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_class r ON r.oid=c.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=r.relnamespace JOIN portal_tables p ON p.table_name=r.relname WHERE n.nspname='ntubtob'
  UNION ALL SELECT '03_catalog', 'portal_constraint_fingerprint_matches', 'required', coalesce(value='f47ccd7fc803a08f2ac3933c2ee2a6fd',false), NULL, NULL FROM portal_constraints
  UNION ALL SELECT '03_catalog', 'expected_index_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_indexes WHERE schemaname='ntubtob' AND indexname IN ('ix_auth_identities_person','ix_person_qualifications_active','ix_event_invitees_event_included')
  UNION ALL SELECT '03_catalog', 'expected_index_fingerprint_matches', 'required', coalesce(value='a1437ec9eb26c32e6d03a5e932463e48',false), NULL, NULL FROM portal_indexes
  UNION ALL SELECT '03_catalog', 'append_only_function_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_proc f JOIN pg_catalog.pg_namespace n ON n.oid=f.pronamespace WHERE n.nspname='ntubtob' AND f.proname='reject_audit_mutation' AND f.pronargs=0
  UNION ALL SELECT '03_catalog', 'append_only_function_matches', 'required', count(*)=1, NULL, NULL FROM pg_catalog.pg_proc f JOIN pg_catalog.pg_namespace n ON n.oid=f.pronamespace JOIN pg_catalog.pg_language l ON l.oid=f.prolang WHERE n.nspname='ntubtob' AND f.proname='reject_audit_mutation' AND f.pronargs=0 AND f.prorettype='trigger'::regtype AND l.lanname='plpgsql' AND md5(f.prosrc)='ddccbce99e4a41005a486a59847cdf02'
  UNION ALL SELECT '03_catalog', 'append_only_trigger_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='ntubtob' AND t.tgname IN ('access_audit_append_only','event_audit_append_only') AND NOT t.tgisinternal
  UNION ALL SELECT '03_catalog', 'append_only_trigger_fingerprint_matches', 'required', coalesce(value='8c049078cfe6b95d550cb83334fbae89',false), NULL, NULL FROM portal_triggers
  UNION ALL SELECT '04_members', 'person_id_is_nullable_bigint', 'required', EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='ntubtob' AND table_name='members' AND column_name='person_id' AND is_nullable='YES' AND data_type='bigint'), NULL, NULL
  UNION ALL SELECT '04_members', 'person_id_unique_constraint_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_class r ON r.oid=c.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname='ntubtob' AND r.relname='members' AND c.conname='uq_members_person_id' AND c.contype='u'
  UNION ALL SELECT '04_members', 'person_id_fk_constraint_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_class r ON r.oid=c.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname='ntubtob' AND r.relname='members' AND c.conname='fk_members_person' AND c.contype='f' AND pg_catalog.pg_get_constraintdef(c.oid,true)='FOREIGN KEY (person_id) REFERENCES ntubtob.people(id) ON DELETE RESTRICT'
  UNION ALL SELECT '04_members', 'person_id_nonnull_count', 'required', NULL, count(*), NULL FROM ntubtob.members WHERE person_id IS NOT NULL
  UNION ALL SELECT '05_portal', 'portal_total_row_count', 'required', NULL, (SELECT count(*) FROM ntubtob.people)+(SELECT count(*) FROM ntubtob.auth_identities)+(SELECT count(*) FROM ntubtob.person_qualifications)+(SELECT count(*) FROM ntubtob.access_audit)+(SELECT count(*) FROM ntubtob.events)+(SELECT count(*) FROM ntubtob.activities)+(SELECT count(*) FROM ntubtob.event_eligibility_rules)+(SELECT count(*) FROM ntubtob.event_invitee_overrides)+(SELECT count(*) FROM ntubtob.event_invitees)+(SELECT count(*) FROM ntubtob.event_attendance_replies)+(SELECT count(*) FROM ntubtob.activity_attendance_replies)+(SELECT count(*) FROM ntubtob.event_managers)+(SELECT count(*) FROM ntubtob.event_audit), NULL
  UNION ALL SELECT '05_portal', 'portal_rls_enabled_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN portal_tables p ON p.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relrowsecurity
  UNION ALL SELECT '05_portal', 'portal_rls_forced_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN portal_tables p ON p.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relforcerowsecurity
  UNION ALL SELECT '05_portal', 'portal_policy_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_policies p JOIN portal_tables e ON e.table_name=p.tablename WHERE p.schemaname='ntubtob'
  UNION ALL SELECT '05_portal', 'portal_public_grant_count', 'required', NULL, count(*), NULL FROM information_schema.table_privileges t JOIN portal_tables p ON p.table_name=t.table_name WHERE t.table_schema='ntubtob' AND t.grantee='PUBLIC'
  UNION ALL SELECT '05_portal', 'portal_other_visible_grant_count', 'required', NULL, count(*), NULL FROM information_schema.table_privileges t JOIN portal_tables p ON p.table_name=t.table_name WHERE t.table_schema='ntubtob' AND t.grantee NOT IN ('PUBLIC',CURRENT_USER)
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
