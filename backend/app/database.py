from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for future SQLAlchemy domain models."""


def get_db() -> Generator[Session, None, None]:
    """Provide a database session and always close it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> None:
    """Raise a SQLAlchemy error when PostgreSQL is not reachable."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
