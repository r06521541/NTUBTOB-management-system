-- TASK-065 sanitized Phase B inventory. No application row values are returned.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';

WITH evidence(section, metric, status, boolean_value, integer_value, text_value) AS (
  SELECT '00_session','transaction_read_only','required',current_setting('transaction_read_only')='on',NULL::bigint,NULL::text
  UNION ALL SELECT '01_revision','revision','required',NULL,NULL,(SELECT version_num FROM ntubtob.alembic_version)
  UNION ALL SELECT '02_precondition','member_count','compare',NULL,count(*),NULL FROM ntubtob.members
  UNION ALL SELECT '02_precondition','linked_member_count','stop_if_nonzero',NULL,count(*),NULL FROM ntubtob.members WHERE person_id IS NOT NULL
  UNION ALL SELECT '02_precondition','people_count','stop_if_nonzero',NULL,count(*),NULL FROM ntubtob.people
  UNION ALL SELECT '02_precondition','identity_count','stop_if_nonzero',NULL,count(*),NULL FROM ntubtob.auth_identities
  UNION ALL SELECT '02_precondition','qualification_count','stop_if_nonzero',NULL,count(*),NULL FROM ntubtob.person_qualifications
  UNION ALL SELECT '02_precondition','access_audit_count','stop_if_nonzero',NULL,count(*),NULL FROM ntubtob.access_audit
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
