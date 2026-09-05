from collections import Counter
from dataclasses import dataclass, field

from ortools.linear_solver import pywraplp

from app.decision.decision_engine import (
    DecisionEngine,
)

from app.policies.engine import (
    PolicyConfig,
)


# ============================================================
# ACTION GROUPS USED FOR PORTFOLIO CAPACITY CONSTRAINTS
# ============================================================

RETRY_ACTIONS = {
    "RETRY_NOW",
    "RETRY_LATER",
}

CUSTOMER_CONTACT_ACTIONS = {
    "WHATSAPP",
    "EMAIL",
    "PAYMENT_LINK",
    "INCENTIVE",
    "HUMAN_ESCALATION",
}


# ============================================================
# INPUT TYPES
# ============================================================


@dataclass(frozen=True)
class PortfolioPayment:
    """
    One payment that needs a recovery decision.
    """

    payment_id: str

    context: dict


@dataclass(frozen=True)
class PortfolioConstraints:
    """
    Merchant-level portfolio constraints.

    None means that a particular constraint
    is not enforced.
    """

    max_total_intervention_spend: float | None = None

    max_incentive_spend: float | None = None

    max_retry_actions: int | None = None

    max_customer_contacts: int | None = None

    max_whatsapp_actions: int | None = None

    max_incentive_actions: int | None = None

    max_human_escalations: int | None = None

    enabled_actions: frozenset[str] | None = None

    solver_time_limit_ms: int = 5000


# ============================================================
# OUTPUT TYPES
# ============================================================


@dataclass(frozen=True)
class OptimizedAssignment:

    payment_id: str

    action: str

    recovery_probability: float

    expected_net_value: float

    incremental_value: float

    intervention_cost: float

    incentive_cost: float


@dataclass(frozen=True)
class PortfolioOptimizationResult:

    status: str

    total_incremental_value: float

    total_expected_net_value: float

    total_intervention_spend: float

    total_incentive_spend: float

    retry_count: int

    customer_contact_count: int

    assignments: list[OptimizedAssignment]

    action_counts: dict[str, int] = field(
        default_factory=dict
    )


# ============================================================
# OPTIMIZER
# ============================================================


