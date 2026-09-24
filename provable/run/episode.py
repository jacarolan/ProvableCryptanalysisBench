"""Prepare a workspace for an externally driven subagent, then collect its Lean certificate.

Mirrors empirical/run/episode.py: TASK.md + workspace + .stop + results/runs/<name>/result.json,
the same default provenance string, and (with --transcript) the same imported trace.json. The
proof checker replaces the live oracle and replay; the certified bound is evaluated at the same
random lam-bit primes and against the same lower bound as empirical (run/evaluate.py).
Agent wall-clock time is taken from the subagent transcript timestamps (first to last event).
No model is launched by this command.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import time

from .check import ROOT, check
from .evaluate import DEFAULT_LAMS, evaluate_lams
from .prompts import SYSTEM_PROMPT, task_prompt

DEFAULT_MODEL = "claude-sonnet-5 (Claude Code subagent, effort medium)"


def prepare(name: str, lams: list[int], model: str, effort: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", name):
        raise ValueError("Use a simple alphanumeric episode name, with optional hyphens/underscores")
    if not all(2 <= lam <= 4096 for lam in lams):
        raise ValueError("lam must be between 2 and 4096")
    ws = ROOT / "workspaces" / name
    ws.mkdir(parents=True, exist_ok=False)
    metadata = {"episode": name, "lams": lams, "model": model, "effort": effort,
                "created_at": time.time(), "model_provenance": "operator-supplied; external subagent"}
    (ws / "episode.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (ws / "TASK.md").write_text(SYSTEM_PROMPT + "\n" + task_prompt(lams, str(ROOT / "lean"), sys.executable, str(ROOT)), encoding="utf-8")
    helper = "import subprocess, sys\nraise SystemExit(subprocess.call(" + repr([
        sys.executable, "-m", "run.check", str(ws / "Submission.lean"), "--out", str(ws / "check.json")
    ]) + ", cwd=" + repr(str(ROOT)) + "))\n"
    (ws / "check_submission.py").write_text(helper, encoding="utf-8")
    return ws


def import_transcript(jsonl: Path, out: Path) -> dict:
    """Same trace.json format as empirical/run/import_trace.py, plus session wall-clock time."""
    from datetime import datetime
    trace, models, stamps = [], set(), []
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        if ev.get("timestamp"):
            stamps.append(datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00")))
        if ev.get("type") not in ("assistant", "user"):
            continue
        msg = ev["message"]
        if ev["type"] == "assistant":
            models.add(msg.get("model"))
        content = msg["content"] if isinstance(msg["content"], list) else [{"type": "text", "text": msg["content"]}]
        trace.append({"role": msg["role"], "content": content, "stop_reason": msg.get("stop_reason")})
    (out / "trace.json").write_text(json.dumps(trace, indent=1), encoding="utf-8")
    return {"transcript_models": sorted(m for m in models if m),
            "turns": sum(1 for t in trace if t["role"] == "assistant"),
            "agent_wall_secs": (max(stamps) - min(stamps)).total_seconds() if stamps else None,
            "refusal": any(t.get("stop_reason") == "refusal" for t in trace)}


def collect(ws: Path, timeout: int, transcript: Path | None = None) -> dict:
    # Metadata is convenience only. The independently checked Lean term determines acceptance.
    meta = json.loads((ws / "episode.json").read_text(encoding="utf-8"))
    out = ROOT / "results" / "runs" / ws.name
    out.mkdir(parents=True, exist_ok=False)
    result = {**meta, "schema_version": 1, "status": "missing_submission",
              "wall_secs_episode": time.time() - meta["created_at"], "has_certificate": False}
    source = ws / "Submission.lean"
    for filename in ["TASK.md", "episode.json", "summary.md", "trace.json", "Submission.lean"]:
        if (ws / filename).is_file():
            shutil.copyfile(ws / filename, out / filename)
    if source.is_file():
        verification = check(out / "Submission.lean", timeout=timeout)
        (out / "check.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
        result.update(status=verification["status"], has_certificate=verification["status"] == "accepted",
                      verification_wall_secs=verification["verification_wall_secs"],
                      certificate=verification["certificate"], source_sha256=verification["source_sha256"])
        if result["has_certificate"]:
            result["evaluation"] = evaluate_lams(verification["certificate"]["bound"], meta.get("lams") or DEFAULT_LAMS)
    if transcript is not None:
        result.update(import_transcript(transcript, out))
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", required=True)
    ap.add_argument("--lams", type=int, nargs="+", default=DEFAULT_LAMS)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--transcript", type=Path, help="subagent JSONL transcript (for trace + agent wall-clock)")
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--max-secs", type=int, default=14400)
    ap.add_argument("--check-timeout", type=int, default=300)
    a = ap.parse_args()
    if a.prepare_only and a.collect:
        ap.error("--prepare-only and --collect are mutually exclusive")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", a.name):
        ap.error("Invalid episode name")
    if a.collect:
        ws = ROOT / "workspaces" / a.name
    else:
        ws = prepare(a.name, a.lams, a.model, a.effort)
        print(json.dumps({"workspace": str(ws), "task": str(ws / "TASK.md")}), flush=True)
        if a.prepare_only:
            return
        until = time.monotonic() + a.max_secs
        while not (ws / ".stop").exists() and time.monotonic() < until:
            time.sleep(1)
    result = collect(ws, a.check_timeout, a.transcript)
    print(json.dumps({k: v for k, v in result.items() if k != "evaluation"}, indent=2))
    raise SystemExit(0 if result["has_certificate"] else 1)


if __name__ == "__main__":
    main()
