-- Sanitized Phase C identity drift inventory. Returns aggregate evidence only.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';

WITH portal_tables(table_name) AS (VALUES
  ('access_audit'),('activities'),('activity_attendance_replies'),('auth_identities'),
  ('event_attendance_replies'),('event_audit'),('event_eligibility_rules'),
  ('event_invitee_overrides'),('event_invitees'),('event_managers'),('events'),('people'),
  ('person_qualifications')
), reliable_line AS (
  SELECT l.id,l.line_user_id,l.member_id,m.person_id FROM ntubtob.line_users l
  JOIN ntubtob.members m ON m.id=l.member_id WHERE l.ignored IS FALSE AND m.person_id IS NOT NULL
), active_team_player AS (
  SELECT person_id FROM ntubtob.person_qualifications WHERE qualification='team_player' AND status='active'
), evidence(section,metric,status,boolean_value,integer_value,text_value) AS (
  SELECT '00_session','transaction_read_only','required',current_setting('transaction_read_only')='on',NULL::bigint,NULL::text
  UNION ALL SELECT '01_phase_a','revision','required',NULL,NULL,(SELECT version_num FROM ntubtob.alembic_version)
  UNION ALL SELECT '01_phase_a','portal_table_count','required',NULL,count(*),NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN portal_tables p ON p.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relkind IN ('r','p')
  UNION ALL SELECT '01_phase_a','portal_rls_enabled_count','required',NULL,count(*),NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN portal_tables p ON p.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relrowsecurity
  UNION ALL SELECT '01_phase_a','portal_rls_forced_count','required',NULL,count(*),NULL FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN portal_tables p ON p.table_name=c.relname WHERE n.nspname='ntubtob' AND c.relforcerowsecurity
  UNION ALL SELECT '01_phase_a','portal_policy_count','required',NULL,count(*),NULL FROM pg_catalog.pg_policies p JOIN portal_tables e ON e.table_name=p.tablename WHERE p.schemaname='ntubtob'
  UNION ALL SELECT '01_phase_a','append_only_trigger_count','required',NULL,count(*),NULL FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='ntubtob' AND NOT t.tgisinternal AND t.tgname IN ('access_audit_append_only','event_audit_append_only')
  UNION ALL SELECT '02_people','member_count','required',NULL,count(*),NULL FROM ntubtob.members
  UNION ALL SELECT '02_people','people_count','required',NULL,count(*),NULL FROM ntubtob.people
  UNION ALL SELECT '02_people','unlinked_member_count','required',NULL,count(*),NULL FROM ntubtob.members WHERE person_id IS NULL
  UNION ALL SELECT '02_people','nonbasic_person_count','required',NULL,count(*),NULL FROM ntubtob.people WHERE portal_access_level<>'basic'
  UNION ALL SELECT '02_people','noninactive_person_count','required',NULL,count(*),NULL FROM ntubtob.people WHERE portal_status<>'inactive'
  UNION ALL SELECT '02_people','duplicate_person_link_count','required',NULL,count(*),NULL FROM (SELECT person_id FROM ntubtob.members WHERE person_id IS NOT NULL GROUP BY person_id HAVING count(*)>1) d
  UNION ALL SELECT '03_identity','reliable_linked_line_count','required',NULL,count(*),NULL FROM reliable_line
  UNION ALL SELECT '03_identity','linked_identity_count','required',NULL,count(*),NULL FROM ntubtob.auth_identities WHERE provider='line' AND status='linked'
  UNION ALL SELECT '03_identity','pending_candidate_count','required',NULL,count(*),NULL FROM ntubtob.line_users WHERE member_id IS NULL AND ignored IS FALSE
  UNION ALL SELECT '03_identity','ignored_candidate_count','required',NULL,count(*),NULL FROM ntubtob.line_users WHERE ignored IS TRUE
  UNION ALL SELECT '03_identity','missing_identity_count','required',NULL,count(*),NULL FROM reliable_line l WHERE NOT EXISTS (SELECT 1 FROM ntubtob.auth_identities a WHERE a.provider='line' AND a.status='linked' AND a.provider_subject=l.line_user_id AND a.person_id=l.person_id)
  UNION ALL SELECT '03_identity','wrong_person_link_count','required',NULL,count(*),NULL FROM reliable_line l JOIN ntubtob.auth_identities a ON a.provider='line' AND a.status='linked' AND a.provider_subject=l.line_user_id WHERE a.person_id<>l.person_id
  UNION ALL SELECT '03_identity','identity_without_reliable_link_count','required',NULL,count(*),NULL FROM ntubtob.auth_identities a WHERE a.provider='line' AND a.status='linked' AND NOT EXISTS (SELECT 1 FROM reliable_line l WHERE l.line_user_id=a.provider_subject AND l.person_id=a.person_id)
  UNION ALL SELECT '03_identity','duplicate_provider_subject_count','required',NULL,count(*),NULL FROM (SELECT provider,provider_subject FROM ntubtob.auth_identities GROUP BY provider,provider_subject HAVING count(*)>1) d
  UNION ALL SELECT '03_identity','orphan_member_link_count','required',NULL,count(*),NULL FROM ntubtob.line_users l WHERE l.member_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ntubtob.members m WHERE m.id=l.member_id)
  UNION ALL SELECT '04_qualification','team_player_count','required',NULL,count(*),NULL FROM active_team_player
  UNION ALL SELECT '04_qualification','team_player_missing_count','required',NULL,count(DISTINCT l.person_id),NULL FROM reliable_line l WHERE NOT EXISTS (SELECT 1 FROM active_team_player q WHERE q.person_id=l.person_id)
  UNION ALL SELECT '04_qualification','team_player_extra_count','required',NULL,count(*),NULL FROM active_team_player q WHERE NOT EXISTS (SELECT 1 FROM reliable_line l WHERE l.person_id=q.person_id)
  UNION ALL SELECT '04_qualification','team_player_revoked_mismatch_count','required',NULL,count(DISTINCT l.person_id),NULL FROM reliable_line l JOIN ntubtob.person_qualifications q ON q.person_id=l.person_id AND q.qualification='team_player' AND q.status='revoked'
  UNION ALL SELECT '05_audit','access_audit_count','required',NULL,count(*),NULL FROM ntubtob.access_audit
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
)
SELECT section,metric,status,boolean_value,integer_value,text_value FROM evidence ORDER BY section,metric;
ROLLBACK;
