"""Database connections and initialization helpers."""

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import config
from app.models import Base

# Engine configuration.
engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite.
)

# Session factory.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create the local data directory and database tables."""
    os.makedirs("data", exist_ok=True)

    Base.metadata.create_all(bind=engine)
    print("Database initialized.")


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session for FastAPI dependencies.

    Yields:
        Session: A database session that is automatically closed when the
        dependency scope finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
