# ProvableCryptanalysisBench

**Certified-difficulty cryptanalysis tasks in the generic group model.** This is a pilot
extension of [CryptanalysisBench](https://github.com/ethz-spylab/cryptanalysis-benchmark)
(Fluri et al., arXiv 2607.18538). It addresses three of the open directions in §5.4 of that
paper:

| §5.4 gap | What this pilot does |
|---|---|
| Difficulty generation is approximate and brittle (scaled-down schemes, scaling bugs) | The harness *is* the idealised model: a challenger with a secret keyed random encoding. Generic lower bounds are therefore theorems about each task, and each instance carries a certified optimal cost with Q\*_UB / Q\*_LB ≈ 2. |
| Only attacks cheap enough to run can be verified | Submitted attacks are replayed across a size ladder, and their query scaling is fitted against the certified optimum (`analysis/extrapolate.py`). |
| Results depend on CPU, memory and runtime budgets | Labels are random, so local compute cannot substitute for oracle queries. The only resource is the query count. |

Each task gives the labels of g and h = g^x in a group of known order N, plus a query budget
B = 4·Q\*. The goal is to recover x. Each rung plants one structural weakness:

| Rung | Planted structure | Optimal attack | Certified Q\* |
|---|---|---|---|
| 1 | smooth group order | Pohlig–Hellman + BSGS | ≈ 2√q_max |
| 2 | short exponent x < 2^t | BSGS on the interval | ≈ 2^(t/2+1) |
| 3 | both combined | PH on the smooth part + interval BSGS on the residual | PH(S) + 2√(2^t/S) |
| 4 | auxiliary input g^(x^d), d \| p−1 | Cheon's attack | ≈ 2√(p/d) + 2√d |

Proofs, the model, and the verified parameter ladders are in **[THEORY.md](THEORY.md)**. The
results write-up is **[NOTE.md](NOTE.md)**.

## Layout

```
ggmbench/            the benchmark
  oracle.py          GGM challenger: keyed PRP labels, mul/inv/exp/submit, query counting, budget
  instances.py       (rung, level, secret seed) -> instance with Q*_UB, Q*_LB, naive cost
  bounds.py          exact reference-attack costs and generic lower bounds
  solvers.py         reference attacks (PH, interval BSGS, combined, Cheon)
  server.py          HTTP challenger; secrets arrive on stdin and never touch disk
  agent_files/oracle_client.py   the only file given to agents (HTTP client + free MockOracle)
harness/
  prompts.py         system prompt (benchmark framing) and task text (interface only)
  sandbox.py         challenger subprocesses, workspace, Git Bash command runner
  agent.py           tool-use loop (bash / write_file / finish), then attack.py replay on fresh instances
  run_grid.py        resumable grid runner
analysis/
  analyze.py         summary table, success-vs-difficulty and efficiency plots
  audit.py           trace audit: structure identified? attack named? refusals? out-of-workspace access?
  extrapolate.py     replays attacks across sizes and fits query scaling
scripts/
  verify_reference.py              reference attacks within Q*_UB, naive cost far above budget
  example_attacks/ph_interval_attack.py   self-contained attack used to smoke-test the replay path
  subagent_episode.py              hosts one episode for an externally driven agent (Claude Code subagent)
  start_hosts.sh / collect_episode.sh / import_subagent_trace.py   subagent-harness helpers
results/
  reference_verification.json, ladder.md   certified ladders (57 instances)
  subagent_runs/<episode>/         result.json, attack.py, trace.json, workspace/ for each pilot episode
  subagent_pilot/                  summary.md/json, efficiency.png, success_vs_difficulty.png
  subagent_audit.json, subagent_extrapolation.json
```

## Running

```bash
pip install anthropic numpy matplotlib sympy
python scripts/verify_reference.py --seeds 3              # certify the ladders (no API calls)
python -m harness.run_grid --rungs 1 --levels 8 --seeds 1 # smoke test (needs ANTHROPIC_API_KEY)
python -m harness.run_grid                                # pilot grid: Sonnet 5, effort medium, 2 seeds
python analysis/analyze.py && python analysis/audit.py && python analysis/extrapolate.py
```

## Evaluation protocol

- **Episode.** The model receives the task text and a live challenger, with budget B = 4·Q\*_UB.
  It has three tools:
  - `bash`: Git Bash on Windows, a fresh shell per call.
  - `write_file`.
  - `finish`.

  The prompt describes the interface, the cost model and the key-generation procedure. It never
  names a weakness or an attack.
- **Deliverable.** A self-contained `attack.py`, as in CryptanalysisBench. After the episode it
  is replayed, alone, against **3 fresh instances** of the same rung and level (new N, new
  labels, new x, same budget rule).
- **Metrics.**
  - Replay success rate.
  - Efficiency log₂(Q_model / Q\*_UB), taken over successful replays (the median of the three).
  - Whether the live instance was solved.
  - Optionally, the scaling fit across sizes.

## Honest limitations

- **Harbor.** CryptanalysisBench uses Harbor 0.13.1 with terminus-2. Harbor needs Docker, which
  was not available, so this pilot uses a minimal tool-use loop with the same shape: terminal
  tool, oracle over HTTP, self-contained attack script.
- **Isolation.** Isolation is at the process level, not a container. Secrets exist only in the
  challenger process's memory, and the agent's environment has no API keys. `audit.py` flags any
  command that touches paths outside the workspace or the admin endpoints.
- **Memorisation.** Pohlig–Hellman and BSGS are textbook, so rungs 1–2 test recognition more than
  discovery. Rungs 3–4 test combining attacks and less familiar structure.
- **Toy primitives.** GGM tasks are a calibration layer, not real-scheme cryptanalysis. The next
  step is to extend certified difficulty to real schemes. Where proofs are unavailable, the
  difficulty would come from estimators, e.g. the lattice estimator for LWE and
  CryptographicEstimators for decoding.
- **Harness actually used.** API credentials were unavailable, so the pilot's 19 episodes ran
  Sonnet 5 (medium effort) as Claude Code subagents driving the same challenger, task file and
  replay protocol (`scripts/subagent_episode.py`). The API harness is implemented and
  smoke-tested without model calls, but has not yet been run against a model.
- **Models.** The pilot runs Sonnet 5 only, at effort `medium`, to keep cost low. The harness
  also supports Opus (`--models opus sonnet`). CryptanalysisBench reports that Fable 5's safeguards
  blocked cryptanalysis runs. Refusals, if any, are recorded as results.
