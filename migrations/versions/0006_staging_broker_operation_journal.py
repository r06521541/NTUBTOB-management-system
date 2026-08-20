"""Add the bounded staging broker operation journal.

Revision ID: 0006_staging_broker_operation_journal
Revises: 0005_mobile_auth_api_foundation
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006_staging_broker_operation_journal"
down_revision: Union[str, None] = "0005_mobile_auth_api_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
    ALTER TABLE ntubtob.alembic_version
      ALTER COLUMN version_num TYPE varchar(64);
    CREATE TABLE ntubtob.staging_broker_operations (
      operation_id varchar(64) NOT NULL,
      operation varchar(16) NOT NULL,
      target_state varchar(32) NOT NULL,
      inspect_fingerprint char(64) NOT NULL,
      lifecycle_state varchar(32) NOT NULL,
      reason_code varchar(32) NULL,
      inspected_at timestamptz NOT NULL,
      confirmed_at timestamptz NULL,
      mutation_issued_at timestamptz NULL,
      completed_at timestamptz NULL,
      created_at timestamptz NOT NULL,
      updated_at timestamptz NOT NULL,
      CONSTRAINT pk_staging_broker_operations PRIMARY KEY (operation_id),
      CONSTRAINT ck_staging_broker_operation_id CHECK (
        operation_id ~ '^[A-Za-z0-9_-]{16,64}$'
      ),
      CONSTRAINT ck_staging_broker_operation CHECK (
        operation IN ('inspect', 'reset', 'grant', 'restore')
      ),
      CONSTRAINT ck_staging_broker_target_state CHECK (
        target_state IN ('ready_basic', 'ready_officer', 'reset_required')
      ),
      CONSTRAINT ck_staging_broker_fingerprint CHECK (
        inspect_fingerprint ~ '^[0-9a-f]{64}$'
      ),
      CONSTRAINT ck_staging_broker_lifecycle_state CHECK (
        lifecycle_state IN (
          'inspected', 'confirmed', 'mutation_issued',
          'postcheck_complete', 'reconcile_required'
        )
      ),
      CONSTRAINT ck_staging_broker_reason_code CHECK (
        reason_code IS NULL OR reason_code IN (
          'OPERATOR_UNKNOWN', 'POSTCHECK_MISMATCH', 'RECONCILE_REQUIRED'
        )
      ),
      CONSTRAINT ck_staging_broker_timestamps CHECK (
        updated_at >= created_at AND inspected_at >= created_at
        AND (confirmed_at IS NULL) = (lifecycle_state = 'inspected')
        AND (mutation_issued_at IS NULL) = (
          lifecycle_state IN ('inspected', 'confirmed')
        )
        AND (completed_at IS NOT NULL) = (
          lifecycle_state IN ('postcheck_complete', 'reconcile_required')
        )
        AND (
          lifecycle_state <> 'reconcile_required' OR reason_code IS NOT NULL
        )
        AND (
          lifecycle_state = 'reconcile_required' OR reason_code IS NULL
        )
      )
    );
    CREATE INDEX ix_staging_broker_lifecycle_updated
      ON ntubtob.staging_broker_operations(lifecycle_state, updated_at);
    ALTER TABLE ntubtob.staging_broker_operations ENABLE ROW LEVEL SECURITY;
    """
    )


def downgrade() -> None:
    # Keep the lossless varchar(64) widening. Alembic writes the shorter 0005
    # revision only after this body returns, so shrinking here would fail while
    # the exact TASK-130-compatible 0006 revision is still stored.
    op.execute("DROP TABLE ntubtob.staging_broker_operations")
