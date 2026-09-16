"""Add optional account deletion requests without fulfillment or runtime enablement.

Revision ID: 0013_account_deletion_requests
Revises: 0012_persistent_admin_authority
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0013_account_deletion_requests"
down_revision: Union[str, None] = "0012_persistent_admin_authority"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ntubtob.account_deletion_requests (
          id uuid PRIMARY KEY,
          person_id bigint NOT NULL REFERENCES ntubtob.people(id) ON DELETE RESTRICT,
          status varchar(20) NOT NULL,
          requested_at timestamptz NOT NULL,
          CONSTRAINT uq_account_deletion_person UNIQUE (person_id),
          CONSTRAINT ck_account_deletion_status CHECK (status = 'requested')
        );
        ALTER TABLE ntubtob.account_deletion_requests ENABLE ROW LEVEL SECURITY;
        """
    )


def downgrade() -> None:
    # Retain acknowledged requests when rolling back the application.
    pass
