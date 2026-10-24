"""Private verified-retention completion and exact minimal-evidence cleanup.

No grants, worker, real inventory acquisition, backup/key destruction or runtime
enablement. An independent operator must establish restore quiescence, complete
copy/working-file inventory and suppression verification BEFORE dispatch. SQL
cannot establish those external facts from booleans or stop external restores.
There is no per-request purge tombstone; an unlinked global irreversible flag
only prevents an unsafe native downgrade. Missing roots are never success/retry.
"""

from alembic import op

revision = "0023_erasure_minimal_retention"
down_revision = "0022_erasure_retention"
branch_labels = None
depends_on = None

# Fixed schema-owned inventory, not public/operator-selected table names.
TABLES = (
    (
        "account_erasure_item_events",
        "id",
        "erasure_item_event_append_only",
        "UPDATE OR DELETE OR TRUNCATE",
    ),
    (
        "account_erasure_items",
        "id",
        "erasure_item_immutable",
        "UPDATE OR DELETE OR TRUNCATE",
    ),
    (
        "account_erasure_request_attempts",
        "attempt_id",
        "erasure_request_attempt_immutable",
        "UPDATE OR DELETE OR TRUNCATE",
    ),
    (
        "account_erasure_steps",
        "id",
        "erasure_step_append_only",
        "UPDATE OR DELETE OR TRUNCATE",
    ),
    (
        "account_erasure_intake_attempts",
        "attempt_id",
        "erasure_intake_attempt_immutable",
        "UPDATE OR DELETE OR TRUNCATE",
    ),
    ("account_erasure_intakes", "id", "erasure_intake_retained", "DELETE OR TRUNCATE"),
    (
        "account_erasure_plan_purges",
        "operation_id",
        "erasure_plan_purges_append_only",
        "UPDATE OR DELETE OR TRUNCATE",
    ),
    (
        "account_erasure_continuity_events",
        "operation_id",
        "erasure_continuity_append_only",
        "UPDATE OR DELETE OR TRUNCATE",
    ),
    (
        "account_erasure_backup_checks",
        "operation_id",
        "erasure_backup_append_only",
        "UPDATE OR DELETE OR TRUNCATE",
    ),
    ("account_erasure_jobs", "id", "erasure_job_no_remove", "DELETE OR TRUNCATE"),
)
MARKERS = (
    "ntubtob.suspend_management_for_erasure(uuid,uuid,bigint,uuid)",
    "ntubtob.extend_erasure_continuity(uuid,uuid,bigint,uuid,timestamptz,timestamptz)",
    "ntubtob.record_erasure_backup_check(uuid,uuid,uuid,text,boolean,timestamptz,timestamptz,boolean,boolean)",
    "ntubtob.guard_erasure_retention_start()",
    "ntubtob.purge_erasure_sealed_plan(uuid,uuid,text,uuid)",
)


def _markers(old, new):
    before = f"ARRAY['{old}']::text[]".replace("'", "''")
    after = f"ARRAY['{new}']::text[]".replace("'", "''")
    for signature in MARKERS:
        op.execute(
            f"""DO $$ DECLARE source text; BEGIN
          SELECT pg_get_functiondef('{signature}'::regprocedure) INTO source;
          IF source IS NULL OR length(source)-length(replace(source,'{before}',''))<>length('{before}')
            OR position('{after}' in source)>0 THEN RAISE EXCEPTION 'minimal_retention_definition_changed'; END IF;
          EXECUTE replace(source,'{before}','{after}'); END $$;"""
        )


