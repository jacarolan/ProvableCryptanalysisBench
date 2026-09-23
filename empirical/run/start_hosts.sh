#!/usr/bin/env bash
# usage: run/start_hosts.sh <seed> <lam> [<lam> ...]   -> one detached episode host per lam
cd "$(dirname "$0")/.." || exit 1
mkdir -p results/hosts
seed=$1; shift
for lam in "$@"; do
  name="sonnet_l${lam}_s${seed}"
  (py -3.13 -m run.episode --lam "$lam" --name "$name" > "results/hosts/$name.log" 2>&1 &)
done
sleep 8
for lam in "$@"; do echo "sonnet_l${lam}_s${seed} $(head -1 results/hosts/sonnet_l${lam}_s${seed}.log)"; done
