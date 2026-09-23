#!/usr/bin/env bash
# usage: run/collect.sh <episode_name> <subagent_id>
# Stops the episode host (which then replays attack.py) and imports the subagent transcript.
cd "$(dirname "$0")/.." || exit 1
name=$1; aid=$2
ws="$(py -3.13 -c 'import tempfile,os;print(os.path.join(tempfile.gettempdir(),"ggm_dl_ws"))')/$name"
touch "$ws/.stop"
for i in $(seq 1 4000); do grep -q '"status"' "results/hosts/$name.log" && break; sleep 3; done
tail -1 "results/hosts/$name.log"
tr="$HOME/.claude/projects/C--Users-jacar-OneDrive-Documents-Slides-App/450e6112-5eeb-4a12-9fe2-15b98d8904f7/subagents/agent-$aid.jsonl"
py -3.13 -m run.import_trace "$tr" "results/runs/$name"
echo "$name $aid" >> results/agent_ids.txt
