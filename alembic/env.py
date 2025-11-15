import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Read DATABASE_URL from environment
database_url = os.getenv("DATABASE_URL", "")
if database_url:
    # Ensure postgres URLs use psycopg2 driver
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    config.set_main_option("sqlalchemy.url", database_url)
else:
    # If no DATABASE_URL, try to get from alembic.ini (for backward compatibility)
    # But in production, DATABASE_URL should always be set
    pass

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# Import all models to ensure they're registered
from app import db  # noqa: E402
from app import User, Customer, Vehicle, Item, Invoice, InvoiceItem, Waybill, Settings, AuditLog  # noqa: E402, F401

target_metadata = db.Model.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

