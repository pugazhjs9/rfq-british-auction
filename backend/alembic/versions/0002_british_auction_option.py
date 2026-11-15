"""british auction option

An RFQ can be created without the British auction option. It then has a fixed
close time, so it has no forced close and no extension settings.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15 10:12:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SETTINGS = ('forced_close_at', 'trigger_window_minutes', 'extension_minutes', 'trigger_type')


def upgrade() -> None:
    # Existing RFQs were all British auctions.
    op.add_column('rfqs', sa.Column('british_auction', sa.Boolean(), server_default=sa.true(), nullable=False))
    for column in SETTINGS:
        op.alter_column('rfqs', column, nullable=True)
    op.create_check_constraint(
        op.f('ck_rfqs_british_auction_settings'),
        'rfqs',
        '(british_auction AND forced_close_at IS NOT NULL AND trigger_window_minutes IS NOT NULL'
        ' AND extension_minutes IS NOT NULL AND trigger_type IS NOT NULL)'
        ' OR (NOT british_auction AND forced_close_at IS NULL AND trigger_window_minutes IS NULL'
        ' AND extension_minutes IS NULL AND trigger_type IS NULL)',
    )
    op.drop_constraint(op.f('ck_rfqs_current_close_within_bounds'), 'rfqs', type_='check')
    op.create_check_constraint(
        op.f('ck_rfqs_current_close_within_bounds'),
        'rfqs',
        'current_close_at >= bid_close_at AND current_close_at <= COALESCE(forced_close_at, bid_close_at)',
    )


def downgrade() -> None:
    # The old schema can't represent a fixed-close RFQ, so those are removed.
    op.execute('DELETE FROM rfqs WHERE NOT british_auction')
    op.drop_constraint(op.f('ck_rfqs_current_close_within_bounds'), 'rfqs', type_='check')
    op.create_check_constraint(
        op.f('ck_rfqs_current_close_within_bounds'),
        'rfqs',
        'current_close_at >= bid_close_at AND current_close_at <= forced_close_at',
    )
    op.drop_constraint(op.f('ck_rfqs_british_auction_settings'), 'rfqs', type_='check')
    for column in SETTINGS:
        op.alter_column('rfqs', column, nullable=False)
    op.drop_column('rfqs', 'british_auction')
