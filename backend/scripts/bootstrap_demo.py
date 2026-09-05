"""Migrate a local database and create non-executing RecoverIQ demo plans."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal, engine  # noqa: E402
from app.models.recovery_batch import OptimizationAssignment  # noqa: E402
from app.schemas.optimization import OptimizationConstraintsRequest  # noqa: E402
from app.services.recovery_batch_service import create_demo_batch, plan_batch  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a safe local RecoverIQ demo database.")
    parser.add_argument(
        "--include-tradeoff",
        action="store_true",
        help="Also create the deterministic local-vs-portfolio fixture.",
    )
    args = parser.parse_args()

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    print("DATABASE_CONNECTED")

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        check=True,
    )
    print("MIGRATIONS_CURRENT")

    with SessionLocal() as db:
        batch = create_demo_batch(
            db,
            payment_count=20,
            reference_id="recoveriq-bootstrap-normal-demo-v1",
        )
        plan = plan_batch(db, batch.id, OptimizationConstraintsRequest())
        assignment_count = len(
            db.scalars(
                select(OptimizationAssignment).where(OptimizationAssignment.plan_id == plan.id)
            ).all()
        )
        print(f"NORMAL_DEMO_BATCH_ID={batch.id}")
        print(f"NORMAL_DEMO_ASSIGNMENTS={assignment_count}")

    if args.include_tradeoff:
        subprocess.run(
            [sys.executable, str(BACKEND_ROOT / "scripts" / "create_portfolio_tradeoff_demo.py")],
            cwd=BACKEND_ROOT,
            check=True,
        )

    print("NO_PROVIDER_ACTIONS_EXECUTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
