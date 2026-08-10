BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';
SELECT jsonb_build_object(
  'id', id, 'display_name', display_name, 'formal_name', formal_name,
  'portal_access_level', portal_access_level, 'portal_status', portal_status,
  'version', version, 'created_at', created_at, 'updated_at', updated_at
)::text
FROM ntubtob.people
ORDER BY id;
COMMIT;
