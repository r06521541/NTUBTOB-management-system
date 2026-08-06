"""Align the local activity-to-legacy-game reference with bigint IDs.

Revision ID: 0003_legacy_bigint_activity_game
Revises: 0002_portal_data_foundation
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003_legacy_bigint_activity_game"
down_revision: Union[str, None] = "0002_portal_data_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ntubtob.activities "
        "ALTER COLUMN game_id TYPE bigint USING game_id::bigint"
    )


def downgrade() -> None:
    # Local rehearsal only. Production rollback retains expand schema.
    op.execute(
        "ALTER TABLE ntubtob.activities "
        "ALTER COLUMN game_id TYPE integer USING game_id::integer"
    )
