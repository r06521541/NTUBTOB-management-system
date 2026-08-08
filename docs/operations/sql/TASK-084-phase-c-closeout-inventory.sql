-- Sanitized Phase C closeout inventory. Aggregate evidence only; no identifiers.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';

WITH evidence(section,metric,status,boolean_value,integer_value,text_value) AS (
  SELECT '00_session','transaction_read_only','required',current_setting('transaction_read_only')='on',NULL::bigint,NULL::text
  UNION ALL SELECT '01_schema','revision','required',NULL,NULL,(SELECT version_num FROM ntubtob.alembic_version)
  UNION ALL SELECT '02_identity','identity_count','required',NULL,count(*),NULL FROM ntubtob.auth_identities
  UNION ALL SELECT '02_identity','active_linked_allowlisted_admin_count','required',NULL,count(DISTINCT a.person_id),NULL FROM ntubtob.auth_identities a JOIN ntubtob.people p ON p.id=a.person_id JOIN ntubtob.members m ON m.person_id=p.id WHERE a.status='linked' AND p.portal_status='active' AND m.id=ANY(string_to_array(:'admin_member_ids',',')::bigint[])
  UNION ALL SELECT '02_identity','safe_ignore_candidate_count','classification',NULL,count(*),NULL FROM ntubtob.auth_identities a JOIN ntubtob.line_users l ON l.line_user_id=a.provider_subject WHERE a.provider='line' AND a.status='pending' AND a.person_id IS NULL AND l.member_id IS NULL AND l.ignored IS FALSE
  UNION ALL SELECT '02_identity','safe_unignore_candidate_count','classification',NULL,count(*),NULL FROM ntubtob.auth_identities a JOIN ntubtob.line_users l ON l.line_user_id=a.provider_subject WHERE a.provider='line' AND a.status='pending' AND a.person_id IS NULL AND l.member_id IS NULL AND l.ignored IS TRUE
  UNION ALL SELECT '02_identity','identity_drift_count','required',NULL,count(*),NULL FROM (SELECT provider,provider_subject FROM ntubtob.auth_identities GROUP BY provider,provider_subject HAVING count(*)>1) d
  UNION ALL SELECT '02_identity','member_person_drift_count','required',NULL,count(*),NULL FROM ntubtob.members WHERE person_id IS NULL
  UNION ALL SELECT '03_audit','access_audit_count','required',NULL,count(*),NULL FROM ntubtob.access_audit
  UNION ALL SELECT '03_audit','duplicate_request_id_count','required',NULL,count(*),NULL FROM (SELECT request_id FROM ntubtob.access_audit GROUP BY request_id HAVING count(*)>1) duplicates
  UNION ALL SELECT '03_audit','mutation_ignored_action_count','bounded',NULL,count(*),NULL FROM ntubtob.access_audit WHERE request_id=:'mutation_request_id' AND action='identity_ignored'
  UNION ALL SELECT '03_audit','mutation_other_action_count','bounded',NULL,count(*),NULL FROM ntubtob.access_audit WHERE request_id=:'mutation_request_id' AND action<>'identity_ignored'
  UNION ALL SELECT '03_audit','recovery_unignored_action_count','bounded',NULL,count(*),NULL FROM ntubtob.access_audit WHERE request_id=:'recovery_request_id' AND action='identity_unignored'
  UNION ALL SELECT '03_audit','recovery_other_action_count','bounded',NULL,count(*),NULL FROM ntubtob.access_audit WHERE request_id=:'recovery_request_id' AND action<>'identity_unignored'
  UNION ALL SELECT '04_qualification','active_team_player_count','required',NULL,count(*),NULL FROM ntubtob.person_qualifications WHERE qualification='team_player' AND status='active'
  UNION ALL SELECT '04_qualification','qualification_drift_count','required',NULL,count(*),NULL FROM ntubtob.person_qualifications q WHERE NOT EXISTS (SELECT 1 FROM ntubtob.people p WHERE p.id=q.person_id)
)
SELECT section,metric,status,boolean_value,integer_value,text_value FROM evidence ORDER BY section,metric;
ROLLBACK;
