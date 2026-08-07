-- READ-ONLY Phase C precheck. Local rehearsal/review artifact only.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';

SELECT 'revision_is_0003' AS metric,
       (SELECT count(*) FROM ntubtob.alembic_version
        WHERE version_num = '0003_legacy_bigint_activity_game') AS actual,
       1::bigint AS expected
UNION ALL
SELECT 'phase_c_column_count', count(*), 0
FROM information_schema.columns
WHERE table_schema = 'ntubtob'
  AND ((table_name = 'people' AND column_name IN ('formal_name', 'admin_note'))
       OR (table_name = 'game_attendance_replies' AND column_name = 'person_id'))
UNION ALL
SELECT 'phase_c_review_table_count', count(*), 0
FROM information_schema.tables
WHERE table_schema = 'ntubtob'
  AND table_name IN ('identity_review_threads', 'identity_review_messages')
UNION ALL
SELECT 'attendance_without_person_candidate', count(*), 0
FROM ntubtob.game_attendance_replies r
LEFT JOIN ntubtob.members m ON m.id = r.member_id
WHERE r.member_id IS NULL OR m.person_id IS NULL;

ROLLBACK;
