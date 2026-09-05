# Portfolio optimizer

For payment `i` and action `j`, RecoverIQ defines a binary choice `x[i,j]`.
The objective maximizes the sum of each selected action's incremental net value,
subject to exactly one action per payment and configured limits on budget,
contacts, retries, incentives, and human escalation. `DO_NOTHING` remains
feasible.

The implementation uses Google OR-Tools. Model predictions are inputs to the
economic calculation; neither an LLM nor the React client authorizes financial
actions. Policy eligibility and rejection reasons are persisted for audit.

The frozen synthetic evaluation summary is available at
[`artifacts/evaluation/frozen_evaluation_summary.json`](../artifacts/evaluation/frozen_evaluation_summary.json).
