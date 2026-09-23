"""Host one episode for a Claude Code subagent.

    python -m run.episode --lam 24 --name sonnet_l24_s0      # runs until <workspace>/.stop exists

Starts a live challenger for a random lam-bit instance, writes TASK.md and oracle_client.py into
a fresh workspace, prints {"workspace", "oracle_url"}, then waits. When `.stop` appears it records
the live result and replays attack.py, alone in an empty directory, on `--replays` fresh
instances, timing each run (wall-clock of `python attack.py`, including startup and HTTP).
Output: results/runs/<name>/{result.json, attack.py, workspace/}.
"""
import argparse
import json
import os
import shutil
import tempfile
import time

from .prompts import SYSTEM_PROMPT, task_prompt
from .sandbox import AGENT_FILES, Challenger, new_workspace, run_command, sandbox_env

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def replay(attack_path: str, lam: int, timeout: int) -> dict:
    with tempfile.TemporaryDirectory() as d, Challenger(lam) as ch:
        shutil.copy(attack_path, os.path.join(d, "attack.py"))
        shutil.copy(os.path.join(AGENT_FILES, "oracle_client.py"), d)
        r = run_command("python attack.py", d, sandbox_env(ch.url), timeout=timeout, max_chars=3000)
        res = ch.result()
    return {"lam": lam, "N": res["N"], "solved": res["solved"], "queries_at_solve": res["queries_at_solve"],
            "queries_used": res["queries_used"], "budget": res["budget"], "lb_expected": res["lb_expected"],
            "bsgs_worst": res["bsgs_worst"], "wall_secs": r["secs"], "exit_code": r["exit_code"],
            "timed_out": r["timed_out"], "seed": res["seed"], "tail": r["output"][-1200:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lam", type=int, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--model", default="claude-sonnet-5 (Claude Code subagent, effort medium)")
    ap.add_argument("--replays", type=int, default=3)
    ap.add_argument("--replay-timeout", type=int, default=3600)
    ap.add_argument("--max-secs", type=int, default=14400)
    a = ap.parse_args()

    ws = new_workspace(a.name)
    t0 = time.time()
    with Challenger(a.lam) as ch:
        with open(os.path.join(ws, "TASK.md"), "w", encoding="utf-8") as f:
            f.write(SYSTEM_PROMPT + "\n\n" + task_prompt(ch.public(), ch.url))
        print(json.dumps({"workspace": ws, "oracle_url": ch.url}), flush=True)
        stop = os.path.join(ws, ".stop")
        while not os.path.exists(stop) and time.time() - t0 < a.max_secs:
            time.sleep(2)
        live = ch.result()
    rec = {"episode": a.name, "model": a.model, "lam": a.lam, "wall_secs_episode": round(time.time() - t0, 1),
           "status": "finished" if os.path.exists(stop) else "time_limit", "live": live}
    out = os.path.join(HERE, "results", "runs", a.name)
    os.makedirs(out, exist_ok=True)
    attack = os.path.join(ws, "attack.py")
    rec["has_attack"] = os.path.exists(attack)
    if rec["has_attack"]:
        shutil.copy(attack, os.path.join(out, "attack.py"))
        rec["replays"] = [replay(attack, a.lam, a.replay_timeout) for _ in range(a.replays)]
    shutil.copytree(ws, os.path.join(out, "workspace"), dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".stop"))
    json.dump(rec, open(os.path.join(out, "result.json"), "w"), indent=1)
    reps = rec.get("replays") or []
    print(json.dumps({"status": rec["status"], "live_solved": live["solved"], "live_queries": live["queries_used"],
                      "replays": [(r["solved"], r["queries_at_solve"], r["wall_secs"]) for r in reps]}), flush=True)


if __name__ == "__main__":
    main()