class PortfolioOptimizer:

    def __init__(self):

        self.decision_engine = (
            DecisionEngine()
        )

    def optimize(
    self,
    payments: list[PortfolioPayment],
    constraints: PortfolioConstraints,
    policy: PolicyConfig | None = None,
    precomputed_decisions: dict | None = None,
) -> PortfolioOptimizationResult:
        """
        Optimize recovery actions across a portfolio.

        Objective:

            maximize:

            SUM(
                x[payment, action]
                *
                incremental_value[payment, action]
            )

        Subject to:

        - exactly one action per payment
        - intervention budget
        - incentive budget
        - retry capacity
        - contact capacity
        - WhatsApp capacity
        - incentive capacity
        - human escalation capacity

        DO_NOTHING has zero incremental value
        and ensures every payment remains feasible.
        """

        if not payments:
            raise ValueError(
                "Portfolio must contain at least one payment."
            )

        if policy is None:
            policy = PolicyConfig()

        self._validate_constraints(
            constraints
        )

        # ====================================================
        # STEP 1
        # Obtain policy-eligible action values.
        #
        # If precomputed decisions are supplied, reuse them.
        # This is important for portfolio experiments where
        # ML predictions have already been batch-computed.
        #
        # Otherwise, fall back to normal per-payment
        # DecisionEngine evaluation.
        # ====================================================

        evaluated_actions = {}

        for payment in payments:

            payment_id = (
                payment.payment_id
            )

            if (
                precomputed_decisions
                is not None
            ):

                if (
                    payment_id
                    not in precomputed_decisions
                ):
                    raise ValueError(
                        f"Missing precomputed decision "
                        f"for payment {payment_id}."
                    )

                decision = (
                    precomputed_decisions[
                        payment_id
                    ]
                )

            else:

                decision = (
                    self.decision_engine.evaluate(
                        context=payment.context,
                        policy=policy,
                    )
                )

            if not decision.ranked_actions:
                raise ValueError(
                    f"No eligible actions for payment "
                    f"{payment_id}."
                )

            evaluated_actions[
                payment_id
            ] = {
                item.action: item
                for item
                in decision.ranked_actions
                if (
                    constraints.enabled_actions is None
                    or item.action in constraints.enabled_actions
                )
            }

            if "DO_NOTHING" not in evaluated_actions[payment_id]:
                raise ValueError(
                    "DO_NOTHING must remain enabled for every payment."
                )

        # ====================================================
        # STEP 2
        # Create MILP solver.
        # ====================================================

        solver = (
            pywraplp.Solver.CreateSolver(
                "SCIP"
            )
        )

        if solver is None:

            solver = (
                pywraplp.Solver.CreateSolver(
                    "CBC"
                )
            )

        if solver is None:
            raise RuntimeError(
                "No compatible OR-Tools MILP solver "
                "is available."
            )

        solver.SetTimeLimit(
            constraints.solver_time_limit_ms
        )

        # ====================================================
        # STEP 3
        # Create binary variables.
        #
        # x[payment_id, action] = 1
        # if that action is chosen.
        # ====================================================

        variables = {}

        for payment in payments:

            payment_id = (
                payment.payment_id
            )

            actions = (
                evaluated_actions[
                    payment_id
                ]
            )

            for action in actions:

                variable_name = (
                    f"x_{payment_id}_{action}"
                )

                variables[
                    payment_id,
                    action,
                ] = solver.BoolVar(
                    variable_name
                )

        # ====================================================
        # STEP 4
        # Exactly one action per payment.
        # ====================================================

        for payment in payments:

            payment_id = (
                payment.payment_id
            )

            payment_variables = [
                variables[
                    payment_id,
                    action,
                ]
                for action
                in evaluated_actions[
                    payment_id
                ]
            ]

            solver.Add(
                solver.Sum(
                    payment_variables
                )
                == 1
            )

        # ====================================================
        # STEP 5
        # Total intervention spend constraint.
        #
        # Includes:
        # intervention cost + incentive cost.
        # ====================================================

        if (
            constraints.max_total_intervention_spend
            is not None
        ):

            total_spend_terms = []

            for payment in payments:

                payment_id = (
                    payment.payment_id
                )

                for (
                    action,
                    value,
                ) in evaluated_actions[
                    payment_id
                ].items():

                    cost = (
                        value.intervention_cost
                        + value.incentive_cost
                    )

                    total_spend_terms.append(
                        variables[
                            payment_id,
                            action,
                        ]
                        * cost
                    )

            solver.Add(
                solver.Sum(
                    total_spend_terms
                )
                <= constraints
                .max_total_intervention_spend
            )

        # ====================================================
        # STEP 6
        # Incentive budget constraint.
        # ====================================================

        if (
            constraints.max_incentive_spend
            is not None
        ):

            incentive_terms = []

            for payment in payments:

                payment_id = (
                    payment.payment_id
                )

                for (
                    action,
                    value,
                ) in evaluated_actions[
                    payment_id
                ].items():

                    incentive_terms.append(
                        variables[
                            payment_id,
                            action,
                        ]
                        * value.incentive_cost
                    )

            solver.Add(
                solver.Sum(
                    incentive_terms
                )
                <= constraints
                .max_incentive_spend
            )

        # ====================================================
        # STEP 7
        # Retry capacity.
        # ====================================================

        if (
            constraints.max_retry_actions
            is not None
        ):

            retry_variables = []

            for payment in payments:

                payment_id = (
                    payment.payment_id
                )

                for action in RETRY_ACTIONS:

                    variable = variables.get(
                        (
                            payment_id,
                            action,
                        )
                    )

                    if variable is not None:

                        retry_variables.append(
                            variable
                        )

            solver.Add(
                solver.Sum(
                    retry_variables
                )
                <= constraints
                .max_retry_actions
            )

        # ====================================================
        # STEP 8
        # Total customer-contact capacity.
        # ====================================================

        if (
            constraints.max_customer_contacts
            is not None
        ):

            contact_variables = []

            for payment in payments:

                payment_id = (
                    payment.payment_id
                )

                for action in (
                    CUSTOMER_CONTACT_ACTIONS
                ):

                    variable = variables.get(
                        (
                            payment_id,
                            action,
                        )
                    )

                    if variable is not None:

                        contact_variables.append(
                            variable
                        )

            solver.Add(
                solver.Sum(
                    contact_variables
                )
                <= constraints
                .max_customer_contacts
            )

        # ====================================================
        # STEP 9
        # WhatsApp capacity.
        # ====================================================

        if (
            constraints.max_whatsapp_actions
            is not None
        ):

            whatsapp_variables = [
                variables[
                    payment.payment_id,
                    "WHATSAPP",
                ]
                for payment in payments
                if (
                    payment.payment_id,
                    "WHATSAPP",
                )
                in variables
            ]

            solver.Add(
                solver.Sum(
                    whatsapp_variables
                )
                <= constraints
                .max_whatsapp_actions
            )

        # ====================================================
        # STEP 10
        # Number of incentive interventions.
        # ====================================================

        if (
            constraints.max_incentive_actions
            is not None
        ):

            incentive_variables = [
                variables[
                    payment.payment_id,
                    "INCENTIVE",
                ]
                for payment in payments
                if (
                    payment.payment_id,
                    "INCENTIVE",
                )
                in variables
            ]

            solver.Add(
                solver.Sum(
                    incentive_variables
                )
                <= constraints
                .max_incentive_actions
            )

        # ====================================================
        # STEP 11
        # Human-agent capacity.
        # ====================================================

        if (
            constraints.max_human_escalations
            is not None
        ):

            human_variables = [
                variables[
                    payment.payment_id,
                    "HUMAN_ESCALATION",
                ]
                for payment in payments
                if (
                    payment.payment_id,
                    "HUMAN_ESCALATION",
                )
                in variables
            ]

            solver.Add(
                solver.Sum(
                    human_variables
                )
                <= constraints
                .max_human_escalations
            )

        # ====================================================
        # STEP 12
        # Objective:
        #
        # MAXIMIZE PORTFOLIO INCREMENTAL VALUE.
        # ====================================================

        objective_terms = []

        for payment in payments:

            payment_id = (
                payment.payment_id
            )

            for (
                action,
                value,
            ) in evaluated_actions[
                payment_id
            ].items():

                objective_terms.append(
                    variables[
                        payment_id,
                        action,
                    ]
                    * value.incremental_value
                )

        solver.Maximize(
            solver.Sum(
                objective_terms
            )
        )

        # ====================================================
        # STEP 13
        # Solve.
        # ====================================================

        status = (
            solver.Solve()
        )

        status_name = (
            self._status_name(
                status
            )
        )

        if status not in {
            pywraplp.Solver.OPTIMAL,
            pywraplp.Solver.FEASIBLE,
        }:

            raise RuntimeError(
                "Portfolio optimization failed "
                f"with status: {status_name}"
            )

        # ====================================================
        # STEP 14
        # Extract selected actions.
        # ====================================================

        assignments = []

        for payment in payments:

            payment_id = (
                payment.payment_id
            )

            selected_action = None
            selected_value = None

            for (
                action,
                value,
            ) in evaluated_actions[
                payment_id
            ].items():

                variable = variables[
                    payment_id,
                    action,
                ]

                if (
                    variable.solution_value()
                    > 0.5
                ):

                    selected_action = action
                    selected_value = value
                    break

            if (
                selected_action is None
                or selected_value is None
            ):
                raise RuntimeError(
                    f"No action selected for "
                    f"{payment_id}."
                )

            assignments.append(
                OptimizedAssignment(
                    payment_id=payment_id,

                    action=selected_action,

                    recovery_probability=(
                        selected_value
                        .recovery_probability
                    ),

                    expected_net_value=(
                        selected_value
                        .expected_net_value
                    ),

                    incremental_value=(
                        selected_value
                        .incremental_value
                    ),

                    intervention_cost=(
                        selected_value
                        .intervention_cost
                    ),

                    incentive_cost=(
                        selected_value
                        .incentive_cost
                    ),
                )
            )

        # ====================================================
        # STEP 15
        # Aggregate portfolio metrics.
        # ====================================================

        total_incremental_value = sum(
            assignment.incremental_value
            for assignment
            in assignments
        )

        total_expected_net_value = sum(
            assignment.expected_net_value
            for assignment
            in assignments
        )

        total_intervention_spend = sum(
            (
                assignment.intervention_cost
                + assignment.incentive_cost
            )
            for assignment
            in assignments
        )

        total_incentive_spend = sum(
            assignment.incentive_cost
            for assignment
            in assignments
        )

        retry_count = sum(
            1
            for assignment
            in assignments
            if assignment.action
            in RETRY_ACTIONS
        )

        customer_contact_count = sum(
            1
            for assignment
            in assignments
            if assignment.action
            in CUSTOMER_CONTACT_ACTIONS
        )

        action_counts = dict(
            Counter(
                assignment.action
                for assignment
                in assignments
            )
        )

        return PortfolioOptimizationResult(
            status=status_name,

            total_incremental_value=float(
                total_incremental_value
            ),

            total_expected_net_value=float(
                total_expected_net_value
            ),

            total_intervention_spend=float(
                total_intervention_spend
            ),

            total_incentive_spend=float(
                total_incentive_spend
            ),

            retry_count=retry_count,

            customer_contact_count=(
                customer_contact_count
            ),

            assignments=assignments,

            action_counts=action_counts,
        )

    # ========================================================
    # VALIDATION
    # ========================================================

    @staticmethod
    def _validate_constraints(
        constraints: PortfolioConstraints,
    ) -> None:

        numeric_constraints = {
            "max_total_intervention_spend":
                constraints
                .max_total_intervention_spend,

            "max_incentive_spend":
                constraints
                .max_incentive_spend,

            "max_retry_actions":
                constraints
                .max_retry_actions,

            "max_customer_contacts":
                constraints
                .max_customer_contacts,

            "max_whatsapp_actions":
                constraints
                .max_whatsapp_actions,

            "max_incentive_actions":
                constraints
                .max_incentive_actions,

            "max_human_escalations":
                constraints
                .max_human_escalations,
        }

        for (
            name,
            value,
        ) in numeric_constraints.items():

            if (
                value is not None
                and value < 0
            ):
                raise ValueError(
                    f"{name} cannot be negative."
                )

        if (
            constraints.solver_time_limit_ms
            <= 0
        ):
            raise ValueError(
                "solver_time_limit_ms "
                "must be greater than zero."
            )

        if (
            constraints.enabled_actions is not None
            and "DO_NOTHING" not in constraints.enabled_actions
        ):
            raise ValueError(
                "enabled_actions must include DO_NOTHING."
            )

    # ========================================================
    # SOLVER STATUS
    # ========================================================

    @staticmethod
    def _status_name(
        status: int,
    ) -> str:

        status_map = {
            pywraplp.Solver.OPTIMAL:
                "OPTIMAL",

            pywraplp.Solver.FEASIBLE:
                "FEASIBLE",

            pywraplp.Solver.INFEASIBLE:
                "INFEASIBLE",

            pywraplp.Solver.UNBOUNDED:
                "UNBOUNDED",

            pywraplp.Solver.ABNORMAL:
                "ABNORMAL",

            pywraplp.Solver.NOT_SOLVED:
                "NOT_SOLVED",
        }

        return status_map.get(
            status,
            f"UNKNOWN_{status}",
        )