def upgrade():
    op.execute(
        """
      CREATE TABLE ntubtob.erasure_evidence_delete_permits (
        backend integer NOT NULL,transaction_id bigint NOT NULL,table_oid oid NOT NULL,
        row_key text NOT NULL,operation varchar(6) NOT NULL,old_hash char(64) NOT NULL,new_hash char(64),
        PRIMARY KEY(backend,transaction_id,table_oid,row_key),
        CONSTRAINT ck_erasure_evidence_permit_action CHECK(operation IN ('delete','update'))
      );
      ALTER TABLE ntubtob.erasure_evidence_delete_permits ENABLE ROW LEVEL SECURITY;
      CREATE TABLE ntubtob.erasure_retention_state (
        singleton_id integer PRIMARY KEY CONSTRAINT ck_erasure_retention_singleton CHECK(singleton_id=1),
        cleanup_performed boolean NOT NULL DEFAULT false
      );
      ALTER TABLE ntubtob.erasure_retention_state ENABLE ROW LEVEL SECURITY;
      INSERT INTO ntubtob.erasure_retention_state(singleton_id) VALUES(1);
      ALTER TABLE ntubtob.account_erasure_admin_recovery_operations
        ALTER COLUMN job_id DROP NOT NULL,ALTER COLUMN expected_generation DROP NOT NULL,
        ALTER COLUMN scope_hash DROP NOT NULL,ADD COLUMN minimized_at timestamptz,
        ADD CONSTRAINT ck_erasure_recovery_minimized CHECK(
          (minimized_at IS NULL AND job_id IS NOT NULL AND expected_generation IS NOT NULL AND scope_hash IS NOT NULL)
          OR (minimized_at IS NOT NULL AND isfinite(minimized_at) AND minimized_at>=applied_at
            AND job_id IS NULL AND expected_generation IS NULL AND scope_hash IS NULL));
      CREATE FUNCTION ntubtob.guard_erasure_recovery_insert() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
        IF NEW.minimized_at IS NOT NULL THEN RAISE EXCEPTION 'recovery_evidence_immutable' USING ERRCODE='23514'; END IF;
        RETURN NEW; END $$;
      CREATE TRIGGER erasure_recovery_original_insert BEFORE INSERT ON ntubtob.account_erasure_admin_recovery_operations
        FOR EACH ROW EXECUTE FUNCTION ntubtob.guard_erasure_recovery_insert();
    """
    )
    _row_guard()
    _context()
    _completion()
    _cleanup()
    _acl()
    _markers(down_revision, revision)


def _row_guard():
    key_case = " ".join(f"WHEN '{name}' THEN '{key}'" for name, key, _, _ in TABLES)
    op.execute(
        f"""
      CREATE FUNCTION ntubtob.consume_erasure_evidence_permit() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE key_column text; consumed text; desired_hash text;
      BEGIN
        IF TG_TABLE_SCHEMA<>'ntubtob' OR row_security_active('ntubtob.erasure_evidence_delete_permits'::regclass) IS DISTINCT FROM FALSE THEN
          RAISE EXCEPTION 'minimal_retention_unfiltered_state_required' USING ERRCODE='23514'; END IF;
        IF TG_OP='DELETE' THEN
          key_column:=CASE TG_TABLE_NAME {key_case} END;
        ELSIF TG_OP='UPDATE' AND TG_TABLE_NAME='account_erasure_admin_recovery_operations' THEN
          key_column:='operation_id';
          IF OLD.minimized_at IS NOT NULL OR NEW.minimized_at IS NULL OR NEW.job_id IS NOT NULL
            OR NEW.expected_generation IS NOT NULL OR NEW.scope_hash IS NOT NULL
            OR (to_jsonb(NEW)-ARRAY['job_id','expected_generation','scope_hash','minimized_at'])
              IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['job_id','expected_generation','scope_hash','minimized_at']) THEN
            RAISE EXCEPTION 'recovery_evidence_immutable' USING ERRCODE='23514'; END IF;
          desired_hash:=encode(sha256(convert_to(to_jsonb(NEW)::text,'UTF8')),'hex');
        END IF;
        IF key_column IS NULL THEN RAISE EXCEPTION 'erasure evidence mutation rejected' USING ERRCODE='23514'; END IF;
        DELETE FROM ntubtob.erasure_evidence_delete_permits
          WHERE backend=pg_backend_pid() AND transaction_id=txid_current() AND table_oid=TG_RELID
            AND row_key=to_jsonb(OLD)->>key_column AND operation=lower(TG_OP)
            AND old_hash=encode(sha256(convert_to(to_jsonb(OLD)::text,'UTF8')),'hex')
            AND new_hash IS NOT DISTINCT FROM desired_hash RETURNING row_key INTO consumed;
        IF consumed IS NULL THEN RAISE EXCEPTION 'erasure evidence mutation rejected' USING ERRCODE='23514'; END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
      END $$;
      DROP TRIGGER admin_recovery_immutable ON ntubtob.account_erasure_admin_recovery_operations;
      CREATE TRIGGER admin_recovery_immutable BEFORE DELETE OR TRUNCATE ON ntubtob.account_erasure_admin_recovery_operations
        FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.guard_admin_recovery_immutable();
      CREATE TRIGGER erasure_recovery_minimize_guard BEFORE UPDATE ON ntubtob.account_erasure_admin_recovery_operations
        FOR EACH ROW EXECUTE FUNCTION ntubtob.consume_erasure_evidence_permit();
    """
    )
    for name, _, trigger, events in TABLES:
        remaining = events.replace("DELETE OR ", "")
        op.execute(
            f"""DROP TRIGGER {trigger} ON ntubtob.{name};
          CREATE TRIGGER {trigger} BEFORE {remaining} ON ntubtob.{name}
            FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.reject_erasure_evidence_mutation();
          CREATE TRIGGER erasure_minimal_delete_guard BEFORE DELETE ON ntubtob.{name}
            FOR EACH ROW EXECUTE FUNCTION ntubtob.consume_erasure_evidence_permit();"""
        )


