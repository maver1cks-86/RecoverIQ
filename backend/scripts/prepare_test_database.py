"""Create an isolated PostgreSQL database for the RecoverIQ test suite."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import settings


def main() -> None:
    source = make_url(settings.DATABASE_URL)
    test_name = f"{source.database}_test"
    if not test_name.endswith("_test"):
        raise RuntimeError("Refusing to create a database without the _test suffix")

    admin_url = source.set(database="postgres")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": test_name},
        )
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{test_name}"'))
    print(source.set(database=test_name).render_as_string(hide_password=True))


if __name__ == "__main__":
    main()
