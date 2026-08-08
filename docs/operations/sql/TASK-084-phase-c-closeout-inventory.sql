-- Sanitized Phase C closeout inventory. Aggregate evidence only; no identifiers.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';

WITH evidence(section,metric,status,boolean_value,integer_value,text_value) AS (
  SELECT '00_session','transaction_read_only','required',current_setting('transaction_read_only')='on',NULL::bigint,NULL::text
  UNION ALL SELECT '01_schema','revision','required',NULL,NULL,(SELECT version_num FROM ntubtob.alembic_version)
  UNION ALL SELECT '02_identity','identity_count','required',NULL,count(*),NULL FROM ntubtob.auth_identities
  UNION ALL SELECT '02_identity','safe_pending_unlinked_count','classification',NULL,count(*),NULL FROM ntubtob.auth_identities a WHERE a.status='pending' AND a.person_id IS NULL
  UNION ALL SELECT '03_audit','access_audit_count','required',NULL,count(*),NULL FROM ntubtob.access_audit
  UNION ALL SELECT '03_audit','duplicate_request_id_count','required',NULL,count(*),NULL FROM (SELECT request_id FROM ntubtob.access_audit GROUP BY request_id HAVING count(*)>1) duplicates
  UNION ALL SELECT '04_qualification','active_team_player_count','required',NULL,count(*),NULL FROM ntubtob.person_qualifications WHERE qualification='team_player' AND status='active'
)
SELECT section,metric,status,boolean_value,integer_value,text_value FROM evidence ORDER BY section,metric;
ROLLBACK;
