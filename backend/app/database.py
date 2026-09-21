"""Database engine, session factory and FastAPI session dependency."""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

if settings.is_sqlite:
    # SQLite (used by the test-suite) does not support connection pooling
    # options and needs ``check_same_thread`` disabled for TestClient usage.
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        echo=settings.db_echo,
    )
else:
    engine = create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,
        echo=settings.db_echo,
    )

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and guarantee it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
