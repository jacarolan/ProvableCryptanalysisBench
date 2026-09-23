"""Convert a Claude Code subagent transcript (JSONL) into this repo's trace.json format so that
analysis/audit.py treats subagent episodes like API-harness episodes.

    python scripts/import_subagent_trace.py <agent-XXXX.jsonl> results/subagent_runs/<episode>
"""
import json
import os
import sys

src, ep_dir = sys.argv[1], sys.argv[2]
trace, models = [], set()
for line in open(src, encoding="utf-8"):
    if not line.strip():
        continue
    ev = json.loads(line)
    if ev.get("type") not in ("assistant", "user"):
        continue
    msg = ev["message"]
    if ev["type"] == "assistant":
        models.add(msg.get("model"))
    content = msg["content"] if isinstance(msg["content"], list) else [{"type": "text", "text": msg["content"]}]
    trace.append({"role": msg["role"], "content": content, "stop_reason": msg.get("stop_reason")})
json.dump(trace, open(os.path.join(ep_dir, "trace.json"), "w", encoding="utf-8"), indent=1)
res_path = os.path.join(ep_dir, "result.json")
rec = json.load(open(res_path))
rec["model"] = "claude-sonnet-5 (subagent)" if models == {"claude-sonnet-5"} else ",".join(sorted(m for m in models if m))
rec["turns"] = sum(1 for t in trace if t["role"] == "assistant")
rec["refusal"] = next((t for t in trace if t.get("stop_reason") == "refusal"), None)
json.dump(rec, open(res_path, "w"), indent=1)
print(rec["episode"], rec["model"], "assistant messages:", rec["turns"])
