#!/usr/bin/env bash
# usage: scripts/start_hosts.sh "1 8" "2 8" ...   -> starts one detached episode host per (rung level)
cd "$(dirname "$0")/.." || exit 1
mkdir -p results/subagent_runs
for spec in "$@"; do
  read -r rung level <<< "$spec"
  name="sub_r${rung}_L${level}"
  (py -3.13 scripts/subagent_episode.py --rung "$rung" --level "$level" --name "$name" --max-secs 14400 --model "claude-sonnet-5 (subagent)" > "results/subagent_runs/host_$name.log" 2>&1 &)
done
sleep 10
for spec in "$@"; do read -r rung level <<< "$spec"; echo "sub_r${rung}_L${level} $(head -1 results/subagent_runs/host_sub_r${rung}_L${level}.log)"; done