def _context():
    tables = [name for name, _, _, _ in TABLES] + [
        "account_erasure_sealed_plans",
        "account_erasure_admin_recovery_operations",
        "portal_authority_state",
        "erasure_evidence_delete_permits",
        "erasure_plan_delete_permits",
        "erasure_retention_state",
    ]
    names = ",".join("'" + name + "'" for name in tables)
    op.execute(
        f"""
      CREATE FUNCTION ntubtob.require_erasure_retention_context(p_request uuid,p_generation uuid,p_backup uuid,p_terminal boolean)
      RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE root record; intake record; observation record; has_job boolean; now_time timestamptz; table_name text;
      BEGIN
        IF p_request IS NULL OR p_generation IS NULL OR p_backup IS NULL OR p_terminal IS NULL THEN
          RAISE EXCEPTION 'minimal_retention_input_rejected' USING ERRCODE='23514'; END IF;
        IF current_setting('transaction_isolation')<>'read committed' THEN
          RAISE EXCEPTION 'minimal_retention_transaction_rejected' USING ERRCODE='23514'; END IF;
        PERFORM pg_advisory_xact_lock(70070); PERFORM pg_advisory_xact_lock(1315198274);
        IF (SELECT array_agg(version_num::text ORDER BY version_num) FROM ntubtob.alembic_version)
          IS DISTINCT FROM ARRAY['0023_erasure_minimal_retention']::text[] THEN
          RAISE EXCEPTION 'minimal_retention_schema_not_ready' USING ERRCODE='23514'; END IF;
        FOREACH table_name IN ARRAY ARRAY[{names}] LOOP
          IF row_security_active(('ntubtob.'||table_name)::regclass) IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'minimal_retention_unfiltered_state_required' USING ERRCODE='23514'; END IF;
        END LOOP;
        IF (SELECT count(*) FROM ntubtob.portal_authority_state)<>1
          OR (SELECT count(*) FROM ntubtob.erasure_retention_state)<>1 THEN
          RAISE EXCEPTION 'minimal_retention_authority_unavailable' USING ERRCODE='23514'; END IF;
        PERFORM 1 FROM ntubtob.portal_authority_state WHERE singleton_id=1 FOR UPDATE;
        PERFORM 1 FROM ntubtob.erasure_retention_state WHERE singleton_id=1 FOR UPDATE;
        SELECT * INTO intake FROM ntubtob.account_erasure_intakes WHERE id=p_request FOR UPDATE;
        SELECT * INTO root FROM ntubtob.account_erasure_jobs WHERE id=p_request FOR UPDATE;
        has_job:=root.id IS NOT NULL;
        IF NOT has_job THEN root:=intake;
        ELSIF intake.id IS NOT NULL AND (intake.status<>'materialized' OR
          ROW(root.target_kind,root.expected_generation,root.requested_at,root.receipt_secret_hash,root.receipt_expires_at,root.evidence_expires_at)
            IS DISTINCT FROM ROW(intake.target_kind,intake.expected_generation,intake.requested_at,intake.receipt_secret_hash,intake.receipt_expires_at,intake.evidence_expires_at)) THEN
          RAISE EXCEPTION 'minimal_retention_binding_rejected' USING ERRCODE='23514'; END IF;
        IF root.id IS NULL THEN RAISE EXCEPTION 'minimal_retention_root_absent_unverified' USING ERRCODE='23514'; END IF;
        IF root.expected_generation<>p_generation OR root.person_id IS NOT NULL OR root.auth_identity_id IS NOT NULL THEN
          RAISE EXCEPTION 'minimal_retention_binding_rejected' USING ERRCODE='23514'; END IF;
        now_time:=clock_timestamp();
        IF now_time<root.updated_at THEN RAISE EXCEPTION 'minimal_retention_clock_rejected' USING ERRCODE='23514'; END IF;
        IF p_terminal THEN
          IF root.status NOT IN ('completed','cancelled') THEN
            RAISE EXCEPTION 'minimal_retention_not_terminal' USING ERRCODE='23514'; END IF;
          IF now_time<root.requested_at+interval '180 days' OR now_time<ntubtob.erasure_continuity_evidence(p_request,NOT has_job) THEN
            RAISE EXCEPTION 'minimal_retention_window_active' USING ERRCODE='23514'; END IF;
        ELSIF NOT has_job OR root.status NOT IN ('online_completed','completed') THEN
          RAISE EXCEPTION 'minimal_retention_not_online' USING ERRCODE='23514'; END IF;
        SELECT * INTO observation FROM ntubtob.account_erasure_backup_checks WHERE request_id=p_request ORDER BY sequence DESC LIMIT 1 FOR UPDATE;
        IF observation.operation_id IS NULL OR observation.operation_id<>p_backup OR NOT observation.inventory_complete
          OR observation.last_restorable_until IS NULL OR observation.last_restorable_until>now_time
          OR observation.suppression_verified_at IS NULL OR observation.suppression_verified_at<observation.last_restorable_until
          OR observation.suppression_verified_at>observation.checked_at OR NOT observation.binding_readable OR NOT observation.key_readable
          OR observation.checked_at<now_time-interval '30 days' OR observation.checked_at>now_time
          OR ROW(observation.target_kind,observation.expected_generation,observation.original_requested_at,observation.original_receipt_hash)
            IS DISTINCT FROM ROW(root.target_kind,root.expected_generation,root.requested_at,root.receipt_secret_hash) THEN
          RAISE EXCEPTION 'minimal_retention_backup_unverified' USING ERRCODE='23514'; END IF;
        IF EXISTS(SELECT 1 FROM ntubtob.erasure_plan_delete_permits WHERE job_id=p_request) THEN
          RAISE EXCEPTION 'minimal_retention_permit_unresolved' USING ERRCODE='23514'; END IF;
        IF has_job THEN
          IF root.status='cancelled' AND (root.irreversible_started_at IS NOT NULL OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_items WHERE job_id=p_request)) THEN
            RAISE EXCEPTION 'minimal_retention_work_unfinished' USING ERRCODE='23514'; END IF;
          IF EXISTS(SELECT 1 FROM ntubtob.account_erasure_items i LEFT JOIN LATERAL (
            SELECT event_kind,result_code FROM ntubtob.account_erasure_item_events WHERE item_id=i.id ORDER BY event_sequence DESC LIMIT 1
          ) e ON true WHERE i.job_id=p_request AND (e.event_kind IS DISTINCT FROM 'confirmed' OR e.result_code NOT IN ('succeeded','credential_missing','not_applicable')))
          OR EXISTS(SELECT 1 FROM (SELECT DISTINCT ON(stage,attempt) event_kind,result_code FROM ntubtob.account_erasure_steps
            WHERE job_id=p_request ORDER BY stage,attempt,event_sequence DESC) s
            WHERE s.event_kind<>'confirmed' OR s.result_code NOT IN ('succeeded','credential_missing','not_applicable')) THEN
            RAISE EXCEPTION 'minimal_retention_work_unfinished' USING ERRCODE='23514'; END IF;
          IF root.status<>'cancelled' AND (EXISTS(SELECT 1 FROM ntubtob.account_erasure_sealed_plans WHERE job_id=p_request)
            OR NOT EXISTS(SELECT 1 FROM ntubtob.account_erasure_plan_purges WHERE job_id=p_request)) THEN
            RAISE EXCEPTION 'minimal_retention_working_copy_unverified' USING ERRCODE='23514'; END IF;
        END IF;
      END $$;
    """
    )


