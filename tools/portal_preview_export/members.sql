BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';
SELECT jsonb_build_object(
  'id', id, 'name', name, 'enroll_year', enroll_year, 'major', major,
  'number', number, 'positions', positions, 'person_id', person_id
)::text
FROM ntubtob.members
ORDER BY id;
COMMIT;
