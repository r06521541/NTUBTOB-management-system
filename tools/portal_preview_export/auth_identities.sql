BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';
SELECT jsonb_build_object(
  'id', id, 'provider', provider, 'person_id', person_id, 'status', status,
  'created_at', created_at, 'updated_at', updated_at
)::text
FROM ntubtob.auth_identities
ORDER BY id;
COMMIT;
