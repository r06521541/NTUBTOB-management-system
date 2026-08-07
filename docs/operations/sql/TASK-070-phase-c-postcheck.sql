-- READ-ONLY Phase C postcheck. Local rehearsal/review artifact only.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';

SELECT 'revision_is_0004' AS metric,
       (SELECT count(*) FROM ntubtob.alembic_version
        WHERE version_num = '0004_phase_c_identity_lifecycle') AS actual,
       1::bigint AS expected
UNION ALL
SELECT 'phase_c_column_count', count(*), 3
FROM information_schema.columns
WHERE table_schema = 'ntubtob'
  AND ((table_name = 'people' AND column_name IN ('formal_name', 'admin_note'))
       OR (table_name = 'game_attendance_replies' AND column_name = 'person_id'))
UNION ALL
SELECT 'review_rls_enabled_count', count(*), 2
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'ntubtob'
  AND c.relname IN ('identity_review_threads', 'identity_review_messages')
  AND c.relrowsecurity
UNION ALL
SELECT 'review_policy_count', count(*), 0
FROM pg_policies
WHERE schemaname = 'ntubtob'
  AND tablename IN ('identity_review_threads', 'identity_review_messages')
UNION ALL
SELECT 'attendance_without_person', count(*), 0
FROM ntubtob.game_attendance_replies WHERE person_id IS NULL
UNION ALL
SELECT 'attendance_person_member_mismatch', count(*), 0
FROM ntubtob.game_attendance_replies r
JOIN ntubtob.members m ON m.id = r.member_id
WHERE r.person_id <> m.person_id
UNION ALL
SELECT 'line_identity_legacy_mismatch', count(*), 0
FROM ntubtob.auth_identities i
JOIN ntubtob.line_users l ON l.line_user_id = i.provider_subject
LEFT JOIN ntubtob.members m ON m.id = l.member_id
WHERE i.provider = 'line'
  AND ((i.status = 'linked' AND i.person_id IS DISTINCT FROM m.person_id)
       OR (i.status = 'pending' AND (i.person_id IS NOT NULL OR l.member_id IS NOT NULL)))
UNION ALL
SELECT 'malformed_audit_relationship', count(*), 0
FROM ntubtob.access_audit a
WHERE (a.action IN ('identity_pending', 'identity_ignored', 'identity_unignored',
                    'identity_rejected', 'identity_unblocked', 'review_message_sent',
                    'review_closed', 'review_redacted')
       AND a.auth_identity_id IS NULL)
   OR (a.action IN ('person_approved', 'person_profile_updated', 'status_changed',
                    'qualification_granted', 'qualification_revoked',
                    'qualification_restored')
       AND a.target_person_id IS NULL)
   OR (a.action IN ('identity_ignored', 'identity_unignored', 'identity_unlinked',
                    'identity_remapped', 'identity_disabled', 'identity_enabled',
                    'identity_rejected', 'identity_unblocked', 'person_approved',
                    'person_profile_updated', 'status_changed',
                    'qualification_revoked', 'qualification_restored')
       AND a.actor_person_id IS NULL)
UNION ALL
SELECT 'guest_period_constraint_count', count(*), 1
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'ntubtob' AND t.relname = 'person_qualifications'
  AND c.conname = 'ck_guest_player_bounded';

ROLLBACK;
