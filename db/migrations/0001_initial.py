"""initial schema

Revision ID: 0001
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.String(64), primary_key=True),
        sa.Column("boss_name", sa.String(128), nullable=False),
        sa.Column("plan", sa.String(32), nullable=False, server_default="trial"),
        sa.Column("created_at", sa.Integer, nullable=False),
        sa.Column("config_json", sa.Text),
    )

    op.create_table(
        "messages",
        sa.Column("msg_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("chat_id", sa.String(128), nullable=False),
        sa.Column("sender_id", sa.String(128), nullable=False),
        sa.Column("sender_name", sa.String(128)),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("msg_type", sa.String(32), nullable=False, server_default="text"),
        sa.Column("timestamp", sa.Integer, nullable=False),
        sa.Column("raw_metadata", sa.Text),
    )
    op.create_index("idx_messages_tenant", "messages", ["tenant_id"])
    op.create_index("idx_messages_chat", "messages", ["tenant_id", "chat_id"])

    op.create_table(
        "suggestions",
        sa.Column("msg_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("inbound_msg_id", sa.String(64), sa.ForeignKey("messages.msg_id"), nullable=False),
        sa.Column("intent", sa.String(32), nullable=False),
        sa.Column("risk", sa.String(16), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("model_route", sa.String(64), nullable=False),
        sa.Column("generated_at", sa.Integer, nullable=False),
        sa.Column("similarity_check_passed", sa.Integer, nullable=False, server_default="1"),
        sa.Column("rewrite_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("forbidden_word_hit", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("idx_suggestions_tenant", "suggestions", ["tenant_id"])

    op.create_table(
        "reviews",
        sa.Column("msg_id", sa.String(64), sa.ForeignKey("suggestions.msg_id"), primary_key=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("edited_text", sa.Text),
        sa.Column("reviewed_at", sa.Integer, nullable=False),
    )

    op.create_table(
        "sent_messages",
        sa.Column("msg_id", sa.String(64), sa.ForeignKey("suggestions.msg_id"), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("chat_id", sa.String(128), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("sent_at", sa.Integer, nullable=False),
        sa.Column("success", sa.Integer, nullable=False),
        sa.Column("error", sa.Text),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("actor", sa.String(32), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("msg_id", sa.String(64)),
        sa.Column("meta", sa.Text),
        sa.Column("timestamp", sa.Integer, nullable=False),
    )
    op.create_index("idx_audit_tenant", "audit_log", ["tenant_id", "timestamp"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("plan", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("started_at", sa.Integer, nullable=False),
        sa.Column("expires_at", sa.Integer, nullable=False),
        sa.Column("last_payment_id", sa.String(128)),
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
    op.drop_table("audit_log")
    op.drop_table("sent_messages")
    op.drop_table("reviews")
    op.drop_table("suggestions")
    op.drop_table("messages")
    op.drop_table("tenants")
