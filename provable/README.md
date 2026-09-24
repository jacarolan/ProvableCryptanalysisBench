# Proof-carrying generic discrete-log benchmark

This is the proof analogue of `../empirical`: the only problem is a uniformly random
discrete logarithm in a cyclic group of public prime order. There are no rungs.
An external subagent submits **an attack program and a Lean proof of its expected query
upper bound**, instead of executing an attack at every large security parameter.

## What is checked

For every prime order `p`, secret `x : Fin p`, and independent uniform seed `s : Fin seeds`:

1. The submitted program starts with handles for `g` and `g^x`.
2. Its output modulo `p` equals `x`, for **every** secret and seed.
3. Its exact expected query count over the uniform secret and seed is at most the
   submitted `Bound` expression evaluated at `p`.

The order can subsequently be sampled as any lambda-bit prime, as in the empirical
generator. Since the theorem covers each prime separately, it also covers any distribution
over those prime orders. `lambda` is the bit length of the group order, not claimed
cryptographic security bits. One proof covers every lambda; it is not re-proved for each size.

The semantics use exponents in `ZMod p` internally. The attack **cannot access them**:
it is a first-order, well-typed register program with only `mul`, `inv`, `exp`, `eq`, and
`ret`. Registers are `Fin n`; invalid handle indices are unrepresentable. Each group
operation costs one query, equality is free, and the checker adds one final submission.
This matches the empirical unit-cost-exponentiation convention.

There is no axiom asserting genericity by polymorphism. The restriction is in the program
syntax. Unlike the empirical random bitstring interface, this initial formal model permits
only equality on handles, not hashing/inspecting their bytes. Thus the transcript does not
depend on which injective encoding is used. Finite seeded randomization is supported; the
seed-space size is currently fixed for each certificate. Unbounded random tapes, potentially
nonterminating Las Vegas programs, and intermediate submit/guess oracles are not modeled.

## Harmonization with `../empirical`

The two branches share the problem, the cost model and the scoring axes. Only the evidence
differs: a measured run in empirical, a kernel-checked proof here.

| | empirical | provable |
|---|---|---|
| problem | random λ-bit prime N, uniform x, h = g^x | the same, for **every** prime N at once |
| cost model | mul/inv/exp = 1 query, equality free, +1 submission | identical (`GGM/Model.lean`, `queries`) |
| agent | Sonnet 5, effort medium, Claude Code subagent | identical provenance string (`run/episode.py`) |
| evidence | `attack.py`, replayed on 3 fresh instances | `Submission.lean`, re-checked from scratch |
| λ-bit primes | `ggm/instances.generate(lam, seed)` | same seeded sampler (`run/evaluate.py --lams`), λ up to 4096 |
| lower bound | `ggm/instances.lb_expected(N)` ≈ 0.94√N | imported from empirical (single source of truth) |
| results | `results/runs/<name>/result.json`, `trace.json` | same layout; plus `check.json` and the λ evaluation |
| plots | `queries.png`, `runtime.png`, `runtime_extrapolated.png` | `analysis/plot.py` → standalone `queries.png` (certified bound vs lower bound, λ = 16–256; certificates are evaluated to 4096 in `result.json`); no runtime plot, since one proof covers every λ |

**Wall-clock time.** Agent session time comes from the subagent transcript timestamps (first to
last event) in both branches. It is listed per proof in `results/summary.md`. It is not plotted
against λ, because one session and one proof check cover every λ. Cross-branch comparisons are
in `../headline_plots/`.

Episode names follow empirical: `sonnet_l<λ>_s<seed>` there, and `sonnet_proof_s<seed>` here,
because a proof is not tied to a λ.

```powershell
python -m run.episode --name sonnet_proof_s0 --prepare-only          # then give TASK.md to the subagent
python -m run.episode --name sonnet_proof_s0 --collect --transcript <agent-XXXX.jsonl>
python analysis/plot.py
```

## Architecture

| Empirical | Provable counterpart |
|---|---|
| `ggm/oracle.py` | `lean/GGM/Model.lean`: oracle-program semantics and query counting |
| `ggm/instances.py` | `lean/GGM/Certificate.lean`: uniform-secret problem and exact expectation |
| `run/prompts.py` | `run/prompts.py`: agent task and fixed proof contract |
| live oracle and fresh-instance replay | `run/check.py`: fresh compilation, type check, axiom audit |
| submitted `attack.py` | submitted `Submission.lean`, exporting `Submission.certificate` |
| workspace / `.stop` / `results/runs/<name>` | same external-subagent episode convention |
| measured attack runtime / queries | certified upper-bound expression and proof-checking time |

