"""Additive nonblocking intake; no scope placeholder, runtime enablement or grants.

Old writers must quiesce before activation. Any acknowledged intake prevents
rollback to an older marker; no downgrade may hide a verified access block.
"""

from alembic import op

revision = "0020_erasure_intake"
down_revision = "0019_erasure_admin_recovery"
branch_labels = None
depends_on = None

# Exact historical function preserved for an EMPTY candidate downgrade.
SUSPEND_0019 = r"""CREATE OR REPLACE FUNCTION ntubtob.suspend_management_for_erasure(
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
        $$;"""
SUSPEND_0020 = r"""CREATE OR REPLACE FUNCTION ntubtob.suspend_management_for_erasure(
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
             IS DISTINCT FROM ARRAY['0020_erasure_intake']::text[] THEN
            RAISE EXCEPTION 'recovery_schema_not_ready' USING ERRCODE='23514';
          END IF;
          FOREACH table_name IN ARRAY ARRAY[
            'portal_authority_state','account_erasure_admin_recovery_operations',
            'account_erasure_jobs','account_erasure_intakes','people','auth_identities'
          ] LOOP
            IF pg_catalog.row_security_active(('ntubtob.' || table_name)::regclass) IS DISTINCT FROM FALSE THEN
              RAISE EXCEPTION 'recovery_unfiltered_state_required' USING ERRCODE='23514';
            END IF;
          END LOOP;
          -- Protect the reachability predicate from non-cooperating direct DML
          -- and phantoms as well as canonical-lock-aware application writers.
          LOCK TABLE ntubtob.people,ntubtob.auth_identities,ntubtob.account_erasure_jobs,ntubtob.account_erasure_intakes IN SHARE MODE;
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
              AND i.status='linked' AND NOT EXISTS (SELECT 1 FROM ntubtob.account_erasure_intakes x WHERE x.status='verified' AND (x.person_id=p.id OR x.auth_identity_id IN (SELECT owned.id FROM ntubtob.auth_identities owned WHERE owned.person_id=p.id))) AND NOT EXISTS (
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
        $$;"""