def _completion():
    op.execute(
        """
      CREATE FUNCTION ntubtob.complete_erasure_retention(p_request uuid,p_generation uuid,p_backup uuid)
      RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE now_time timestamptz; next_attempt integer; step_id bigint;
        actual_rows bigint; expected_job jsonb; expected_step jsonb;
      BEGIN
        PERFORM ntubtob.require_erasure_retention_context(p_request,p_generation,p_backup,false);
        IF (SELECT status FROM ntubtob.account_erasure_jobs WHERE id=p_request)='completed' THEN RETURN 'retention_already_completed'; END IF;
        now_time:=clock_timestamp();
        SELECT to_jsonb(j)||jsonb_build_object('status','completed','completed_at',now_time,'updated_at',now_time)
          INTO expected_job FROM ntubtob.account_erasure_jobs j WHERE id=p_request;
        SELECT COALESCE(max(attempt),0)+1 INTO next_attempt FROM ntubtob.account_erasure_steps WHERE job_id=p_request AND stage='completion';
        INSERT INTO ntubtob.account_erasure_steps(job_id,stage,attempt,event_sequence,event_kind,result_code,occurred_at)
          VALUES(p_request,'completion',next_attempt,1,'confirmed','succeeded',now_time) RETURNING id INTO step_id;
        GET DIAGNOSTICS actual_rows=ROW_COUNT;
        expected_step:=jsonb_build_object('id',step_id,'job_id',p_request,'stage','completion','attempt',next_attempt,
          'event_sequence',1,'event_kind','confirmed','result_code','succeeded','occurred_at',now_time);
        IF actual_rows<>1 OR (SELECT to_jsonb(s) FROM ntubtob.account_erasure_steps s WHERE id=step_id)
          IS DISTINCT FROM expected_step THEN
          RAISE EXCEPTION 'minimal_retention_completion_unverified' USING ERRCODE='23514'; END IF;
        UPDATE ntubtob.account_erasure_jobs SET status='completed',completed_at=now_time,updated_at=now_time WHERE id=p_request;
        GET DIAGNOSTICS actual_rows=ROW_COUNT;
        IF actual_rows<>1 OR (SELECT to_jsonb(j) FROM ntubtob.account_erasure_jobs j WHERE id=p_request)
          IS DISTINCT FROM expected_job OR (SELECT to_jsonb(s) FROM ntubtob.account_erasure_steps s WHERE id=step_id)
          IS DISTINCT FROM expected_step THEN
          RAISE EXCEPTION 'minimal_retention_completion_unverified' USING ERRCODE='23514'; END IF;
        RETURN 'retention_completed';
      END $$;
    """
    )


