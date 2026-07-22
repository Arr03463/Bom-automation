"""add projects.partsbox_* provisioning state

Persists what was actually created in PartsBox for a Project, per artifact, so a
partially-provisioned Project can never render as complete. Before this the
endpoint fabricated a "PB-<id>" reference, returned it once, and stored nothing.

`partsbox_filter_done` is a human acknowledgement: the PartsBox API has no
filter/preset operation (it is a UI-only feature), so the per-project build
filter is created by hand and confirmed here.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('partsbox_project_id', sa.String(), nullable=True))
    op.add_column('projects', sa.Column('partsbox_storage_id', sa.String(), nullable=True))
    op.add_column('projects', sa.Column('partsbox_filter_done', sa.Boolean(),
                                        nullable=False, server_default=sa.false()))
    op.add_column('projects', sa.Column('partsbox_error', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('projects', 'partsbox_error')
    op.drop_column('projects', 'partsbox_filter_done')
    op.drop_column('projects', 'partsbox_storage_id')
    op.drop_column('projects', 'partsbox_project_id')
