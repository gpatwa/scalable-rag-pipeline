"""persist typed support command proposals

Revision ID: 0008_support_action_commands
Revises: 0007_search_interaction_events
Create Date: 2026-08-23 00:00:00
"""
import sqlalchemy as sa
from alembic import op


revision = "0008_support_action_commands"
down_revision = "0007_search_interaction_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_actions", sa.Column("command_contract_version", sa.String(length=32), nullable=True))
    op.add_column("support_actions", sa.Column("command_payload", sa.JSON(), nullable=True))
    op.add_column("support_actions", sa.Column("policy_status", sa.String(length=32), nullable=True))
    op.add_column("support_actions", sa.Column("policy_reason", sa.Text(), nullable=True))
    op.add_column("support_actions", sa.Column("evidence_ids", sa.JSON(), nullable=True))
    op.add_column("support_actions", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.create_unique_constraint(
        "uq_support_action_tenant_idempotency",
        "support_actions",
        ["tenant_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_support_action_tenant_idempotency", "support_actions", type_="unique")
    op.drop_column("support_actions", "idempotency_key")
    op.drop_column("support_actions", "evidence_ids")
    op.drop_column("support_actions", "policy_reason")
    op.drop_column("support_actions", "policy_status")
    op.drop_column("support_actions", "command_payload")
    op.drop_column("support_actions", "command_contract_version")
