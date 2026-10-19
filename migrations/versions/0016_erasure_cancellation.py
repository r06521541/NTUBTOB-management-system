"""Retained cancellation evidence and monotonic irreversible dispatch fence.

This source-only candidate supplies no cancellation authority or executor. Legacy
non-requested jobs or possible irreversible step evidence require separately
reviewed reconciliation, never an invented historical fence. Cancel does not
restore sessions, permissions or provider credentials. A retaining downgrade is
not evidence that an old runtime can safely serve these rows; rollout must gate it.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0016_erasure_cancellation"
down_revision: Union[str, None] = "0015_account_generations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        LOCK TABLE ntubtob.account_erasure_jobs,
          ntubtob.account_erasure_steps IN ACCESS EXCLUSIVE MODE;
        DO $$
        BEGIN
          IF pg_catalog.current_setting('transaction_isolation') <> 'read committed' THEN
            RAISE EXCEPTION 'read committed erasure migration required' USING ERRCODE = '23514';
          END IF;
          IF pg_catalog.row_security_active('ntubtob.account_erasure_jobs'::regclass)
             IS DISTINCT FROM FALSE OR
             pg_catalog.row_security_active('ntubtob.account_erasure_steps'::regclass)
             IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'unfiltered erasure evidence required' USING ERRCODE = '23514';
          END IF;
          IF EXISTS (SELECT 1 FROM ntubtob.account_erasure_jobs WHERE status <> 'requested') OR
             EXISTS (SELECT 1 FROM ntubtob.account_erasure_steps
                      WHERE stage IN ('provider_revocation', 'online_erasure',
                                      'online_verification', 'restore_suppression', 'completion')
                        AND event_kind <> 'planned') THEN
            RAISE EXCEPTION 'legacy erasure reconciliation required' USING ERRCODE = '23514';
          END IF;
        END;
        $$;

        ALTER TABLE ntubtob.account_erasure_jobs
          ADD COLUMN cancelled_at timestamptz,
          ADD COLUMN irreversible_started_at timestamptz,
          DROP CONSTRAINT ck_erasure_job_status,
          DROP CONSTRAINT ck_erasure_job_target,
          DROP CONSTRAINT ck_erasure_job_times,
          DROP CONSTRAINT ck_erasure_job_verified,
          ADD CONSTRAINT ck_erasure_job_status CHECK (
            status IN ('requested', 'verified', 'processing', 'needs_attention', 'online_completed', 'completed', 'cancelled')
          ),
          ADD CONSTRAINT ck_erasure_job_target CHECK (
            (status <> 'cancelled' AND target_kind = 'person' AND person_id IS NOT NULL AND auth_identity_id IS NULL) OR
            (status <> 'cancelled' AND target_kind = 'pending_identity' AND auth_identity_id IS NOT NULL AND person_id IS NULL) OR
            (status IN ('online_completed', 'completed', 'cancelled') AND person_id IS NULL AND auth_identity_id IS NULL)
          ),
          ADD CONSTRAINT ck_erasure_job_times CHECK (
            isfinite(requested_at) AND isfinite(updated_at) AND
            isfinite(COALESCE(verified_at, requested_at)) AND
            isfinite(COALESCE(online_completed_at, requested_at)) AND
            isfinite(COALESCE(completed_at, requested_at)) AND
            isfinite(COALESCE(cancelled_at, requested_at)) AND
            isfinite(COALESCE(irreversible_started_at, requested_at)) AND
            updated_at >= requested_at AND
            (verified_at IS NULL OR (verified_at >= requested_at AND verified_at <= updated_at)) AND
            (irreversible_started_at IS NULL OR (irreversible_started_at >= verified_at AND irreversible_started_at <= updated_at)) AND
            (online_completed_at IS NULL OR (online_completed_at >= verified_at AND online_completed_at >= irreversible_started_at AND online_completed_at <= updated_at)) AND
            (completed_at IS NULL OR (completed_at >= online_completed_at AND completed_at <= updated_at)) AND
            (cancelled_at IS NULL OR (cancelled_at >= requested_at AND (verified_at IS NULL OR cancelled_at >= verified_at) AND cancelled_at <= updated_at))
          ),
          ADD CONSTRAINT ck_erasure_job_verified CHECK (
            (status = 'requested' AND verified_at IS NULL) OR
            (status NOT IN ('requested', 'cancelled') AND verified_at IS NOT NULL) OR status = 'cancelled'
          ),
          ADD CONSTRAINT ck_erasure_job_cancelled CHECK (
            (status = 'cancelled' AND cancelled_at IS NOT NULL) OR (status <> 'cancelled' AND cancelled_at IS NULL)
          ),
          ADD CONSTRAINT ck_erasure_job_irreversible CHECK (
            (irreversible_started_at IS NULL OR status NOT IN ('requested', 'cancelled')) AND
            (status NOT IN ('online_completed', 'completed') OR irreversible_started_at IS NOT NULL)
          );
        ALTER TABLE ntubtob.account_erasure_steps
          DROP CONSTRAINT ck_erasure_step_stage,
          ADD CONSTRAINT ck_erasure_step_stage CHECK (
            stage IN ('verification', 'access_block', 'provider_revocation', 'online_erasure', 'online_verification', 'restore_suppression', 'completion', 'cancellation')
          );

        CREATE OR REPLACE FUNCTION ntubtob.guard_erasure_job() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            IF NEW.status <> 'requested' THEN
              RAISE EXCEPTION 'erasure job must begin requested' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.status = 'cancelled' AND NEW IS DISTINCT FROM OLD THEN
            RAISE EXCEPTION 'cancelled erasure job is immutable' USING ERRCODE = '23514';
          END IF;
          IF NEW.id IS DISTINCT FROM OLD.id OR
             NEW.target_kind IS DISTINCT FROM OLD.target_kind OR
             NEW.expected_generation IS DISTINCT FROM OLD.expected_generation OR
             NEW.requested_at IS DISTINCT FROM OLD.requested_at OR
             NEW.receipt_secret_hash IS DISTINCT FROM OLD.receipt_secret_hash THEN
            RAISE EXCEPTION 'erasure job binding is immutable' USING ERRCODE = '23514';
          END IF;
          IF (NEW.person_id IS DISTINCT FROM OLD.person_id OR
              NEW.auth_identity_id IS DISTINCT FROM OLD.auth_identity_id) AND NOT (
                NEW.status IN ('online_completed', 'completed', 'cancelled') AND
                NEW.person_id IS NULL AND NEW.auth_identity_id IS NULL
              ) THEN
            RAISE EXCEPTION 'erasure target detachment rejected' USING ERRCODE = '23514';
          END IF;
          IF NEW.status <> OLD.status AND NOT (
               (OLD.status = 'requested' AND NEW.status = 'verified') OR
               (OLD.status = 'verified' AND NEW.status IN ('processing', 'needs_attention')) OR
               (OLD.status = 'processing' AND NEW.status IN ('needs_attention', 'online_completed')) OR
               (OLD.status = 'needs_attention' AND NEW.status = 'processing') OR
               (OLD.status = 'online_completed' AND NEW.status = 'completed') OR
               (OLD.status IN ('requested', 'verified', 'processing', 'needs_attention') AND NEW.status = 'cancelled')
             ) THEN
            RAISE EXCEPTION 'erasure status transition rejected' USING ERRCODE = '23514';
          END IF;
          IF (OLD.status <> 'requested' OR NEW.status <> 'requested') AND (
               NEW.scope_version IS DISTINCT FROM OLD.scope_version OR
               NEW.scope_hash IS DISTINCT FROM OLD.scope_hash OR
               NEW.retention_policy_version IS DISTINCT FROM OLD.retention_policy_version OR
               NEW.fulfillment_due_at IS DISTINCT FROM OLD.fulfillment_due_at OR
               NEW.receipt_expires_at IS DISTINCT FROM OLD.receipt_expires_at OR
               NEW.evidence_expires_at IS DISTINCT FROM OLD.evidence_expires_at
             ) THEN
            RAISE EXCEPTION 'erasure policy and scope are immutable' USING ERRCODE = '23514';
          END IF;
          IF NEW.status = 'cancelled' AND (
               OLD.irreversible_started_at IS NOT NULL OR
               NEW.verified_at IS DISTINCT FROM OLD.verified_at OR
               NEW.online_completed_at IS DISTINCT FROM OLD.online_completed_at OR
               NEW.completed_at IS DISTINCT FROM OLD.completed_at
             ) THEN
            RAISE EXCEPTION 'erasure cancellation rejected' USING ERRCODE = '23514';
          END IF;
          IF (OLD.verified_at IS NOT NULL AND NEW.verified_at IS DISTINCT FROM OLD.verified_at) OR
             (OLD.online_completed_at IS NOT NULL AND NEW.online_completed_at IS DISTINCT FROM OLD.online_completed_at) OR
             (OLD.completed_at IS NOT NULL AND NEW.completed_at IS DISTINCT FROM OLD.completed_at) OR
             (OLD.irreversible_started_at IS NOT NULL AND NEW.irreversible_started_at IS DISTINCT FROM OLD.irreversible_started_at) OR
             NEW.updated_at < OLD.updated_at THEN
            RAISE EXCEPTION 'erasure timestamp rewrite rejected' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TABLE ntubtob.account_erasure_request_attempts (
          attempt_id uuid PRIMARY KEY,
          job_id uuid NOT NULL REFERENCES ntubtob.account_erasure_jobs(id) ON DELETE RESTRICT,
          assertion_binding varchar(64) NOT NULL,
          created_at timestamptz NOT NULL,
          proof_expires_at timestamptz NOT NULL,
          CONSTRAINT ck_erasure_attempt_binding CHECK (assertion_binding ~ '^[0-9a-f]{64}$'),
          CONSTRAINT ck_erasure_attempt_times CHECK (
            isfinite(created_at) AND isfinite(proof_expires_at) AND
            proof_expires_at > created_at AND
            EXTRACT(EPOCH FROM (proof_expires_at - created_at)) <= 300
          )
        );
        ALTER TABLE ntubtob.account_erasure_request_attempts ENABLE ROW LEVEL SECURITY;
        CREATE FUNCTION ntubtob.guard_erasure_request_attempt() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $$
        DECLARE target_status text; target_requested timestamptz; target_deadline timestamptz;
        BEGIN
          IF pg_catalog.row_security_active('ntubtob.account_erasure_jobs'::regclass)
             IS DISTINCT FROM FALSE THEN
            RAISE EXCEPTION 'unfiltered erasure job required' USING ERRCODE = '23514';
          END IF;
          SELECT status, requested_at, evidence_expires_at
            INTO target_status, target_requested, target_deadline
            FROM ntubtob.account_erasure_jobs WHERE id=NEW.job_id FOR UPDATE;
          IF NOT FOUND OR target_status <> 'requested' OR
             NEW.created_at < target_requested OR NEW.proof_expires_at > target_deadline THEN
            RAISE EXCEPTION 'erasure attempt binding rejected' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        CREATE TRIGGER erasure_request_attempt_binding
          BEFORE INSERT ON ntubtob.account_erasure_request_attempts
          FOR EACH ROW EXECUTE FUNCTION ntubtob.guard_erasure_request_attempt();
        CREATE TRIGGER erasure_request_attempt_immutable
          BEFORE UPDATE OR DELETE OR TRUNCATE ON ntubtob.account_erasure_request_attempts
          FOR EACH STATEMENT EXECUTE FUNCTION ntubtob.reject_erasure_evidence_mutation();
        """
    )


def downgrade() -> None:
    # Evidence, terminal cancellation and the dispatch fence survive rollback.
    # Re-upgrade requires explicit reconciliation of the retained schema.
    pass
