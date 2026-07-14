"""add local CRM business tables

Revision ID: 6c4e1b9a3d2f
Revises: 2b7c9d1e4a6f
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6c4e1b9a3d2f"
down_revision: Union[str, Sequence[str], None] = "2b7c9d1e4a6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("customers",
        sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("normalized_name", sa.String(200), nullable=False), sa.Column("industry", sa.String(100), nullable=False),
        sa.Column("level", sa.String(20), nullable=False), sa.Column("owner_user_id", sa.String(36)), sa.Column("status", sa.String(20), nullable=False),
        *_timestamps(), sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]), sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("tenant_id", "normalized_name", name="uq_customer_tenant_name"))
    op.create_index("ix_customers_tenant_id", "customers", ["tenant_id"])
    op.create_index("ix_customers_owner_user_id", "customers", ["owner_user_id"])

    op.create_table("contacts",
        sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("customer_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False), sa.Column("title", sa.String(100), nullable=False), sa.Column("email", sa.String(255), nullable=False), sa.Column("phone", sa.String(50), nullable=False),
        *_timestamps(), sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]), sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("customer_id", "email", name="uq_contact_customer_email"))
    op.create_index("ix_contacts_tenant_id", "contacts", ["tenant_id"])
    op.create_index("ix_contacts_customer_id", "contacts", ["customer_id"])

    op.create_table("leads",
        sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("customer_id", sa.String(36)), sa.Column("company", sa.String(200), nullable=False),
        sa.Column("normalized_company", sa.String(200), nullable=False), sa.Column("contact_name", sa.String(100), nullable=False), sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("source", sa.String(50), nullable=False), sa.Column("stage", sa.String(30), nullable=False), sa.Column("owner_user_id", sa.String(36), nullable=False),
        *_timestamps(), sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]), sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]), sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("tenant_id", "normalized_company", "contact_email", name="uq_lead_tenant_company_email"))
    for name, column in [("ix_leads_tenant_id", "tenant_id"), ("ix_leads_customer_id", "customer_id"), ("ix_leads_owner_user_id", "owner_user_id")]:
        op.create_index(name, "leads", [column])

    op.create_table("opportunities",
        sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("customer_id", sa.String(36), nullable=False), sa.Column("lead_id", sa.String(36)),
        sa.Column("name", sa.String(200), nullable=False), sa.Column("amount_cents", sa.Integer(), nullable=False), sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("expected_close_date", sa.Date()), sa.Column("owner_user_id", sa.String(36)), *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]), sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]), sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]), sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]), sa.PrimaryKeyConstraint("id"))
    for name, column in [("ix_opportunities_tenant_id", "tenant_id"), ("ix_opportunities_customer_id", "customer_id"), ("ix_opportunities_lead_id", "lead_id"), ("ix_opportunities_owner_user_id", "owner_user_id")]:
        op.create_index(name, "opportunities", [column])

    op.create_table("follow_up_tasks",
        sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("customer_id", sa.String(36)), sa.Column("lead_id", sa.String(36)), sa.Column("opportunity_id", sa.String(36)),
        sa.Column("title", sa.String(200), nullable=False), sa.Column("due_date", sa.Date(), nullable=False), sa.Column("assignee_user_id", sa.String(36), nullable=False), sa.Column("created_by_user_id", sa.String(36), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        *_timestamps(), sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]), sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]), sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]), sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]), sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"]), sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]), sa.PrimaryKeyConstraint("id"))
    for name, column in [("ix_follow_up_tasks_tenant_id", "tenant_id"), ("ix_follow_up_tasks_customer_id", "customer_id"), ("ix_follow_up_tasks_lead_id", "lead_id"), ("ix_follow_up_tasks_opportunity_id", "opportunity_id"), ("ix_follow_up_tasks_assignee_user_id", "assignee_user_id"), ("ix_follow_up_tasks_created_by_user_id", "created_by_user_id")]:
        op.create_index(name, "follow_up_tasks", [column])

    op.create_table("action_drafts",
        sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("actor_user_id", sa.String(36), nullable=False), sa.Column("action", sa.String(50), nullable=False),
        sa.Column("params_json", sa.JSON(), nullable=False), sa.Column("summary", sa.Text(), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("expires_at", sa.DateTime(), nullable=False),
        *_timestamps(), sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]), sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_action_drafts_tenant_id", "action_drafts", ["tenant_id"])
    op.create_index("ix_action_drafts_actor_user_id", "action_drafts", ["actor_user_id"])
    op.create_index("ix_action_drafts_status", "action_drafts", ["status"])

    op.create_table("audit_logs",
        sa.Column("tenant_id", sa.String(36), nullable=False), sa.Column("actor_user_id", sa.String(36), nullable=False), sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False), sa.Column("entity_id", sa.String(36)), sa.Column("before_json", sa.JSON()), sa.Column("after_json", sa.JSON()), sa.Column("result_json", sa.JSON()),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("error_code", sa.String(50)), sa.Column("request_id", sa.String(100)), sa.Column("idempotency_key", sa.String(100)),
        *_timestamps(), sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]), sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_audit_tenant_idempotency"))
    for name, column in [("ix_audit_logs_tenant_id", "tenant_id"), ("ix_audit_logs_actor_user_id", "actor_user_id"), ("ix_audit_logs_entity_id", "entity_id")]:
        op.create_index(name, "audit_logs", [column])


def downgrade() -> None:
    for table in ["audit_logs", "action_drafts", "follow_up_tasks", "opportunities", "leads", "contacts", "customers"]:
        op.drop_table(table)
