"""Private backup observations and a global new-effect start backstop.

No grants, scheduler, inventory acquisition, automatic retention renewal, live
purge or runtime activation. An explicit private function can remove one eligible
sealed plan; it is not all-copy or minimal-ledger cleanup. Trusted independent operators must review actual complete
inventory before recording its digest. A caller-supplied boolean is not evidence
when the caller has not been granted this private operational capability.
"""

from alembic import op

revision = "0022_erasure_retention"
down_revision = "0021_erasure_continuity"
branch_labels = None
depends_on = None


def _marker(signature, old, new):
    before = f"ARRAY['{old}']::text[]".replace("'", "''")
    after = f"ARRAY['{new}']::text[]".replace("'", "''")
    op.execute(
        f"""DO $$ DECLARE source text; BEGIN
        SELECT pg_get_functiondef('{signature}'::regprocedure) INTO source;
        IF source IS NULL OR length(source)-length(replace(source,'{before}',''))<>length('{before}')
          OR position('{after}' in source)>0 THEN
          RAISE EXCEPTION 'retention_definition_changed';
        END IF;
        EXECUTE replace(source,'{before}','{after}');
        END $$;"""
    )


def upgrade():
    op.execute(
        """
        CREATE TABLE ntubtob.account_erasure_backup_checks (
          operation_id uuid PRIMARY KEY,
          request_id uuid NOT NULL,
          target_kind varchar(24) NOT NULL,
          expected_generation uuid NOT NULL,
          original_requested_at timestamptz NOT NULL,
          original_receipt_hash char(64) NOT NULL,
          sequence bigint NOT NULL,
          inventory_digest char(64) NOT NULL,
          checked_at timestamptz NOT NULL,
          inventory_complete boolean NOT NULL,
          last_restorable_until timestamptz,
          suppression_verified_at timestamptz,
          binding_readable boolean NOT NULL,
          key_readable boolean NOT NULL,
          operator_name varchar(63) NOT NULL,
          CONSTRAINT ck_erasure_backup_target CHECK(target_kind IN ('person','pending_identity')),
          CONSTRAINT uq_erasure_backup_sequence UNIQUE(request_id,sequence),
          CONSTRAINT ck_erasure_backup_sequence CHECK(sequence>0),
          CONSTRAINT ck_erasure_backup_hashes CHECK(original_receipt_hash ~ '^[0-9a-f]{64}$'
            AND inventory_digest ~ '^[0-9a-f]{64}$'),
          CONSTRAINT ck_erasure_backup_times CHECK(isfinite(original_requested_at)
            AND isfinite(checked_at) AND checked_at>=original_requested_at
            AND (last_restorable_until IS NULL OR isfinite(last_restorable_until))
            AND (suppression_verified_at IS NULL OR (isfinite(suppression_verified_at)
              AND suppression_verified_at BETWEEN original_requested_at AND checked_at)))
        );
        CREATE INDEX ix_erasure_backup_request_checked ON ntubtob.account_erasure_backup_checks(request_id,checked_at);
        ALTER TABLE ntubtob.account_erasure_backup_checks ENABLE ROW LEVEL SECURITY;
        CREATE TRIGGER erasure_backup_append_only
          BEFORE UPDATE OR DELETE OR TRUNCATE ON ntubtob.account_erasure_backup_checks
          FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.reject_erasure_evidence_mutation();

        CREATE FUNCTION ntubtob.record_erasure_backup_check(
          p_operation uuid,p_request uuid,p_generation uuid,p_inventory text,
          p_complete boolean,p_horizon timestamptz,p_suppression timestamptz,
          p_binding boolean,p_key boolean) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
        DECLARE root record; intake record; replay record; applied_time timestamptz; table_name text;
          previous_sequence bigint; previous_time timestamptz;
        BEGIN
          IF p_operation IS NULL OR p_request IS NULL OR p_generation IS NULL
            OR p_inventory IS NULL OR p_inventory !~ '^[0-9a-f]{64}$'
            OR p_complete IS NULL OR p_binding IS NULL OR p_key IS NULL
            OR (p_horizon IS NOT NULL AND NOT isfinite(p_horizon))
            OR (p_suppression IS NOT NULL AND NOT isfinite(p_suppression)) THEN
            RAISE EXCEPTION 'backup_check_input_rejected' USING ERRCODE='23514';
          END IF;
          IF current_setting('transaction_isolation')<>'read committed' THEN
            RAISE EXCEPTION 'backup_check_transaction_rejected' USING ERRCODE='23514';
          END IF;
          PERFORM pg_advisory_xact_lock(70070);
          PERFORM pg_advisory_xact_lock(1315198274);
          IF (SELECT array_agg(version_num::text ORDER BY version_num) FROM ntubtob.alembic_version)
            IS DISTINCT FROM ARRAY['0022_erasure_retention']::text[] THEN
            RAISE EXCEPTION 'backup_check_schema_not_ready' USING ERRCODE='23514';
          END IF;
          FOREACH table_name IN ARRAY ARRAY['account_erasure_jobs','account_erasure_intakes','account_erasure_backup_checks'] LOOP
            IF row_security_active(('ntubtob.'||table_name)::regclass) IS DISTINCT FROM FALSE THEN
              RAISE EXCEPTION 'backup_check_unfiltered_state_required' USING ERRCODE='23514';
            END IF;
          END LOOP;
          SELECT * INTO intake FROM ntubtob.account_erasure_intakes WHERE id=p_request FOR UPDATE;
          SELECT * INTO root FROM ntubtob.account_erasure_jobs WHERE id=p_request FOR UPDATE;
          IF root.id IS NULL THEN root:=intake;
          ELSIF intake.id IS NOT NULL AND (intake.status<>'materialized' OR
            ROW(root.target_kind,root.expected_generation,root.requested_at,root.receipt_secret_hash)
            IS DISTINCT FROM ROW(intake.target_kind,intake.expected_generation,intake.requested_at,intake.receipt_secret_hash)) THEN
            RAISE EXCEPTION 'backup_check_root_changed' USING ERRCODE='23514';
          END IF;
          IF root.id IS NULL OR root.expected_generation<>p_generation THEN
            RAISE EXCEPTION 'backup_check_root_rejected' USING ERRCODE='23514';
          END IF;
          SELECT * INTO replay FROM ntubtob.account_erasure_backup_checks WHERE operation_id=p_operation;
          IF FOUND THEN
            IF ROW(replay.request_id,replay.expected_generation,replay.inventory_digest::text,
              replay.inventory_complete,replay.last_restorable_until,replay.suppression_verified_at,
              replay.binding_readable,replay.key_readable,replay.operator_name::text)
              IS NOT DISTINCT FROM ROW(p_request,p_generation,p_inventory,p_complete,p_horizon,p_suppression,p_binding,p_key,SESSION_USER::text)
              AND ROW(replay.target_kind,replay.original_requested_at,replay.original_receipt_hash)
              IS NOT DISTINCT FROM ROW(root.target_kind,root.requested_at,root.receipt_secret_hash) THEN
              RETURN p_operation;
            END IF;
            RAISE EXCEPTION 'backup_check_operation_replay' USING ERRCODE='23514';
          END IF;
          SELECT sequence,checked_at INTO previous_sequence,previous_time
            FROM ntubtob.account_erasure_backup_checks WHERE request_id=p_request ORDER BY sequence DESC LIMIT 1;
          applied_time:=clock_timestamp();
          IF applied_time<GREATEST(root.requested_at,root.updated_at,COALESCE(previous_time,root.requested_at))
            OR (p_suppression IS NOT NULL AND (p_suppression>applied_time OR p_suppression<root.requested_at)) THEN
            RAISE EXCEPTION 'backup_check_clock_rejected' USING ERRCODE='23514';
          END IF;
          INSERT INTO ntubtob.account_erasure_backup_checks VALUES
            (p_operation,p_request,root.target_kind,p_generation,root.requested_at,root.receipt_secret_hash,COALESCE(previous_sequence,0)+1,
             p_inventory,applied_time,p_complete,p_horizon,p_suppression,p_binding,p_key,SESSION_USER);
          RETURN p_operation;
        END $$;

        CREATE FUNCTION ntubtob.guard_erasure_retention_start() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
        DECLARE table_name text; checked_time timestamptz;
        BEGIN
          IF current_setting('transaction_isolation')<>'read committed' THEN
            RAISE EXCEPTION 'retention_transaction_rejected' USING ERRCODE='23514';
          END IF;
          PERFORM pg_advisory_xact_lock(70070);
          PERFORM pg_advisory_xact_lock(1315198274);
          IF (SELECT array_agg(version_num::text ORDER BY version_num) FROM ntubtob.alembic_version)
            IS DISTINCT FROM ARRAY['0022_erasure_retention']::text[] THEN
            RAISE EXCEPTION 'retention_schema_not_ready' USING ERRCODE='23514';
          END IF;
          FOREACH table_name IN ARRAY ARRAY['account_erasure_jobs','account_erasure_intakes','account_erasure_items','account_erasure_backup_checks'] LOOP
            IF row_security_active(('ntubtob.'||table_name)::regclass) IS DISTINCT FROM FALSE THEN
              RAISE EXCEPTION 'retention_unfiltered_state_required' USING ERRCODE='23514';
            END IF;
          END LOOP;
          -- Only the immutable restore-binding custody item may still be
          -- established. Provider/local/privacy/finalization starts are fenced.
          IF EXISTS(SELECT 1 FROM ntubtob.account_erasure_items WHERE id=NEW.item_id AND stage='restore_suppression') THEN
            RETURN NEW;
          END IF;
          checked_time:=clock_timestamp();
          IF EXISTS (
            SELECT 1 FROM (
              SELECT id,target_kind,expected_generation,requested_at,receipt_secret_hash FROM ntubtob.account_erasure_jobs
              UNION ALL
              SELECT i.id,i.target_kind,i.expected_generation,i.requested_at,i.receipt_secret_hash
                FROM ntubtob.account_erasure_intakes i
                WHERE NOT EXISTS(SELECT 1 FROM ntubtob.account_erasure_jobs j WHERE j.id=i.id)
            ) root LEFT JOIN LATERAL (
              SELECT * FROM ntubtob.account_erasure_backup_checks b WHERE b.request_id=root.id
                ORDER BY b.sequence DESC LIMIT 1
            ) observation ON true
            WHERE root.requested_at<=checked_time-interval '150 days' AND (
              observation.operation_id IS NULL OR
              ROW(observation.target_kind,observation.expected_generation,observation.original_requested_at,observation.original_receipt_hash)
                IS DISTINCT FROM ROW(root.target_kind,root.expected_generation,root.requested_at,root.receipt_secret_hash)
              OR observation.checked_at<checked_time-interval '30 days'
              OR observation.checked_at>checked_time OR NOT observation.inventory_complete
              OR observation.last_restorable_until IS NULL
              OR NOT observation.binding_readable OR NOT observation.key_readable)
          ) THEN
            RAISE EXCEPTION 'retention_backup_horizon_unresolved' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$;
        -- BEFORE alphabetically precedes the existing parent/item-lock guard.
        -- No exemption based on an already-processing job. Existing outcomes and
        -- reconciliations are not new dispatches and do not invoke this trigger.
        CREATE TRIGGER erasure_00_retention_start BEFORE INSERT ON ntubtob.account_erasure_item_events
          FOR EACH ROW WHEN(NEW.event_sequence=1 AND NEW.event_kind='started')
          EXECUTE FUNCTION ntubtob.guard_erasure_retention_start();
        REVOKE ALL ON TABLE ntubtob.account_erasure_backup_checks FROM PUBLIC;
        REVOKE ALL ON FUNCTION ntubtob.record_erasure_backup_check(uuid,uuid,uuid,text,boolean,timestamptz,timestamptz,boolean,boolean) FROM PUBLIC;
        REVOKE ALL ON FUNCTION ntubtob.guard_erasure_retention_start() FROM PUBLIC;
        DO $$ DECLARE grant_row record; signature text; BEGIN
          FOR grant_row IN SELECT DISTINCT a.grantee FROM pg_class c,
            LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
            WHERE c.oid='ntubtob.account_erasure_backup_checks'::regclass AND a.grantee<>c.relowner AND a.grantee<>0 LOOP
            EXECUTE format('REVOKE ALL ON TABLE ntubtob.account_erasure_backup_checks FROM %I',pg_get_userbyid(grant_row.grantee));
          END LOOP;
          FOREACH signature IN ARRAY ARRAY[
            'ntubtob.record_erasure_backup_check(uuid,uuid,uuid,text,boolean,timestamptz,timestamptz,boolean,boolean)',
            'ntubtob.guard_erasure_retention_start()'] LOOP
            FOR grant_row IN SELECT DISTINCT a.grantee FROM pg_proc p,
              LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a
              WHERE p.oid=signature::regprocedure AND a.grantee<>p.proowner AND a.grantee<>0 LOOP
              EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I',signature,pg_get_userbyid(grant_row.grantee));
            END LOOP;
          END LOOP;
        END $$;
        """
    )
    _private_plan_cleanup()
    for signature in (
        "ntubtob.suspend_management_for_erasure(uuid,uuid,bigint,uuid)",
        "ntubtob.extend_erasure_continuity(uuid,uuid,bigint,uuid,timestamptz,timestamptz)",
    ):
        _marker(signature, down_revision, revision)