def upgrade():
    op.execute(
        r"""
CREATE TABLE ntubtob.account_erasure_intakes (
	id UUID NOT NULL,
	target_kind VARCHAR(16) NOT NULL,
	person_id BIGINT,
	auth_identity_id BIGINT,
	expected_generation UUID NOT NULL,
	status VARCHAR(16) NOT NULL,
	receipt_secret_hash VARCHAR(64) NOT NULL,
	retention_policy_version INTEGER NOT NULL,
	requested_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	fulfillment_due_at TIMESTAMP WITH TIME ZONE NOT NULL,
	receipt_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	evidence_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	verified_at TIMESTAMP WITH TIME ZONE,
	cancelled_at TIMESTAMP WITH TIME ZONE,
	materialized_job_id UUID,
	PRIMARY KEY (id),
	CONSTRAINT ck_erasure_intake_status CHECK (status IN ('requested','verified','cancelled','materialized')),
	CONSTRAINT ck_erasure_intake_kind CHECK (target_kind IN ('person','pending_identity')),
	CONSTRAINT ck_erasure_intake_target CHECK (((status IN ('cancelled','materialized')) AND person_id IS NULL AND auth_identity_id IS NULL) OR (status IN ('requested','verified') AND ((target_kind='person' AND person_id IS NOT NULL AND auth_identity_id IS NULL) OR (target_kind='pending_identity' AND person_id IS NULL AND auth_identity_id IS NOT NULL)))),
	CONSTRAINT ck_erasure_intake_metadata CHECK (receipt_secret_hash ~ '^[0-9a-f]{64}$' AND retention_policy_version>0),
	CONSTRAINT ck_erasure_intake_times CHECK (isfinite(requested_at) AND isfinite(updated_at) AND isfinite(fulfillment_due_at) AND isfinite(receipt_expires_at) AND isfinite(evidence_expires_at) AND updated_at>=requested_at AND fulfillment_due_at>requested_at AND receipt_expires_at>requested_at AND evidence_expires_at>=GREATEST(fulfillment_due_at,receipt_expires_at)),
	CONSTRAINT ck_erasure_intake_verified CHECK ((verified_at IS NULL OR (isfinite(verified_at) AND verified_at>=requested_at AND verified_at<=updated_at)) AND (status NOT IN ('verified','materialized') OR verified_at IS NOT NULL) AND (status<>'requested' OR verified_at IS NULL)),
	CONSTRAINT ck_erasure_intake_cancelled CHECK ((status='cancelled' AND cancelled_at IS NOT NULL AND isfinite(cancelled_at) AND cancelled_at>=requested_at AND cancelled_at<=updated_at) OR (status<>'cancelled' AND cancelled_at IS NULL)),
	CONSTRAINT ck_erasure_intake_materialized CHECK ((status='materialized' AND materialized_job_id IS NOT NULL AND materialized_job_id=id) OR (status<>'materialized' AND materialized_job_id IS NULL)),
	UNIQUE (person_id),
	FOREIGN KEY(person_id) REFERENCES ntubtob.people (id) ON DELETE RESTRICT,
	UNIQUE (auth_identity_id),
	FOREIGN KEY(auth_identity_id) REFERENCES ntubtob.auth_identities (id) ON DELETE RESTRICT,
	UNIQUE (materialized_job_id),
	FOREIGN KEY(materialized_job_id) REFERENCES ntubtob.account_erasure_jobs (id) ON DELETE RESTRICT
)

;
CREATE TABLE ntubtob.account_erasure_intake_attempts (
	attempt_id UUID NOT NULL,
	intake_id UUID NOT NULL,
	assertion_binding VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	proof_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (attempt_id),
	CONSTRAINT ck_erasure_intake_attempt_binding CHECK (assertion_binding ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_erasure_intake_attempt_times CHECK (isfinite(created_at) AND isfinite(proof_expires_at) AND proof_expires_at>created_at),
	FOREIGN KEY(intake_id) REFERENCES ntubtob.account_erasure_intakes (id) ON DELETE RESTRICT
)

;

    ALTER TABLE ntubtob.account_erasure_intakes ENABLE ROW LEVEL SECURITY;
    ALTER TABLE ntubtob.account_erasure_intake_attempts ENABLE ROW LEVEL SECURITY;

    CREATE FUNCTION ntubtob.guard_erasure_intake() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
    DECLARE actual uuid; j ntubtob.account_erasure_jobs%ROWTYPE;
    BEGIN
      PERFORM pg_advisory_xact_lock(70070);
      PERFORM pg_advisory_xact_lock(1315198274);
      IF row_security_active('ntubtob.account_erasure_jobs'::regclass) IS DISTINCT FROM FALSE
         OR row_security_active('ntubtob.account_erasure_intakes'::regclass) IS DISTINCT FROM FALSE
         OR row_security_active('ntubtob.people'::regclass) IS DISTINCT FROM FALSE
         OR row_security_active('ntubtob.auth_identities'::regclass) IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'intake_unfiltered_required' USING ERRCODE='23514';
      END IF;
      IF TG_OP='INSERT' THEN
        IF NEW.status<>'requested' OR NEW.verified_at IS NOT NULL OR NEW.cancelled_at IS NOT NULL OR NEW.materialized_job_id IS NOT NULL
           OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_jobs WHERE id=NEW.id OR person_id=NEW.person_id OR auth_identity_id=NEW.auth_identity_id
             OR auth_identity_id IN (SELECT id FROM ntubtob.auth_identities WHERE person_id=NEW.person_id)
             OR person_id IN (SELECT person_id FROM ntubtob.auth_identities WHERE id=NEW.auth_identity_id))
           OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_intakes WHERE person_id=NEW.person_id OR auth_identity_id=NEW.auth_identity_id
             OR auth_identity_id IN (SELECT id FROM ntubtob.auth_identities WHERE person_id=NEW.person_id)
             OR person_id IN (SELECT person_id FROM ntubtob.auth_identities WHERE id=NEW.auth_identity_id)) THEN
          RAISE EXCEPTION 'intake_insert_rejected' USING ERRCODE='23514';
        END IF;
        IF NEW.target_kind='person' THEN
          SELECT account_generation INTO actual FROM ntubtob.people WHERE id=NEW.person_id FOR UPDATE;
        ELSE
          SELECT account_generation INTO actual FROM ntubtob.auth_identities WHERE id=NEW.auth_identity_id AND person_id IS NULL AND status IN ('pending','disabled','blocked') FOR UPDATE;
        END IF;
        IF actual IS DISTINCT FROM NEW.expected_generation THEN
          RAISE EXCEPTION 'intake_target_rejected' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END IF;
      IF OLD.status IN ('cancelled','materialized')
         OR (to_jsonb(NEW)-ARRAY['status','person_id','auth_identity_id','verified_at','cancelled_at','updated_at','materialized_job_id'])
            IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','person_id','auth_identity_id','verified_at','cancelled_at','updated_at','materialized_job_id'])
         OR NEW.updated_at<OLD.updated_at
         OR (OLD.verified_at IS NOT NULL AND NEW.verified_at IS DISTINCT FROM OLD.verified_at)
         OR NOT ((OLD.status='requested' AND NEW.status IN ('verified','cancelled'))
             OR (OLD.status='verified' AND NEW.status IN ('cancelled','materialized'))) THEN
        RAISE EXCEPTION 'intake_transition_rejected' USING ERRCODE='23514';
      END IF;
      IF NEW.status='verified' AND (NEW.person_id IS DISTINCT FROM OLD.person_id OR NEW.auth_identity_id IS DISTINCT FROM OLD.auth_identity_id) THEN
        RAISE EXCEPTION 'intake_target_rejected' USING ERRCODE='23514';
      END IF;
      IF OLD.status='requested' AND NEW.status='cancelled' AND NEW.verified_at IS NOT NULL THEN
        RAISE EXCEPTION 'intake_proof_rejected' USING ERRCODE='23514';
      END IF;
      IF NEW.status='materialized' THEN
        IF row_security_active('ntubtob.account_erasure_sealed_plans'::regclass) IS DISTINCT FROM FALSE
           OR row_security_active('ntubtob.account_erasure_steps'::regclass) IS DISTINCT FROM FALSE THEN
          RAISE EXCEPTION 'intake_unfiltered_required' USING ERRCODE='23514';
        END IF;
        SELECT * INTO j FROM ntubtob.account_erasure_jobs WHERE id=NEW.id FOR UPDATE;
        IF NOT FOUND OR j.status<>'verified' OR j.person_id IS DISTINCT FROM OLD.person_id OR j.auth_identity_id IS DISTINCT FROM OLD.auth_identity_id
           OR j.target_kind<>OLD.target_kind OR j.expected_generation<>OLD.expected_generation OR j.verified_at IS DISTINCT FROM OLD.verified_at
           OR j.requested_at<>OLD.requested_at OR j.receipt_secret_hash<>OLD.receipt_secret_hash OR j.retention_policy_version<>OLD.retention_policy_version
           OR j.fulfillment_due_at<>OLD.fulfillment_due_at OR j.receipt_expires_at<>OLD.receipt_expires_at OR j.evidence_expires_at<>OLD.evidence_expires_at
           OR NOT EXISTS(SELECT 1 FROM ntubtob.account_erasure_sealed_plans WHERE job_id=NEW.id)
           OR NOT EXISTS(SELECT 1 FROM ntubtob.account_erasure_steps WHERE job_id=NEW.id AND stage='verification' AND event_kind='confirmed' AND result_code='succeeded' AND occurred_at=OLD.verified_at) THEN
          RAISE EXCEPTION 'intake_materialization_rejected' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END;
    $$;
    CREATE TRIGGER erasure_intake_write_guard BEFORE INSERT OR UPDATE ON ntubtob.account_erasure_intakes FOR EACH ROW EXECUTE FUNCTION ntubtob.guard_erasure_intake();
    CREATE TRIGGER erasure_intake_retained BEFORE DELETE OR TRUNCATE ON ntubtob.account_erasure_intakes FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.reject_erasure_evidence_mutation();

    CREATE FUNCTION ntubtob.guard_erasure_intake_job() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
    DECLARE i ntubtob.account_erasure_intakes%ROWTYPE;
    BEGIN
      PERFORM pg_advisory_xact_lock(70070);
      PERFORM pg_advisory_xact_lock(1315198274);
      IF row_security_active('ntubtob.account_erasure_intakes'::regclass) IS DISTINCT FROM FALSE
         OR row_security_active('ntubtob.auth_identities'::regclass) IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'intake_unfiltered_required' USING ERRCODE='23514';
      END IF;
      FOR i IN SELECT * FROM ntubtob.account_erasure_intakes WHERE id=NEW.id OR person_id=NEW.person_id OR auth_identity_id=NEW.auth_identity_id
        OR auth_identity_id IN (SELECT id FROM ntubtob.auth_identities WHERE person_id=NEW.person_id)
        OR person_id IN (SELECT person_id FROM ntubtob.auth_identities WHERE id=NEW.auth_identity_id) FOR UPDATE LOOP
        IF i.id<>NEW.id OR i.status<>'verified' OR NEW.status<>'requested'
           OR i.person_id IS DISTINCT FROM NEW.person_id OR i.auth_identity_id IS DISTINCT FROM NEW.auth_identity_id
           OR i.target_kind<>NEW.target_kind OR i.expected_generation<>NEW.expected_generation
           OR i.receipt_secret_hash<>NEW.receipt_secret_hash OR i.requested_at<>NEW.requested_at
           OR i.retention_policy_version<>NEW.retention_policy_version OR i.fulfillment_due_at<>NEW.fulfillment_due_at
           OR i.receipt_expires_at<>NEW.receipt_expires_at OR i.evidence_expires_at<>NEW.evidence_expires_at THEN
          RAISE EXCEPTION 'intake_job_binding_rejected' USING ERRCODE='23514';
        END IF;
      END LOOP;
      RETURN NEW;
    END;
    $$;
    CREATE TRIGGER erasure_intake_job_guard BEFORE INSERT ON ntubtob.account_erasure_jobs FOR EACH ROW EXECUTE FUNCTION ntubtob.guard_erasure_intake_job();

    CREATE FUNCTION ntubtob.guard_erasure_intake_atomic() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
    BEGIN
      IF row_security_active('ntubtob.account_erasure_intakes'::regclass) IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'intake_unfiltered_required' USING ERRCODE='23514';
      END IF;
      IF EXISTS(SELECT 1 FROM ntubtob.account_erasure_intakes WHERE id=NEW.id AND (status<>'materialized' OR materialized_job_id IS DISTINCT FROM NEW.id)) THEN
        RAISE EXCEPTION 'intake_materialization_incomplete' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END;
    $$;
    CREATE CONSTRAINT TRIGGER erasure_intake_job_atomic AFTER INSERT ON ntubtob.account_erasure_jobs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ntubtob.guard_erasure_intake_atomic();

    CREATE FUNCTION ntubtob.guard_erasure_intake_attempt() RETURNS trigger
    LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
    DECLARE i ntubtob.account_erasure_intakes%ROWTYPE;
    BEGIN
      PERFORM pg_advisory_xact_lock(70070);
      PERFORM pg_advisory_xact_lock(1315198274);
      IF row_security_active('ntubtob.account_erasure_intakes'::regclass) IS DISTINCT FROM FALSE
         OR row_security_active('ntubtob.account_erasure_intake_attempts'::regclass) IS DISTINCT FROM FALSE
         OR row_security_active('ntubtob.account_erasure_request_attempts'::regclass) IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'intake_unfiltered_required' USING ERRCODE='23514';
      END IF;
      IF TG_TABLE_NAME='account_erasure_request_attempts' THEN
        IF EXISTS(SELECT 1 FROM ntubtob.account_erasure_intake_attempts WHERE attempt_id=NEW.attempt_id) THEN
          RAISE EXCEPTION 'intake_attempt_replay' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END IF;
      SELECT * INTO i FROM ntubtob.account_erasure_intakes WHERE id=NEW.intake_id FOR UPDATE;
      IF NOT FOUND OR i.status<>'requested' OR NEW.created_at<i.requested_at OR NEW.proof_expires_at>i.evidence_expires_at
         OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_request_attempts WHERE attempt_id=NEW.attempt_id) THEN
        RAISE EXCEPTION 'intake_attempt_rejected' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END;
    $$;
    CREATE TRIGGER erasure_intake_attempt_guard BEFORE INSERT ON ntubtob.account_erasure_intake_attempts FOR EACH ROW EXECUTE FUNCTION ntubtob.guard_erasure_intake_attempt();
    CREATE TRIGGER erasure_intake_old_attempt_guard BEFORE INSERT ON ntubtob.account_erasure_request_attempts FOR EACH ROW EXECUTE FUNCTION ntubtob.guard_erasure_intake_attempt();
    CREATE TRIGGER erasure_intake_attempt_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON ntubtob.account_erasure_intake_attempts FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.reject_erasure_evidence_mutation();

    DO $$
    DECLARE obj text; recipient record; role_sql text;
    BEGIN
      FOREACH obj IN ARRAY ARRAY['account_erasure_intakes','account_erasure_intake_attempts'] LOOP
        FOR recipient IN SELECT DISTINCT a.grantee,r.rolname FROM pg_class c
          CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
          LEFT JOIN pg_roles r ON r.oid=a.grantee WHERE c.oid=('ntubtob.'||obj)::regclass AND a.grantee<>c.relowner LOOP
          role_sql:=CASE WHEN recipient.grantee=0 THEN 'PUBLIC' ELSE quote_ident(recipient.rolname) END;
          EXECUTE 'REVOKE ALL ON TABLE ntubtob.'||quote_ident(obj)||' FROM '||role_sql;
        END LOOP;
      END LOOP;
      FOREACH obj IN ARRAY ARRAY['guard_erasure_intake','guard_erasure_intake_job','guard_erasure_intake_atomic','guard_erasure_intake_attempt'] LOOP
        FOR recipient IN SELECT DISTINCT a.grantee,r.rolname FROM pg_proc p
          CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a
          LEFT JOIN pg_roles r ON r.oid=a.grantee WHERE p.oid=('ntubtob.'||obj||'()')::regprocedure AND a.grantee<>p.proowner LOOP
          role_sql:=CASE WHEN recipient.grantee=0 THEN 'PUBLIC' ELSE quote_ident(recipient.rolname) END;
          EXECUTE 'REVOKE ALL ON FUNCTION ntubtob.'||quote_ident(obj)||'() FROM '||role_sql;
        END LOOP;
      END LOOP;
    END;
    $$;
    """
    )
    # CREATE OR REPLACE preserves the existing restricted operator ACL/owner.
    op.execute(SUSPEND_0020)


