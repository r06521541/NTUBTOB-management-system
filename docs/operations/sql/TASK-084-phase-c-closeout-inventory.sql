-- Sanitized Phase C closeout inventory. Aggregate evidence only; no identifiers. Canonical checkout uses LF.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';

WITH reliable_line AS (
  SELECT l.id,l.line_user_id,l.member_id,m.person_id FROM ntubtob.line_users l
  JOIN ntubtob.members m ON m.id=l.member_id WHERE l.ignored IS FALSE AND m.person_id IS NOT NULL
), active_team_player AS (
  SELECT person_id FROM ntubtob.person_qualifications WHERE qualification='team_player' AND status='active'
), logging_boundary AS (
  SELECT current_setting('log_statement')='none'
    AND current_setting('log_min_duration_statement')::integer=-1
    AND coalesce(current_setting('log_min_duration_sample',true),'-1')::integer=-1
    AND coalesce(current_setting('pgaudit.log',true),'none')='none' AS safe
), evidence(section,metric,status,boolean_value,integer_value,text_value) AS (
  SELECT '00_session','transaction_read_only','required',current_setting('transaction_read_only')='on',NULL::bigint,NULL::text
  UNION ALL SELECT '00_session','statement_logging_safe','required',(SELECT safe FROM logging_boundary),NULL,NULL
  UNION ALL SELECT '01_schema','revision','required',NULL,NULL,(SELECT version_num FROM ntubtob.alembic_version)
  UNION ALL SELECT '02_identity','people_count','required',NULL,count(*),NULL FROM ntubtob.people
  UNION ALL SELECT '02_identity','member_count','required',NULL,count(*),NULL FROM ntubtob.members
  UNION ALL SELECT '02_identity','identity_count','required',NULL,count(*),NULL FROM ntubtob.auth_identities
  UNION ALL SELECT '02_identity','reliable_linked_line_count','required',NULL,count(*),NULL FROM reliable_line
  UNION ALL SELECT '02_identity','active_linked_allowlisted_admin_count','required',NULL,count(DISTINCT a.person_id),NULL FROM ntubtob.auth_identities a JOIN ntubtob.people p ON p.id=a.person_id JOIN ntubtob.members m ON m.person_id=p.id WHERE a.status='linked' AND p.portal_status='active' AND m.id=ANY(string_to_array(:'admin_member_ids',',')::bigint[])
  UNION ALL SELECT '02_identity','safe_ignore_candidate_count','classification',NULL,count(*),NULL FROM ntubtob.auth_identities a JOIN ntubtob.line_users l ON l.line_user_id=a.provider_subject WHERE a.provider='line' AND a.status='pending' AND a.person_id IS NULL AND l.member_id IS NULL AND l.ignored IS FALSE
  UNION ALL SELECT '02_identity','safe_unignore_candidate_count','classification',NULL,count(*),NULL FROM ntubtob.auth_identities a JOIN ntubtob.line_users l ON l.line_user_id=a.provider_subject WHERE a.provider='line' AND a.status='pending' AND a.person_id IS NULL AND l.member_id IS NULL AND l.ignored IS TRUE
  UNION ALL SELECT '02_identity','identity_drift_count','required',NULL,count(*),NULL FROM (SELECT provider,provider_subject FROM ntubtob.auth_identities GROUP BY provider,provider_subject HAVING count(*)>1) d
  UNION ALL SELECT '02_identity','member_person_drift_count','required',NULL,count(*),NULL FROM ntubtob.members WHERE person_id IS NULL
  UNION ALL SELECT '02_identity','duplicate_person_link_count','required',NULL,count(*),NULL FROM (SELECT person_id FROM ntubtob.members WHERE person_id IS NOT NULL GROUP BY person_id HAVING count(*)>1) d
  UNION ALL SELECT '02_identity','missing_identity_count','required',NULL,count(*),NULL FROM reliable_line l WHERE NOT EXISTS (SELECT 1 FROM ntubtob.auth_identities a WHERE a.provider='line' AND a.status='linked' AND a.provider_subject=l.line_user_id AND a.person_id=l.person_id)
  UNION ALL SELECT '02_identity','wrong_person_link_count','required',NULL,count(*),NULL FROM reliable_line l JOIN ntubtob.auth_identities a ON a.provider='line' AND a.status='linked' AND a.provider_subject=l.line_user_id WHERE a.person_id<>l.person_id
  UNION ALL SELECT '02_identity','identity_without_reliable_link_count','required',NULL,count(*),NULL FROM ntubtob.auth_identities a WHERE a.provider='line' AND a.status='linked' AND NOT EXISTS (SELECT 1 FROM reliable_line l WHERE l.line_user_id=a.provider_subject AND l.person_id=a.person_id)
  UNION ALL SELECT '02_identity','orphan_member_link_count','required',NULL,count(*),NULL FROM ntubtob.line_users l WHERE l.member_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ntubtob.members m WHERE m.id=l.member_id)
  UNION ALL SELECT '03_audit','access_audit_count','required',NULL,count(*),NULL FROM ntubtob.access_audit
  UNION ALL SELECT '03_audit','duplicate_request_id_count','required',NULL,count(*),NULL FROM (SELECT request_id FROM ntubtob.access_audit GROUP BY request_id HAVING count(*)>1) duplicates
  UNION ALL SELECT '03_audit','mutation_ignored_action_count','bounded',NULL,count(*),NULL FROM ntubtob.access_audit WHERE request_id=:'mutation_request_id' AND action='identity_ignored'
  UNION ALL SELECT '03_audit','mutation_other_action_count','bounded',NULL,count(*),NULL FROM ntubtob.access_audit WHERE request_id=:'mutation_request_id' AND action<>'identity_ignored'
  UNION ALL SELECT '03_audit','recovery_unignored_action_count','bounded',NULL,count(*),NULL FROM ntubtob.access_audit WHERE request_id=:'recovery_request_id' AND action='identity_unignored'
  UNION ALL SELECT '03_audit','recovery_other_action_count','bounded',NULL,count(*),NULL FROM ntubtob.access_audit WHERE request_id=:'recovery_request_id' AND action<>'identity_unignored'
  UNION ALL SELECT '03_audit','bounded_same_target_count','bounded',NULL,count(*),NULL FROM ntubtob.access_audit mutation JOIN ntubtob.access_audit recovery ON recovery.auth_identity_id=mutation.auth_identity_id WHERE mutation.request_id=:'mutation_request_id' AND mutation.action='identity_ignored' AND recovery.request_id=:'recovery_request_id' AND recovery.action='identity_unignored'
  UNION ALL SELECT '04_qualification','active_team_player_count','required',NULL,count(*),NULL FROM active_team_player
  UNION ALL SELECT '04_qualification','qualification_drift_count','required',NULL,count(*),NULL FROM ntubtob.person_qualifications q WHERE NOT EXISTS (SELECT 1 FROM ntubtob.people p WHERE p.id=q.person_id)
  UNION ALL SELECT '04_qualification','team_player_missing_count','required',NULL,count(DISTINCT l.person_id),NULL FROM reliable_line l WHERE NOT EXISTS (SELECT 1 FROM active_team_player q WHERE q.person_id=l.person_id)
  UNION ALL SELECT '04_qualification','team_player_extra_count','required',NULL,count(*),NULL FROM active_team_player q WHERE NOT EXISTS (SELECT 1 FROM reliable_line l WHERE l.person_id=q.person_id)
  UNION ALL SELECT '04_qualification','team_player_revoked_mismatch_count','required',NULL,count(DISTINCT l.person_id),NULL FROM reliable_line l JOIN ntubtob.person_qualifications q ON q.person_id=l.person_id AND q.qualification='team_player' AND q.status='revoked'
  UNION ALL SELECT '05_attendance','game_attendance_reply_count','required',NULL,count(*),NULL FROM ntubtob.game_attendance_replies
)
SELECT section,metric,status,boolean_value,integer_value,text_value FROM evidence ORDER BY section,metric;
ROLLBACK;
