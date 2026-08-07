-- TASK-062 Phase A execution-time pre-check. Sanitized aggregates only.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';

WITH legacy_tables(table_name) AS (VALUES
  ('attendance_reply_types'), ('ballparks'), ('cancellations'), ('discord_webhooks'),
  ('game_attendance_replies'), ('games'), ('line_groups'), ('line_notify_tokens'),
  ('line_users'), ('members')
), evidence(section, metric, status, boolean_value, integer_value, text_value) AS (
  SELECT '00_session', 'transaction_read_only', 'required', current_setting('transaction_read_only') = 'on', NULL::bigint, NULL::text
  UNION ALL SELECT '01_legacy', 'legacy_table_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN legacy_tables e ON e.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relkind IN ('r','p')
  UNION ALL SELECT '01_legacy', 'legacy_rls_enabled_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN legacy_tables e ON e.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relrowsecurity
  UNION ALL SELECT '01_legacy', 'legacy_rls_forced_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN legacy_tables e ON e.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relforcerowsecurity
  UNION ALL SELECT '01_legacy', 'legacy_policy_count', 'required', NULL, count(*), NULL FROM pg_catalog.pg_policies p JOIN legacy_tables e ON e.table_name=p.tablename WHERE p.schemaname='ntubtob'
  UNION ALL SELECT '02_gate', 'alembic_version_exists', 'stop_if_true', to_regclass('ntubtob.alembic_version') IS NOT NULL, NULL, NULL
  UNION ALL SELECT '02_gate', 'portal_table_count', 'stop_if_nonzero', NULL, count(*), NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='ntubtob' AND c.relname IN ('access_audit','activities','activity_attendance_replies','auth_identities','event_attendance_replies','event_audit','event_eligibility_rules','event_invitee_overrides','event_invitees','event_managers','events','people','person_qualifications') AND c.relkind IN ('r','p')
  UNION ALL SELECT '02_gate', 'members_person_id_exists', 'stop_if_true', EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='ntubtob' AND table_name='members' AND column_name='person_id'), NULL, NULL
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
