from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from time import perf_counter

import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path: sys.path.insert(0, str(BACKEND_ROOT))

from app.decision.decision_engine import DecisionEngine, RecoveryDecision
from app.decision.economic_value import calculate_economic_value
from app.optimizer.portfolio_optimizer import PortfolioConstraints, PortfolioOptimizer, PortfolioPayment
from app.policies.engine import PolicyConfig
from app.services.optimization_service import _context

DATA = PROJECT_ROOT / "data" / "processed" / "test.csv"


def benchmark(size: int, timeout_ms: int) -> dict:
    start = perf_counter(); frame = pd.read_csv(DATA, nrows=size); contexts = [_context(row) for _,row in frame.iterrows()]; ids=[str(v) for v in frame.payment_id]; feature_seconds=perf_counter()-start
    engine=DecisionEngine(); start=perf_counter(); predictions=engine.action_evaluator.evaluate_batch(contexts); scoring_seconds=perf_counter()-start
    start=perf_counter(); decisions={}; policy=PolicyConfig()
    for payment_id,context,items in zip(ids,contexts,predictions):
        control=next(x.recovery_probability for x in items if x.action=="DO_NOTHING")
        values=[calculate_economic_value(action=x.action,recovery_probability=x.recovery_probability,estimated_uplift=0 if x.action=="DO_NOTHING" else x.recovery_probability-control,amount=float(context["amount"])) for x in items]
        allowed,policy_results=engine.policy_engine.filter_actions([x.action for x in values],context,policy); ranked=sorted((x for x in values if x.action in set(allowed)),key=lambda x:x.incremental_value,reverse=True); best=ranked[0]
        decisions[payment_id]=RecoveryDecision(best.action,best.recovery_probability,best.expected_net_value,best.incremental_value,ranked,policy_results)
    economics_seconds=perf_counter()-start; start=perf_counter()
    result=PortfolioOptimizer().optimize([PortfolioPayment(i,c) for i,c in zip(ids,contexts)],PortfolioConstraints(max_total_intervention_spend=size*2,max_retry_actions=int(size*.35),max_customer_contacts=int(size*.3),max_whatsapp_actions=int(size*.15),max_incentive_actions=int(size*.05),max_human_escalations=int(size*.03),solver_time_limit_ms=timeout_ms),policy,decisions); solver_seconds=perf_counter()-start
    return {"payments":size,"feature_preparation_seconds":round(feature_seconds,4),"batch_ml_scoring_seconds":round(scoring_seconds,4),"policy_economics_seconds":round(economics_seconds,4),"solver_seconds":round(solver_seconds,4),"total_seconds":round(feature_seconds+scoring_seconds+economics_seconds+solver_seconds,4),"solver_status":result.status,"assignment_count":len(result.assignments)}


def main() -> int:
    parser=argparse.ArgumentParser(description="Measured Phase 27 planning-only scalability benchmark");parser.add_argument("--sizes",nargs="+",type=int,default=[1000,5000,10000]);parser.add_argument("--timeout-ms",type=int,default=30000);parser.add_argument("--csv",type=Path);args=parser.parse_args();rows=[]
    for size in args.sizes:
        try: rows.append(benchmark(size,args.timeout_ms))
        except Exception as exc: rows.append({"payments":size,"solver_status":f"FAILED: {exc}","assignment_count":0})
    headers=["payments","feature_preparation_seconds","batch_ml_scoring_seconds","policy_economics_seconds","solver_seconds","total_seconds","solver_status","assignment_count"]
    print(" | ".join(headers)); print(" | ".join("---" for _ in headers))
    for row in rows: print(" | ".join(str(row.get(key,"")) for key in headers))
    if args.csv:
        args.csv.parent.mkdir(parents=True,exist_ok=True)
        with args.csv.open("w",newline="",encoding="utf-8") as handle: writer=csv.DictWriter(handle,fieldnames=headers);writer.writeheader();writer.writerows(rows)
    return 0

if __name__=="__main__": raise SystemExit(main())
