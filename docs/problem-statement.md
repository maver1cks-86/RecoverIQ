# Problem statement

Merchants may have many failed or at-risk payments at once, while retry,
messaging, incentive, and operational capacity are limited. RecoverIQ evaluates
the eligible recovery actions for each payment and allocates those scarce
resources across the portfolio.

The objective is to maximize **incremental net revenue recovered**, not merely
payment success or model accuracy. Prediction estimates recovery likelihood;
the economic layer prices each option; deterministic policy rules constrain it;
and the optimizer chooses a feasible portfolio allocation. Razorpay Test Mode
is used only as the payment-side execution and webhook integration in this
repository.

See the [README](../README.md) for product positioning, evidence boundaries,
and the complete system walkthrough.
