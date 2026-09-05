# Razorpay Test Mode Reviewer Guide

RecoverIQ currently executes only `PAYMENT_LINK` through a real external adapter. All demonstrations must use Razorpay **Test Mode**. Other planned actions are optimization/manual concepts and do not call fake providers.

## Configure

Copy `backend/.env.example` to `backend/.env` and set your own:

- `DATABASE_URL` and `REDIS_URL`
- `RAZORPAY_KEY_ID` beginning with `rzp_test_`
- `RAZORPAY_KEY_SECRET`
- `RAZORPAY_WEBHOOK_SECRET`
- `RAZORPAY_MODE=test`

Start PostgreSQL, Redis, FastAPI, the Celery worker, and the React frontend using the README. If Razorpay cannot reach localhost, expose port 8000 using a tunnel you trust. In the Razorpay Test Mode dashboard configure the public URL ending in:

```text
/webhooks/razorpay
```

Subscribe to `payment_link.paid`. Use the exact same webhook signing secret in Razorpay and `backend/.env`. Never commit credentials or a private tunnel URL.

## Create an unexecuted recording plan

From the repository root:

```text
backend/.venv/Scripts/python.exe backend/scripts/create_payment_link_execution_demo.py
```

On macOS/Linux use `backend/.venv/bin/python`. The command prints a fresh Batch ID and Payment ID. It runs synthetic ingestion, action-conditioned scoring, economics, policy, and MILP planning, but creates no provider action.

## Browser flow

1. Open Recovery Batches and load the printed Batch ID.
2. Confirm `READY`, observed recovery ₹0, one `PAYMENT_LINK`, and no provider ID.
3. Inspect the printed payment and confirm `FAILED`, `PLANNED`, policy `ALLOWED`, and positive incremental value.
4. Click **Execute Approved Plan** once.
5. Observe `QUEUED → EXECUTING → AWAITING_PAYMENT` without refreshing.
6. Open the generated Razorpay Test Mode Payment Link.
7. Complete a Test Mode payment.
8. Return to RecoverIQ and wait for the signed webhook to close the loop.
9. Confirm `RECOVERED`, provider status `paid`, and observed recovered amount.
10. Open Audit Trail for the payment.

Creating a Payment Link is not a successful recovery. Success is confirmed only after `payment_link.paid` passes signature validation and its outcome is committed.

## Implemented reliability controls

- The execute endpoint returns after queueing; Celery runs provider execution.
- A batch must be `READY`, and subsequent execute attempts are rejected.
- Decisions/interventions are reused for the stable optimization assignment.
- Razorpay references derive from a stable assignment idempotency key.
- The webhook signature is verified against the raw request body before parsing.
- Provider event IDs are unique in PostgreSQL; terminal duplicates are acknowledged without reapplying state.
- Stale lower-precedence events cannot reverse a successful recovery.
- Database commits occur before Redis Pub/Sub notifications. WebSocket failure cannot roll back provider/webhook state.
- The browser refetches PostgreSQL-backed APIs on events and uses bounded polling as fallback.

State progression:

```text
FAILED → PLANNED → QUEUED → EXECUTING → AWAITING_PAYMENT
                                               ↓
                                  payment_link.paid webhook
                                               ↓
                                           RECOVERED
```
