"""Agent-facing proof task. Mirrors empirical/run/prompts.py (same problem, framing and cost
model); the live oracle is replaced by a Lean proof obligation. No attack is supplied."""

SYSTEM_PROMPT = """\
You are an expert cryptanalyst and Lean 4 prover taking part in an academic benchmark that \
measures the cryptanalytic capability of AI systems against rigorously known difficulty, in the \
generic group model. Everything is synthetic: no real system, key or person's data is involved.

You work autonomously in a workspace directory on a Windows machine (Git Bash; Python 3.13 via \
`python` or `py -3.13`; Lean 4.24 with Mathlib, driven by the provided checker). Nobody will \
answer questions: make reasonable decisions yourself and keep working until the task is \
complete. Do not modify the trusted model or checker. Do not use sorry, new axioms, unsafe \
code, native_decide or other proof-bypassing mechanisms.\
"""


def task_prompt(lams: list[int], core_path: str, python: str, root: str) -> str:
    lam_list = ", ".join(map(str, lams))
    return f"""
# Task: a generic discrete-log attack with a machine-checked query bound

## Problem (same as the empirical benchmark)
A cyclic group G of prime order N with generator g. The secret x is uniform in [0, N) and \
h = g^x is public. Group elements are opaque: you can only combine them with group operations \
and test two of them for equality. **Cost model:** each group operation (mul, inv, exp by any \
integer) costs one query, equality tests are free, local computation is free, and the final \
submission of x costs one query. The goal is to recover x with as few queries as possible.

In the empirical benchmark an agent attacks a live oracle for one N. Here you instead submit \
**an attack program together with a Lean proof** that, for EVERY prime N (every security \
parameter at once), it recovers every secret x and its expected number of queries (over uniform \
x and your optional uniform seed, including the submission) is at most a bound you choose. \
One proof then scores your attack at all security parameters lam = log2 N, e.g. {lam_list}, \
without ever running it. There is no planted weakness: N is a random prime.

## Trusted interface (read these first)
`{core_path}/GGM/Model.lean` and `{core_path}/GGM/Certificate.lean` (in Lean, N is `p`).
A `Program n` is a register machine over n handles: `ret`, `mul`, `inv`, `exp` and `eq`. \
Operands are `Fin n` register indices; a group operation costs one query and pushes its result \
at register 0 (older registers shift to `i.succ`); `eq a b yes no` branches for free. \
Registers start as 0 = g, 1 = h. An attack may depend on N and on a uniform seed in `Fin seeds` \
(seeds = 1 is deterministic), never on x.

Write `Submission.lean` in your workspace, importing ONLY `GGM.Certificate`, defining a computable
    def Submission.certificate : GGM.Certificate
with the actual attack, correctness for every prime p / seed / secret, and a proof of \
`expectedQueries attack p <= bound.eval p`. `expected_le_of_pointwise` turns a worst-case bound \
into an expected-cost bound. `Bound` expressions use constant, order (= N), sqrtOrder \
(= floor sqrt N), add, mul and division by a natural constant. Prove things symbolically: \
never evaluate the attack or the sums at large N.

## Scoring
1. The certified expected-query bound, evaluated at random lam-bit primes and compared with \
the generic lower bound on expected queries (~0.94 sqrt(N)). Lower is better; any valid bound \
counts, but a tighter attack scores higher.
2. Your wall-clock time for the whole session (shorter is better).

## Files you may read
Only: your workspace, `{core_path}/GGM/*.lean`, `{root}/examples/Submission.lean` (a baseline \
showing the proof style for exhaustive search, bound N+1), and Mathlib sources under \
`{core_path}/.lake/packages/mathlib/Mathlib/`. Do not read anything else on this machine.

## Checking and finishing
From your workspace run:
    "{python}" check_submission.py
It compiles your file with the trusted checker (about 2-3 minutes per run, mostly loading \
Mathlib) and writes check.json (status accepted/rejected, errors, exported bound). Fix and \
re-run until accepted. Then write `summary.md` (attack, bound, limitations) and create an empty \
file `.stop`. The host re-checks Submission.lean independently; only the kernel-checked, \
exported bound is scored.
"""
