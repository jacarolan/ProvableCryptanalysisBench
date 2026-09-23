"""Run the evaluation grid: rungs x levels x models x seeds (resumable; skips finished episodes).

    python -m harness.run_grid                      # pilot default: Sonnet 5, effort medium, 2 seeds
    python -m harness.run_grid --models opus sonnet --seeds 3 --effort high   # full design
    python -m harness.run_grid --models sonnet --rungs 1 --levels 8 --seeds 1   # smoke test
"""
import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from ggmbench.instances import LEVELS
from .agent import run_episode

ap = argparse.ArgumentParser()
ap.add_argument("--models", nargs="+", default=["sonnet"])
ap.add_argument("--rungs", nargs="+", type=int, default=[1, 2, 3, 4])
ap.add_argument("--levels", nargs="+", type=int, default=None)
ap.add_argument("--seeds", type=int, default=2)
ap.add_argument("--workers", type=int, default=4)
ap.add_argument("--out", default="results/runs")
ap.add_argument("--effort", default="medium")
ap.add_argument("--max-turns", type=int, default=50)
a = ap.parse_args()

jobs = []
for rep in range(a.seeds):
    for rung in a.rungs:
        for L in LEVELS[rung]:
            if a.levels and L not in a.levels:
                continue
            for m in a.models:
                done = os.path.join(a.out, f"{m}_r{rung}_L{L}_s{rep}", "result.json")
                if os.path.exists(done) and json.load(open(done)).get("status") not in ("error",):
                    continue
                jobs.append((m, rung, L, rep))
print(f"{len(jobs)} episodes to run", flush=True)
with ThreadPoolExecutor(a.workers) as ex:
    futs = {ex.submit(run_episode, m, r, L, s, a.out, a.max_turns, effort=a.effort): (m, r, L, s) for m, r, L, s in jobs}
    for f in as_completed(futs):
        try:
            rec = f.result()
            reps = rec.get("replays") or []
            print(f"{rec['episode']}: {rec['status']} live_solved={rec['live']['solved']} "
                  f"q={rec['live']['queries_used']}/{rec['live']['budget']} "
                  f"replay={[ (x['solved'], x['queries_at_solve']) for x in reps]} "
                  f"turns={rec['turns']} secs={rec['wall_secs']}", flush=True)
        except Exception as e:
            print(futs[f], "FAILED", repr(e), flush=True)
