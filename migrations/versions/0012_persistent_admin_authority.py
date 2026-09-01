"""Add persistent Web Portal admin authority rollout state.

Revision ID: 0012_persistent_admin_authority
Revises: 0011_event_notification_guest_lifecycle
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0012_persistent_admin_authority"
down_revision: Union[str, None] = "0011_event_notification_guest_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ntubtob.portal_authority_state (
          singleton_id smallint PRIMARY KEY,
          mode varchar(32) NOT NULL,
          epoch bigint NOT NULL,
          updated_at timestamptz NOT NULL,
          CONSTRAINT ck_portal_authority_singleton CHECK (singleton_id = 1),
          CONSTRAINT ck_portal_authority_mode CHECK (
            mode IN ('legacy_allowlist', 'persistent')
          ),
          CONSTRAINT ck_portal_authority_epoch CHECK (epoch >= 1)
        );

        INSERT INTO ntubtob.portal_authority_state
          (singleton_id, mode, epoch, updated_at)
        VALUES (1, 'legacy_allowlist', 1, now());

        ALTER TABLE ntubtob.portal_authority_state ENABLE ROW LEVEL SECURITY;
        """
    )


def downgrade() -> None:
    # Mode/epoch state is durable authorization evidence.  A rollback changes
    # runtime selection first; automatic downgrade must not erase this record.
    pass
