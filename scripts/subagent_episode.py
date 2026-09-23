"""Host one episode for an externally driven agent (e.g. a Claude Code subagent) instead of the API loop.

    python scripts/subagent_episode.py --rung 1 --level 8 --name sub_r1_L8   # runs until stopped
    touch <workspace>/.stop                                                  # (done by the operator)

Starts a live challenger, creates the workspace with oracle_client.py and TASK.md, prints the
workspace path and oracle URL, then waits. When `.stop` appears in the workspace it records the
live result, replays attack.py on fresh instances (as harness/agent.py does), and writes
results/subagent_runs/<name>/result.json.
"""
import argparse
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.agent import replay  # noqa: E402
from harness.prompts import SYSTEM_PROMPT, task_prompt  # noqa: E402
from harness.sandbox import Challenger, new_workspace  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--rung", type=int, required=True)
ap.add_argument("--level", type=int, required=True)
ap.add_argument("--name", required=True)
ap.add_argument("--model", default="claude-sonnet-5 (subagent)")
ap.add_argument("--replays", type=int, default=3)
ap.add_argument("--max-secs", type=int, default=7200)
ap.add_argument("--out", default="results/subagent_runs")
a = ap.parse_args()

ws = new_workspace(a.name)
t0 = time.time()
with Challenger(a.rung, a.level) as ch:
    with open(os.path.join(ws, "TASK.md"), "w", encoding="utf-8") as f:
        f.write(SYSTEM_PROMPT + "\n\n" + task_prompt(ch.public(), ch.url))
    print(json.dumps({"workspace": ws, "oracle_url": ch.url}), flush=True)
    stop = os.path.join(ws, ".stop")
    while not os.path.exists(stop) and time.time() - t0 < a.max_secs:
        time.sleep(2)
    live = ch.result()
rec = {"episode": a.name, "model": a.model, "rung": a.rung, "level": a.level, "rep": 0,
       "status": "finished" if os.path.exists(stop) else "time_limit", "wall_secs": round(time.time() - t0, 1),
       "live": live, "harness": "claude-code-subagent"}
attack = os.path.join(ws, "attack.py")
rec["has_attack"] = os.path.exists(attack)
ep_dir = os.path.join(a.out, a.name)
os.makedirs(ep_dir, exist_ok=True)
if rec["has_attack"]:
    shutil.copy(attack, os.path.join(ep_dir, "attack.py"))
    rec["replays"] = [replay(attack, a.rung, a.level) for _ in range(a.replays)]
shutil.copytree(ws, os.path.join(ep_dir, "workspace"), dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".stop"))
json.dump(rec, open(os.path.join(ep_dir, "result.json"), "w"), indent=1)
reps = rec.get("replays") or []
print(json.dumps({"status": rec["status"], "live_solved": live["solved"], "live_queries": live["queries_used"],
                  "budget": live["budget"], "q_ub": live["q_ub"],
                  "replays": [(r["solved"], r["queries_at_solve"], r["q_ub"]) for r in reps]}), flush=True)
