BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';
SELECT jsonb_build_object(
  'id', id, 'person_id', person_id, 'qualification', qualification,
  'status', status, 'valid_from', valid_from, 'valid_until', valid_until,
  'created_at', created_at, 'updated_at', updated_at
)::text
FROM ntubtob.person_qualifications
ORDER BY id;
COMMIT;
