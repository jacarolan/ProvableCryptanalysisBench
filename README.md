# ProvableCryptanalysisBench

This repository measures AI cryptanalytic capability against **rigorously known difficulty**,
using discrete-log tasks in the generic group model (GGM). In the GGM the optimal query cost is
a theorem, so an agent's attack can be scored against a proven lower bound instead of an
estimate.

| Folder | What it is |
|---|---|
| [`empirical/`](empirical/README.md) | **Current.** Plain generic discrete log in random prime-order groups. Sonnet 5 (medium effort) subagents write attacks, which are replayed on fresh instances. Results are plotted as queries and wall-clock time against the security parameter λ, next to the proven lower bound on expected queries. |
| `provable/` | **In progress.** A Lean 4 + Mathlib formalization of the GGM (`provable/lean/GGM/Model.lean`), so agents can *prove* their attack's query bound for all instances. This lets results scale to λ = 128 without running the attack. |
| `legacy_rungs/` | Earlier design with four "rungs" of planted structure (smooth order, short exponent, both combined, Cheon auxiliary input), certified ladders, and the Sonnet subagent results. Kept for reference; its code still runs from inside that folder. |
