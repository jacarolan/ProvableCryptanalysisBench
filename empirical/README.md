# Empirical: generic discrete log, measured

The problem is plain discrete log in the generic group model, with no planted structure.

- **Instance** at security parameter λ: the group order N is a uniformly random λ-bit prime,
  G = ⟨g⟩ has order N, x is uniform in [0, N), and the challenger publishes h = g^x.
- **Oracle:** the challenger holds x and a keyed random labelling of Z_N (a pseudorandom
  permutation, so labels reveal nothing).
- **Queries:** the agent may ask for `mul`, `inv` or `exp`, 1 query each; submitting a guess
  also costs 1. Comparing two labels is free.
- **Budget:** 4 × the worst-case cost of baby-step giant-step (~8√N queries), which only stops
  runaway attacks.

## Lower bound on expected queries

Any generic algorithm that makes at most m queries (submission included) succeeds with
probability at most ε(m) = (C(m+2, 2) + 1)/N. This is Shoup's collision argument with the two
published elements g and h.

Now take an attack that always succeeds, and let T be its number of queries. Stopping it after
m queries gives an m-query algorithm, so Pr[T ≤ m] ≤ ε(m). Hence

  E[T] = Σ_{m ≥ 0} Pr[T > m] ≥ Σ_{m ≥ 0} max(0, 1 − ε(m)) ≈ (2/3)·√(2N) ≈ 0.943·√N.

`ggm/instances.py:lb_expected` evaluates this sum exactly, using the hockey-stick identity.
Averaged over a random λ-bit prime N, it gives the line ≈ 0.81·2^(λ/2) in the plot.

For comparison, baby-step giant-step costs 2√N in the worst case and about 1.5√N in
expectation (≈ 1.6–2.1× the bound).

## Protocol (Sonnet 5, medium effort, as Claude Code subagents)

For each λ ∈ {16, 20, 24, 28, 32, 36, 40}:

1. `run/episode.py` starts a live challenger.
2. It writes `TASK.md` (interface, cost model and key generation only; no hints) into a fresh
   workspace.
3. A Sonnet 5 subagent writes `attack.py` and solves the live instance.
4. The host then replays `attack.py`, alone in an empty directory, on **3 fresh instances** of
   the same λ. It records the queries used and the wall-clock time of `python attack.py`, which
   includes Python startup and the localhost HTTP round trips.
5. Plots come from the replays: `analysis/plot.py` writes `results/queries.png`,
   `results/runtime.png`, `results/runtime_extrapolated.png` and `results/summary.md`.

**Runtime extrapolation** (`analysis/runtime_fit.py`, parameters in `results/runtime_fit.json`):
- **Model:** the measured runs are fitted to t = t₀ + k·√N, with t₀ ≈ 0.70 s of start-up
  overhead and k ≈ 0.16 ms per √N (≈ 80 µs per query). Every attack is baby-step giant-step,
  so the time grows like √N.
- **Extrapolated times** (plotted to λ = 256 on a linear λ axis, where √N growth is a straight
  line): about 2 min at λ = 40 (matching the measurement), a week at λ = 64,
  10⁸ years at λ = 128, and 10²⁷ years at λ = 256.
- **Assumptions:** the same machine and unlimited memory. BSGS stores ~√N labels, so the
  estimates are optimistic beyond λ ≈ 60–70.

Everything else is in `results/`:
- `runs/<episode>/` holds each episode's `result.json`, `attack.py`, workspace and imported
  transcript `trace.json`.
- `hosts/` holds the host logs, and `agent_ids.txt` maps episodes to subagent transcripts.

```bash
cd empirical
run/start_hosts.sh 0 16 20 24 28 32 36 40   # start hosts, then launch one subagent per TASK.md
run/collect.sh <episode> <subagent_id>      # stop host, replay attack.py, import transcript
py -3.13 analysis/plot.py
```

## Caveats

- **Tested in the model, not on real groups.** The agents are evaluated *inside* the generic
  group model. The oracle enforces it, so the lower bound is a theorem about this task. The
  results say nothing about attacks on concrete groups, such as index calculus in F_p^*.
- **The harness is a Claude Code subagent.** The agent is Sonnet 5 at effort `medium`, running
  as a Claude Code subagent with a shell and files. Isolation is by instruction (stay in the
  workspace), and transcripts are kept for audit. There is no container.
- **Wall-clock time is machine-dependent.** It depends on the machine (one Windows laptop,
  local HTTP) and on how the attack batches its requests. It is reported alongside the query
  count and does not replace it.
- **Sample size is small:** one agent per λ, each with 3 fresh-instance replays.
