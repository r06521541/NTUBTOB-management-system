BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';
SELECT jsonb_build_object(
  'id', id, 'game_id', game_id, 'member_id', member_id,
  'person_id', person_id, 'reply', reply, 'updated_at', updated_at
)::text
FROM ntubtob.game_attendance_replies
ORDER BY id;
COMMIT;