The existing rung-based Lean files are preserved in `archive/rungs/`, and the earlier
polymorphic-handle specification in `archive/v0_polymorphic/`. Neither is imported or accepted
by the new checker. Nothing in `../empirical` is modified by this folder; it is read for the
shared sampler, the lower bound and the comparison plots.

## Setup

Use Python 3.10+ (standard library only), Elan, and the pinned Lean 4.24.0 toolchain.
Mathlib and its transitive dependencies are pinned by `lean/lake-manifest.json`.

From `provable/lean`:

```powershell
lake exe cache get
lake build
```

From `provable`:

```powershell
python -m unittest discover -s tests -v
python -m run.check examples/Submission.lean --out results/example-check.json
python -m run.evaluate results/example-check.json --bits 32 64 128 256 512 --out results/example-bounds.json
```

`examples/Submission.lean` is a kernel-checked **exhaustive-search baseline**, with a loose
expected-query upper bound `p + 1` including submission. It proves the plumbing, not an
optimal attack or a tight average. In particular it is not a claimed BSGS or Pollard-rho result.
The negative fixture `tests/reject_wrong_bound.lean` must be rejected by `run.check`.

## Give a task to an external subagent

```powershell
python -m run.episode --name proof_001 --prepare-only   # default provenance: Sonnet 5 medium subagent; override with --model/--effort
```

Give the printed `TASK.md` path to the subagent. It writes `Submission.lean`, checks it with
the workspace's `check_submission.py`, and writes `summary.md` and `.stop` when finished.
The operator collects it with:

```powershell
python -m run.episode --name proof_001 --collect
```

Omit `--prepare-only` to have the host wait for `.stop` (or `--max-secs`) and then collect.
Existing workspaces/results are never silently deleted or reused. To retry, use a new name.
Model/effort fields are operator-provided provenance; this host does not launch or impersonate
a model. Use the actual configured model when dispatching the subagent externally.

## Submission interface

Import **only** `GGM.Certificate`. Define a computable `Submission.certificate : GGM.Certificate`.
It contains `seeds`, `seeds_pos`, `attack`, `bound`, `correct`, and `expected_le`.
The first handle is register 0 (`g`) and the second is register 1 (`h`). An operation pushes
its result at 0, shifting all old handles with `.succ`. An equality instruction branches
without creating a register or charging a query. See the example for recursive construction
and an induction proof. `expected_le_of_pointwise` converts a uniform pointwise cost upper
bound into a valid, possibly loose, expected bound.

`Bound` admits nonnegative constants, `order`, `sqrtOrder` (floor square root), addition,
multiplication, and rational division by a natural constant. Use `sqrtOrder + 1` for a
convenient upper bound on a ceiling square root. Division by zero is Lean's field zero,
so it cannot falsely certify a positive expected cost: the proof obligation still applies.

The checker exports only this small expression tree. Evaluating it is independent of the
number of operations the attack would execute. `--orders` evaluates at exact supplied
orders, conditionally on primality; it does not silently treat a probable prime as proved.
`--bits` evaluates the monotone expression at `2^lambda - 1`, an upper envelope for every
lambda-bit prime. This is **not** the average over sampled prime orders.

## Acceptance, provenance, and limits

- All submissions are compiled in a fresh temporary directory; submitted `.olean` files are ignored.
- Trusted modules are cached by source, compiler-version, and dependency-manifest hashes;
  compiled object hashes are checked before reuse. Each submission and audit is freshly compiled.
- The checker forces kernel checking (`-t0`), treats warnings as errors, and checks the
  transitive axioms of the certificate. Only `propext`, `Classical.choice`, and `Quot.sound`
  are accepted. `sorryAx`, native computation axioms, and arbitrary assumptions are rejected.
- The single import and source restrictions prevent ordinary attempts to redefine the task,
  bypass kernel checking, or spoof output. These restrictions deliberately exclude custom
  elaborators and unsafe/native proof mechanisms.
- Lean tactics are executable code. This is a **cooperative-agent harness, not an OS sandbox**.
  Run genuinely hostile submissions in a separate isolated account/container. The pinned
  compiler, standard axioms, Mathlib dependencies, checker and model definitions are trusted.
- A proof certifies the Lean program, not a separately written Python attack. No Python-to-Lean
  equivalence is claimed. Query cost excludes local computation, memory, and compilation time.
- `verification_wall_secs` is proof-checking time, never an attack runtime measurement.
- The new core proves submitted upper bounds; it does not yet formalize the generic birthday
  lower bound. Any numerical comparison to the empirical lower bound must say so explicitly.
- Finite samples and low success rates cannot substitute for the required pointwise correctness
  theorem. There is no averaging only over successful attacks.

Large orders are feasible because proofs reason symbolically. A submission that unfolds or
enumerates every secret during proof checking can still time out; large-parameter efficiency
is an intended use of the contract, not a guarantee about arbitrary proof scripts.