def downgrade():
    op.execute(
        """
    DO $$ BEGIN
      PERFORM pg_advisory_xact_lock(70070);
      PERFORM pg_advisory_xact_lock(1315198274);
      LOCK TABLE ntubtob.account_erasure_intakes,ntubtob.account_erasure_intake_attempts,ntubtob.account_erasure_jobs IN ACCESS EXCLUSIVE MODE;
      IF row_security_active('ntubtob.account_erasure_intakes'::regclass) IS DISTINCT FROM FALSE
         OR row_security_active('ntubtob.account_erasure_intake_attempts'::regclass) IS DISTINCT FROM FALSE THEN
        RAISE EXCEPTION 'intake_unfiltered_required' USING ERRCODE='23514';
      END IF;
      IF EXISTS(SELECT 1 FROM ntubtob.account_erasure_intakes) OR EXISTS(SELECT 1 FROM ntubtob.account_erasure_intake_attempts) THEN
        RAISE EXCEPTION 'intake_history_retained' USING ERRCODE='23514';
      END IF;
    END; $$;
    DROP TRIGGER erasure_intake_job_atomic ON ntubtob.account_erasure_jobs;
    DROP TRIGGER erasure_intake_job_guard ON ntubtob.account_erasure_jobs;
    DROP TRIGGER erasure_intake_old_attempt_guard ON ntubtob.account_erasure_request_attempts;
    DROP TABLE ntubtob.account_erasure_intake_attempts;
    DROP TABLE ntubtob.account_erasure_intakes;
    DROP FUNCTION ntubtob.guard_erasure_intake_attempt();
    DROP FUNCTION ntubtob.guard_erasure_intake_atomic();
    DROP FUNCTION ntubtob.guard_erasure_intake_job();
    DROP FUNCTION ntubtob.guard_erasure_intake();
    """
    )
    op.execute(SUSPEND_0019)