def _cleanup():
    deletes = []
    for name, key, _, _ in TABLES:
        if name == "account_erasure_item_events":
            predicate = "item_id=ANY(item_ids)"
        elif name in {"account_erasure_jobs", "account_erasure_intakes"}:
            predicate = "id=p_request"
        elif name == "account_erasure_intake_attempts":
            predicate = "intake_id=p_request"
        elif name in {
            "account_erasure_continuity_events",
            "account_erasure_backup_checks",
        }:
            predicate = "request_id=p_request"
        else:
            predicate = "job_id=p_request"
        deletes.append(
            f"""
          INSERT INTO ntubtob.erasure_evidence_delete_permits
            SELECT pg_backend_pid(),txid_current(),'ntubtob.{name}'::regclass::oid,t.{key}::text,'delete',
              encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex'),NULL
            FROM (SELECT * FROM ntubtob.{name} WHERE {predicate} ORDER BY {key} FOR UPDATE) t;
          GET DIAGNOSTICS expected_rows=ROW_COUNT;
          DELETE FROM ntubtob.{name} WHERE {predicate};
          GET DIAGNOSTICS actual_rows=ROW_COUNT;
          IF actual_rows<>expected_rows OR EXISTS(SELECT 1 FROM ntubtob.{name} WHERE {predicate}) THEN
            RAISE EXCEPTION 'minimal_retention_delete_unverified' USING ERRCODE='23514'; END IF;
        """
        )
    body = "\n".join(deletes)
    # The constraint catalogue is a fail-closed fixed inbound boundary. An empty
    # unexpected referencing table is still schema drift, not permission to erase.
    expected = (
        ("account_erasure_steps", "job_id", "account_erasure_jobs", "id"),
        ("account_erasure_items", "job_id", "account_erasure_jobs", "id"),
        ("account_erasure_request_attempts", "job_id", "account_erasure_jobs", "id"),
        ("account_erasure_sealed_plans", "job_id", "account_erasure_jobs", "id"),
        (
            "account_erasure_admin_recovery_operations",
            "job_id",
            "account_erasure_jobs",
            "id",
        ),
        (
            "account_erasure_intakes",
            "materialized_job_id",
            "account_erasure_jobs",
            "id",
        ),
        ("account_erasure_plan_purges", "job_id", "account_erasure_jobs", "id"),
        ("account_erasure_item_events", "item_id", "account_erasure_items", "id"),
        (
            "account_erasure_intake_attempts",
            "intake_id",
            "account_erasure_intakes",
            "id",
        ),
        (
            "account_erasure_plan_purges",
            "backup_operation_id",
            "account_erasure_backup_checks",
            "operation_id",
        ),
    )
    values = ",".join(
        "(" + ",".join("'" + value + "'" for value in row) + ")" for row in expected
    )
    targets = ",".join("'ntubtob." + name + "'::regclass" for name, _, _, _ in TABLES)
    op.execute(
        f"""
      CREATE FUNCTION ntubtob.purge_erasure_minimal_evidence(p_request uuid,p_generation uuid,p_backup uuid)
      RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE now_time timestamptz; item_ids uuid[]; expected_rows bigint; actual_rows bigint; plan record;
        expected_recovery jsonb; recovery_pair record;
      BEGIN
        PERFORM ntubtob.require_erasure_retention_context(p_request,p_generation,p_backup,true);
        IF EXISTS(SELECT 1 FROM ntubtob.erasure_evidence_delete_permits) THEN
          RAISE EXCEPTION 'minimal_retention_permit_unresolved' USING ERRCODE='23514'; END IF;
        IF EXISTS(
          WITH expected(child,column_name,parent,parent_column) AS (VALUES {values})
          SELECT 1 FROM pg_constraint c
          WHERE c.contype='f' AND c.confrelid IN ({targets}) AND (
            c.confdeltype<>'r' OR cardinality(c.conkey)<>1 OR cardinality(c.confkey)<>1 OR NOT EXISTS(
              SELECT 1 FROM expected e JOIN pg_attribute ca ON ca.attrelid=c.conrelid AND ca.attnum=c.conkey[1]
                JOIN pg_attribute pa ON pa.attrelid=c.confrelid AND pa.attnum=c.confkey[1]
                WHERE c.conrelid=('ntubtob.'||e.child)::regclass AND ca.attname=e.column_name
                  AND c.confrelid=('ntubtob.'||e.parent)::regclass AND pa.attname=e.parent_column))) THEN
          RAISE EXCEPTION 'minimal_retention_dependency_changed' USING ERRCODE='23514'; END IF;
        IF EXISTS(
          WITH expected(child,column_name,parent,parent_column) AS (VALUES {values})
          SELECT 1 FROM expected e WHERE NOT EXISTS(
            SELECT 1 FROM pg_constraint c
              JOIN pg_attribute ca ON ca.attrelid=c.conrelid AND ca.attnum=c.conkey[1]
              JOIN pg_attribute pa ON pa.attrelid=c.confrelid AND pa.attnum=c.confkey[1]
            WHERE c.contype='f' AND c.confdeltype='r' AND cardinality(c.conkey)=1 AND cardinality(c.confkey)=1
              AND c.conrelid=('ntubtob.'||e.child)::regclass AND ca.attname=e.column_name
              AND c.confrelid=('ntubtob.'||e.parent)::regclass AND pa.attname=e.parent_column)) THEN
          RAISE EXCEPTION 'minimal_retention_dependency_changed' USING ERRCODE='23514'; END IF;
        SELECT COALESCE(array_agg(id ORDER BY id),ARRAY[]::uuid[]) INTO item_ids FROM ntubtob.account_erasure_items WHERE job_id=p_request;
        now_time:=clock_timestamp();
        -- Cancelled requests never dispatched. Their captured plan has no online
        -- completion date; this stronger terminal180+backup gate is its one fixed
        -- cleanup path. Completed requests already require the reviewed22 purge.
        IF EXISTS(SELECT 1 FROM ntubtob.account_erasure_jobs WHERE id=p_request AND status='cancelled') THEN
          SELECT * INTO plan FROM ntubtob.account_erasure_sealed_plans WHERE job_id=p_request FOR UPDATE;
          IF plan.job_id IS NOT NULL THEN
            INSERT INTO ntubtob.erasure_plan_delete_permits VALUES(pg_backend_pid(),txid_current(),p_request,
              encode(sha256(convert_to(row_to_json(plan)::text,'UTF8')),'hex'));
            DELETE FROM ntubtob.account_erasure_sealed_plans WHERE job_id=p_request;
            GET DIAGNOSTICS actual_rows=ROW_COUNT;
            IF actual_rows<>1 OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_sealed_plans WHERE job_id=p_request)
              OR EXISTS(SELECT 1 FROM ntubtob.erasure_plan_delete_permits WHERE job_id=p_request) THEN
              RAISE EXCEPTION 'minimal_retention_delete_unverified' USING ERRCODE='23514'; END IF;
          END IF;
        END IF;
        -- Preserve the existing, still-effective authority operation and pointer.
        -- Only the erased target linkage is removed; operator/time is NOT anonymous.
        INSERT INTO ntubtob.erasure_evidence_delete_permits
          SELECT pg_backend_pid(),txid_current(),'ntubtob.account_erasure_admin_recovery_operations'::regclass::oid,
            r.operation_id::text,'update',encode(sha256(convert_to(to_jsonb(r)::text,'UTF8')),'hex'),
            encode(sha256(convert_to((to_jsonb(r)||jsonb_build_object('job_id',NULL,'expected_generation',NULL,'scope_hash',NULL,'minimized_at',now_time))::text,'UTF8')),'hex')
          FROM (SELECT * FROM ntubtob.account_erasure_admin_recovery_operations WHERE job_id=p_request ORDER BY operation_id FOR UPDATE) r;
        GET DIAGNOSTICS expected_rows=ROW_COUNT;
        SELECT COALESCE(jsonb_object_agg(row_key,new_hash),'{{}}'::jsonb) INTO expected_recovery
          FROM ntubtob.erasure_evidence_delete_permits
          WHERE backend=pg_backend_pid() AND transaction_id=txid_current()
            AND table_oid='ntubtob.account_erasure_admin_recovery_operations'::regclass::oid AND operation='update';
        UPDATE ntubtob.account_erasure_admin_recovery_operations SET job_id=NULL,expected_generation=NULL,scope_hash=NULL,minimized_at=now_time WHERE job_id=p_request;
        GET DIAGNOSTICS actual_rows=ROW_COUNT;
        IF actual_rows<>expected_rows OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_admin_recovery_operations WHERE job_id=p_request) THEN
          RAISE EXCEPTION 'minimal_retention_delete_unverified' USING ERRCODE='23514'; END IF;
        FOR recovery_pair IN SELECT key,value FROM jsonb_each_text(expected_recovery) LOOP
          IF (SELECT encode(sha256(convert_to(to_jsonb(r)::text,'UTF8')),'hex')
            FROM ntubtob.account_erasure_admin_recovery_operations r WHERE operation_id=recovery_pair.key::uuid)
            IS DISTINCT FROM recovery_pair.value THEN
            RAISE EXCEPTION 'minimal_retention_delete_unverified' USING ERRCODE='23514'; END IF;
        END LOOP;
        {body}
        IF EXISTS(SELECT 1 FROM ntubtob.erasure_evidence_delete_permits)
          OR EXISTS(SELECT 1 FROM ntubtob.erasure_plan_delete_permits WHERE job_id=p_request)
          OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_sealed_plans WHERE job_id=p_request) THEN
          RAISE EXCEPTION 'minimal_retention_delete_unverified' USING ERRCODE='23514'; END IF;
        UPDATE ntubtob.erasure_retention_state SET cleanup_performed=true WHERE singleton_id=1;
        GET DIAGNOSTICS actual_rows=ROW_COUNT;
        IF actual_rows<>1 OR (SELECT count(*) FROM ntubtob.erasure_retention_state)<>1
          OR (SELECT cleanup_performed FROM ntubtob.erasure_retention_state WHERE singleton_id=1) IS DISTINCT FROM true THEN
          RAISE EXCEPTION 'minimal_retention_state_unverified' USING ERRCODE='23514'; END IF;
        RETURN 'minimal_evidence_removed';
      END $$;
      CREATE FUNCTION ntubtob.guard_erasure_retention_state() RETURNS trigger
      LANGUAGE plpgsql SET search_path=pg_catalog AS $$ DECLARE owner_id oid; BEGIN
        SELECT proowner INTO owner_id FROM pg_proc WHERE oid='ntubtob.purge_erasure_minimal_evidence(uuid,uuid,uuid)'::regprocedure;
        IF TG_OP<>'UPDATE' OR (current_user::regrole)::oid IS DISTINCT FROM owner_id
          OR NEW.singleton_id IS DISTINCT FROM OLD.singleton_id OR NEW.cleanup_performed IS NOT TRUE THEN
          RAISE EXCEPTION 'minimal_retention_state_protected' USING ERRCODE='23514'; END IF;
        RETURN NEW; END $$;
      CREATE TRIGGER erasure_retention_state_write BEFORE INSERT OR UPDATE OR DELETE ON ntubtob.erasure_retention_state
        FOR EACH ROW EXECUTE FUNCTION ntubtob.guard_erasure_retention_state();
      CREATE TRIGGER erasure_retention_state_truncate BEFORE TRUNCATE ON ntubtob.erasure_retention_state
        FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.reject_erasure_evidence_mutation();
    """
    )


