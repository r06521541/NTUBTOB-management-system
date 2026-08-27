"""Add Event edit and cancellation audit actions.

Revision ID: 0009_event_management_writes
Revises: 0008_mobile_notification_delivery
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0009_event_management_writes"
down_revision: Union[str, None] = "0008_mobile_notification_delivery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ntubtob.event_audit
          DROP CONSTRAINT ck_event_audit_action,
          ADD CONSTRAINT ck_event_audit_action CHECK (
            action IN (
              'published', 'edited', 'cancelled',
              'invitee_included', 'invitee_excluded'
            )
          );
        """
    )


def downgrade() -> None:
    # Rolling back application writes must not delete Event, invitee snapshots, or
    # append-only audit evidence. The widened constraint is intentionally retained.
    pass
