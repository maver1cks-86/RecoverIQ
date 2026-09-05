"""Migrate and test only against the dedicated RecoverIQ test database."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402


def main() -> int:
    test_url = make_url(settings.DATABASE_URL).set(
        database=f"{make_url(settings.DATABASE_URL).database}_test"
    )
    if not test_url.database or not test_url.database.endswith("_test"):
        raise RuntimeError("Refusing to run destructive tests outside a _test database")

    env = os.environ.copy()
    env["DATABASE_URL"] = test_url.render_as_string(hide_password=False)
    # The database-name guard above makes this destructive reset test-only.
    engine = create_engine(test_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=True,
    )
    return subprocess.run(
        [sys.executable, "-m", "pytest", "app/tests", "tests", "-q"],
        cwd=ROOT,
        env=env,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
