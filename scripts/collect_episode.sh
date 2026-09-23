#!/usr/bin/env bash
# usage: scripts/collect_episode.sh <episode_name> <subagent_id>
# Signals the host to stop, waits for its replays to finish, and imports the subagent transcript.
cd "$(dirname "$0")/.." || exit 1
name=$1; aid=$2
ws="$(py -3.13 -c 'import tempfile,os;print(os.path.join(tempfile.gettempdir(),"ggmbench_ws"))')/$name"
touch "$ws/.stop"
for i in $(seq 1 1200); do grep -q '"status"' "results/subagent_runs/host_$name.log" && break; sleep 3; done
tail -1 "results/subagent_runs/host_$name.log"
tr="$HOME/.claude/projects/C--Users-jacar-OneDrive-Documents-Slides-App/450e6112-5eeb-4a12-9fe2-15b98d8904f7/subagents/agent-$aid.jsonl"
py -3.13 scripts/import_subagent_trace.py "$tr" "results/subagent_runs/$name"
echo "$name $aid" >> results/subagent_runs/agent_ids.txt
