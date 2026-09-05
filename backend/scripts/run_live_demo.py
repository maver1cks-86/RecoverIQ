from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
from pathlib import Path
import sys
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import joinedload


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings
from app.database import SessionLocal
from app.integrations.razorpay.client import RazorpayClient
from app.models.decision import RecoveryDecision
from app.models.enums import InterventionStatus, PaymentStatus
from app.models.intervention import Intervention
from app.models.payment import Payment
from app.models.recovery_batch import OptimizationAssignment
from app.models.webhook_event import WebhookEvent
from app.schemas.optimization import OptimizationConstraintsRequest
from app.services.recovery_batch_service import create_demo_batch, plan_batch
from app.tasks.batch_tasks import execute_recovery_assignment_task


def require_test_mode() -> None:
    if settings.RAZORPAY_MODE.lower() != "test":
        raise RuntimeError("RAZORPAY_MODE must be 'test' for the live demo.")

    if not settings.RAZORPAY_KEY_ID.startswith("rzp_test_"):
        raise RuntimeError(
            "Refusing to run without a Razorpay Test Mode key."
        )

    if not settings.RAZORPAY_KEY_SECRET:
        raise RuntimeError("Razorpay Test Mode credentials are incomplete.")


def print_chain() -> None:
    print()
    print("RECOVERIQ LIVE RAZORPAY TEST-MODE DEMO")
    print("=" * 72)
    print(
        "Failed Payments -> ML/Economics/Policy -> MILP -> persisted assignment "
        "-> LangGraph -> PAYMENT_LINK "
        "-> Razorpay -> user pays -> webhook -> Celery -> Payment RECOVERED"
    )
    print()


async def fetch_payment_link_url(provider_action_id: str) -> str | None:
    payment_link = await RazorpayClient().fetch_payment_link(
        provider_action_id
    )
    return payment_link.short_url


def run_demo() -> int:
    require_test_mode()
    print_chain()

    with SessionLocal() as db:
        batch = create_demo_batch(
            db,
            20,
            reference_id=f"phase27-live-{uuid4().hex}",
        )
        plan = plan_batch(
            db,
            batch.id,
            OptimizationConstraintsRequest(
                enabled_actions=["PAYMENT_LINK", "DO_NOTHING"],
            ),
        )
        assignment = db.scalar(
            select(OptimizationAssignment)
            .where(
                OptimizationAssignment.plan_id == plan.id,
                OptimizationAssignment.selected_action == "PAYMENT_LINK",
            )
            .order_by(OptimizationAssignment.id)
        )
        if assignment is None:
            print("The optimizer selected no profitable PAYMENT_LINK assignment.")
            print("LIVE DEMO STOPPED HONESTLY — no provider action was created.")
            return 0
        assignment_id = assignment.id
        payment_id = assignment.payment_id
        amount = assignment.payment.amount

    print(f"Created and planned batch: {batch.id}, plan v{plan.version}")
    print(f"Naturally selected persisted PAYMENT_LINK assignment: {assignment_id}")
    print(f"Payment: {payment_id}; amount: INR {amount}")
    print("Executing that persisted assignment through LangGraph...")
    state = execute_recovery_assignment_task.run(assignment_id)
    selected_action = "PAYMENT_LINK"

    print("DECISION AND ORCHESTRATION RESULT")
    print("-" * 72)
    print(f"Payment ID: {payment_id}")
    print(f"Optimization assignment ID: {assignment_id}")
    print(f"Selected action: {selected_action}")
    print(f"Execution status: {state.get('status')}")

    provider_action_id = state.get("provider_action_id")
    if not provider_action_id:
        print("Provider action ID: unavailable")
        print("LIVE DEMO FAILED — Razorpay did not return a Payment Link ID.")
        return 1

    payment_url = asyncio.run(fetch_payment_link_url(provider_action_id))

    print("Provider: razorpay")
    print(f"Provider action ID: {provider_action_id}")
    print(f"Razorpay Payment Link URL: {payment_url or 'unavailable'}")
    print()
    print("NEXT STEPS")
    print("1. Open and pay the URL using Razorpay Test Mode payment details.")
    print("2. Let Razorpay deliver the webhook through the public tunnel.")
    print("3. Let the Celery worker process the persisted webhook event.")
    print(
        "4. Verify the complete chain with: "
        f"python backend/scripts/run_live_demo.py --verify {payment_id}"
    )
    print()
    print("Payment Link created. Payment was NOT completed automatically.")
    return 0


def _payment_link_id(payload: dict) -> str | None:
    payment_link = payload.get("payment_link")
    if not isinstance(payment_link, dict):
        return None
    entity = payment_link.get("entity")
    if not isinstance(entity, dict):
        return None
    value = entity.get("id")
    return value if isinstance(value, str) else None


def latest_webhook_status(
    db,
    provider_action_id: str | None,
) -> str | None:
    if not provider_action_id:
        return None

    events = db.scalars(
        select(WebhookEvent)
        .where(WebhookEvent.provider == "razorpay")
        .order_by(WebhookEvent.received_at.desc(), WebhookEvent.id.desc())
    )
    for event in events:
        if _payment_link_id(event.payload) == provider_action_id:
            return event.status
    return None


def verify_demo(payment_id: int) -> int:
    print_chain()
    print(f"Verifying payment ID: {payment_id}")

    with SessionLocal() as db:
        payment = db.get(Payment, payment_id)
        if payment is None:
            print(f"ERROR: Payment {payment_id} was not found.")
            return 1

        intervention = db.scalar(
            select(Intervention)
            .join(RecoveryDecision)
            .options(joinedload(Intervention.outcome))
            .where(RecoveryDecision.payment_id == payment_id)
            .order_by(Intervention.id.desc())
        )
        outcome = intervention.outcome if intervention is not None else None
        webhook_status = latest_webhook_status(
            db,
            intervention.provider_action_id if intervention is not None else None,
        )

        payment_status = payment.status.value
        intervention_status = (
            intervention.status.value if intervention is not None else None
        )
        provider_status = (
            intervention.provider_status if intervention is not None else None
        )
        recovered = outcome.recovered if outcome is not None else None
        recovered_amount = (
            outcome.recovered_amount if outcome is not None else None
        )

    print()
    print("POST-PAYMENT STATE")
    print("-" * 72)
    print(f"Payment.status: {payment_status}")
    print(f"Intervention.status: {intervention_status}")
    print(f"provider_status: {provider_status}")
    print(f"Outcome.recovered: {recovered}")
    print(f"Outcome.recovered_amount: {recovered_amount}")
    print(f"Latest relevant WebhookEvent.status: {webhook_status}")

    succeeded = all(
        [
            payment_status == PaymentStatus.RECOVERED.value,
            intervention_status == InterventionStatus.SUCCEEDED.value,
            provider_status == "paid",
            recovered is True,
            webhook_status == "processed",
        ]
    )

    print()
    if succeeded:
        print("LIVE DEMO SUCCESS")
        return 0

    print("LIVE DEMO NOT COMPLETE")
    print(
        "The full Razorpay -> webhook -> Celery recovery chain has not yet "
        "reached every required terminal state."
    )
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run or verify the RecoverIQ Razorpay Test Mode live demo."
    )
    parser.add_argument(
        "--verify",
        type=int,
        metavar="PAYMENT_ID",
        help="Verify the post-payment state for an earlier demo payment.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.verify is not None:
            return verify_demo(args.verify)
        return run_demo()
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