def downgrade():
    op.execute(
        """LOCK TABLE ntubtob.account_erasure_backup_checks IN ACCESS EXCLUSIVE MODE;
        DO $$ BEGIN
          IF row_security_active('ntubtob.account_erasure_backup_checks'::regclass) IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'retention_unfiltered_state_required';
          END IF;
          IF EXISTS(SELECT 1 FROM ntubtob.account_erasure_backup_checks) THEN
            RAISE EXCEPTION 'retention_evidence_retained';
          END IF;
          IF row_security_active('ntubtob.account_erasure_plan_purges'::regclass) IS DISTINCT FROM FALSE
            OR row_security_active('ntubtob.erasure_plan_delete_permits'::regclass) IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'retention_unfiltered_state_required';
          END IF;
          IF EXISTS(SELECT 1 FROM ntubtob.account_erasure_plan_purges)
            OR EXISTS(SELECT 1 FROM ntubtob.erasure_plan_delete_permits) THEN
            RAISE EXCEPTION 'retention_evidence_retained';
          END IF;
        END $$;"""
    )
    for signature in (
        "ntubtob.suspend_management_for_erasure(uuid,uuid,bigint,uuid)",
        "ntubtob.extend_erasure_continuity(uuid,uuid,bigint,uuid,timestamptz,timestamptz)",
    ):
        _marker(signature, revision, down_revision)
    op.execute(
        """DROP TRIGGER erasure_sealed_plan_delete_guard ON ntubtob.account_erasure_sealed_plans;
        DROP TRIGGER erasure_sealed_plan_immutable ON ntubtob.account_erasure_sealed_plans;
        CREATE TRIGGER erasure_sealed_plan_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON ntubtob.account_erasure_sealed_plans
          FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.reject_erasure_evidence_mutation();
        DROP FUNCTION ntubtob.purge_erasure_sealed_plan(uuid,uuid,text,uuid);
        DROP FUNCTION ntubtob.consume_erasure_plan_delete_permit();
        DROP TABLE ntubtob.erasure_plan_delete_permits;
        DROP TABLE ntubtob.account_erasure_plan_purges;
        DROP TRIGGER erasure_00_retention_start ON ntubtob.account_erasure_item_events;
        DROP FUNCTION ntubtob.guard_erasure_retention_start();
        DROP FUNCTION ntubtob.record_erasure_backup_check(uuid,uuid,uuid,text,boolean,timestamptz,timestamptz,boolean,boolean);
        DROP TABLE ntubtob.account_erasure_backup_checks;"""
    )


