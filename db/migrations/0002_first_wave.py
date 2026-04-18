"""First Wave · 2026-04-16 · 新增 7 张表。

customer_profiles / knowledge_chunks / follow_up_tasks
account_health_metrics / account_health_status / account_failover_log
training_queue

注意：此 migration 仅为 schema 文档同步用。
实际启动通过 SQLAlchemy `Base.metadata.create_all` 自动创建（dev 模式）。
prod 切 PostgreSQL 时通过 alembic 应用本 migration。
"""

from __future__ import annotations

revision = "0002_first_wave"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op
    import sqlalchemy as sa

    # F2 customer_profiles
    op.create_table(
        "customer_profiles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("chat_id", sa.String(128), nullable=False),
        sa.Column("nickname", sa.String(128)),
        sa.Column("preferred_addressing", sa.String(64)),
        sa.Column("vip_tier", sa.String(8), nullable=False, server_default="C"),
        sa.Column("purchase_history", sa.Text),
        sa.Column("sensitive_topics", sa.Text),
        sa.Column("tags", sa.Text),
        sa.Column("last_intent", sa.String(32)),
        sa.Column("last_emotion", sa.String(32)),
        sa.Column("last_message_at", sa.Integer),
        sa.Column("total_messages", sa.Integer, nullable=False, server_default="0"),
        sa.Column("accepted_replies", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text),
        sa.Column("updated_at", sa.Integer, nullable=False),
        sa.UniqueConstraint("tenant_id", "chat_id", name="uq_customer_tenant_chat"),
    )
    op.create_index("idx_customer_tenant", "customer_profiles", ["tenant_id"])
    op.create_index("idx_customer_lastmsg", "customer_profiles", ["tenant_id", sa.text("last_message_at DESC")])

    # F3 knowledge_chunks
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(256), nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("embedding", sa.Text, nullable=False),
        sa.Column("tags", sa.Text),
        sa.Column("created_at", sa.Integer, nullable=False),
    )
    op.create_index("idx_knowledge_tenant", "knowledge_chunks", ["tenant_id"])
    op.create_index("idx_knowledge_source", "knowledge_chunks", ["tenant_id", "source"])

    # F4 follow_up_tasks
    op.create_table(
        "follow_up_tasks",
        sa.Column("task_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("chat_id", sa.String(128), nullable=False),
        sa.Column("sender_name", sa.String(128)),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("scheduled_at", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("template_id", sa.String(64)),
        sa.Column("context_json", sa.Text),
        sa.Column("created_at", sa.Integer, nullable=False),
        sa.Column("sent_at", sa.Integer),
    )
    op.create_index("idx_followup_due", "follow_up_tasks", ["status", "scheduled_at"])
    op.create_index("idx_followup_tenant", "follow_up_tasks", ["tenant_id", "status"])

    # F6 account_health_metrics
    op.create_table(
        "account_health_metrics",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("recorded_at", sa.Integer, nullable=False),
    )
    op.create_index("idx_health_tenant", "account_health_metrics",
                    ["tenant_id", "account_id", sa.text("recorded_at DESC")])

    # F6 account_health_status
    op.create_table(
        "account_health_status",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("daily_quota_override", sa.Integer),
        sa.Column("paused_until", sa.Integer),
        sa.Column("last_evaluated_at", sa.Integer, nullable=False),
        sa.UniqueConstraint("tenant_id", "account_id", name="uq_health_tenant_account"),
    )

    # F7 account_failover_log
    op.create_table(
        "account_failover_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("from_account", sa.String(64), nullable=False),
        sa.Column("to_account", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(256), nullable=False),
        sa.Column("triggered_at", sa.Integer, nullable=False),
        sa.Column("auto", sa.Integer, nullable=False, server_default="1"),
    )
    op.create_index("idx_failover_tenant", "account_failover_log",
                    ["tenant_id", sa.text("triggered_at DESC")])

    # C2 training_queue
    op.create_table(
        "training_queue",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("customer_msg", sa.Text, nullable=False),
        sa.Column("ai_reply", sa.Text, nullable=False),
        sa.Column("final_text", sa.Text, nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("intent", sa.String(32)),
        sa.Column("emotion", sa.String(32)),
        sa.Column("weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.Integer, nullable=False),
    )
    op.create_index("idx_training_tenant", "training_queue",
                    ["tenant_id", sa.text("created_at DESC")])


def downgrade() -> None:
    from alembic import op

    op.drop_table("training_queue")
    op.drop_table("account_failover_log")
    op.drop_table("account_health_status")
    op.drop_table("account_health_metrics")
    op.drop_table("follow_up_tasks")
    op.drop_table("knowledge_chunks")
    op.drop_table("customer_profiles")
