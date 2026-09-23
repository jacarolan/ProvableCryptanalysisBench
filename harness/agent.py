"""Minimal tool-use agent loop (fallback for Harbor/terminus-2, which needs Docker).

One episode = one live challenger instance + one model. Afterwards the submitted attack.py is
replayed against fresh instances of the same rung and level (CryptanalysisBench style).
"""
from __future__ import annotations

import json
import os
import shutil
import time
import traceback

import anthropic

from .prompts import SYSTEM_PROMPT, task_prompt
from .sandbox import Challenger, new_workspace, run_command, sandbox_env

MODELS = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5"}

TOOLS = [
    {"name": "bash",
     "description": "Run a bash command (Git Bash on Windows) in a fresh shell in the workspace directory. "
                    "Returns combined stdout/stderr (long output is truncated) and the exit code.",
     "input_schema": {"type": "object", "properties": {
         "command": {"type": "string"},
         "timeout_sec": {"type": "integer", "description": "default 600, max 1800"}},
         "required": ["command"], "additionalProperties": False}},
    {"name": "write_file",
     "description": "Create or overwrite a text file (path relative to the workspace).",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"}, "content": {"type": "string"}},
         "required": ["path", "content"], "additionalProperties": False}},
    {"name": "finish",
     "description": "End the session. Call once attack.py is written and you have tried the live instance.",
     "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}},
                      "required": ["summary"], "additionalProperties": False}},
]


def _dump(blocks):
    return [b.model_dump(mode="json", exclude_none=True) if hasattr(b, "model_dump") else b for b in blocks]


def _exec_tool(name, inp, ws, env):
    if name == "bash":
        t = max(1, min(int(inp.get("timeout_sec") or 600), 1800))
        r = run_command(inp["command"], ws, env, timeout=t)
        head = f"[exit {r['exit_code']}{', TIMED OUT' if r['timed_out'] else ''}, {r['secs']}s]\n"
        return head + r["output"], r
    if name == "write_file":
        path = os.path.normpath(os.path.join(ws, inp["path"]))
        if not path.startswith(os.path.normpath(ws)):
            return "error: path must be inside the workspace", None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(inp["content"])
        return f"wrote {len(inp['content'])} chars to {inp['path']}", None
    return f"unknown tool {name}", None


def run_episode(model_key: str, rung: int, level: int, rep: int, out_dir: str, max_turns: int = 80,
                wall_secs: int = 5400, effort: str = "medium", n_replays: int = 3,
                max_output_tokens: int = 150_000) -> dict:
    model = MODELS[model_key]
    ep_id = f"{model_key}_r{rung}_L{level}_s{rep}"
    ep_dir = os.path.join(out_dir, ep_id)
    os.makedirs(ep_dir, exist_ok=True)
    client = anthropic.Anthropic(max_retries=8)
    ws = new_workspace(ep_id)
    trace: list = []
    rec = {"episode": ep_id, "model": model, "rung": rung, "level": level, "rep": rep,
           "status": "running", "turns": 0, "usage": {}, "refusal": None, "finish_summary": None}
    t0 = time.time()
    with Challenger(rung, level) as ch:
        env = sandbox_env(ch.url)
        prompt = task_prompt(ch.public(), ch.url)
        messages = [{"role": "user", "content": prompt}]
        trace.append({"role": "user", "content": prompt})
        nudges = 0
        try:
            while (rec["turns"] < max_turns and time.time() - t0 < wall_secs
                   and rec["usage"].get("output_tokens", 0) < max_output_tokens):
                rec["turns"] += 1
                with client.messages.stream(
                    model=model, max_tokens=64000, system=SYSTEM_PROMPT, tools=TOOLS, messages=messages,
                    thinking={"type": "adaptive", "display": "summarized"},
                    output_config={"effort": effort}, cache_control={"type": "ephemeral"},
                ) as stream:
                    resp = stream.get_final_message()
                for k, v in resp.usage.model_dump().items():
                    if isinstance(v, (int, float)):
                        rec["usage"][k] = rec["usage"].get(k, 0) + v
                trace.append({"role": "assistant", "stop_reason": resp.stop_reason, "content": _dump(resp.content),
                              "t": round(time.time() - t0, 1)})
                if resp.stop_reason == "refusal":
                    sd = getattr(resp, "stop_details", None)
                    rec["refusal"] = sd.model_dump() if hasattr(sd, "model_dump") else str(sd)
                    rec["status"] = "refused"
                    break
                messages.append({"role": "assistant", "content": resp.content})
                tool_uses = [b for b in resp.content if b.type == "tool_use"]
                if not tool_uses:
                    if resp.stop_reason == "max_tokens" or nudges < 3:
                        nudges += 1
                        msg = "Continue working autonomously. Call `finish` when attack.py is done."
                        messages.append({"role": "user", "content": msg})
                        trace.append({"role": "user", "content": msg})
                        continue
                    rec["status"] = "stopped_without_finish"
                    break
                results, finished = [], False
                for tu in tool_uses:
                    if tu.name == "finish":
                        finished = True
                        rec["finish_summary"] = tu.input.get("summary")
                        results.append({"type": "tool_result", "tool_use_id": tu.id, "content": "Session ended."})
                        continue
                    try:
                        text, meta = _exec_tool(tu.name, tu.input, ws, env)
                    except Exception as e:  # tool errors go back to the model
                        text, meta = f"tool error: {e}", None
                    results.append({"type": "tool_result", "tool_use_id": tu.id, "content": text or "(no output)"})
                messages.append({"role": "user", "content": results})
                trace.append({"role": "user", "content": results, "t": round(time.time() - t0, 1)})
                if finished:
                    rec["status"] = "finished"
                    break
            else:
                rec["status"] = "turn_time_or_token_limit"
        except Exception as e:
            rec["status"] = "error"
            rec["error"] = f"{type(e).__name__}: {e}"
            rec["traceback"] = traceback.format_exc()
        rec["live"] = ch.result()
    rec["wall_secs"] = round(time.time() - t0, 1)
    attack = os.path.join(ws, "attack.py")
    rec["has_attack"] = os.path.exists(attack)
    if rec["has_attack"]:
        shutil.copy(attack, os.path.join(ep_dir, "attack.py"))
        rec["replays"] = [replay(attack, rung, level) for _ in range(n_replays)]
    shutil.copytree(ws, os.path.join(ep_dir, "workspace"), dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    with open(os.path.join(ep_dir, "trace.json"), "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=1)
    with open(os.path.join(ep_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    return rec


def replay(attack_path: str, rung: int, level: int, budget_factor: int | None = None, timeout: int = 1800) -> dict:
    """Run attack.py alone, in a clean directory, against a fresh instance."""
    import tempfile
    with tempfile.TemporaryDirectory() as d, Challenger(rung, level, budget_factor=budget_factor) as ch:
        shutil.copy(attack_path, os.path.join(d, "attack.py"))
        from .sandbox import AGENT_FILES
        shutil.copy(os.path.join(AGENT_FILES, "oracle_client.py"), d)
        r = run_command("python attack.py", d, sandbox_env(ch.url), timeout=timeout, max_chars=4000)
        res = ch.result()
    return {"level": level, "solved": res["solved"], "queries_at_solve": res["queries_at_solve"],
            "queries_used": res["queries_used"], "budget": res["budget"], "q_ub": res["q_ub"], "q_lb": res["q_lb"],
            "exit_code": r["exit_code"], "timed_out": r["timed_out"], "secs": r["secs"], "tail": r["output"][-1500:],
            "secret_structure": res["secret_structure"], "seed": res["seed"]}
