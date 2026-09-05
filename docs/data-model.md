# Data model

The principal persisted lifecycle is:

`Merchant -> Customer -> Payment -> RecoveryDecision -> Intervention -> Outcome`

Recovery batches group payments for portfolio planning. Decisions retain the
selected action, probability, expected value, model version, and policy state.
Interventions retain execution/provider state, while outcomes retain observed
recovery. Webhook events are stored separately for signature-validated,
idempotent reconciliation and audit evidence.

Financial columns use SQL numeric/decimal types. Database evolution is managed
with Alembic; run `python -m alembic upgrade head` from `backend/` rather than
creating tables manually.
