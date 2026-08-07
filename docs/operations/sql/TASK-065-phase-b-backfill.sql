-- TASK-065 deterministic Phase B backfill. Repository artifact only; execution needs separate Owner approval.
BEGIN;
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '90s';
SELECT pg_advisory_xact_lock(650065);

DO $task065$
DECLARE
  member_row record;
  line_row record;
  person_key bigint;
  identity_key bigint;
BEGIN
  IF (SELECT count(*) FROM ntubtob.alembic_version) <> 1 OR
     (SELECT version_num FROM ntubtob.alembic_version) <> '0003_legacy_bigint_activity_game' THEN
    RAISE EXCEPTION 'TASK-065 revision precondition failed';
  END IF;
  IF (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='ntubtob' AND c.relname IN
      ('access_audit','activities','activity_attendance_replies','auth_identities','event_attendance_replies',
       'event_audit','event_eligibility_rules','event_invitee_overrides','event_invitees','event_managers','events',
       'people','person_qualifications') AND c.relkind IN ('r','p')) <> 13
     OR (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
         WHERE n.nspname='ntubtob' AND c.relname IN
         ('access_audit','activities','activity_attendance_replies','auth_identities','event_attendance_replies',
          'event_audit','event_eligibility_rules','event_invitee_overrides','event_invitees','event_managers','events',
          'people','person_qualifications') AND c.relrowsecurity) <> 13
     OR (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
         WHERE n.nspname='ntubtob' AND c.relname IN
         ('access_audit','activities','activity_attendance_replies','auth_identities','event_attendance_replies',
          'event_audit','event_eligibility_rules','event_invitee_overrides','event_invitees','event_managers','events',
          'people','person_qualifications') AND c.relforcerowsecurity) <> 0
     OR (SELECT count(*) FROM pg_catalog.pg_policies WHERE schemaname='ntubtob' AND tablename IN
         ('access_audit','activities','activity_attendance_replies','auth_identities','event_attendance_replies',
          'event_audit','event_eligibility_rules','event_invitee_overrides','event_invitees','event_managers','events',
          'people','person_qualifications')) <> 0
     OR (SELECT count(*) FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
         JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='ntubtob'
         AND t.tgname IN ('access_audit_append_only','event_audit_append_only') AND NOT t.tgisinternal) <> 2 THEN
    RAISE EXCEPTION 'TASK-065 Phase A boundary drift';
  END IF;
  IF (SELECT count(*) FROM ntubtob.members) <> {{member_count}}
     OR (SELECT count(*) FROM ntubtob.line_users) <> {{line_user_count}}
     OR (SELECT count(*) FROM ntubtob.line_users WHERE member_id IS NOT NULL AND ignored IS FALSE)
        <> {{linked_nonignored_line_count}}
     OR (SELECT count(DISTINCT member_id) FROM ntubtob.line_users WHERE member_id IS NOT NULL AND ignored IS FALSE)
        <> {{linked_nonignored_member_count}}
     OR (SELECT count(*) FROM ntubtob.line_users WHERE member_id IS NOT NULL AND ignored IS TRUE)
        <> {{linked_ignored_line_count}}
     OR (SELECT count(*) FROM ntubtob.line_users WHERE member_id IS NULL AND ignored IS FALSE)
        <> {{unlinked_nonignored_line_count}}
     OR (SELECT count(*) FROM ntubtob.line_users WHERE member_id IS NULL AND ignored IS TRUE)
        <> {{unlinked_ignored_line_count}} THEN
    RAISE EXCEPTION 'TASK-065 approved inventory count drift';
  END IF;
  IF (SELECT count(*) FROM ntubtob.events)+(SELECT count(*) FROM ntubtob.activities)+
     (SELECT count(*) FROM ntubtob.event_eligibility_rules)+(SELECT count(*) FROM ntubtob.event_invitee_overrides)+
     (SELECT count(*) FROM ntubtob.event_invitees)+(SELECT count(*) FROM ntubtob.event_attendance_replies)+
     (SELECT count(*) FROM ntubtob.activity_attendance_replies)+(SELECT count(*) FROM ntubtob.event_managers)+
     (SELECT count(*) FROM ntubtob.event_audit) <> 0 THEN
    RAISE EXCEPTION 'TASK-065 unrelated portal rows exist';
  END IF;
  IF EXISTS (SELECT 1 FROM ntubtob.people p WHERE NOT EXISTS (SELECT 1 FROM ntubtob.members m WHERE m.person_id=p.id))
     OR EXISTS (SELECT 1 FROM ntubtob.access_audit WHERE request_id NOT LIKE 'task065-%')
     OR EXISTS (SELECT 1 FROM ntubtob.person_qualifications q WHERE q.qualification<>'team_player'
                OR NOT EXISTS (SELECT 1 FROM ntubtob.members m JOIN ntubtob.line_users l ON l.member_id=m.id
                               WHERE m.person_id=q.person_id AND l.ignored IS FALSE))
     OR EXISTS (SELECT 1 FROM ntubtob.auth_identities a WHERE a.provider<>'line' OR a.status<>'linked'
                OR NOT EXISTS (SELECT 1 FROM ntubtob.line_users l JOIN ntubtob.members m ON m.id=l.member_id
                               WHERE l.ignored IS FALSE AND l.line_user_id=a.provider_subject AND m.person_id=a.person_id)) THEN
    RAISE EXCEPTION 'TASK-065 found non-batch or inconsistent portal rows';
  END IF;
  IF EXISTS (SELECT line_user_id FROM ntubtob.line_users GROUP BY line_user_id HAVING count(*) > 1)
     OR EXISTS (SELECT 1 FROM ntubtob.line_users l LEFT JOIN ntubtob.members m ON m.id=l.member_id
                WHERE l.member_id IS NOT NULL AND m.id IS NULL) THEN
    RAISE EXCEPTION 'TASK-065 legacy identity precondition failed';
  END IF;

  FOR member_row IN SELECT id,name FROM ntubtob.members ORDER BY id FOR UPDATE LOOP
    SELECT person_id INTO person_key FROM ntubtob.members WHERE id=member_row.id;
    IF person_key IS NULL THEN
      INSERT INTO ntubtob.people
        (display_name,portal_access_level,portal_status,version,created_at,updated_at)
      VALUES (member_row.name,'basic','inactive',1,transaction_timestamp(),transaction_timestamp())
      RETURNING id INTO person_key;
      UPDATE ntubtob.members SET person_id=person_key WHERE id=member_row.id AND person_id IS NULL;
      IF NOT FOUND THEN RAISE EXCEPTION 'TASK-065 concurrent member link drift'; END IF;
    ELSIF NOT EXISTS (SELECT 1 FROM ntubtob.people WHERE id=person_key AND display_name=member_row.name
                      AND portal_access_level='basic' AND portal_status='inactive') THEN
      RAISE EXCEPTION 'TASK-065 existing member Person drift';
    END IF;
    INSERT INTO ntubtob.access_audit
      (action,target_person_id,after_state,reason,request_id,created_at)
    VALUES ('member_backfilled',person_key,json_build_object('member_id',member_row.id),
            'Phase B permanent roster Person backfill','task065-member-'||member_row.id,transaction_timestamp())
    ON CONFLICT (request_id) DO NOTHING;
  END LOOP;

  FOR line_row IN
    SELECT l.id,l.line_user_id,l.member_id,m.person_id
    FROM ntubtob.line_users l JOIN ntubtob.members m ON m.id=l.member_id
    WHERE l.member_id IS NOT NULL AND l.ignored IS FALSE ORDER BY l.id FOR UPDATE OF l
  LOOP
    identity_key := NULL;
    INSERT INTO ntubtob.auth_identities
      (provider,provider_subject,person_id,status,created_at,updated_at)
    VALUES ('line',line_row.line_user_id,line_row.person_id,'linked',transaction_timestamp(),transaction_timestamp())
    ON CONFLICT (provider,provider_subject) DO NOTHING
    RETURNING id INTO identity_key;
    IF identity_key IS NULL THEN
      SELECT id INTO identity_key FROM ntubtob.auth_identities
      WHERE provider='line' AND provider_subject=line_row.line_user_id
        AND person_id=line_row.person_id AND status='linked';
      IF identity_key IS NULL THEN RAISE EXCEPTION 'TASK-065 identity collision'; END IF;
    END IF;
    INSERT INTO ntubtob.access_audit
      (action,target_person_id,auth_identity_id,after_state,reason,request_id,created_at)
    VALUES ('identity_linked',line_row.person_id,identity_key,json_build_object('provider','line'),
            'Phase B reliable legacy LINE member link','task065-identity-'||line_row.id,transaction_timestamp())
    ON CONFLICT (request_id) DO NOTHING;
  END LOOP;

  INSERT INTO ntubtob.person_qualifications
    (person_id,qualification,status,reason,created_at,updated_at)
  SELECT DISTINCT m.person_id,'team_player','active','Reliable legacy LINE member link',
         transaction_timestamp(),transaction_timestamp()
  FROM ntubtob.members m JOIN ntubtob.line_users l ON l.member_id=m.id
  WHERE l.ignored IS FALSE
  ON CONFLICT (person_id,qualification) DO NOTHING;

  INSERT INTO ntubtob.access_audit
    (action,target_person_id,after_state,reason,request_id,created_at)
  SELECT 'qualification_granted',q.person_id,json_build_object('qualification','team_player'),
         'Phase B reliable legacy LINE member link','task065-team-player-'||m.id,transaction_timestamp()
  FROM ntubtob.person_qualifications q JOIN ntubtob.members m ON m.person_id=q.person_id
  WHERE q.qualification='team_player' AND q.status='active'
  ON CONFLICT (request_id) DO NOTHING;
END
$task065$;
COMMIT;