def _private_plan_cleanup():
    # Fixed one-row delete, never a general evidence/table mutation capability.
    op.execute(
        """
        CREATE TABLE ntubtob.erasure_plan_delete_permits (
          backend integer NOT NULL,transaction_id bigint NOT NULL,job_id uuid NOT NULL,
          row_hash char(64) NOT NULL,
          PRIMARY KEY(backend,transaction_id,job_id)
        );
        ALTER TABLE ntubtob.erasure_plan_delete_permits ENABLE ROW LEVEL SECURITY;
        CREATE TABLE ntubtob.account_erasure_plan_purges (
          operation_id uuid PRIMARY KEY,
          job_id uuid NOT NULL UNIQUE REFERENCES ntubtob.account_erasure_jobs(id) ON DELETE RESTRICT,
          expected_generation uuid NOT NULL,scope_hash char(64) NOT NULL,
          backup_operation_id uuid NOT NULL REFERENCES ntubtob.account_erasure_backup_checks(operation_id) ON DELETE RESTRICT,
          row_hash char(64) NOT NULL,occurred_at timestamptz NOT NULL,operator_name varchar(63) NOT NULL,
          CONSTRAINT ck_erasure_plan_purge_hashes CHECK(scope_hash ~ '^[0-9a-f]{64}$' AND row_hash ~ '^[0-9a-f]{64}$'),
          CONSTRAINT ck_erasure_plan_purge_time CHECK(isfinite(occurred_at))
        );
        ALTER TABLE ntubtob.account_erasure_plan_purges ENABLE ROW LEVEL SECURITY;
        CREATE TRIGGER erasure_plan_purges_append_only
          BEFORE UPDATE OR DELETE OR TRUNCATE ON ntubtob.account_erasure_plan_purges
          FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.reject_erasure_evidence_mutation();
        CREATE FUNCTION ntubtob.consume_erasure_plan_delete_permit() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
        DECLARE consumed uuid;
        BEGIN
          IF row_security_active('ntubtob.erasure_plan_delete_permits'::regclass) IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'plan_purge_unfiltered_state_required' USING ERRCODE='23514';
          END IF;
          DELETE FROM ntubtob.erasure_plan_delete_permits
            WHERE backend=pg_backend_pid() AND transaction_id=txid_current() AND job_id=OLD.job_id
              AND row_hash=encode(sha256(convert_to(row_to_json(OLD)::text,'UTF8')),'hex')
            RETURNING job_id INTO consumed;
          IF consumed IS NULL THEN
            RAISE EXCEPTION 'erasure evidence mutation rejected' USING ERRCODE='23514';
          END IF;
          RETURN OLD;
        END $$;
        DROP TRIGGER erasure_sealed_plan_immutable ON ntubtob.account_erasure_sealed_plans;
        CREATE TRIGGER erasure_sealed_plan_immutable BEFORE UPDATE OR TRUNCATE ON ntubtob.account_erasure_sealed_plans
          FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.reject_erasure_evidence_mutation();
        CREATE TRIGGER erasure_sealed_plan_delete_guard BEFORE DELETE ON ntubtob.account_erasure_sealed_plans
          FOR EACH ROW EXECUTE FUNCTION ntubtob.consume_erasure_plan_delete_permit();
        CREATE FUNCTION ntubtob.purge_erasure_sealed_plan(p_job uuid,p_generation uuid,p_scope text,p_operation uuid)
        RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
        DECLARE job record; observation record; plan record; replay record; applied_time timestamptz;
          digest text; deleted bigint; table_name text;
        BEGIN
          IF p_job IS NULL OR p_generation IS NULL OR p_operation IS NULL OR p_scope IS NULL
            OR p_scope !~ '^[0-9a-f]{64}$' THEN
            RAISE EXCEPTION 'plan_purge_input_rejected' USING ERRCODE='23514';
          END IF;
          IF current_setting('transaction_isolation')<>'read committed' THEN
            RAISE EXCEPTION 'plan_purge_transaction_rejected' USING ERRCODE='23514';
          END IF;
          PERFORM pg_advisory_xact_lock(70070);
          PERFORM pg_advisory_xact_lock(1315198274);
          IF (SELECT array_agg(version_num::text ORDER BY version_num) FROM ntubtob.alembic_version)
            IS DISTINCT FROM ARRAY['0022_erasure_retention']::text[] THEN
            RAISE EXCEPTION 'plan_purge_schema_not_ready' USING ERRCODE='23514';
          END IF;
          FOREACH table_name IN ARRAY ARRAY['account_erasure_jobs','account_erasure_items','account_erasure_item_events',
            'account_erasure_sealed_plans','account_erasure_backup_checks','account_erasure_plan_purges','erasure_plan_delete_permits'] LOOP
            IF row_security_active(('ntubtob.'||table_name)::regclass) IS DISTINCT FROM FALSE THEN
              RAISE EXCEPTION 'plan_purge_unfiltered_state_required' USING ERRCODE='23514';
            END IF;
          END LOOP;
          SELECT * INTO job FROM ntubtob.account_erasure_jobs WHERE id=p_job FOR UPDATE;
          IF job.id IS NULL OR job.expected_generation<>p_generation OR job.scope_hash<>p_scope THEN
            RAISE EXCEPTION 'plan_purge_binding_rejected' USING ERRCODE='23514';
          END IF;
          SELECT * INTO replay FROM ntubtob.account_erasure_plan_purges WHERE operation_id=p_operation;
          IF FOUND THEN
            IF replay.job_id=p_job AND replay.expected_generation=p_generation AND replay.scope_hash=p_scope
              AND replay.operator_name=SESSION_USER AND NOT EXISTS(SELECT 1 FROM ntubtob.account_erasure_sealed_plans WHERE job_id=p_job) THEN
              RETURN p_operation;
            END IF;
            RAISE EXCEPTION 'plan_purge_operation_replay' USING ERRCODE='23514';
          END IF;
          IF EXISTS(SELECT 1 FROM ntubtob.account_erasure_plan_purges WHERE job_id=p_job) THEN
            RAISE EXCEPTION 'plan_purge_already_recorded' USING ERRCODE='23514';
          END IF;
          applied_time:=clock_timestamp();
          IF job.status NOT IN ('online_completed','completed') OR job.online_completed_at IS NULL
            OR applied_time<GREATEST(job.updated_at,job.online_completed_at+interval '30 days') THEN
            RAISE EXCEPTION 'plan_purge_not_due' USING ERRCODE='23514';
          END IF;
          SELECT * INTO observation FROM ntubtob.account_erasure_backup_checks WHERE request_id=p_job ORDER BY sequence DESC LIMIT 1;
          IF observation.operation_id IS NULL OR NOT observation.binding_readable OR NOT observation.key_readable
            OR observation.checked_at<applied_time-interval '30 days' OR observation.checked_at>applied_time
            OR ROW(observation.target_kind,observation.expected_generation,observation.original_requested_at,observation.original_receipt_hash)
              IS DISTINCT FROM ROW(job.target_kind,job.expected_generation,job.requested_at,job.receipt_secret_hash) THEN
            RAISE EXCEPTION 'plan_purge_custody_unverified' USING ERRCODE='23514';
          END IF;
          IF NOT EXISTS(SELECT 1 FROM ntubtob.account_erasure_items i JOIN ntubtob.account_erasure_item_events e ON e.item_id=i.id
              WHERE i.job_id=p_job AND i.stage='restore_suppression' AND e.event_kind='confirmed' AND e.result_code='succeeded')
            OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_items i LEFT JOIN LATERAL (
              SELECT event_kind,result_code FROM ntubtob.account_erasure_item_events WHERE item_id=i.id ORDER BY event_sequence DESC LIMIT 1
            ) e ON true WHERE i.job_id=p_job AND (e.event_kind IS DISTINCT FROM 'confirmed'
              OR e.result_code NOT IN ('succeeded','credential_missing','not_applicable'))) THEN
            RAISE EXCEPTION 'plan_purge_work_unfinished' USING ERRCODE='23514';
          END IF;
          SELECT * INTO plan FROM ntubtob.account_erasure_sealed_plans WHERE job_id=p_job FOR UPDATE;
          IF plan.job_id IS NULL THEN
            RAISE EXCEPTION 'plan_purge_absence_unverified' USING ERRCODE='23514';
          END IF;
          digest:=encode(sha256(convert_to(row_to_json(plan)::text,'UTF8')),'hex');
          INSERT INTO ntubtob.erasure_plan_delete_permits VALUES(pg_backend_pid(),txid_current(),p_job,digest);
          DELETE FROM ntubtob.account_erasure_sealed_plans WHERE job_id=p_job;
          GET DIAGNOSTICS deleted=ROW_COUNT;
          IF deleted<>1 OR EXISTS(SELECT 1 FROM ntubtob.erasure_plan_delete_permits
              WHERE backend=pg_backend_pid() AND transaction_id=txid_current() AND job_id=p_job) THEN
            RAISE EXCEPTION 'plan_purge_delete_unverified' USING ERRCODE='23514';
          END IF;
          INSERT INTO ntubtob.account_erasure_plan_purges VALUES(p_operation,p_job,p_generation,p_scope,
            observation.operation_id,digest,applied_time,SESSION_USER);
          RETURN p_operation;
        END $$;
        REVOKE ALL ON TABLE ntubtob.erasure_plan_delete_permits,ntubtob.account_erasure_plan_purges FROM PUBLIC;
        REVOKE ALL ON FUNCTION ntubtob.consume_erasure_plan_delete_permit() FROM PUBLIC;
        REVOKE ALL ON FUNCTION ntubtob.purge_erasure_sealed_plan(uuid,uuid,text,uuid) FROM PUBLIC;
        DO $$ DECLARE grant_row record; table_name text; signature text; BEGIN
          FOREACH table_name IN ARRAY ARRAY['erasure_plan_delete_permits','account_erasure_plan_purges'] LOOP
            FOR grant_row IN SELECT DISTINCT a.grantee FROM pg_class c,
              LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
              WHERE c.oid=('ntubtob.'||table_name)::regclass AND a.grantee<>c.relowner AND a.grantee<>0 LOOP
              EXECUTE format('REVOKE ALL ON TABLE ntubtob.%I FROM %I',table_name,pg_get_userbyid(grant_row.grantee));
            END LOOP;
          END LOOP;
          FOREACH signature IN ARRAY ARRAY['ntubtob.consume_erasure_plan_delete_permit()','ntubtob.purge_erasure_sealed_plan(uuid,uuid,text,uuid)'] LOOP
            FOR grant_row IN SELECT DISTINCT a.grantee FROM pg_proc p,
              LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a
              WHERE p.oid=signature::regprocedure AND a.grantee<>p.proowner AND a.grantee<>0 LOOP
              EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I',signature,pg_get_userbyid(grant_row.grantee));
            END LOOP;
          END LOOP;
        END $$;
        """
    )
