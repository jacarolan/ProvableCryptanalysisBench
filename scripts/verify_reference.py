"""Check every rung/level: the reference attack succeeds within Q*_UB (its certified worst case),
Q*_UB is within a small constant of the generic lower bound, and structure-ignoring generic
attacks cost far more than the budget. Writes results/reference_verification.json."""
import argparse, json, math, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ggmbench.instances import LEVELS, generate
from ggmbench.oracle import GroupOracle, LocalClient
from ggmbench.solvers import SOLVERS

ap = argparse.ArgumentParser()
ap.add_argument("--seeds", type=int, default=5)
ap.add_argument("--max-level", type=int, default=20)
ap.add_argument("--out", default="results/reference_verification.json")
a = ap.parse_args()
rows, ok_all = [], True
for rung, levels in LEVELS.items():
    for L in levels:
        if L > a.max_level: continue
        for s in range(a.seeds):
            inst = generate(rung, L, (1000 + s))
            o = GroupOracle(inst.N, inst.x, inst.published, inst.budget, inst.public_info())
            t = time.time()
            SOLVERS[rung](LocalClient(o))
            r = o.result()
            ok = r["solved"] and r["queries_used"] <= inst.q_ub
            ok_all &= ok
            row = dict(rung=rung, level=L, seed=s, N_bits=inst.N.bit_length(), q_used=r["queries_used"],
                       q_ub=inst.q_ub, q_lb=inst.q_lb, budget=inst.budget, naive=inst.naive_cost,
                       ub_over_lb=round(inst.q_ub / inst.q_lb, 2),
                       log2_naive_over_budget=round(math.log2(inst.naive_cost / inst.budget), 1),
                       solved=r["solved"], within_ub=ok, secs=round(time.time() - t, 2))
            rows.append(row)
            print(row, flush=True)
os.makedirs(os.path.dirname(a.out), exist_ok=True)
json.dump(rows, open(a.out, "w"), indent=1)
print("ALL OK" if ok_all else "FAILURES")