def _acl():
    tables = ("erasure_evidence_delete_permits", "erasure_retention_state")
    functions = (
        "ntubtob.guard_erasure_recovery_insert()",
        "ntubtob.consume_erasure_evidence_permit()",
        "ntubtob.require_erasure_retention_context(uuid,uuid,uuid,boolean)",
        "ntubtob.complete_erasure_retention(uuid,uuid,uuid)",
        "ntubtob.purge_erasure_minimal_evidence(uuid,uuid,uuid)",
        "ntubtob.guard_erasure_retention_state()",
    )
    for table in tables:
        op.execute(f"REVOKE ALL ON TABLE ntubtob.{table} FROM PUBLIC")
    for function in functions:
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
    table_names = ",".join("'" + name + "'" for name in tables)
    signatures = ",".join("'" + name + "'" for name in functions)
    op.execute(
        f"""DO $$ DECLARE recipient record; table_name text; signature text; BEGIN
      FOREACH table_name IN ARRAY ARRAY[{table_names}] LOOP
        FOR recipient IN SELECT DISTINCT a.grantee FROM pg_class c,
          LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
          WHERE c.oid=('ntubtob.'||table_name)::regclass AND a.grantee<>c.relowner AND a.grantee<>0 LOOP
          EXECUTE format('REVOKE ALL ON TABLE ntubtob.%I FROM %I',table_name,pg_get_userbyid(recipient.grantee)); END LOOP;
      END LOOP;
      FOREACH signature IN ARRAY ARRAY[{signatures}] LOOP
        FOR recipient IN SELECT DISTINCT a.grantee FROM pg_proc p,
          LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a
          WHERE p.oid=signature::regprocedure AND a.grantee<>p.proowner AND a.grantee<>0 LOOP
          EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I',signature,pg_get_userbyid(recipient.grantee)); END LOOP;
      END LOOP; END $$;"""
    )


