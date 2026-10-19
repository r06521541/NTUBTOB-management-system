"""Private, exact-row privacy mutations; no grants, purge or runtime enablement.

The migration owner must differ from the runtime role. Table owners/superusers are
outside this capability boundary. Grant EXECUTE only to a separately reviewed
internal fulfillment principal; PUBLIC receives no permission. Manual decisions
are trusted review inputs, not an automatic inference about textual ownership.
"""

from alembic import op

revision = "0018_erasure_privacy_mutation"
down_revision = "0017_erasure_work_items"
branch_labels = None
depends_on = None

# Identifiers below are source constants, never SQL supplied by callers.
FIELDS = {
    "access_audit": (
        "actor_person_id",
        "target_person_id",
        "auth_identity_id",
        "reason",
        "before_state",
        "after_state",
    ),
    "event_audit": ("actor_person_id", "reason", "details"),
    "mobile_notifications": ("title", "body"),
    "mobile_notification_publish_audits": ("actor_person_id", "audience_reference_id"),
    "event_notification_publish_audits": ("actor_person_id",),
    "guest_qualification_audits": (
        "actor_person_id",
        "reason",
        "before_state",
        "after_state",
    ),
    "events": ("created_by_person_id", "title"),
    "event_invitee_overrides": ("actor_person_id", "reason"),
    "event_invitees": ("actor_person_id", "reason"),
    "event_managers": ("assigned_by_person_id",),
    "person_qualifications": ("granted_by_person_id", "reason"),
    "identity_review_messages": ("sender_person_id", "body", "body_redacted"),
    "identity_review_threads": ("auth_identity_id",),
    "activities": ("title",),
    "games": ("location", "home_team", "away_team"),
}
IMMUTABLE = tuple(FIELDS)[:6]
NULLABLE = {
    "event_audit": "actor_person_id",
    "mobile_notification_publish_audits": "actor_person_id",
    "event_notification_publish_audits": "actor_person_id",
    "guest_qualification_audits": "actor_person_id",
    "events": "created_by_person_id",
    "event_invitee_overrides": "actor_person_id",
    "event_managers": "assigned_by_person_id",
    "identity_review_threads": "auth_identity_id",
}
OLD_TRIGGERS = {
    "access_audit": "access_audit_append_only",
    "event_audit": "event_audit_append_only",
    "mobile_notifications": "mobile_notification_content_immutable",
    "mobile_notification_publish_audits": "mobile_notification_audit_immutable",
    "event_notification_publish_audits": "event_notification_publish_audits_append_only",
    "guest_qualification_audits": "guest_qualification_audits_append_only",
}


