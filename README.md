# ProvableCryptanalysisBench

This repository measures AI cryptanalytic capability against **rigorously known difficulty**,
using discrete-log tasks in the generic group model (GGM). In the GGM the optimal query cost is
a theorem, so an agent's attack can be scored against a proven lower bound instead of an
estimate.

| Folder | What it is |
|---|---|
| [`empirical/`](empirical/README.md) | **Current.** Plain generic discrete log in random prime-order groups. Sonnet 5 (medium effort) subagents write attacks, which are replayed on fresh instances. Results are plotted as queries and wall-clock time against the security parameter λ, next to the proven lower bound on expected queries. |
| [`provable/`](provable/README.md) | The same problem, but each Sonnet 5 subagent submits a Lean 4 attack program together with a kernel-checked proof of its expected query bound for **every** prime N. One proof therefore scores the attack at every λ up to 4096 without running it. |
| [`headline_plots/`](headline_plots/make_headline.py) | Cross-branch figures (λ = 16–256, linear λ axis): queries vs λ (lower bound, empirical dots, provable curve), empirical runtime extrapolated to λ = 256, and a table of the provable runtimes. Regenerate with `py -3.13 headline_plots/make_headline.py`. |
| `legacy_rungs/` | Earlier design with four "rungs" of planted structure (smooth order, short exponent, both combined, Cheon auxiliary input), certified ladders, and the Sonnet subagent results. Kept for reference; its code still runs from inside that folder. |
