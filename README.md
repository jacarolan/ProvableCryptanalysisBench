# ProvableCryptanalysisBench

This repository is a pilot project towards measuring AI cryptanalytic capability against **rigorously known difficulty**,
using random instances of discrete-log in the generic group model (GGM). In the GGM the optimal query cost is
proven, so attacks are scored against a hard lower bound. We compare two approaches:
1. Empirically testing attacks on actual security games through code.
2. Provable attacks where the agent submits a Lean proof of an attack.

For this toy example we find the second to be far more scalable, allowing analysis of realistic security parameters that would take beyond the age of the universe (on a laptop) to evaluate empirically. Note that λ = log_2 N is the security parameter, where N is the order of the group and taken to be prime. The discrete logarithm problem in this model has approximately λ/2 bits of security due to the birthday bound.


| Folder | What it is |
|---|---|
| [`empirical/`](empirical/README.md) | Plain generic discrete log in random prime-order groups. Sonnet 5 (medium effort) subagents write attacks, which are replayed on fresh instances. Results are plotted as queries and wall-clock time against the security parameter λ, next to the proven lower bound on expected queries. |
| [`provable/`](provable/README.md) | The same problem, but each Sonnet 5 subagent submits a Lean 4 attack program together with a kernel-checked proof of its expected query bound for **every** prime N. One proof therefore scores the attack at every λ up to 4096 without running it. |
| [`headline_plots/`](headline_plots/make_headline.py) | Primary figures (λ = 16–256): queries vs λ (lower bound, empirical dots, provable curve), empirical runtime extrapolated to λ = 256, and a table of the provable runtimes. Regenerate with `py -3.13 headline_plots/make_headline.py`. |
