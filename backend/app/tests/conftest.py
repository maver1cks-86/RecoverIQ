"""Keep integration tests isolated from local/demo application data."""

import os

from sqlalchemy.engine import make_url


# Pytest imports this file before collecting test modules.  Every application
# module therefore binds its engine to the dedicated test database, never to
# the developer/demo database configured in backend/.env.
default = "postgresql://recoveriq:recoveriq@localhost:5433/recoveriq_test"
candidate = os.environ.get("RECOVERIQ_TEST_DATABASE_URL")
inherited = os.environ.get("DATABASE_URL")
if candidate is None and inherited:
    database_name = make_url(inherited).database or ""
    candidate = inherited if database_name.endswith("_test") else None
selected = candidate or default
if not (make_url(selected).database or "").endswith("_test"):
    raise RuntimeError("Refusing to run destructive integration tests outside a _test database")
os.environ["DATABASE_URL"] = selected
