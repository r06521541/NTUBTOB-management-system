-- TASK-065 sanitized Phase B inventory. No application row values are returned.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';

WITH portal_tables(table_name) AS (VALUES
  ('access_audit'),('activities'),('activity_attendance_replies'),('auth_identities'),
  ('event_attendance_replies'),('event_audit'),('event_eligibility_rules'),
  ('event_invitee_overrides'),('event_invitees'),('event_managers'),('events'),('people'),
  ('person_qualifications')
), evidence(section, metric, status, boolean_value, integer_value, text_value) AS (
  SELECT '00_session','transaction_read_only','required',current_setting('transaction_read_only')='on',NULL::bigint,NULL::text
  UNION ALL SELECT '01_phase_a','revision','required',NULL,NULL,(SELECT version_num FROM ntubtob.alembic_version)
  UNION ALL SELECT '01_phase_a','portal_table_count','required',NULL,count(*),NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN portal_tables p ON p.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relkind IN ('r','p')
  UNION ALL SELECT '01_phase_a','portal_rls_enabled_count','required',NULL,count(*),NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN portal_tables p ON p.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relrowsecurity
  UNION ALL SELECT '01_phase_a','portal_rls_forced_count','required',NULL,count(*),NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN portal_tables p ON p.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relforcerowsecurity
  UNION ALL SELECT '01_phase_a','portal_policy_count','required',NULL,count(*),NULL FROM pg_catalog.pg_policies p JOIN portal_tables e ON e.table_name=p.tablename WHERE p.schemaname='ntubtob'
  UNION ALL SELECT '01_phase_a','append_only_trigger_count','required',NULL,count(*),NULL FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='ntubtob' AND t.tgname IN ('access_audit_append_only','event_audit_append_only') AND NOT t.tgisinternal
  UNION ALL SELECT '02_precondition','member_count','compare',NULL,count(*),NULL FROM ntubtob.members
  UNION ALL SELECT '02_precondition','linked_member_count','stop_if_nonzero',NULL,count(*),NULL FROM ntubtob.members WHERE person_id IS NOT NULL
  UNION ALL SELECT '02_precondition','people_count','stop_if_nonzero',NULL,count(*),NULL FROM ntubtob.people
  UNION ALL SELECT '02_precondition','identity_count','stop_if_nonzero',NULL,count(*),NULL FROM ntubtob.auth_identities
  UNION ALL SELECT '02_precondition','qualification_count','stop_if_nonzero',NULL,count(*),NULL FROM ntubtob.person_qualifications
  UNION ALL SELECT '02_precondition','access_audit_count','stop_if_nonzero',NULL,count(*),NULL FROM ntubtob.access_audit
  UNION ALL SELECT '02_precondition','other_portal_row_count','stop_if_nonzero',NULL,
    (SELECT count(*) FROM ntubtob.events)+(SELECT count(*) FROM ntubtob.activities)+
    (SELECT count(*) FROM ntubtob.event_eligibility_rules)+(SELECT count(*) FROM ntubtob.event_invitee_overrides)+
    (SELECT count(*) FROM ntubtob.event_invitees)+(SELECT count(*) FROM ntubtob.event_attendance_replies)+
    (SELECT count(*) FROM ntubtob.activity_attendance_replies)+(SELECT count(*) FROM ntubtob.event_managers)+
    (SELECT count(*) FROM ntubtob.event_audit),NULL
  UNION ALL SELECT '03_line','line_user_count','compare',NULL,count(*),NULL FROM ntubtob.line_users
  UNION ALL SELECT '03_line','linked_nonignored_line_count','compare',NULL,count(*),NULL FROM ntubtob.line_users WHERE member_id IS NOT NULL AND ignored IS FALSE
  UNION ALL SELECT '03_line','linked_nonignored_member_count','compare',NULL,count(DISTINCT member_id),NULL FROM ntubtob.line_users WHERE member_id IS NOT NULL AND ignored IS FALSE
  UNION ALL SELECT '03_line','linked_ignored_line_count','compare',NULL,count(*),NULL FROM ntubtob.line_users WHERE member_id IS NOT NULL AND ignored IS TRUE
  UNION ALL SELECT '03_line','unlinked_nonignored_line_count','compare',NULL,count(*),NULL FROM ntubtob.line_users WHERE member_id IS NULL AND ignored IS FALSE
  UNION ALL SELECT '03_line','unlinked_ignored_line_count','compare',NULL,count(*),NULL FROM ntubtob.line_users WHERE member_id IS NULL AND ignored IS TRUE
  UNION ALL SELECT '03_line','duplicate_line_subject_groups','required',NULL,count(*),NULL FROM (SELECT line_user_id FROM ntubtob.line_users GROUP BY line_user_id HAVING count(*)>1) d
  UNION ALL SELECT '03_line','orphan_line_member_count','required',NULL,count(*),NULL FROM ntubtob.line_users l LEFT JOIN ntubtob.members m ON m.id=l.member_id WHERE l.member_id IS NOT NULL AND m.id IS NULL
)
SELECT section,metric,status,boolean_value,integer_value,text_value FROM evidence ORDER BY section,metric;
ROLLBACK;
