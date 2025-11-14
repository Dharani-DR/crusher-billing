import os

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.engine.url import make_url

db = SQLAlchemy()

DATABASE_READY = False


def configure_database(app):
    """
    Configure SQLAlchemy to use PostgreSQL via DATABASE_URL env var.

    Returns:
        bool: True when configuration succeeded, False when DATABASE_URL missing/invalid
    """
    global DATABASE_READY

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        DATABASE_READY = False
        return False

    try:
        url = make_url(database_url)
    except Exception:
        DATABASE_READY = False
        return False

    # Ensure postgres URLs use psycopg2 driver
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg2")

    app.config["SQLALCHEMY_DATABASE_URI"] = str(url)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    }

    db.init_app(app)
    DATABASE_READY = True
    return True


def is_database_ready():
    return DATABASE_READY

