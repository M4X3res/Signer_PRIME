"""Initial schema: licenses and devices tables with partial unique index

Revision ID: 001
Revises: 
Create Date: 2026-09-12 13:15:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Создание таблиц licenses и devices с partial unique index для защиты от гонок."""
    
    # Таблица licenses
    op.create_table(
        'licenses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('license_key', sa.String(length=32), nullable=False),
        sa.Column('stripe_customer_id', sa.String(length=64), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(length=64), nullable=True),
        sa.Column('plan', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='active'),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('max_devices', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Индексы для licenses
    op.create_index('ix_licenses_license_key', 'licenses', ['license_key'], unique=True)
    op.create_index('ix_licenses_stripe_customer_id', 'licenses', ['stripe_customer_id'], unique=False)
    op.create_index('ix_licenses_stripe_subscription_id', 'licenses', ['stripe_subscription_id'], unique=False)
    
    # Таблица devices
    op.create_table(
        'devices',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('license_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('fingerprint_hash', sa.String(length=64), nullable=False),
        sa.Column('device_label', sa.String(length=128), nullable=True),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['license_id'], ['licenses.id'], ondelete='CASCADE'),
    )
    
    # Индексы для devices
    op.create_index('ix_devices_license_id', 'devices', ['license_id'], unique=False)
    
    # КРИТИЧНО: Partial unique index для защиты от гонок на уровне БД
    # Только одна активная (deactivated_at IS NULL) запись на комбинацию (license_id, fingerprint_hash)
    op.execute("""
        CREATE UNIQUE INDEX uq_active_device
        ON devices (license_id, fingerprint_hash)
        WHERE deactivated_at IS NULL;
    """)


def downgrade() -> None:
    """Откат миграции."""
    
    # Удаление partial unique index
    op.execute("DROP INDEX IF EXISTS uq_active_device;")
    
    # Удаление таблиц
    op.drop_index('ix_devices_license_id', table_name='devices')
    op.drop_table('devices')
    
    op.drop_index('ix_licenses_stripe_subscription_id', table_name='licenses')
    op.drop_index('ix_licenses_stripe_customer_id', table_name='licenses')
    op.drop_index('ix_licenses_license_key', table_name='licenses')
    op.drop_table('licenses')
