# Hard-coded Data and Public-Submission Audit

## Scope

The audit searched runtime backend and frontend code, tests, scripts, configuration, migrations, documentation, generated data, and Git-tracked files for fixed database identifiers, money/results, action assignments, provider identifiers, URLs and ports, credentials, tunnel URLs, absolute personal paths, fake provider outcomes, and frontend values presented as live results.

## Classification

| Category | Findings | Disposition |
|---|---|---|
| A — legitimate constants/config | Recovery action enum, synthetic intervention costs, deterministic seeds, local Docker ports, safe localhost defaults, supported webhook events, solver defaults | Retained and documented. Runtime credentials come from environment variables. |
| B — synthetic deterministic fixtures | Twenty-payment generator seed, portfolio trade-off constraints, payment-link execution constraints, frozen synthetic evaluation metrics | Retained only in clearly named scripts/artifacts. Scripts print generated IDs; runtime code does not depend on local IDs. |
| C — test-only fixtures | Fake `plink_...` IDs, test webhook secrets, test database credentials matching Docker Compose | Retained under tests. They are non-production values and the suite is guarded to use a database ending in `_test`. |
| D — unsafe hardcoding | A local LLM credential was present in the working copy of `.env.example`; a cancellation utility targeted one fixed provider link ID | Fixed. The example now has placeholders only. The cancellation utility now requires an explicit CLI argument. |
| E — requires explanation | Frozen monetary results and local demo IDs; localhost URLs; Docker development password | Documented as synthetic/local-only. Batch/payment IDs are examples, never runtime dependencies. Docker credentials are deliberately local development defaults and must be replaced for deployment. |

## Intentional deterministic values

- `create_portfolio_tradeoff_demo.py` uses a stable reference and deterministic synthetic generator so it is idempotent and reproducible.
- `create_payment_link_execution_demo.py` uses the same deterministic payment characteristics but a unique reference every run so a paid historical fixture is never reused.
- `INTERVENTION_COSTS` and the 5%-capped incentive cost are synthetic business assumptions used consistently by the economics layer.
- Frozen evaluation results live in data artifacts and `artifacts/evaluation/frozen_evaluation_summary.json`; they are labeled offline synthetic evaluation, not observed provider outcomes.
- Test IDs and credentials are confined to test files.

## Safety conclusions

The React UI reads optimizer, batch, outcome, intervention, and audit values from backend APIs. No UI component is keyed to batches 122/125 or payments 1202/1217/1277. Runtime decision logic contains no forced demo assignment. Only `PAYMENT_LINK` reaches the Razorpay adapter; unsupported actions stop at manual/no-action states.

The exposed working-copy LLM credential was not present in `HEAD`, but it should still be revoked because it was stored outside the intended secret file.
