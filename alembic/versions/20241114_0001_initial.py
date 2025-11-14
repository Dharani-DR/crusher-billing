"""initial postgres schema

Revision ID: 20241114_0001
Revises:
Create Date: 2024-11-14 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20241114_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("gst_number", sa.String(length=50)),
        sa.Column("phone", sa.String(length=20)),
        sa.Column("address", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("timezone('utc', now())")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=150), nullable=False, unique=True),
        sa.Column("email", sa.String(length=150)),
        sa.Column("name", sa.String(length=200)),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="user"),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("last_login", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("timezone('utc', now())")),
    )

    op.create_table(
        "vehicles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vehicle_number", sa.String(length=50), nullable=False, unique=True),
        sa.Column("vehicle_type", sa.String(length=50)),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("timezone('utc', now())")),
    )

    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("timezone('utc', now())")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("timezone('utc', now())")),
    )

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_name_tamil", sa.Text(), server_default="ஸ்ரீ தனலட்சுமி புளூ மெட்டல்ஸ்"),
        sa.Column("company_name_english", sa.String(length=200), server_default="Sri Dhanalakshmi Blue Metals"),
        sa.Column(
            "address_tamil",
            sa.Text(),
            server_default="நெமிலி & எண்வரடி அஞ்சல், எண்டியூர்,\nவாணூர் தாலுகா, விழுப்புரம் மாவட்டம்.",
        ),
        sa.Column(
            "address_english",
            sa.Text(),
            server_default="Nemili & Envaradi Post, Endiyur,\nVandur Taluk, Villupuram District.",
        ),
        sa.Column("gstin", sa.String(length=50), server_default="33AUXPR8335C1Z7"),
        sa.Column("phone_numbers", sa.String(length=200), server_default="97883 88823, 97515 31619, 75026 27223"),
        sa.Column("cgst_percent", sa.Float(), server_default="2.5"),
        sa.Column("sgst_percent", sa.Float(), server_default="2.5"),
        sa.Column("from_location", sa.String(length=100), server_default="நெமிலி"),
        sa.Column("sms_provider", sa.String(length=50), server_default="twilio"),
        sa.Column("sms_api_key", sa.String(length=200)),
        sa.Column("sms_api_secret", sa.String(length=200)),
        sa.Column("sms_sender_id", sa.String(length=50)),
        sa.Column("sms_api_url", sa.String(length=500)),
        sa.Column("sms_template", sa.Text()),
        sa.Column("whatsapp_provider", sa.String(length=50), server_default="twilio"),
        sa.Column("whatsapp_sender_number", sa.String(length=20)),
        sa.Column("whatsapp_api_key", sa.String(length=200)),
        sa.Column("whatsapp_api_url", sa.String(length=500)),
        sa.Column("whatsapp_template", sa.Text()),
        sa.Column("auto_send_sms", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("auto_send_whatsapp", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("timezone('utc', now())")),
    )

    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bill_no", sa.String(length=50), nullable=False, unique=True),
        sa.Column("date", sa.DateTime(), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id")),
        sa.Column("subtotal", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cgst", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sgst", sa.Float(), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Float(), nullable=False, server_default="0"),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("timezone('utc', now())")),
        sa.Column("from_location", sa.String(length=100), server_default="நெமிலி"),
        sa.Column("delivery_location", sa.String(length=200)),
        sa.Column("has_waybill", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "invoice_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("item_name", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
    )

    op.create_table(
        "waybills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=False, unique=True),
        sa.Column("driver_name", sa.String(length=200)),
        sa.Column("loading_time", sa.DateTime()),
        sa.Column("unloading_time", sa.DateTime()),
        sa.Column("material_type", sa.String(length=200)),
        sa.Column("vehicle_capacity", sa.String(length=100)),
        sa.Column("delivery_location", sa.String(length=200)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("timezone('utc', now())")),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50)),
        sa.Column("resource_id", sa.Integer()),
        sa.Column("details", sa.Text()),
        sa.Column("ip_address", sa.String(length=50)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("timezone('utc', now())")),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("waybills")
    op.drop_table("invoice_items")
    op.drop_table("invoices")
    op.drop_table("settings")
    op.drop_table("items")
    op.drop_table("vehicles")
    op.drop_table("users")
    op.drop_table("customers")

