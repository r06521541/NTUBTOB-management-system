-- TASK-071 sanitized production post-check. Aggregate catalog/count evidence only.
BEGIN TRANSACTION READ ONLY;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';
SET LOCAL idle_in_transaction_session_timeout = '60s';

WITH legacy_tables(name) AS (VALUES
  ('attendance_reply_types'),('ballparks'),('cancellations'),('discord_webhooks'),('game_attendance_replies'),('games'),('line_groups'),('line_notify_tokens'),('line_users'),('members')
), phase_b_tables(name) AS (VALUES
  ('access_audit'),('activities'),('activity_attendance_replies'),('auth_identities'),('event_attendance_replies'),('event_audit'),('event_eligibility_rules'),('event_invitee_overrides'),('event_invitees'),('event_managers'),('events'),('people'),('person_qualifications')
), all_expected_tables(name) AS (SELECT name FROM legacy_tables UNION ALL SELECT name FROM phase_b_tables), legacy_table_fingerprint AS (
  SELECT md5(string_agg(c.relname||'|'||c.relrowsecurity::text||'|'||c.relforcerowsecurity::text,E'\n' ORDER BY c.relname)) value FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN legacy_tables e ON e.name=c.relname WHERE n.nspname='ntubtob'
), legacy_column_fingerprint AS (
  SELECT md5(string_agg(c.table_name||'.'||c.column_name||'|'||c.data_type||'|'||c.udt_name||'|'||c.is_nullable||'|'||coalesce(c.column_default,'NULL')||'|'||c.is_identity||'|'||c.is_generated,E'\n' ORDER BY c.table_name,c.column_name)) value FROM information_schema.columns c JOIN legacy_tables e ON e.name=c.table_name WHERE c.table_schema='ntubtob'
), legacy_constraint_fingerprint AS (
  SELECT md5(string_agg(r.relname||'.'||c.conname||'|'||CASE c.contype WHEN 'p' THEN 'primary_key' WHEN 'f' THEN 'foreign_key' ELSE c.contype::text END||'|'||pg_get_constraintdef(c.oid,true)||'|'||c.convalidated::text,E'\n' ORDER BY r.relname,c.conname)) value FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace JOIN legacy_tables e ON e.name=r.relname WHERE n.nspname='ntubtob' AND c.contype IN ('p','f')
), phase_b_column_fingerprint AS (
  SELECT md5(string_agg(c.table_name||'.'||c.column_name||'|'||c.data_type||'|'||c.udt_name||'|'||c.is_nullable||'|'||coalesce(c.column_default,'NULL')||'|'||c.is_identity||'|'||c.is_generated,E'\n' ORDER BY c.table_name,c.ordinal_position)) value FROM information_schema.columns c JOIN phase_b_tables e ON e.name=c.table_name WHERE c.table_schema='ntubtob'
), phase_b_constraint_fingerprint AS (
  SELECT md5(string_agg(r.relname||'.'||c.conname||'|'||c.contype::text||'|'||pg_get_constraintdef(c.oid,true)||'|'||c.convalidated::text,E'\n' ORDER BY r.relname,c.conname)) value FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace JOIN phase_b_tables e ON e.name=r.relname WHERE n.nspname='ntubtob'
), phase_b_index_fingerprint AS (
  SELECT md5(string_agg(indexname||'|'||indexdef,E'\n' ORDER BY indexname)) value FROM pg_indexes WHERE schemaname='ntubtob' AND indexname IN ('ix_auth_identities_person','ix_person_qualifications_active','ix_event_invitees_event_included')
), phase_c_column_fingerprint AS (
  SELECT md5(string_agg(c.table_name||'.'||c.column_name||'|'||c.data_type||'|'||c.udt_name||'|'||c.is_nullable||'|'||coalesce(c.column_default,'NULL')||'|'||c.is_identity||'|'||c.is_generated,E'\n' ORDER BY c.table_name,c.ordinal_position)) value
  FROM information_schema.columns c WHERE c.table_schema='ntubtob' AND (
    (c.table_name='people' AND c.column_name IN ('formal_name','admin_note')) OR
    (c.table_name='game_attendance_replies' AND c.column_name='person_id') OR
    c.table_name IN ('identity_review_threads','identity_review_messages'))
), phase_c_constraint_fingerprint AS (
  SELECT md5(string_agg(r.relname||'.'||c.conname||'|'||c.contype::text||'|'||pg_get_constraintdef(c.oid,true)||'|'||c.convalidated::text,E'\n' ORDER BY r.relname,c.conname)) value
  FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace
  WHERE n.nspname='ntubtob' AND (r.relname IN ('identity_review_threads','identity_review_messages') OR
    c.conname IN ('ck_people_formal_name','ck_people_admin_note','ck_access_audit_action','ck_guest_player_bounded','fk_game_attendance_person'))
), phase_c_index_fingerprint AS (
  SELECT md5(string_agg(indexname||'|'||indexdef,E'\n' ORDER BY indexname)) value FROM pg_indexes
  WHERE schemaname='ntubtob' AND indexname IN ('ix_identity_review_threads_status_activity','ix_identity_review_messages_thread_created','ix_game_attendance_person_game_updated')
), reliable_line AS (
  SELECT l.line_user_id,m.person_id FROM ntubtob.line_users l JOIN ntubtob.members m ON m.id=l.member_id WHERE l.ignored IS FALSE AND m.person_id IS NOT NULL
), active_team_player AS (SELECT person_id FROM ntubtob.person_qualifications WHERE qualification='team_player' AND status='active'), evidence(section,metric,status,boolean_value,integer_value,text_value) AS (
  SELECT '00_session','transaction_read_only','required',current_setting('transaction_read_only')='on',NULL::bigint,NULL::text
  UNION ALL SELECT '00_session','server_major_supported','required',current_setting('server_version_num')::int / 10000 IN (15,16),NULL,NULL
  UNION ALL SELECT '01_contract','revision','required',NULL,NULL,(SELECT version_num FROM ntubtob.alembic_version)
  UNION ALL SELECT '01_contract','legacy_table_count','required',NULL,count(*),NULL FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN legacy_tables e ON e.name=c.relname WHERE n.nspname='ntubtob' AND c.relkind IN ('r','p')
  UNION ALL SELECT '01_contract','phase_b_table_count','required',NULL,count(*),NULL FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN phase_b_tables e ON e.name=c.relname WHERE n.nspname='ntubtob' AND c.relkind IN ('r','p')
  UNION ALL SELECT '01_contract','legacy_rls_enabled_count','required',NULL,count(*),NULL FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN legacy_tables e ON e.name=c.relname WHERE n.nspname='ntubtob' AND c.relrowsecurity
  UNION ALL SELECT '01_contract','phase_b_rls_enabled_count','required',NULL,count(*),NULL FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN phase_b_tables e ON e.name=c.relname WHERE n.nspname='ntubtob' AND c.relrowsecurity
  UNION ALL SELECT '01_contract','forced_rls_count','required',NULL,count(*),NULL FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN all_expected_tables e ON e.name=c.relname WHERE n.nspname='ntubtob' AND c.relforcerowsecurity
  UNION ALL SELECT '01_contract','policy_count','required',NULL,count(*),NULL FROM pg_policies p JOIN all_expected_tables e ON e.name=p.tablename WHERE p.schemaname='ntubtob'
  UNION ALL SELECT '01_contract','append_only_trigger_count','required',NULL,count(*),NULL FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='ntubtob' AND NOT t.tgisinternal AND t.tgname IN ('access_audit_append_only','event_audit_append_only')
  UNION ALL SELECT '01_contract','public_table_grant_count','required',NULL,count(*),NULL FROM information_schema.role_table_grants g JOIN all_expected_tables e ON e.name=g.table_name WHERE g.table_schema='ntubtob' AND g.grantee='PUBLIC'
  UNION ALL SELECT '01_contract','legacy_table_fingerprint_matches','required',value='210bc2099cf9e95bac888a69d0c1a82c',NULL,NULL FROM legacy_table_fingerprint
  UNION ALL SELECT '01_contract','legacy_column_fingerprint_matches','required',value='bc53b86d7f5a95638e055b43664e9b0c',NULL,NULL FROM legacy_column_fingerprint
  UNION ALL SELECT '01_contract','legacy_constraint_fingerprint_matches','required',value='6bd46c706eb126c26b822536ed7e4dbc',NULL,NULL FROM legacy_constraint_fingerprint
  UNION ALL SELECT '01_contract','phase_b_column_fingerprint_matches','required',value='11748d658b5668d9d607b1e24d95cbbc',NULL,NULL FROM phase_b_column_fingerprint
  UNION ALL SELECT '01_contract','phase_b_constraint_fingerprint_matches','required',value='f89ac8fd28744fabae3a255b1396a73d',NULL,NULL FROM phase_b_constraint_fingerprint
  UNION ALL SELECT '01_contract','phase_b_index_fingerprint_matches','required',value='a1437ec9eb26c32e6d03a5e932463e48',NULL,NULL FROM phase_b_index_fingerprint
  UNION ALL SELECT '01_contract','phase_c_table_count','required',NULL,count(*),NULL FROM information_schema.tables WHERE table_schema='ntubtob' AND table_name IN ('identity_review_threads','identity_review_messages')
  UNION ALL SELECT '01_contract','phase_c_rls_enabled_count','required',NULL,count(*),NULL FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='ntubtob' AND c.relname IN ('identity_review_threads','identity_review_messages') AND c.relrowsecurity
  UNION ALL SELECT '01_contract','phase_c_forced_rls_count','required',NULL,count(*),NULL FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='ntubtob' AND c.relname IN ('identity_review_threads','identity_review_messages') AND c.relforcerowsecurity
  UNION ALL SELECT '01_contract','phase_c_policy_count','required',NULL,count(*),NULL FROM pg_policies WHERE schemaname='ntubtob' AND tablename IN ('identity_review_threads','identity_review_messages')
  UNION ALL SELECT '02_phase_b','member_count','compare',NULL,count(*),NULL FROM ntubtob.members
  UNION ALL SELECT '02_phase_b','people_count','compare',NULL,count(*),NULL FROM ntubtob.people
  UNION ALL SELECT '02_phase_b','unlinked_member_count','required',NULL,count(*),NULL FROM ntubtob.members WHERE person_id IS NULL
  UNION ALL SELECT '02_phase_b','duplicate_person_link_count','required',NULL,count(*),NULL FROM (SELECT person_id FROM ntubtob.members GROUP BY person_id HAVING count(*)>1) d
  UNION ALL SELECT '02_phase_b','linked_identity_count','compare',NULL,count(*),NULL FROM ntubtob.auth_identities WHERE provider='line' AND status='linked'
  UNION ALL SELECT '02_phase_b','identity_projection_drift_count','required',NULL,count(*),NULL FROM (SELECT line_user_id,person_id FROM reliable_line EXCEPT SELECT provider_subject,person_id FROM ntubtob.auth_identities WHERE provider='line' AND status='linked' UNION ALL SELECT provider_subject,person_id FROM ntubtob.auth_identities WHERE provider='line' AND status='linked' EXCEPT SELECT line_user_id,person_id FROM reliable_line) d
  UNION ALL SELECT '02_phase_b','duplicate_provider_subject_count','required',NULL,count(*),NULL FROM (SELECT provider,provider_subject FROM ntubtob.auth_identities GROUP BY provider,provider_subject HAVING count(*)>1) d
  UNION ALL SELECT '02_phase_b','team_player_count','compare',NULL,count(*),NULL FROM active_team_player
  UNION ALL SELECT '02_phase_b','team_player_drift_count','required',NULL,count(*),NULL FROM (SELECT DISTINCT person_id FROM reliable_line EXCEPT SELECT person_id FROM active_team_player UNION ALL SELECT person_id FROM active_team_player EXCEPT SELECT DISTINCT person_id FROM reliable_line) d
  UNION ALL SELECT '02_phase_b','access_audit_count','compare',NULL,count(*),NULL FROM ntubtob.access_audit
  UNION ALL SELECT '02_phase_b','unexpected_audit_count','required',NULL,count(*),NULL FROM ntubtob.access_audit WHERE NOT ((action='member_backfilled' AND request_id LIKE 'task065-member-%') OR (action='identity_linked' AND request_id LIKE 'task065-identity-%') OR (action='qualification_granted' AND request_id LIKE 'task065-team-player-%'))
  UNION ALL SELECT '02_phase_b','audit_relationship_drift_count','required',NULL,count(*),NULL FROM ntubtob.access_audit a WHERE NOT (
    (a.action='member_backfilled' AND a.actor_person_id IS NULL AND a.auth_identity_id IS NULL AND a.before_state IS NULL AND EXISTS (SELECT 1 FROM ntubtob.members m WHERE m.person_id=a.target_person_id AND a.request_id='task065-member-'||m.id AND a.after_state::jsonb=jsonb_build_object('member_id',m.id))) OR
    (a.action='identity_linked' AND a.actor_person_id IS NULL AND a.before_state IS NULL AND EXISTS (SELECT 1 FROM ntubtob.auth_identities i JOIN ntubtob.line_users l ON l.line_user_id=i.provider_subject JOIN ntubtob.members m ON m.id=l.member_id WHERE i.id=a.auth_identity_id AND i.person_id=a.target_person_id AND m.person_id=i.person_id AND l.ignored IS FALSE AND a.request_id='task065-identity-'||l.id AND a.after_state::jsonb=jsonb_build_object('provider','line'))) OR
    (a.action='qualification_granted' AND a.actor_person_id IS NULL AND a.auth_identity_id IS NULL AND a.before_state IS NULL AND EXISTS (SELECT 1 FROM ntubtob.person_qualifications q JOIN ntubtob.members m ON m.person_id=q.person_id WHERE q.person_id=a.target_person_id AND q.qualification='team_player' AND q.status='active' AND a.request_id='task065-team-player-'||m.id AND a.after_state::jsonb=jsonb_build_object('qualification','team_player'))))
  UNION ALL SELECT '03_phase_c','alembic_revision_row_count','required',NULL,count(*),NULL FROM ntubtob.alembic_version
  UNION ALL SELECT '03_phase_c','phase_c_column_count','required',NULL,count(*),NULL FROM information_schema.columns WHERE table_schema='ntubtob' AND ((table_name='people' AND column_name IN ('formal_name','admin_note')) OR (table_name='game_attendance_replies' AND column_name='person_id') OR table_name IN ('identity_review_threads','identity_review_messages'))
  UNION ALL SELECT '03_phase_c','phase_c_column_fingerprint_matches','required',value='21515e2b449df86d4d31a2789638a3d7',NULL,NULL FROM phase_c_column_fingerprint
  UNION ALL SELECT '03_phase_c','phase_c_constraint_count','required',NULL,count(*),NULL FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='ntubtob' AND (t.relname IN ('identity_review_threads','identity_review_messages') OR c.conname IN ('ck_people_formal_name','ck_people_admin_note','ck_access_audit_action','ck_guest_player_bounded','fk_game_attendance_person'))
  UNION ALL SELECT '03_phase_c','phase_c_constraint_fingerprint_matches','required',value='6fb4bde4b853d543d377f8a3b767d01f',NULL,NULL FROM phase_c_constraint_fingerprint
  UNION ALL SELECT '03_phase_c','phase_c_index_count','required',NULL,count(*),NULL FROM pg_indexes WHERE schemaname='ntubtob' AND indexname IN ('ix_identity_review_threads_status_activity','ix_identity_review_messages_thread_created','ix_game_attendance_person_game_updated')
  UNION ALL SELECT '03_phase_c','phase_c_index_fingerprint_matches','required',value='b0dacc9d12f7a1114831805d3e56954d',NULL,NULL FROM phase_c_index_fingerprint
  UNION ALL SELECT '03_phase_c','attendance_person_fk_count','required',NULL,count(*),NULL FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='ntubtob' AND t.relname='game_attendance_replies' AND c.conname='fk_game_attendance_person' AND c.contype='f'
  UNION ALL SELECT '03_phase_c','guest_bound_constraint_count','required',NULL,count(*),NULL FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='ntubtob' AND t.relname='person_qualifications' AND c.conname='ck_guest_player_bounded' AND c.contype='c'
  UNION ALL SELECT '04_attendance','attendance_reply_count','compare',NULL,count(*),NULL FROM ntubtob.game_attendance_replies
  UNION ALL SELECT '04_attendance','attendance_null_member_count','required',NULL,count(*),NULL FROM ntubtob.game_attendance_replies WHERE member_id IS NULL
  UNION ALL SELECT '04_attendance','attendance_orphan_member_count','required',NULL,count(*),NULL FROM ntubtob.game_attendance_replies r LEFT JOIN ntubtob.members m ON m.id=r.member_id WHERE r.member_id IS NOT NULL AND m.id IS NULL
  UNION ALL SELECT '04_attendance','attendance_member_without_person_count','required',NULL,count(*),NULL FROM ntubtob.game_attendance_replies r JOIN ntubtob.members m ON m.id=r.member_id WHERE m.person_id IS NULL
  UNION ALL SELECT '04_attendance','attendance_person_column_count','required',NULL,count(*),NULL FROM information_schema.columns WHERE table_schema='ntubtob' AND table_name='game_attendance_replies' AND column_name='person_id'
  UNION ALL SELECT '04_attendance','attendance_null_person_count','required',NULL,count(*),NULL FROM ntubtob.game_attendance_replies WHERE person_id IS NULL
  UNION ALL SELECT '04_attendance','attendance_person_mismatch_count','required',NULL,count(*),NULL FROM ntubtob.game_attendance_replies r JOIN ntubtob.members m ON m.id=r.member_id WHERE r.person_id IS DISTINCT FROM m.person_id
  UNION ALL SELECT '04_attendance','phase_c_backfill_audit_count','required',NULL,count(*),NULL FROM ntubtob.access_audit WHERE action='member_backfilled' AND request_id LIKE 'phase-c-attendance-member-%'
  UNION ALL SELECT '05_out_of_band','runtime_flags','out_of_band',NULL,NULL,'not_checked_by_database'
  UNION ALL SELECT '90_counts','game_attendance_replies','compare',NULL,count(*),NULL FROM ntubtob.game_attendance_replies
  UNION ALL SELECT '90_counts','games','compare',NULL,count(*),NULL FROM ntubtob.games
  UNION ALL SELECT '90_counts','line_users','compare',NULL,count(*),NULL FROM ntubtob.line_users
  UNION ALL SELECT '90_counts','members','compare',NULL,count(*),NULL FROM ntubtob.members
)
SELECT section,metric,status,boolean_value,integer_value,text_value FROM evidence ORDER BY section,metric;
ROLLBACK;
