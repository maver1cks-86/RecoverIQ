# RecoverIQ Architecture

RecoverIQ is an implemented modular monolith: React, FastAPI, PostgreSQL, Redis/Celery, bounded LangGraph orchestration, and a Razorpay Test Mode `PAYMENT_LINK` adapter.

## 1. High-level components

```mermaid
flowchart LR
  UI[React UI] --> API[FastAPI]
  API --> ML[Action-conditioned XGBoost]
  ML --> ECON[Economics]
  ECON --> POLICY[Policy]
  POLICY --> MILP[OR-Tools MILP]
  API <--> DB[(PostgreSQL)]
  API --> REDIS[(Redis)]
  REDIS --> CELERY[Celery]
  CELERY --> GRAPH[Bounded LangGraph]
  GRAPH --> RZP[Razorpay Test Mode]
  RZP --> WH[Signed webhook]
  WH --> DB
  DB --> LIVE[WebSocket and polling]
  LIVE --> UI
  UI --> COPILOTS[Recovery and What-if Copilots]
```

## 2. Prediction and decision pipeline

```mermaid
flowchart LR
  P[Failed payment and customer context] --> C[Candidate actions]
  C --> M[Action-conditioned probabilities]
  M --> V[Expected and incremental value]
  V --> G[Deterministic policy eligibility]
  G --> R[Ranked candidates]
  R --> O[Portfolio optimizer]
  O --> PLAN[Versioned persisted plan]
```

Outcome-only columns and identifiers are excluded by feature allow-lists. `DO_NOTHING` is the control and always remains feasible.

## 3. Optimization

```mermaid
flowchart TD
  D[Payment/action values] --> X[Binary x payment action]
  X --> ONE[One action per payment]
  X --> BUDGET[Spend and incentive budgets]
  X --> CAPS[Retry contact WhatsApp incentive human caps]
  X --> ELIG[Policy and action eligibility]
  ONE --> SOLVE[Maximize total incremental value]
  BUDGET --> SOLVE
  CAPS --> SOLVE
  ELIG --> SOLVE
  SOLVE --> PLAN[Immutable allocation evidence]
```

The LLM and LangGraph never select `x`. OR-Tools receives policy-eligible, economically valued candidates.

## 4. Async execution

```mermaid
flowchart LR
  APPROVE[Execute approved plan] --> API[FastAPI validates READY]
  API --> DB[Commit queued assignments]
  DB --> BROKER[Redis Celery broker]
  BROKER --> WORKER[Celery]
  WORKER --> GRAPH[LangGraph planned_action]
  GRAPH --> DECISION[Persist or reuse decision]
  DECISION --> INT[Persist or reuse intervention]
  INT --> ADAPTER[PAYMENT_LINK adapter]
  ADAPTER --> WAIT[AWAITING_PAYMENT]
```

Unsupported rails become manual/no-action states. LangGraph rejects execution without a persisted optimizer assignment.

## 5. Razorpay Payment Link sequence

```mermaid
sequenceDiagram
  actor Merchant
  participant UI as Frontend
  participant API as FastAPI
  participant DB as PostgreSQL
  participant Redis
  participant Worker as Celery
  participant Graph as LangGraph
  participant RZP as Razorpay
  participant WH as Webhook Handler
  participant WS as WebSocket

  Merchant->>UI: Execute approved plan once
  UI->>API: POST batch execute
  API->>DB: Commit QUEUED and NO_ACTION
  API->>Redis: Enqueue assignment
  API-->>UI: 202 Accepted
  Redis->>Worker: Deliver task
  Worker->>Graph: Execute persisted planned_action
  Graph->>DB: Persist decision and intervention
  Graph->>RZP: Create Test Mode Payment Link
  RZP-->>Graph: Provider ID and URL
  Graph->>DB: Commit AWAITING_PAYMENT
  DB-->>WS: Publish after commit
  WS-->>UI: Refetch persisted state
  Merchant->>RZP: Complete Test Mode payment
  RZP->>WH: payment_link.paid and signature
  WH->>WH: Verify raw-body signature
  WH->>DB: Persist unique event
  WH->>Redis: Enqueue processing
  Redis->>Worker: Deliver webhook task
  Worker->>DB: Commit paid intervention, outcome and RECOVERED payment
  Worker->>WS: Publish after commit
  WS-->>UI: Refetch RECOVERED state
```

Provider action creation is not recovery. Only the verified provider outcome closes the loop.

## 6. WebSocket and polling

```mermaid
flowchart TD
  COMMIT[Committed PostgreSQL state] --> PUB[Best-effort Redis Pub/Sub]
  PUB --> WS[/ws/batches/{batch_id}]
  WS --> FETCH[Refetch batch summary and rows]
  FAIL{Socket connected?} -->|No| POLL[3-second fallback polling]
  FAIL -->|Yes| RECON[15-second reconciliation]
  POLL --> FETCH
  RECON --> FETCH
  FETCH --> TERM{Relevant work terminal?}
  TERM -->|Yes| STOP[Stop polling]
  TERM -->|No| FAIL
```

Events are invalidation hints. PostgreSQL is authoritative, and request sequencing prevents stale responses replacing newer state.

## 7. What-if Copilot

```mermaid
flowchart LR
  TEXT[Merchant language] --> LLM[Interpretation only]
  LLM --> SCHEMA[Strict validated fields]
  SCHEMA --> PREVIEW[Before/after preview]
  PREVIEW --> CONFIRM{Merchant confirms?}
  CONFIRM -->|No| END[No mutation]
  CONFIRM -->|Yes| MILP[Existing deterministic MILP]
  MILP --> EXPLAIN[Grounded result explanation]
```

Invalid or unknown fields are rejected. LLM failure never invents constraints.

## 8. Recovery Copilot

```mermaid
flowchart LR
  Q[Question and payment] --> READ[Read persisted audit evidence]
  READ --> FACTS[Deterministic facts]
  FACTS --> OPTIONAL[Optional grounded wording]
  OPTIONAL --> ANSWER[Read-only answer]
```

The Copilot has no write or execution authority.

## 9. Audit lifecycle

```mermaid
flowchart LR
  PAY[Payment] --> PLAN[Plan and ranked alternatives]
  PLAN --> POL[Policy evidence]
  POL --> DEC[Decision]
  DEC --> INT[Intervention]
  INT --> PROVIDER[Provider action]
  PROVIDER --> WH[Webhook event]
  WH --> OUT[Outcome]
  OUT --> STATUS[Recovered payment]
```

Financial values use SQL numeric/Decimal. Audit responses distinguish estimates from provider-confirmed outcomes.

## Current and future scope

Current infrastructure is a local/prototype modular monolith. Managed horizontal deployment, stronger multi-tenant isolation/RBAC, observability, partitioning, rate limits, drift monitoring, controlled experiments, and additional provider adapters are future work. Kubernetes, Kafka, microservices, and non-Payment-Link provider executors are not current components.