def upgrade():
    op.execute(
        """
    CREATE TABLE ntubtob.erasure_privacy_permits (
      backend integer NOT NULL, transaction_id bigint NOT NULL,
      table_name text NOT NULL, row_id bigint NOT NULL, operation text NOT NULL,
      old_hash text NOT NULL, new_hash text,
      PRIMARY KEY (backend,transaction_id,table_name,row_id)
    );
    REVOKE ALL ON ntubtob.erasure_privacy_permits FROM PUBLIC;
    ALTER TABLE ntubtob.erasure_privacy_permits ENABLE ROW LEVEL SECURITY;

    CREATE FUNCTION ntubtob.guard_erasure_privacy_mutation() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    DECLARE before_row jsonb; after_row jsonb; permitted boolean; column_name text;
    BEGIN
      IF TG_OP='INSERT' THEN
        after_row := to_jsonb(NEW);
        IF TG_ARGV[1] <> '' AND after_row->TG_ARGV[1]='null'::jsonb THEN
          RAISE EXCEPTION 'privacy attribution required' USING ERRCODE='23514';
        END IF;
        IF TG_TABLE_NAME='event_invitees' AND after_row->>'source' <> 'qualification' AND after_row->'actor_person_id'='null'::jsonb THEN
          RAISE EXCEPTION 'privacy attribution required' USING ERRCODE='23514';
        END IF;
        IF TG_TABLE_NAME='identity_review_messages' AND after_row->>'sender_role'='admin' AND after_row->'sender_person_id'='null'::jsonb THEN
          RAISE EXCEPTION 'privacy attribution required' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END IF;
      before_row := to_jsonb(OLD);
      IF TG_OP='UPDATE' THEN after_row := to_jsonb(NEW); END IF;
      DELETE FROM ntubtob.erasure_privacy_permits
       WHERE backend=pg_backend_pid() AND transaction_id=txid_current()
         AND table_name=TG_TABLE_NAME AND row_id=OLD.id AND operation=TG_OP
         AND old_hash=encode(sha256(convert_to(before_row::text,'UTF8')),'hex')
         AND new_hash IS NOT DISTINCT FROM
             CASE WHEN TG_OP='UPDATE' THEN encode(sha256(convert_to(after_row::text,'UTF8')),'hex') END
       RETURNING true INTO permitted;
      IF permitted IS TRUE THEN
        IF TG_OP='DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
      END IF;
      IF TG_ARGV[0]='immutable' THEN
        RAISE EXCEPTION 'privacy permit required' USING ERRCODE='23514';
      END IF;
      IF TG_OP='UPDATE' THEN
        -- A historical redacted row may still be edited normally. A new
        -- attribution-requiring classification is not such a historical row.
        IF TG_TABLE_NAME='event_invitees' AND after_row->>'source' <> 'qualification'
           AND after_row->'source' IS DISTINCT FROM before_row->'source'
           AND after_row->'actor_person_id'='null'::jsonb THEN
          RAISE EXCEPTION 'privacy attribution required' USING ERRCODE='23514';
        END IF;
        IF TG_TABLE_NAME='identity_review_messages' AND after_row->>'sender_role'='admin'
           AND after_row->'sender_role' IS DISTINCT FROM before_row->'sender_role'
           AND after_row->'sender_person_id'='null'::jsonb THEN
          RAISE EXCEPTION 'privacy attribution required' USING ERRCODE='23514';
        END IF;
        FOREACH column_name IN ARRAY ARRAY['actor_person_id','created_by_person_id','assigned_by_person_id','granted_by_person_id','sender_person_id','auth_identity_id'] LOOP
          IF before_row ? column_name AND before_row->column_name <> 'null'::jsonb AND after_row->column_name='null'::jsonb THEN
            RAISE EXCEPTION 'privacy permit required' USING ERRCODE='23514';
          END IF;
        END LOOP;
        RETURN NEW;
      END IF;
      RETURN OLD;
    END;
    $$;
    REVOKE ALL ON FUNCTION ntubtob.guard_erasure_privacy_mutation() FROM PUBLIC;
    """
    )
    for table, column in NULLABLE.items():
        op.execute(f"ALTER TABLE ntubtob.{table} ALTER COLUMN {column} DROP NOT NULL")
    op.execute(
        """
      ALTER TABLE ntubtob.event_invitees DROP CONSTRAINT ck_event_invitee_source_fields;
      ALTER TABLE ntubtob.event_invitees ADD CONSTRAINT ck_event_invitee_source_fields CHECK (
        (source='qualification' AND source_qualification IS NOT NULL AND actor_person_id IS NULL) OR
        (source IN ('manual_include','manual_exclude') AND length(reason) BETWEEN 3 AND 300));
      ALTER TABLE ntubtob.identity_review_messages DROP CONSTRAINT ck_identity_review_sender;
      ALTER TABLE ntubtob.identity_review_messages ADD CONSTRAINT ck_identity_review_sender CHECK (
        (sender_role='applicant' AND sender_person_id IS NULL) OR sender_role='admin');
    """
    )
    for table in FIELDS:
        if table in OLD_TRIGGERS:
            op.execute(f"DROP TRIGGER {OLD_TRIGGERS[table]} ON ntubtob.{table}")
        mode = "immutable" if table in IMMUTABLE else "attribution"
        required = NULLABLE.get(table, "")
        op.execute(
            f"""
          CREATE TRIGGER erasure_privacy_guard BEFORE INSERT OR UPDATE OR DELETE ON ntubtob.{table}
          FOR EACH ROW EXECUTE FUNCTION ntubtob.guard_erasure_privacy_mutation('{mode}','{required}');
        """
        )
    allowed_case = "\n".join(
        "WHEN '%s' THEN ARRAY[%s]" % (table, ",".join("'%s'" % key for key in keys))
        for table, keys in FIELDS.items()
    )
    update_case = "\n".join(
        "WHEN '%s' THEN UPDATE ntubtob.%s SET %s FROM jsonb_populate_record(NULL::ntubtob.%s,new_row) AS desired WHERE %s.id=p_row;"
        % (table, table, ",".join(f"{key}=desired.{key}" for key in keys), table, table)
        for table, keys in FIELDS.items()
    )
    op.execute(
        """
    CREATE FUNCTION ntubtob.apply_erasure_privacy_mutation(
      p_job uuid,p_item uuid,p_table text,p_row bigint,p_old_hash text,p_patch jsonb,
      p_action text DEFAULT 'update') RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    DECLARE job ntubtob.account_erasure_jobs; item ntubtob.account_erasure_items;
      old_row jsonb; new_row jsonb; stored_row jsonb; affected_count bigint;
      allowed text[]; field text; generation uuid; owned_delete boolean;
      expected_binding text; last_sequence integer; last_kind text; failure_stage text := 'input';
    BEGIN
      IF current_setting('transaction_isolation') <> 'read committed' OR
         p_job IS NULL OR p_item IS NULL OR p_row IS NULL OR p_row<=0 OR
         p_old_hash IS NULL OR p_old_hash !~ '^[0-9a-f]{64}$' OR
         p_action IS NULL OR p_action NOT IN ('update','delete') OR
         p_patch IS NULL OR jsonb_typeof(p_patch)<>'object' THEN
        RAISE EXCEPTION 'privacy input rejected' USING ERRCODE='23514';
      END IF;
      allowed := CASE p_table
    """
        + allowed_case
        + """
        ELSE NULL END;
      IF allowed IS NULL THEN RAISE EXCEPTION 'privacy table rejected' USING ERRCODE='23514'; END IF;
      PERFORM pg_advisory_xact_lock(70070);
      PERFORM pg_advisory_xact_lock(1315198274);
      failure_stage := 'job_binding';
      SELECT * INTO job FROM ntubtob.account_erasure_jobs WHERE id=p_job FOR UPDATE;
      IF NOT FOUND OR job.status<>'processing' OR job.irreversible_started_at IS NULL THEN
        RAISE EXCEPTION 'privacy job rejected' USING ERRCODE='23514';
      END IF;
      SELECT * INTO item FROM ntubtob.account_erasure_items WHERE id=p_item FOR UPDATE;
      IF NOT FOUND OR item.job_id<>job.id OR item.expected_generation<>job.expected_generation OR
         item.stage NOT IN ('online_erasure','manual_redaction') THEN
        RAISE EXCEPTION 'privacy item rejected' USING ERRCODE='23514';
      END IF;
      IF job.target_kind='person' THEN
        SELECT account_generation INTO generation FROM ntubtob.people WHERE id=job.person_id FOR UPDATE;
      ELSE
        SELECT account_generation INTO generation FROM ntubtob.auth_identities
          WHERE id=job.auth_identity_id AND person_id IS NULL AND status IN ('pending','blocked','disabled') FOR UPDATE;
      END IF;
      IF generation IS DISTINCT FROM job.expected_generation THEN
        RAISE EXCEPTION 'privacy generation rejected' USING ERRCODE='23514';
      END IF;
      SELECT event_sequence,event_kind INTO last_sequence,last_kind FROM ntubtob.account_erasure_item_events
        WHERE item_id=p_item ORDER BY event_sequence DESC LIMIT 1;
      IF last_sequence IS DISTINCT FROM 1 OR last_kind IS DISTINCT FROM 'started' THEN
        RAISE EXCEPTION 'privacy start required' USING ERRCODE='23514';
      END IF;
      failure_stage := 'item_binding';
      expected_binding := encode(sha256(convert_to(jsonb_build_array('privacy_mutation_v1',p_job,
        job.expected_generation,p_table,p_row,p_old_hash,p_patch,p_action)::text,'UTF8')),'hex');
      IF item.binding_hash<>expected_binding THEN
        RAISE EXCEPTION 'privacy binding rejected' USING ERRCODE='23514';
      END IF;
      -- p_table is a checked source allowlist, never a caller SQL expression.
      failure_stage := 'row_version';
      EXECUTE format('SELECT to_jsonb(t) FROM ntubtob.%I t WHERE id=$1 FOR UPDATE',p_table)
        INTO old_row USING p_row;
      IF old_row IS NULL OR encode(sha256(convert_to(old_row::text,'UTF8')),'hex')<>p_old_hash THEN
        RAISE EXCEPTION 'privacy version rejected' USING ERRCODE='23514';
      END IF;
      failure_stage := 'disposition';
      IF p_action='delete' THEN
        IF p_patch<>'{}'::jsonb OR
           p_table NOT IN ('access_audit','guest_qualification_audits','identity_review_messages') OR
           item.stage<>'manual_redaction' THEN
          RAISE EXCEPTION 'privacy delete rejected' USING ERRCODE='23514';
        END IF;
        owned_delete := false;
        IF p_table IN ('access_audit','guest_qualification_audits') THEN
          owned_delete := job.person_id IS NOT NULL AND
            (old_row->>'target_person_id')::bigint IS NOT DISTINCT FROM job.person_id;
          IF p_table='access_audit' AND old_row->'target_person_id'='null'::jsonb THEN
            IF job.person_id IS NOT NULL THEN
              -- Historical identity-only evidence belongs to its current Person,
              -- never merely to the actor that performed a review.
              PERFORM 1 FROM ntubtob.auth_identities
                WHERE id=(old_row->>'auth_identity_id')::bigint AND person_id=job.person_id FOR UPDATE;
              owned_delete := FOUND;
            ELSIF job.target_kind='pending_identity' AND job.auth_identity_id IS NOT NULL THEN
              owned_delete := (old_row->>'auth_identity_id')::bigint IS NOT DISTINCT FROM job.auth_identity_id;
            END IF;
          END IF;
        ELSIF job.person_id IS NOT NULL THEN
          owned_delete := (old_row->>'sender_person_id')::bigint IS NOT DISTINCT FROM job.person_id;
          IF old_row->>'sender_role'='applicant' THEN
            -- The containing thread alone never establishes authorship of an
            -- administrator's message. Both current relationship rows stay locked.
            PERFORM 1 FROM ntubtob.identity_review_threads t
              JOIN ntubtob.auth_identities i ON i.id=t.auth_identity_id
              WHERE t.id=(old_row->>'thread_id')::bigint AND i.person_id=job.person_id FOR UPDATE OF t,i;
            owned_delete := FOUND;
          END IF;
        END IF;
        IF owned_delete IS NOT TRUE THEN
          RAISE EXCEPTION 'privacy delete rejected' USING ERRCODE='23514';
        END IF;
        failure_stage := 'storage_mutation';
        INSERT INTO ntubtob.erasure_privacy_permits VALUES
          (pg_backend_pid(),txid_current(),p_table,p_row,'DELETE',p_old_hash,NULL);
        IF p_table='access_audit' THEN DELETE FROM ntubtob.access_audit WHERE id=p_row;
        ELSIF p_table='guest_qualification_audits' THEN DELETE FROM ntubtob.guest_qualification_audits WHERE id=p_row;
        ELSE DELETE FROM ntubtob.identity_review_messages WHERE id=p_row; END IF;
      ELSE
        IF p_patch='{}'::jsonb THEN RAISE EXCEPTION 'privacy empty patch' USING ERRCODE='23514'; END IF;
        FOR field IN SELECT jsonb_object_keys(p_patch) LOOP
          IF NOT field=ANY(allowed) OR NOT old_row ? field THEN
            RAISE EXCEPTION 'privacy field rejected' USING ERRCODE='23514';
          END IF;
          IF field IN ('actor_person_id','target_person_id','created_by_person_id','assigned_by_person_id','granted_by_person_id','sender_person_id') THEN
            IF p_patch->field<>'null'::jsonb OR job.person_id IS NULL OR
               (old_row->>field)::bigint IS DISTINCT FROM job.person_id THEN
              RAISE EXCEPTION 'privacy attribution rejected' USING ERRCODE='23514';
            END IF;
          ELSIF field='auth_identity_id' THEN
            IF p_patch->field<>'null'::jsonb OR
               (p_table='identity_review_threads' AND
                (job.person_id IS NULL OR item.stage<>'manual_redaction')) THEN
              RAISE EXCEPTION 'privacy identity rejected' USING ERRCODE='23514';
            END IF;
            PERFORM 1 FROM ntubtob.auth_identities WHERE id=(old_row->>field)::bigint AND
              ((job.person_id IS NOT NULL AND person_id=job.person_id) OR id=job.auth_identity_id) FOR UPDATE;
            IF NOT FOUND THEN
              RAISE EXCEPTION 'privacy identity rejected' USING ERRCODE='23514';
            END IF;
          ELSIF field='audience_reference_id' THEN
            IF p_patch->field<>'null'::jsonb OR job.person_id IS NULL OR
               old_row->>'audience_type'<>'individual' OR
               (old_row->>field)::bigint IS DISTINCT FROM job.person_id THEN
              RAISE EXCEPTION 'privacy audience rejected' USING ERRCODE='23514';
            END IF;
          ELSIF item.stage<>'manual_redaction' THEN
            RAISE EXCEPTION 'privacy review required' USING ERRCODE='23514';
          END IF;
        END LOOP;
        new_row := old_row || p_patch;
        IF new_row=old_row THEN
          RAISE EXCEPTION 'privacy unchanged patch' USING ERRCODE='23514';
        END IF;
        failure_stage := 'storage_mutation';
        INSERT INTO ntubtob.erasure_privacy_permits VALUES
          (pg_backend_pid(),txid_current(),p_table,p_row,'UPDATE',p_old_hash,
           encode(sha256(convert_to(new_row::text,'UTF8')),'hex'));
        CASE p_table
    """
        + update_case
        + """
        ELSE RAISE EXCEPTION 'privacy table rejected' USING ERRCODE='23514'; END CASE;
      END IF;
      GET DIAGNOSTICS affected_count = ROW_COUNT;
      failure_stage := 'storage_verification';
      IF affected_count IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'privacy row count rejected' USING ERRCODE='23514';
      END IF;
      EXECUTE format('SELECT to_jsonb(t) FROM ntubtob.%I t WHERE id=$1',p_table)
        INTO stored_row USING p_row;
      IF (p_action='delete' AND stored_row IS NOT NULL) OR
         (p_action='update' AND stored_row IS DISTINCT FROM new_row) THEN
        RAISE EXCEPTION 'privacy postimage rejected' USING ERRCODE='23514';
      END IF;
      IF EXISTS (SELECT 1 FROM ntubtob.erasure_privacy_permits WHERE backend=pg_backend_pid()
          AND transaction_id=txid_current() AND table_name=p_table AND row_id=p_row) THEN
        RAISE EXCEPTION 'privacy permit not consumed' USING ERRCODE='23514';
      END IF;
    EXCEPTION WHEN OTHERS THEN
      -- Type/constraint errors can include private replacement text. Do not
      -- propagate SQLERRM/DETAIL; the failed block also rolls back its permit.
      RAISE EXCEPTION 'privacy mutation rejected at %',failure_stage USING ERRCODE='23514';
    END;
    $$;
    REVOKE ALL ON FUNCTION ntubtob.apply_erasure_privacy_mutation(uuid,uuid,text,bigint,text,jsonb,text) FROM PUBLIC;
    """
    )
    op.execute(
        """
        -- Object-specific cleanup includes named ALTER DEFAULT PRIVILEGES
        -- grants. Never rewrite the owner's global/default ACL configuration.
        DO $$
        DECLARE recipient record; signature text; recipient_sql text;
        BEGIN
          FOR recipient IN
            SELECT DISTINCT a.grantee,r.rolname
              FROM pg_catalog.pg_class c
              CROSS JOIN LATERAL pg_catalog.aclexplode(
                COALESCE(c.relacl,pg_catalog.acldefault('r',c.relowner))) a
              LEFT JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
              WHERE c.oid='ntubtob.erasure_privacy_permits'::regclass AND a.grantee<>c.relowner
          LOOP
            recipient_sql := CASE WHEN recipient.grantee=0 THEN 'PUBLIC'
              ELSE pg_catalog.quote_ident(recipient.rolname) END;
            EXECUTE 'REVOKE ALL ON TABLE ntubtob.erasure_privacy_permits FROM ' || recipient_sql || ' CASCADE';
          END LOOP;
          FOREACH signature IN ARRAY ARRAY[
            'ntubtob.guard_erasure_privacy_mutation()',
            'ntubtob.apply_erasure_privacy_mutation(uuid,uuid,text,bigint,text,jsonb,text)'
          ] LOOP
            FOR recipient IN
              SELECT DISTINCT a.grantee,r.rolname
                FROM pg_catalog.pg_proc p
                CROSS JOIN LATERAL pg_catalog.aclexplode(
                  COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
                LEFT JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
                WHERE p.oid=signature::regprocedure AND a.grantee<>p.proowner
            LOOP
              recipient_sql := CASE WHEN recipient.grantee=0 THEN 'PUBLIC'
                ELSE pg_catalog.quote_ident(recipient.rolname) END;
              EXECUTE 'REVOKE ALL ON FUNCTION ' || signature || ' FROM ' || recipient_sql || ' CASCADE';
            END LOOP;
          END LOOP;
        END;
        $$;
        """
    )

    op.execute(
        """
    CREATE TABLE ntubtob.account_erasure_sealed_plans (
      job_id uuid PRIMARY KEY REFERENCES ntubtob.account_erasure_jobs(id) ON DELETE RESTRICT,
      key_id varchar(64) NOT NULL,
      ciphertext bytea NOT NULL,
      CONSTRAINT ck_erasure_plan_key CHECK (key_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'),
      CONSTRAINT ck_erasure_plan_size CHECK (octet_length(ciphertext) BETWEEN 52 AND 4194355)
    );
    ALTER TABLE ntubtob.account_erasure_sealed_plans ENABLE ROW LEVEL SECURITY;
    CREATE FUNCTION ntubtob.guard_erasure_sealed_plan() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog AS $$
    DECLARE target_status text;
    BEGIN
      IF pg_catalog.row_security_active('ntubtob.account_erasure_jobs'::regclass) IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'sealed plan binding rejected' USING ERRCODE='23514';
      END IF;
      SELECT status INTO target_status FROM ntubtob.account_erasure_jobs WHERE id=NEW.job_id FOR UPDATE;
      IF NOT FOUND OR target_status<>'requested' THEN
        RAISE EXCEPTION 'sealed plan binding rejected' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END;
    $$;
    CREATE FUNCTION ntubtob.guard_erasure_sealed_plan_job_binding() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog AS $$
    BEGIN
      IF pg_catalog.row_security_active('ntubtob.account_erasure_sealed_plans'::regclass) IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'sealed plan binding rejected' USING ERRCODE='23514';
      END IF;
      IF EXISTS (SELECT 1 FROM ntubtob.account_erasure_sealed_plans WHERE job_id=OLD.id) AND (
        NEW.scope_version IS DISTINCT FROM OLD.scope_version OR
        NEW.scope_hash IS DISTINCT FROM OLD.scope_hash OR
        NEW.retention_policy_version IS DISTINCT FROM OLD.retention_policy_version OR
        NEW.fulfillment_due_at IS DISTINCT FROM OLD.fulfillment_due_at OR
        NEW.receipt_expires_at IS DISTINCT FROM OLD.receipt_expires_at OR
        NEW.evidence_expires_at IS DISTINCT FROM OLD.evidence_expires_at
      ) THEN
        RAISE EXCEPTION 'sealed plan binding rejected' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END;
    $$;
    CREATE TRIGGER erasure_sealed_plan_insert_guard BEFORE INSERT ON ntubtob.account_erasure_sealed_plans
      FOR EACH ROW EXECUTE FUNCTION ntubtob.guard_erasure_sealed_plan();
    CREATE TRIGGER erasure_sealed_plan_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON ntubtob.account_erasure_sealed_plans
      FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.reject_erasure_evidence_mutation();
    CREATE TRIGGER erasure_sealed_plan_job_binding BEFORE UPDATE ON ntubtob.account_erasure_jobs
      FOR EACH ROW EXECUTE FUNCTION ntubtob.guard_erasure_sealed_plan_job_binding();
    DO $$
    DECLARE recipient record; signature text; recipient_sql text;
    BEGIN
      FOR recipient IN
        SELECT DISTINCT a.grantee,r.rolname FROM pg_catalog.pg_class c
        CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE(c.relacl,pg_catalog.acldefault('r',c.relowner))) a
        LEFT JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
        WHERE c.oid='ntubtob.account_erasure_sealed_plans'::regclass AND a.grantee<>c.relowner
      LOOP
        recipient_sql := CASE WHEN recipient.grantee=0 THEN 'PUBLIC' ELSE pg_catalog.quote_ident(recipient.rolname) END;
        EXECUTE 'REVOKE ALL ON TABLE ntubtob.account_erasure_sealed_plans FROM ' || recipient_sql;
      END LOOP;
      FOREACH signature IN ARRAY ARRAY['ntubtob.guard_erasure_sealed_plan()','ntubtob.guard_erasure_sealed_plan_job_binding()'] LOOP
        FOR recipient IN
          SELECT DISTINCT a.grantee,r.rolname FROM pg_catalog.pg_proc p
          CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
          LEFT JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
          WHERE p.oid=signature::regprocedure AND a.grantee<>p.proowner
        LOOP
          recipient_sql := CASE WHEN recipient.grantee=0 THEN 'PUBLIC' ELSE pg_catalog.quote_ident(recipient.rolname) END;
          EXECUTE 'REVOKE ALL ON FUNCTION ' || signature || ' FROM ' || recipient_sql;
        END LOOP;
      END LOOP;
    END;
    $$;
    """
    )


def downgrade():
    # Attribution cannot be reconstructed; retain guards and nullable history.
    pass
