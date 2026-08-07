-- TASK-065 sanitized Phase B post-check. No identity or member values are returned.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';

WITH portal_tables(table_name) AS (VALUES
  ('access_audit'),('activities'),('activity_attendance_replies'),('auth_identities'),
  ('event_attendance_replies'),('event_audit'),('event_eligibility_rules'),
  ('event_invitee_overrides'),('event_invitees'),('event_managers'),('events'),('people'),
  ('person_qualifications')
), evidence(section,metric,status,boolean_value,integer_value,text_value) AS (
  SELECT '00_session','transaction_read_only','required',current_setting('transaction_read_only')='on',NULL::bigint,NULL::text
  UNION ALL SELECT '01_phase_a','revision','required',NULL,NULL,(SELECT version_num FROM ntubtob.alembic_version)
  UNION ALL SELECT '01_phase_a','portal_table_count','required',NULL,count(*),NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN portal_tables p ON p.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relkind IN ('r','p')
  UNION ALL SELECT '01_phase_a','portal_rls_enabled_count','required',NULL,count(*),NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN portal_tables p ON p.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relrowsecurity
  UNION ALL SELECT '01_phase_a','portal_rls_forced_count','required',NULL,count(*),NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN portal_tables p ON p.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relforcerowsecurity
  UNION ALL SELECT '01_phase_a','portal_policy_count','required',NULL,count(*),NULL FROM pg_catalog.pg_policies p JOIN portal_tables e ON e.table_name=p.tablename WHERE p.schemaname='ntubtob'
  UNION ALL SELECT '02_people','member_count','compare',NULL,count(*),NULL FROM ntubtob.members
  UNION ALL SELECT '02_people','people_count','compare',NULL,count(*),NULL FROM ntubtob.people
  UNION ALL SELECT '02_people','unlinked_member_count','required',NULL,count(*),NULL FROM ntubtob.members WHERE person_id IS NULL
  UNION ALL SELECT '02_people','nonbasic_person_count','required',NULL,count(*),NULL FROM ntubtob.people WHERE portal_access_level<>'basic'
  UNION ALL SELECT '02_people','noninactive_person_count','required',NULL,count(*),NULL FROM ntubtob.people WHERE portal_status<>'inactive'
  UNION ALL SELECT '02_people','duplicate_person_link_count','required',NULL,count(*),NULL FROM (SELECT person_id FROM ntubtob.members WHERE person_id IS NOT NULL GROUP BY person_id HAVING count(*)>1) d
  UNION ALL SELECT '03_identity','linked_identity_count','compare',NULL,count(*),NULL FROM ntubtob.auth_identities WHERE provider='line' AND status='linked'
  UNION ALL SELECT '03_identity','identity_without_reliable_link_count','required',NULL,count(*),NULL FROM ntubtob.auth_identities a WHERE NOT EXISTS (SELECT 1 FROM ntubtob.line_users l JOIN ntubtob.members m ON m.id=l.member_id WHERE l.ignored IS FALSE AND l.line_user_id=a.provider_subject AND m.person_id=a.person_id)
  UNION ALL SELECT '03_identity','ignored_identity_count','required',NULL,count(*),NULL FROM ntubtob.auth_identities a JOIN ntubtob.line_users l ON l.line_user_id=a.provider_subject WHERE l.ignored IS TRUE
  UNION ALL SELECT '04_qualification','team_player_count','compare',NULL,count(*),NULL FROM ntubtob.person_qualifications WHERE qualification='team_player' AND status='active'
  UNION ALL SELECT '04_qualification','team_player_without_line_count','required',NULL,count(*),NULL FROM ntubtob.person_qualifications q WHERE q.qualification='team_player' AND q.status='active' AND NOT EXISTS (SELECT 1 FROM ntubtob.members m JOIN ntubtob.line_users l ON l.member_id=m.id WHERE m.person_id=q.person_id AND l.ignored IS FALSE)
  UNION ALL SELECT '05_audit','access_audit_count','compare',NULL,count(*),NULL FROM ntubtob.access_audit
  UNION ALL SELECT '05_audit','member_audit_count','compare',NULL,count(*),NULL FROM ntubtob.access_audit WHERE action='member_backfilled' AND request_id LIKE 'task065-member-%'
  UNION ALL SELECT '05_audit','identity_audit_count','compare',NULL,count(*),NULL FROM ntubtob.access_audit WHERE action='identity_linked' AND request_id LIKE 'task065-identity-%'
  UNION ALL SELECT '05_audit','qualification_audit_count','compare',NULL,count(*),NULL FROM ntubtob.access_audit WHERE action='qualification_granted' AND request_id LIKE 'task065-team-player-%'
  UNION ALL SELECT '05_audit','unexpected_audit_count','required',NULL,count(*),NULL FROM ntubtob.access_audit WHERE NOT (
    (action='member_backfilled' AND request_id LIKE 'task065-member-%') OR
    (action='identity_linked' AND request_id LIKE 'task065-identity-%') OR
    (action='qualification_granted' AND request_id LIKE 'task065-team-player-%'))
  UNION ALL SELECT '05_audit','inconsistent_audit_count','required',NULL,count(*),NULL FROM ntubtob.access_audit a WHERE NOT (
    (a.action='member_backfilled' AND a.actor_person_id IS NULL AND a.auth_identity_id IS NULL AND a.before_state IS NULL
     AND EXISTS (SELECT 1 FROM ntubtob.members m WHERE m.person_id=a.target_person_id
                 AND a.request_id='task065-member-'||m.id
                 AND a.after_state::jsonb=jsonb_build_object('member_id',m.id))) OR
    (a.action='identity_linked' AND a.actor_person_id IS NULL AND a.before_state IS NULL
     AND EXISTS (SELECT 1 FROM ntubtob.auth_identities i JOIN ntubtob.line_users l ON l.line_user_id=i.provider_subject
                 JOIN ntubtob.members m ON m.id=l.member_id
                 WHERE i.id=a.auth_identity_id AND i.person_id=a.target_person_id AND m.person_id=i.person_id
                   AND l.ignored IS FALSE AND a.request_id='task065-identity-'||l.id
                   AND a.after_state::jsonb=jsonb_build_object('provider','line'))) OR
    (a.action='qualification_granted' AND a.actor_person_id IS NULL AND a.auth_identity_id IS NULL AND a.before_state IS NULL
     AND EXISTS (SELECT 1 FROM ntubtob.person_qualifications q JOIN ntubtob.members m ON m.person_id=q.person_id
                 WHERE q.person_id=a.target_person_id AND q.qualification='team_player' AND q.status='active'
                   AND a.request_id='task065-team-player-'||m.id
                   AND a.after_state::jsonb=jsonb_build_object('qualification','team_player'))))
  UNION ALL SELECT '06_unchanged','other_portal_row_count','required',NULL,
    (SELECT count(*) FROM ntubtob.events)+(SELECT count(*) FROM ntubtob.activities)+
    (SELECT count(*) FROM ntubtob.event_eligibility_rules)+(SELECT count(*) FROM ntubtob.event_invitee_overrides)+
    (SELECT count(*) FROM ntubtob.event_invitees)+(SELECT count(*) FROM ntubtob.event_attendance_replies)+
    (SELECT count(*) FROM ntubtob.activity_attendance_replies)+(SELECT count(*) FROM ntubtob.event_managers)+
    (SELECT count(*) FROM ntubtob.event_audit),NULL
)
SELECT section,metric,status,boolean_value,integer_value,text_value FROM evidence ORDER BY section,metric;
ROLLBACK;
