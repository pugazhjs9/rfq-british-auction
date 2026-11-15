"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-11-14 01:17:02.799037

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.schema.CreateSequence(sa.Sequence('rfq_reference_seq')))
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('company', sa.String(length=120), nullable=False),
    sa.Column('role', sa.Enum('BUYER', 'SUPPLIER', name='user_role'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_table('rfqs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('reference_id', sa.String(length=20), server_default=sa.text("'RFQ-' || lpad(nextval('rfq_reference_seq')::text, 5, '0')"), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('buyer_id', sa.Integer(), nullable=False),
    sa.Column('pickup_date', sa.Date(), nullable=False),
    sa.Column('bid_start_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('bid_close_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('current_close_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('forced_close_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('trigger_window_minutes', sa.Integer(), nullable=False),
    sa.Column('extension_minutes', sa.Integer(), nullable=False),
    sa.Column('trigger_type', sa.Enum('BID_RECEIVED', 'ANY_RANK_CHANGE', 'L1_CHANGE', name='trigger_type'), nullable=False),
    sa.Column('extension_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('finalized_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('bid_close_at < forced_close_at', name=op.f('ck_rfqs_forced_close_after_bid_close')),
    sa.CheckConstraint('bid_start_at < bid_close_at', name=op.f('ck_rfqs_bid_close_after_start')),
    sa.CheckConstraint('current_close_at >= bid_close_at AND current_close_at <= forced_close_at', name=op.f('ck_rfqs_current_close_within_bounds')),
    sa.CheckConstraint('extension_minutes > 0', name=op.f('ck_rfqs_extension_positive')),
    sa.CheckConstraint('trigger_window_minutes > 0', name=op.f('ck_rfqs_trigger_window_positive')),
    sa.ForeignKeyConstraint(['buyer_id'], ['users.id'], name=op.f('fk_rfqs_buyer_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rfqs')),
    sa.UniqueConstraint('reference_id', name=op.f('uq_rfqs_reference_id'))
    )
    op.create_index('ix_rfqs_unfinalized_close', 'rfqs', ['current_close_at'], unique=False, postgresql_where=sa.text('finalized_at IS NULL'))
    op.create_table('bids',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('rfq_id', sa.Integer(), nullable=False),
    sa.Column('supplier_id', sa.Integer(), nullable=False),
    sa.Column('carrier_name', sa.String(length=120), nullable=False),
    sa.Column('freight_charges', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('origin_charges', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('destination_charges', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('total_amount', sa.Numeric(precision=14, scale=2), sa.Computed('freight_charges + origin_charges + destination_charges', persisted=True), nullable=False),
    sa.Column('transit_time_days', sa.Integer(), nullable=False),
    sa.Column('quote_valid_until', sa.Date(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('destination_charges >= 0', name=op.f('ck_bids_destination_non_negative')),
    sa.CheckConstraint('freight_charges >= 0', name=op.f('ck_bids_freight_non_negative')),
    sa.CheckConstraint('origin_charges >= 0', name=op.f('ck_bids_origin_non_negative')),
    sa.CheckConstraint('transit_time_days > 0', name=op.f('ck_bids_transit_time_positive')),
    sa.ForeignKeyConstraint(['rfq_id'], ['rfqs.id'], name=op.f('fk_bids_rfq_id_rfqs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['supplier_id'], ['users.id'], name=op.f('fk_bids_supplier_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_bids'))
    )
    op.create_index('ix_bids_rfq_supplier_latest', 'bids', ['rfq_id', 'supplier_id', sa.text('created_at DESC')], unique=False)
    op.create_index('ix_bids_rfq_total', 'bids', ['rfq_id', 'total_amount'], unique=False)
    op.create_table('auction_events',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('rfq_id', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.Enum('AUCTION_CREATED', 'BID_SUBMITTED', 'EXTENDED', 'EXTENSION_SKIPPED', 'AUCTION_CLOSED', 'AUCTION_FORCE_CLOSED', name='auction_event_type'), nullable=False),
    sa.Column('bid_id', sa.BigInteger(), nullable=True),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('previous_close_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('new_close_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_auction_events_actor_id_users')),
    sa.ForeignKeyConstraint(['bid_id'], ['bids.id'], name=op.f('fk_auction_events_bid_id_bids'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['rfq_id'], ['rfqs.id'], name=op.f('fk_auction_events_rfq_id_rfqs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_auction_events'))
    )
    op.create_index('ix_auction_events_rfq_time', 'auction_events', ['rfq_id', 'created_at', 'id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_auction_events_rfq_time', table_name='auction_events')
    op.drop_table('auction_events')
    op.drop_index('ix_bids_rfq_total', table_name='bids')
    op.drop_index('ix_bids_rfq_supplier_latest', table_name='bids')
    op.drop_table('bids')
    op.drop_index('ix_rfqs_unfinalized_close', table_name='rfqs', postgresql_where=sa.text('finalized_at IS NULL'))
    op.drop_table('rfqs')
    op.drop_table('users')
    op.execute(sa.schema.DropSequence(sa.Sequence('rfq_reference_seq')))
    for enum_name in ('auction_event_type', 'trigger_type', 'user_role'):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
