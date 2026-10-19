"""Private one-shot last-admin suspension; no grants or runtime enablement.

Deploy only while old writers are quiesced, after all callers understand durable
suspension. The migration/function owner is trusted and must be separate from the
operator and runtime roles. Owners/superusers and roles able to inherit/SET ROLE
to them are outside this boundary. Deployment must grant only the fixed approval
function to the separately authenticated operator; this migration creates/grants
no roles. No ordinary runtime may inherit that privilege or own these objects.

The pointer is a durable management-write suspension, not erasure verification,
an executor bypass, promotion or permission to resume. All operation history and
the pointer survive attempted downgrade; only an unused candidate can be removed.
"""

from alembic import op

revision = "0019_erasure_admin_recovery"
down_revision = "0018_erasure_privacy_mutation"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE ntubtob.account_erasure_admin_recovery_operations (
          operation_id uuid CONSTRAINT pk_erasure_admin_recovery PRIMARY KEY,
          job_id uuid NOT NULL CONSTRAINT uq_erasure_admin_recovery_job UNIQUE
            CONSTRAINT fk_erasure_admin_recovery_job REFERENCES ntubtob.account_erasure_jobs(id) ON DELETE RESTRICT,
          expected_generation uuid NOT NULL,
          scope_hash char(64) NOT NULL CONSTRAINT ck_erasure_recovery_scope_hash CHECK (scope_hash ~ '^[0-9a-f]{64}$'),
          expected_epoch bigint NOT NULL CONSTRAINT ck_erasure_recovery_expected_epoch CHECK (expected_epoch BETWEEN 1 AND 9223372036854775806),
          applied_epoch bigint NOT NULL CONSTRAINT ck_erasure_recovery_applied_epoch CHECK (applied_epoch = expected_epoch + 1),
          operator_session_user varchar(63) NOT NULL,
          applied_at timestamptz NOT NULL CONSTRAINT ck_erasure_recovery_applied_at CHECK (isfinite(applied_at))
        );
        ALTER TABLE ntubtob.account_erasure_admin_recovery_operations ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON ntubtob.account_erasure_admin_recovery_operations FROM PUBLIC;
        ALTER TABLE ntubtob.portal_authority_state
          ADD COLUMN management_suspension_operation_id uuid,
          ADD CONSTRAINT fk_authority_management_suspension
            FOREIGN KEY (management_suspension_operation_id)
            REFERENCES ntubtob.account_erasure_admin_recovery_operations(operation_id) ON DELETE RESTRICT;

        CREATE FUNCTION ntubtob.guard_admin_recovery_immutable() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
        BEGIN
          RAISE EXCEPTION 'recovery_evidence_immutable' USING ERRCODE='23514';
        END;
        $$;
        CREATE TRIGGER admin_recovery_immutable
          BEFORE UPDATE OR DELETE OR TRUNCATE ON ntubtob.account_erasure_admin_recovery_operations
          FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.guard_admin_recovery_immutable();

        CREATE FUNCTION ntubtob.guard_management_suspension() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
        DECLARE function_owner oid; valid_operation boolean;
        BEGIN
          -- Column REVOKE cannot subtract a table-level UPDATE grant. This
          -- invoker trigger sees the SECURITY DEFINER owner only inside its
          -- fixed update, but the runtime principal on an ordinary table write.
          IF TG_OP IN ('DELETE','TRUNCATE') THEN
            RAISE EXCEPTION 'authority_state_removal_forbidden' USING ERRCODE='23514';
          END IF;
          IF TG_OP='INSERT' THEN
            IF NEW.management_suspension_operation_id IS NOT NULL THEN
              RAISE EXCEPTION 'suspension_pointer_protected' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.management_suspension_operation_id IS NOT NULL AND (
            NEW.management_suspension_operation_id IS DISTINCT FROM OLD.management_suspension_operation_id
            OR NEW.mode IS DISTINCT FROM OLD.mode OR NEW.epoch IS DISTINCT FROM OLD.epoch
          ) THEN
            RAISE EXCEPTION 'management_suspension_persistent' USING ERRCODE='23514';
          END IF;
          IF NEW.management_suspension_operation_id IS DISTINCT FROM OLD.management_suspension_operation_id THEN
            SELECT p.proowner INTO function_owner FROM pg_catalog.pg_proc p
             WHERE p.oid='ntubtob.suspend_management_for_erasure(uuid,uuid,bigint,uuid)'::regprocedure;
            IF function_owner IS DISTINCT FROM (current_user::regrole)::oid THEN
              RAISE EXCEPTION 'suspension_pointer_protected' USING ERRCODE='23514';
            END IF;
            SELECT EXISTS (
              SELECT 1 FROM ntubtob.account_erasure_admin_recovery_operations o
              WHERE o.operation_id=NEW.management_suspension_operation_id
                AND o.expected_epoch=OLD.epoch AND o.applied_epoch=NEW.epoch
                AND o.applied_at=NEW.updated_at
            ) INTO valid_operation;
            IF OLD.management_suspension_operation_id IS NOT NULL
               OR OLD.mode<>'persistent' OR NEW.mode IS DISTINCT FROM OLD.mode
               OR valid_operation IS NOT TRUE THEN
              RAISE EXCEPTION 'suspension_pointer_binding_rejected' USING ERRCODE='23514';
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$;
        CREATE TRIGGER management_suspension_write_guard
          BEFORE INSERT OR UPDATE OR DELETE ON ntubtob.portal_authority_state
          FOR EACH ROW EXECUTE FUNCTION ntubtob.guard_management_suspension();
        CREATE TRIGGER management_suspension_truncate_guard
          BEFORE TRUNCATE ON ntubtob.portal_authority_state
          FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.guard_management_suspension();

        CREATE FUNCTION ntubtob.suspend_management_for_erasure(
          p_job uuid, p_expected_generation uuid, p_expected_epoch bigint, p_operation uuid
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
        DECLARE job ntubtob.account_erasure_jobs%ROWTYPE;
                authority ntubtob.portal_authority_state%ROWTYPE;
                target ntubtob.people%ROWTYPE;
                table_name text; applied_time timestamptz;
        BEGIN
          IF p_job IS NULL OR p_expected_generation IS NULL OR p_operation IS NULL
             OR p_expected_epoch IS NULL OR p_expected_epoch NOT BETWEEN 1 AND 9223372036854775806 THEN
            RAISE EXCEPTION 'recovery_input_rejected' USING ERRCODE='23514';
          END IF;
          IF current_setting('transaction_isolation')<>'read committed' THEN
            RAISE EXCEPTION 'recovery_read_committed_required' USING ERRCODE='23514';
          END IF;
          PERFORM pg_advisory_xact_lock(70070);
          PERFORM pg_advisory_xact_lock(1315198274);
          IF (SELECT array_agg(version_num::text ORDER BY version_num) FROM ntubtob.alembic_version)
             IS DISTINCT FROM ARRAY['0019_erasure_admin_recovery']::text[] THEN
            RAISE EXCEPTION 'recovery_schema_not_ready' USING ERRCODE='23514';
          END IF;
          FOREACH table_name IN ARRAY ARRAY[
            'portal_authority_state','account_erasure_admin_recovery_operations',
            'account_erasure_jobs','people','auth_identities'
          ] LOOP
            IF pg_catalog.row_security_active(('ntubtob.' || table_name)::regclass) IS DISTINCT FROM FALSE THEN
              RAISE EXCEPTION 'recovery_unfiltered_state_required' USING ERRCODE='23514';
            END IF;
          END LOOP;
          -- Protect the reachability predicate from non-cooperating direct DML
          -- and phantoms as well as canonical-lock-aware application writers.
          LOCK TABLE ntubtob.people,ntubtob.auth_identities,ntubtob.account_erasure_jobs IN SHARE MODE;
          IF (SELECT count(*) FROM ntubtob.portal_authority_state)<>1 THEN
            RAISE EXCEPTION 'recovery_authority_unavailable' USING ERRCODE='23514';
          END IF;
          SELECT * INTO authority FROM ntubtob.portal_authority_state WHERE singleton_id=1 FOR UPDATE;
          IF NOT FOUND OR authority.mode<>'persistent' OR authority.epoch<>p_expected_epoch
             OR authority.management_suspension_operation_id IS NOT NULL THEN
            RAISE EXCEPTION 'recovery_authority_rejected' USING ERRCODE='23514';
          END IF;
          IF EXISTS (SELECT 1 FROM ntubtob.account_erasure_admin_recovery_operations WHERE operation_id=p_operation OR job_id=p_job) THEN
            RAISE EXCEPTION 'recovery_operation_replay' USING ERRCODE='23514';
          END IF;
          SELECT * INTO job FROM ntubtob.account_erasure_jobs WHERE id=p_job FOR UPDATE;
          IF NOT FOUND OR job.target_kind<>'person' OR job.person_id IS NULL
             OR job.auth_identity_id IS NOT NULL OR job.expected_generation<>p_expected_generation
             OR job.status NOT IN ('verified','processing','needs_attention') OR job.verified_at IS NULL THEN
            RAISE EXCEPTION 'recovery_job_rejected' USING ERRCODE='23514';
          END IF;
          SELECT * INTO target FROM ntubtob.people WHERE id=job.person_id FOR UPDATE;
          IF NOT FOUND OR target.account_generation<>p_expected_generation
             OR target.portal_access_level<>'admin' OR target.portal_status<>'active'
             OR NOT EXISTS (SELECT 1 FROM ntubtob.auth_identities WHERE person_id=target.id AND status='linked') THEN
            RAISE EXCEPTION 'recovery_target_rejected' USING ERRCODE='23514';
          END IF;
          -- Same reachable-other-admin predicate as persistent lifecycle policy.
          -- This verified target is intentionally already blocked by its own job.
          IF EXISTS (
            SELECT 1 FROM ntubtob.people p JOIN ntubtob.auth_identities i ON i.person_id=p.id
            WHERE p.id<>target.id AND p.portal_access_level='admin' AND p.portal_status='active'
              AND i.status='linked' AND NOT EXISTS (
                SELECT 1 FROM ntubtob.account_erasure_jobs j WHERE j.status<>'requested'
                  AND (j.person_id=p.id OR j.auth_identity_id IN (
                    SELECT owned.id FROM ntubtob.auth_identities owned WHERE owned.person_id=p.id))
              )
          ) THEN
            RAISE EXCEPTION 'recovery_not_last_admin' USING ERRCODE='23514';
          END IF;
          applied_time := clock_timestamp();
          INSERT INTO ntubtob.account_erasure_admin_recovery_operations
            (operation_id,job_id,expected_generation,scope_hash,expected_epoch,applied_epoch,operator_session_user,applied_at)
          VALUES (p_operation,p_job,p_expected_generation,job.scope_hash,p_expected_epoch,p_expected_epoch+1,session_user,applied_time);
          UPDATE ntubtob.portal_authority_state
             SET management_suspension_operation_id=p_operation,epoch=p_expected_epoch+1,updated_at=applied_time
           WHERE singleton_id=1;
          RETURN p_operation;
        END;
        $$;
        REVOKE ALL ON FUNCTION ntubtob.suspend_management_for_erasure(uuid,uuid,bigint,uuid) FROM PUBLIC;
        REVOKE ALL ON FUNCTION ntubtob.guard_management_suspension() FROM PUBLIC;
        REVOKE ALL ON FUNCTION ntubtob.guard_admin_recovery_immutable() FROM PUBLIC;
        """
    )
    op.execute(
        """
        -- Clean named default ACL grants on these new objects only. No role or
        -- global default privilege change, and no migration-time operator grant.
        DO $$
        DECLARE recipient record; recipient_sql text; signature text;
        BEGIN
          FOR recipient IN
            SELECT DISTINCT a.grantee,r.rolname FROM pg_catalog.pg_class c
            CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE(c.relacl,pg_catalog.acldefault('r',c.relowner))) a
            LEFT JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
            WHERE c.oid='ntubtob.account_erasure_admin_recovery_operations'::regclass AND a.grantee<>c.relowner
          LOOP
            recipient_sql := CASE WHEN recipient.grantee=0 THEN 'PUBLIC' ELSE pg_catalog.quote_ident(recipient.rolname) END;
            EXECUTE 'REVOKE ALL ON TABLE ntubtob.account_erasure_admin_recovery_operations FROM ' || recipient_sql || ' CASCADE';
          END LOOP;
          FOREACH signature IN ARRAY ARRAY[
            'ntubtob.suspend_management_for_erasure(uuid,uuid,bigint,uuid)',
            'ntubtob.guard_management_suspension()',
            'ntubtob.guard_admin_recovery_immutable()'
          ] LOOP
            FOR recipient IN
              SELECT DISTINCT a.grantee,r.rolname FROM pg_catalog.pg_proc p
              CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
              LEFT JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
              WHERE p.oid=signature::regprocedure AND a.grantee<>p.proowner
            LOOP
              recipient_sql := CASE WHEN recipient.grantee=0 THEN 'PUBLIC' ELSE pg_catalog.quote_ident(recipient.rolname) END;
              EXECUTE 'REVOKE ALL ON FUNCTION ' || signature || ' FROM ' || recipient_sql || ' CASCADE';
            END LOOP;
          END LOOP;
        END;
        $$;
        """
    )


def downgrade():
    op.execute(
        """
        DO $$
        BEGIN
          PERFORM pg_advisory_xact_lock(70070);
          PERFORM pg_advisory_xact_lock(1315198274);
          LOCK TABLE ntubtob.portal_authority_state,ntubtob.account_erasure_admin_recovery_operations IN ACCESS EXCLUSIVE MODE;
          IF pg_catalog.row_security_active('ntubtob.portal_authority_state'::regclass) IS DISTINCT FROM FALSE
             OR pg_catalog.row_security_active('ntubtob.account_erasure_admin_recovery_operations'::regclass) IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'recovery_unfiltered_state_required' USING ERRCODE='23514';
          END IF;
          IF EXISTS (SELECT 1 FROM ntubtob.account_erasure_admin_recovery_operations)
             OR EXISTS (SELECT 1 FROM ntubtob.portal_authority_state WHERE management_suspension_operation_id IS NOT NULL) THEN
            RAISE EXCEPTION 'recovery_history_retained' USING ERRCODE='23514';
          END IF;
        END;
        $$;
        DROP TRIGGER management_suspension_write_guard ON ntubtob.portal_authority_state;
        DROP TRIGGER management_suspension_truncate_guard ON ntubtob.portal_authority_state;
        ALTER TABLE ntubtob.portal_authority_state DROP COLUMN management_suspension_operation_id;
        DROP FUNCTION ntubtob.suspend_management_for_erasure(uuid,uuid,bigint,uuid);
        DROP FUNCTION ntubtob.guard_management_suspension();
        DROP TABLE ntubtob.account_erasure_admin_recovery_operations;
        DROP FUNCTION ntubtob.guard_admin_recovery_immutable();
        """
    )
