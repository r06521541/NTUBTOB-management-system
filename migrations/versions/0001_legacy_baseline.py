"""Record the reviewed minimal legacy fixture boundary.

Revision ID: 0001_legacy_baseline
Revises:
"""

from typing import Sequence, Union

revision: str = "0001_legacy_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentionally empty. Production must inventory and stamp explicitly.
    pass


def downgrade() -> None:
    pass