def downgrade():
    op.execute(
        """LOCK TABLE ntubtob.erasure_retention_state,ntubtob.erasure_evidence_delete_permits,
      ntubtob.account_erasure_admin_recovery_operations IN ACCESS EXCLUSIVE MODE;
      DO $$ DECLARE table_name text; BEGIN
        FOREACH table_name IN ARRAY ARRAY['erasure_retention_state','erasure_evidence_delete_permits','account_erasure_admin_recovery_operations'] LOOP
          IF row_security_active(('ntubtob.'||table_name)::regclass) IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'minimal_retention_unfiltered_state_required'; END IF; END LOOP;
        IF (SELECT count(*) FROM ntubtob.erasure_retention_state)<>1
          OR EXISTS(SELECT 1 FROM ntubtob.erasure_retention_state WHERE cleanup_performed)
          OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_admin_recovery_operations WHERE minimized_at IS NOT NULL)
          OR EXISTS(SELECT 1 FROM ntubtob.erasure_evidence_delete_permits) THEN
          RAISE EXCEPTION 'minimal_retention_irreversible'; END IF;
      END $$;"""
    )
    _markers(revision, down_revision)
    for name, _, trigger, events in TABLES:
        op.execute(
            f"""DROP TRIGGER erasure_minimal_delete_guard ON ntubtob.{name};
          DROP TRIGGER {trigger} ON ntubtob.{name};
          CREATE TRIGGER {trigger} BEFORE {events} ON ntubtob.{name}
            FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.reject_erasure_evidence_mutation();"""
        )
    op.execute(
        """
      DROP TRIGGER erasure_recovery_original_insert ON ntubtob.account_erasure_admin_recovery_operations;
      DROP TRIGGER erasure_recovery_minimize_guard ON ntubtob.account_erasure_admin_recovery_operations;
      DROP TRIGGER admin_recovery_immutable ON ntubtob.account_erasure_admin_recovery_operations;
      CREATE TRIGGER admin_recovery_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON ntubtob.account_erasure_admin_recovery_operations
        FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.guard_admin_recovery_immutable();
      ALTER TABLE ntubtob.account_erasure_admin_recovery_operations
        DROP CONSTRAINT ck_erasure_recovery_minimized,DROP COLUMN minimized_at,
        ALTER COLUMN job_id SET NOT NULL,ALTER COLUMN expected_generation SET NOT NULL,ALTER COLUMN scope_hash SET NOT NULL;
      DROP TABLE ntubtob.erasure_evidence_delete_permits;
      DROP TABLE ntubtob.erasure_retention_state;
      DROP FUNCTION ntubtob.guard_erasure_retention_state();
      DROP FUNCTION ntubtob.guard_erasure_recovery_insert();
      DROP FUNCTION ntubtob.consume_erasure_evidence_permit();
      DROP FUNCTION ntubtob.purge_erasure_minimal_evidence(uuid,uuid,uuid);
      DROP FUNCTION ntubtob.complete_erasure_retention(uuid,uuid,uuid);
      DROP FUNCTION ntubtob.require_erasure_retention_context(uuid,uuid,uuid,boolean);
    """
    )
