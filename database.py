import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.engine.url import make_url

db = SQLAlchemy()

DATABASE_READY = False
engine = None
SessionLocal = None


def configure_database(app):
    """
    Configure SQLAlchemy to use PostgreSQL via DATABASE_URL env var.
    Uses connection pooling for production.

    Returns:
        bool: True when configuration succeeded, False when DATABASE_URL missing/invalid
    """
    global DATABASE_READY, engine, SessionLocal

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

    # Create engine with pooling
    engine = create_engine(
        str(url),
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_pre_ping=True,
    )

    # Create sessionmaker
    SessionLocal = sessionmaker(bind=engine)

    app.config["SQLALCHEMY_DATABASE_URI"] = str(url)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_pre_ping": True,
    }

    db.init_app(app)
    DATABASE_READY = True
    return True


def is_database_ready():
    return DATABASE_READY

