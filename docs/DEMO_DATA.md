# Demo and Evaluation Data

RecoverIQ uses synthetic data because historical merchant recovery data is not bundled with the proof of concept. Synthetic records encode conditional relationships among payment amount/method/failure, customer payment history, behavioral response rates, selected action, and simulated outcome. Generation and splitting are deterministic.

## Frozen model dataset

- Generated: 50,000 records
- Train: 32,000
- Validation: 8,000
- Frozen test: 10,000
- Split seed: 42

Normal application startup does not regenerate these files. Model features are declared in `backend/app/ml/features.py`; outcome-only fields (`true_recovery_probability`, `recovered_amount`, `recovery_time_hours`), costs, and identifier columns are explicitly excluded. Training selects only `MODEL_FEATURES`. The experimental T-learner uses its separate `UPLIFT_FEATURES` allow-list and is not the active champion decision path.

Rebuild the offline pipeline deliberately from the repository root:

```text
python scripts/generate_dateset.py
python scripts/split_dataset.py
python scripts/train_recovery_model.py
python scripts/evaluate_strategies.py
```

This rewrites generated/model/evaluation artifacts; do not run it merely to start the app. The checked summary is `artifacts/evaluation/frozen_evaluation_summary.json`.

## Database fixtures

Bootstrap a migrated database and an idempotent normal plan:

```text
python backend/scripts/bootstrap_demo.py
```

Add the deterministic portfolio trade-off:

```text
python backend/scripts/bootstrap_demo.py --include-tradeoff
```

Or create it directly:

```text
python backend/scripts/create_portfolio_tradeoff_demo.py
```

Create a fresh, unexecuted Payment Link plan:

```text
python backend/scripts/create_payment_link_execution_demo.py
```

The trade-off fixture is idempotent. The execution fixture intentionally creates fresh records every time. Neither script executes provider actions. Database-generated IDs differ by installation; always use the IDs printed by the command rather than expecting local examples such as 122 or 125.
