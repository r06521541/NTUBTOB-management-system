"""Private, operator-only continuity events; original deadlines remain immutable.

No role grants, retention cleanup, automatic renewal or runtime enablement.
An acknowledged extension prevents downgrade; old readers cannot honor it.
"""

from alembic import op

revision = "0021_erasure_continuity"
down_revision = "0020_erasure_intake"
branch_labels = None
depends_on = None


def _recovery_marker(old, new):
    # Preserve owner/ACL and all other SQL; replace only one exact marker predicate.
    # This is deliberately not an attestation of the entire installed function.
    before = f"ARRAY['{old}']::text[]".replace("'", "''")
    after = f"ARRAY['{new}']::text[]".replace("'", "''")
    op.execute(
        f"""DO $$ DECLARE source text; BEGIN
        SELECT pg_get_functiondef('ntubtob.suspend_management_for_erasure(uuid,uuid,bigint,uuid)'::regprocedure) INTO source;
        IF source IS NULL OR length(source)-length(replace(source,'{before}',''))<>length('{before}')
          OR position('{after}' in source)>0 THEN
          RAISE EXCEPTION 'continuity_recovery_definition_changed';
        END IF;
        EXECUTE replace(source, '{before}', '{after}');
        END $$;"""
    )


def _attempt_deadlines(*, reverse=False):
    replacements = (
        (
            "guard_erasure_request_attempt",
            "SELECT status, requested_at, evidence_expires_at",
            "SELECT status, requested_at, ntubtob.erasure_continuity_evidence(id,false)",
        ),
        (
            "guard_erasure_intake_attempt",
            "NEW.proof_expires_at>i.evidence_expires_at",
            "NEW.proof_expires_at>ntubtob.erasure_continuity_evidence(i.id,true)",
        ),
    )
    for name, before, after in replacements:
        if reverse:
            before, after = after, before
        op.execute(
            f"""DO $$ DECLARE source text; BEGIN
          SELECT pg_get_functiondef('ntubtob.{name}()'::regprocedure) INTO source;
          IF source IS NULL OR length(source)-length(replace(source,'{before}',''))<>length('{before}')
            OR position('{after}' in source)>0 THEN
            RAISE EXCEPTION 'continuity_attempt_definition_changed';
          END IF;
          EXECUTE replace(source,'{before}','{after}');
          END $$;"""
        )


