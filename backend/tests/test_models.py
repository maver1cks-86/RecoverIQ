from collections.abc import Generator
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import engine
from app.decision.actions import RecoveryAction
from app.models import (
    Customer,
    Intervention,
    Merchant,
    MerchantPolicy,
    Outcome,
    Payment,
    RecoveryDecision,
)
from app.models.enums import InterventionStatus, PaymentStatus, PolicyStatus


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def test_initial_model_relationships_and_money_round_trip(
    db_session: Session,
) -> None:
    merchant = Merchant(name="Phase 8 Test Merchant")
    customer = Customer(
        merchant=merchant,
        external_customer_id="phase-8-customer",
        successful_payments=2,
        failed_payments=1,
        previous_recoveries=1,
        avg_transaction_value=Decimal("1250.55"),
    )
    payment = Payment(
        merchant=merchant,
        customer=customer,
        razorpay_payment_id=None,
        amount=Decimal("1499.99"),
        currency="INR",
        payment_method="card",
        status=PaymentStatus.FAILED,
        failure_code="TEMPORARY_BANK_FAILURE",
        attempt_count=1,
    )
    policy = MerchantPolicy(
        merchant=merchant,
        max_retries=3,
        max_contacts=2,
        max_incentive=Decimal("100.00"),
        incentive_budget=Decimal("5000.00"),
        minimum_margin=Decimal("50.00"),
        human_approval_amount=Decimal("10000.00"),
    )
    decision = RecoveryDecision(
        payment=payment,
        selected_action=RecoveryAction.DO_NOTHING,
        predicted_probability=0.12,
        expected_value=Decimal("123.45"),
        policy_status=PolicyStatus.ALLOWED,
        model_version=None,
    )
    intervention = Intervention(
        decision=decision,
        action_type=RecoveryAction.DO_NOTHING,
        status=InterventionStatus.PLANNED,
        intervention_cost=Decimal("0.00"),
        incentive_cost=Decimal("0.00"),
    )
    outcome = Outcome(
        intervention=intervention,
        recovered=False,
        recovered_amount=Decimal("0.00"),
        recovery_time_hours=None,
    )

    db_session.add(merchant)
    db_session.flush()
    merchant_id = merchant.id
    db_session.expire_all()

    stored_merchant = db_session.scalar(
        select(Merchant).where(Merchant.id == merchant_id)
    )

    assert stored_merchant is not None
    assert stored_merchant.customers[0].merchant is stored_merchant
    assert stored_merchant.payments[0].merchant is stored_merchant
    assert stored_merchant.policy is not None
    assert stored_merchant.policy.merchant is stored_merchant

    stored_payment = stored_merchant.payments[0]
    assert stored_payment.customer is stored_merchant.customers[0]
    assert stored_payment.amount == Decimal("1499.99")
    assert stored_payment.customer.avg_transaction_value == Decimal("1250.55")

    stored_decision = stored_payment.recovery_decisions[0]
    assert stored_decision.payment is stored_payment
    assert stored_decision.selected_action is RecoveryAction.DO_NOTHING
    assert stored_decision.expected_value == Decimal("123.45")

    stored_intervention = stored_decision.interventions[0]
    assert stored_intervention.decision is stored_decision
    assert stored_intervention.action_type is RecoveryAction.DO_NOTHING
    assert stored_intervention.intervention_cost == Decimal("0.00")

    stored_outcome = stored_intervention.outcome
    assert stored_outcome is not None
    assert stored_outcome.intervention is stored_intervention
    assert stored_outcome.recovered_amount == Decimal("0.00")
