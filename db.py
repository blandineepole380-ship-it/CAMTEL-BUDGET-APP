from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from settings import settings
from models import Base


def _make_engine():
    # Render gives DATABASE_URL like: postgresql://... but SQLAlchemy needs postgresql+psycopg2
    url = settings.database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url, pool_pre_ping=True)


engine = _make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize DB schema.

    SQLAlchemy's `create_all` creates missing tables, but it does NOT alter
    existing tables. If your database already has an older `users` table,
    newer columns like `role` may be missing.

    For this small app we apply a tiny, safe, idempotent migration at startup.
    """

    # Create missing tables first
    Base.metadata.create_all(bind=engine)

    # Lightweight migration for older deployments
    insp = inspect(engine)
    if insp.has_table("users"):
        cols = {c["name"] for c in insp.get_columns("users")}
        if "role" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE users "
                        "ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"
                    )
                )