def upgrade():
    op.execute(
        """
        CREATE TABLE ntubtob.account_erasure_continuity_events (
          operation_id uuid PRIMARY KEY,
          request_id uuid NOT NULL,
          target_kind varchar(24) NOT NULL,
          expected_generation uuid NOT NULL,
          original_requested_at timestamptz NOT NULL,
          original_receipt_hash char(64) NOT NULL,
          sequence bigint NOT NULL,
          previous_receipt_until timestamptz NOT NULL,
          previous_evidence_until timestamptz NOT NULL,
          receipt_until timestamptz NOT NULL,
          evidence_until timestamptz NOT NULL,
          occurred_at timestamptz NOT NULL,
          operator_name varchar(63) NOT NULL,
          reason varchar(32) NOT NULL DEFAULT 'unfinished_request',
          CONSTRAINT uq_erasure_continuity_sequence UNIQUE(request_id,sequence),
          CONSTRAINT ck_erasure_continuity_target CHECK(target_kind IN ('person','pending_identity')),
          CONSTRAINT ck_erasure_continuity_hash CHECK(original_receipt_hash ~ '^[0-9a-f]{64}$'),
          CONSTRAINT ck_erasure_continuity_sequence CHECK(sequence>0),
          CONSTRAINT ck_erasure_continuity_reason CHECK(reason='unfinished_request'),
          CONSTRAINT ck_erasure_continuity_times CHECK(
            isfinite(original_requested_at) AND isfinite(previous_receipt_until)
            AND isfinite(previous_evidence_until) AND isfinite(receipt_until)
            AND isfinite(evidence_until) AND isfinite(occurred_at)
            AND original_requested_at<=occurred_at AND occurred_at<previous_receipt_until
            AND previous_receipt_until<receipt_until AND previous_evidence_until<=evidence_until
            AND evidence_until>=receipt_until)
        );
        ALTER TABLE ntubtob.account_erasure_continuity_events ENABLE ROW LEVEL SECURITY;
        CREATE TRIGGER erasure_continuity_append_only
          BEFORE UPDATE OR DELETE OR TRUNCATE ON ntubtob.account_erasure_continuity_events
          FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.reject_erasure_evidence_mutation();

        CREATE FUNCTION ntubtob.erasure_continuity_evidence(p_request uuid,p_intake boolean)
        RETURNS timestamptz LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
        DECLARE root record; event record; receipt_time timestamptz; evidence_time timestamptz;
          previous_time timestamptz; next_sequence bigint:=1; table_name text;
        BEGIN
          PERFORM pg_advisory_xact_lock(70070);
          PERFORM pg_advisory_xact_lock(1315198274);
          IF current_setting('transaction_isolation')<>'read committed'
             OR p_request IS NULL OR p_intake IS NULL THEN
            RAISE EXCEPTION 'continuity_read_rejected' USING ERRCODE='23514';
          END IF;
          FOREACH table_name IN ARRAY ARRAY['account_erasure_jobs','account_erasure_intakes','account_erasure_continuity_events'] LOOP
            IF row_security_active(('ntubtob.'||table_name)::regclass) IS DISTINCT FROM FALSE THEN
              RAISE EXCEPTION 'continuity_unfiltered_state_required' USING ERRCODE='23514';
            END IF;
          END LOOP;
          IF p_intake THEN
            SELECT id,target_kind,expected_generation,requested_at,receipt_secret_hash,
              receipt_expires_at,evidence_expires_at INTO root
              FROM ntubtob.account_erasure_intakes WHERE id=p_request FOR UPDATE;
          ELSE
            SELECT id,target_kind,expected_generation,requested_at,receipt_secret_hash,
              receipt_expires_at,evidence_expires_at INTO root
              FROM ntubtob.account_erasure_jobs WHERE id=p_request FOR UPDATE;
          END IF;
          IF root.id IS NULL THEN
            RAISE EXCEPTION 'continuity_root_rejected' USING ERRCODE='23514';
          END IF;
          receipt_time:=root.receipt_expires_at; evidence_time:=root.evidence_expires_at;
          previous_time:=root.requested_at;
          FOR event IN SELECT * FROM ntubtob.account_erasure_continuity_events
              WHERE request_id=p_request ORDER BY sequence FOR SHARE LOOP
            IF ROW(event.target_kind,event.expected_generation,event.original_requested_at,event.original_receipt_hash)
                 IS DISTINCT FROM ROW(root.target_kind,root.expected_generation,root.requested_at,root.receipt_secret_hash)
               OR event.sequence<>next_sequence OR event.previous_receipt_until<>receipt_time
               OR event.previous_evidence_until<>evidence_time
               OR event.occurred_at<previous_time OR event.occurred_at>=receipt_time
               OR event.receipt_until<=receipt_time
               OR event.evidence_until<GREATEST(evidence_time,event.receipt_until) THEN
              RAISE EXCEPTION 'continuity_chain_changed' USING ERRCODE='23514';
            END IF;
            receipt_time:=event.receipt_until; evidence_time:=event.evidence_until;
            previous_time:=event.occurred_at; next_sequence:=next_sequence+1;
          END LOOP;
          RETURN evidence_time;
        END $$;

        CREATE FUNCTION ntubtob.extend_erasure_continuity(
          p_request uuid,p_generation uuid,p_sequence bigint,p_operation uuid,
          p_receipt_until timestamptz,p_evidence_until timestamptz
        ) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
        DECLARE root record; intake record; last_event record; replay record;
          receipt_time timestamptz; evidence_time timestamptz; applied_time timestamptz;
          sequence_number bigint; table_name text;
        BEGIN
          IF p_request IS NULL OR p_generation IS NULL OR p_operation IS NULL
             OR p_sequence IS NULL OR p_sequence NOT BETWEEN 0 AND 9223372036854775806
             OR p_receipt_until IS NULL OR p_evidence_until IS NULL
             OR NOT isfinite(p_receipt_until) OR NOT isfinite(p_evidence_until)
             OR p_evidence_until<p_receipt_until THEN
            RAISE EXCEPTION 'continuity_input_rejected' USING ERRCODE='23514';
          END IF;
          IF current_setting('transaction_isolation')<>'read committed' THEN
            RAISE EXCEPTION 'continuity_transaction_rejected' USING ERRCODE='23514';
          END IF;
          PERFORM pg_advisory_xact_lock(70070);
          PERFORM pg_advisory_xact_lock(1315198274);
          IF (SELECT array_agg(version_num::text ORDER BY version_num) FROM ntubtob.alembic_version)
              IS DISTINCT FROM ARRAY['0021_erasure_continuity']::text[] THEN
            RAISE EXCEPTION 'continuity_schema_not_ready' USING ERRCODE='23514';
          END IF;
          FOREACH table_name IN ARRAY ARRAY['account_erasure_jobs','account_erasure_intakes','account_erasure_continuity_events'] LOOP
            IF row_security_active(('ntubtob.'||table_name)::regclass) IS DISTINCT FROM FALSE THEN
              RAISE EXCEPTION 'continuity_unfiltered_state_required' USING ERRCODE='23514';
            END IF;
          END LOOP;
          SELECT id,target_kind,status,expected_generation,requested_at,updated_at,receipt_secret_hash,
            receipt_expires_at,evidence_expires_at INTO intake
            FROM ntubtob.account_erasure_intakes WHERE id=p_request FOR UPDATE;
          SELECT id,target_kind,status,expected_generation,requested_at,updated_at,receipt_secret_hash,
            receipt_expires_at,evidence_expires_at INTO root
            FROM ntubtob.account_erasure_jobs WHERE id=p_request FOR UPDATE;
          IF root.id IS NULL THEN root:=intake;
          ELSIF intake.id IS NOT NULL AND (
            intake.status<>'materialized' OR
            ROW(root.target_kind,root.expected_generation,root.requested_at,root.receipt_secret_hash,root.receipt_expires_at,root.evidence_expires_at)
            IS DISTINCT FROM ROW(intake.target_kind,intake.expected_generation,intake.requested_at,intake.receipt_secret_hash,intake.receipt_expires_at,intake.evidence_expires_at)) THEN
            RAISE EXCEPTION 'continuity_root_binding_changed' USING ERRCODE='23514';
          END IF;
          IF root.id IS NULL OR root.expected_generation<>p_generation THEN
            RAISE EXCEPTION 'continuity_root_rejected' USING ERRCODE='23514';
          END IF;
          SELECT * INTO replay FROM ntubtob.account_erasure_continuity_events WHERE operation_id=p_operation;
          IF FOUND THEN
            IF replay.request_id=p_request AND replay.expected_generation=p_generation
              AND replay.sequence=p_sequence+1 AND replay.receipt_until=p_receipt_until
              AND replay.evidence_until=p_evidence_until AND replay.operator_name=SESSION_USER THEN
              RETURN p_operation;
            END IF;
            RAISE EXCEPTION 'continuity_operation_replay' USING ERRCODE='23514';
          END IF;
          IF root.status NOT IN ('requested','verified','processing','needs_attention','online_completed') THEN
            RAISE EXCEPTION 'continuity_unfinished_request_required' USING ERRCODE='23514';
          END IF;
          SELECT * INTO last_event FROM ntubtob.account_erasure_continuity_events
            WHERE request_id=p_request ORDER BY sequence DESC LIMIT 1 FOR UPDATE;
          sequence_number:=COALESCE(last_event.sequence,0);
          receipt_time:=COALESCE(last_event.receipt_until,root.receipt_expires_at);
          evidence_time:=COALESCE(last_event.evidence_until,root.evidence_expires_at);
          IF sequence_number<>p_sequence OR (sequence_number>0 AND
            ROW(last_event.target_kind,last_event.expected_generation,last_event.original_requested_at,last_event.original_receipt_hash)
            IS DISTINCT FROM ROW(root.target_kind,root.expected_generation,root.requested_at,root.receipt_secret_hash)) THEN
            RAISE EXCEPTION 'continuity_chain_changed' USING ERRCODE='23514';
          END IF;
          applied_time:=clock_timestamp();
          IF applied_time<GREATEST(root.requested_at,root.updated_at,COALESCE(last_event.occurred_at,root.requested_at))
             OR applied_time>=receipt_time
             OR p_receipt_until<=receipt_time OR p_evidence_until<evidence_time THEN
            RAISE EXCEPTION 'continuity_window_rejected' USING ERRCODE='23514';
          END IF;
          INSERT INTO ntubtob.account_erasure_continuity_events
            (operation_id,request_id,target_kind,expected_generation,original_requested_at,original_receipt_hash,
             sequence,previous_receipt_until,previous_evidence_until,receipt_until,evidence_until,occurred_at,operator_name)
            VALUES(p_operation,p_request,root.target_kind,root.expected_generation,root.requested_at,root.receipt_secret_hash,
              p_sequence+1,receipt_time,evidence_time,p_receipt_until,p_evidence_until,applied_time,SESSION_USER);
          RETURN p_operation;
        END $$;
        REVOKE ALL ON TABLE ntubtob.account_erasure_continuity_events FROM PUBLIC;
        REVOKE ALL ON FUNCTION ntubtob.extend_erasure_continuity(uuid,uuid,bigint,uuid,timestamptz,timestamptz) FROM PUBLIC;
        REVOKE ALL ON FUNCTION ntubtob.erasure_continuity_evidence(uuid,boolean) FROM PUBLIC;
        DO $$ DECLARE grant_row record; BEGIN
          FOR grant_row IN
            SELECT DISTINCT a.grantee FROM pg_class c,
              LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
              WHERE c.oid='ntubtob.account_erasure_continuity_events'::regclass
                AND a.grantee<>c.relowner AND a.grantee<>0
          LOOP
            EXECUTE format('REVOKE ALL ON TABLE ntubtob.account_erasure_continuity_events FROM %I',pg_get_userbyid(grant_row.grantee));
          END LOOP;
          FOR grant_row IN
            SELECT DISTINCT a.grantee FROM pg_proc p,
              LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a
              WHERE p.oid IN ('ntubtob.extend_erasure_continuity(uuid,uuid,bigint,uuid,timestamptz,timestamptz)'::regprocedure,
                'ntubtob.erasure_continuity_evidence(uuid,boolean)'::regprocedure)
                AND a.grantee<>p.proowner AND a.grantee<>0
          LOOP
            EXECUTE format('REVOKE ALL ON FUNCTION ntubtob.extend_erasure_continuity(uuid,uuid,bigint,uuid,timestamptz,timestamptz) FROM %I',pg_get_userbyid(grant_row.grantee));
            EXECUTE format('REVOKE ALL ON FUNCTION ntubtob.erasure_continuity_evidence(uuid,boolean) FROM %I',pg_get_userbyid(grant_row.grantee));
          END LOOP;
        END $$;
        """
    )
    _recovery_marker("0020_erasure_intake", revision)
    _attempt_deadlines()


def downgrade():
    op.execute(
        """LOCK TABLE ntubtob.account_erasure_continuity_events IN ACCESS EXCLUSIVE MODE;
        DO $$ BEGIN
          IF row_security_active('ntubtob.account_erasure_continuity_events'::regclass) IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'continuity_unfiltered_state_required';
          END IF;
          IF EXISTS(SELECT 1 FROM ntubtob.account_erasure_continuity_events) THEN
            RAISE EXCEPTION 'continuity_evidence_retained';
          END IF;
        END $$;"""
    )
    _recovery_marker(revision, "0020_erasure_intake")
    _attempt_deadlines(reverse=True)
    op.execute(
        """DROP FUNCTION ntubtob.erasure_continuity_evidence(uuid,boolean);
        DROP FUNCTION ntubtob.extend_erasure_continuity(uuid,uuid,bigint,uuid,timestamptz,timestamptz);
        DROP TABLE ntubtob.account_erasure_continuity_events;"""
    )
