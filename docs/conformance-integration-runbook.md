# RecoverIQ conformance integration rehearsal

This runbook exercises the live database-backed path. Razorpay must remain in
Test Mode. It never completes a payment automatically and never prints secrets.

## 1. Start infrastructure and apply the schema

From the repository root:

```powershell
docker compose up -d postgres redis
.\backend\.venv\Scripts\Activate.ps1
Set-Location backend
python -m alembic upgrade head
Invoke-RestMethod http://127.0.0.1:8000/health/database
```

Run these long-lived processes in separate PowerShell terminals:

```powershell
Set-Location backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

```powershell
Set-Location backend
.\.venv\Scripts\Activate.ps1
python -m celery -A app.celery_app:celery_app worker --loglevel=info --pool=solo
```

```powershell
Set-Location frontend
npm run dev
```

Expose port 8000 with the approved tunnel and configure the exact public URL
`https://<host>/webhooks/razorpay` in the Razorpay Test Mode dashboard. The
dashboard webhook secret and `RAZORPAY_WEBHOOK_SECRET` must match.

## 2. Prove a portfolio tradeoff

```powershell
$api = "http://127.0.0.1:8000"
$batch = Invoke-RestMethod -Method Post -Uri "$api/recovery-batches/demo" -ContentType "application/json" -Body '{"payment_count":20}'
$batchId = $batch.id
$batch.revenue_at_risk

$tight = @{
  constraints = @{
    total_budget = 20
    incentive_budget = 0
    max_retries = 1
    max_contacts = 1
    max_whatsapp = 0
    max_incentive_actions = 0
    max_human_escalations = 0
    solver_timeout_ms = 30000
  }
} | ConvertTo-Json -Depth 4

Invoke-RestMethod -Method Post -Uri "$api/recovery-batches/$batchId/optimize" -ContentType "application/json" -Body $tight
do { Start-Sleep 1; $state = Invoke-RestMethod "$api/recovery-batches/$batchId" } while ($state.status -in @("QUEUED", "SCORING", "OPTIMIZING"))
$summary = Invoke-RestMethod "$api/recovery-batches/$batchId/summary"
$assignments = Invoke-RestMethod "$api/recovery-batches/$batchId/assignments?page=1&page_size=100"
$summary | Select-Object observed_recovered_amount, estimated_incremental_value, plan_version, constraint_utilization
$assignments.items | Where-Object selected_rank -gt 1 | Select-Object payment_id, standalone_best_action, selected_action, selected_rank, alternatives
```

Expected: revenue at risk is positive, observed recovery is zero before a
provider-confirmed outcome, every resource use is within its limit, and the
deterministic tight plan contains at least one rank greater than one. Re-submit
different constraints before execution to create plan version 2; the original
plan and snapshot remain immutable.

## 3. Create an execution-capable plan without forcing an outcome

```powershell
$executionBatch = Invoke-RestMethod -Method Post -Uri "$api/recovery-batches/demo" -ContentType "application/json" -Body '{"payment_count":20}'
$executionId = $executionBatch.id
$executionPlan = @{
  constraints = @{
    total_budget = 2000
    incentive_budget = 0
    max_retries = 0
    max_contacts = 20
    max_whatsapp = 0
    max_incentive_actions = 0
    max_human_escalations = 0
    solver_timeout_ms = 30000
    enabled_actions = @("PAYMENT_LINK", "DO_NOTHING")
  }
} | ConvertTo-Json -Depth 4

Invoke-RestMethod -Method Post -Uri "$api/recovery-batches/$executionId/optimize" -ContentType "application/json" -Body $executionPlan
do { Start-Sleep 1; $state = Invoke-RestMethod "$api/recovery-batches/$executionId" } while ($state.status -in @("QUEUED", "SCORING", "OPTIMIZING"))
$executionAssignments = Invoke-RestMethod "$api/recovery-batches/$executionId/assignments?page=1&page_size=100&action=PAYMENT_LINK"
$selected = $executionAssignments.items | Select-Object -First 1
$selected | Select-Object id, payment_id, selected_action, selected_rank, policy_status
```

Stop if `$selected` is empty; that honestly means PAYMENT_LINK was not
economically positive for this generated portfolio. Do not edit an assignment
or fake the selection.

```powershell
Invoke-RestMethod -Method Post -Uri "$api/recovery-batches/$executionId/execute"
do { Start-Sleep 1; $page = Invoke-RestMethod "$api/recovery-batches/$executionId/assignments?page=1&page_size=100&action=PAYMENT_LINK"; $selected = $page.items | Where-Object id -eq $selected.id } while ($selected.execution_status -in @("QUEUED", "EXECUTING"))
$selected | Select-Object selected_action, execution_status, provider, provider_action_id, payment_url
```

The Celery log must show the assignment ID. The row must still say
`PAYMENT_LINK`; a provider ID and Test Mode URL indicate creation, not payment.

## 4. Complete and observe the Test Mode payment

Open `$selected.payment_url` and pay it with Razorpay Test Mode payment details.
After the signed webhook is delivered and Celery processes it:

```powershell
$paymentId = $selected.payment_id
Invoke-RestMethod "$api/audit/payments/$paymentId" | ConvertTo-Json -Depth 10
Invoke-RestMethod "$api/recovery-batches/$executionId/summary" | Select-Object observed_recovered_amount, execution_counts
$copilotBody = @{ message = "Explain this persisted recovery and outcome"; context = @{ payment_id = $paymentId; page = "recovery-batch" } } | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method Post -Uri "$api/copilot/chat" -ContentType "application/json" -Body $copilotBody
```

Required persisted terminal chain: `Payment=RECOVERED`,
`Intervention=SUCCEEDED`, `Outcome.recovered=true`, provider status `paid`, and
processed webhook evidence. Observed recovered amount must rise by the provider
confirmed recovered amount, not by the estimated incremental value.

Finally, call the execute endpoint again. It must return HTTP 409 because the
batch is no longer READY. Use Razorpay's Test Mode webhook replay for the same
event ID; the endpoint must return `duplicate`, and observed recovered amount
must remain unchanged.

## 5. Automated clean check

```powershell
Set-Location backend
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python -m pytest app\tests -q
Set-Location ..\frontend
npm run build
```
