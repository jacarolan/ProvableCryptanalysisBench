"""Optional extrapolation (open direction 2 of CryptanalysisBench §5.4): run each submitted
attack.py across the rung's size ladder and fit its query scaling.

For every episode we replay attack.py at every level of its rung (budget raised to 8 Q* so
sub-optimal scalings stay measurable) and fit  log2 Q_model = a + b * log2 Q*  over solved runs.
b ~ 1 with a bounded offset means the attack tracks the optimal scaling, so its cost at sizes too
large to run is Q_model(n) ~ 2^a * Q*(n), and Q*(n) is a theorem. Anything with b > 1 is
extrapolated to diverge from the optimum.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ggmbench.instances import LEVELS  # noqa: E402
from harness.agent import replay  # noqa: E402


def fit(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return {"slope": b, "intercept": my - b * mx, "n": n}


def run(ep_dir: str, reps: int, factor: int, max_level: int) -> dict:
    rec = json.load(open(os.path.join(ep_dir, "result.json")))
    attack = os.path.join(ep_dir, "attack.py")
    rung = rec["rung"]
    pts = []
    for L in LEVELS[rung]:
        if L > max_level:
            continue
        for _ in range(reps):
            r = replay(attack, rung, L, budget_factor=factor, timeout=1800)
            pts.append(r)
    ok = [p for p in pts if p["solved"]]
    f = fit([math.log2(p["q_ub"]) for p in ok], [math.log2(p["queries_at_solve"]) for p in ok])
    return {"episode": rec["episode"], "model": rec["model"], "rung": rung, "points": pts, "fit": f,
            "levels_solved": sorted({p["level"] for p in ok})}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="results/runs")
    ap.add_argument("--out", default="results/extrapolation.json")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--factor", type=int, default=8)
    ap.add_argument("--max-level", type=int, default=20)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    eps = [os.path.join(a.runs, d) for d in sorted(os.listdir(a.runs))
           if os.path.exists(os.path.join(a.runs, d, "attack.py"))]
    with ThreadPoolExecutor(a.workers) as ex:
        res = list(ex.map(lambda e: run(e, a.reps, a.factor, a.max_level), eps))
    json.dump(res, open(a.out, "w"), indent=1)
    for r in res:
        f = r["fit"]
        print(r["episode"], "levels solved", r["levels_solved"],
              f"slope={f['slope']:.2f} offset={f['intercept']:.2f}" if f else "no fit")
