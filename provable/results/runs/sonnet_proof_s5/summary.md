# Baby-step giant-step generic discrete-log attack

## Attack

For prime order `p`, let `m = Nat.sqrt p + 1` (so `p < m*m`, `Nat.lt_succ_sqrt`).

1. **Baby steps.** Build `m` registers holding the constants `0, 1, ..., m-1` by repeated
   `exp` on the constant-`1` register (`m` queries).
2. **Constant `-m`.** Build one more register holding `-m` via `exp` (1 query).
3. **Giant steps.** Starting from `y := h` (free, register 1), at each step `j` compare
   `y` against every baby register (`eq` is free). A match with baby value `v` means
   `x = v + j*m (mod p)`, so return the literal `v + j*m`. Otherwise replace `y` by
   `y + (-m)` (1 query) and continue with `j+1`.

Since every `x < p` can be written as `x = i0 + j0*m` with `i0 = x % m < m` and
`j0 = x / m < m` (using `p < m*m`), a match is guaranteed by giant step `j0 <= m-1`.
The very first giant step (`j=0`, `y=h`) is free; each subsequent step costs one `mul`.
The attack is fully deterministic (`seeds = 1`).

Worst-case query count, for every `x`:
`m` (baby `exp`s) `+ 1` (the `-m` constant) `+ (m-1)` (giant-step `mul`s, at most)
`+ 1` (submission) `= 2*m + 1 = 2*(sqrtOrder + 1) + 1 = 2*sqrtOrder + 3`.

This is a *worst-case, pointwise* bound (not just an average), so
`expected_le_of_pointwise` applies directly to certify the expected-query bound.

## Certified bound

`bound = 2 * sqrtOrder + 3` (i.e. `Bound.add (Bound.mul (Bound.constant 2) Bound.sqrtOrder) (Bound.constant 3)`),
proved in `Submission.lean` via:

- `program_correct : forall p, Nat.Prime p -> forall x : Fin p, (run (program p) (initial p x)).1 % p = x.val`
  -- full correctness for every prime order and every secret, proved via a baby-step /
  giant-step correctness argument (`babies_correct`, `giant_sound`, `testChain_value`,
  `testChain_sound`) that never evaluates the attack or runs any search -- it is a purely
  symbolic argument about `x = i0 + j0*m` and register values mod `p`.
- `program_cost : forall p x, (run (program p) (initial p x)).2 + 1 <= 2*(Nat.sqrt p + 1) + 1`
  -- a worst-case (not just average) query bound, proved by structural induction on the
  baby/giant recursion (`babies_cost`, `giant_cost`, `testChain_cost`).
- `certificate.expected_le` combines these via `expected_le_of_pointwise` (seeds = 1, so
  the "expectation" is just this single deterministic value).

`check_submission.py` reports `status: "accepted"` with exported bound
`2*sqrtOrder + 3`, which is asymptotically `~2*sqrt(N)` -- about twice the generic lower
bound (`~0.94*sqrt(N)`), and far better than the `N+1` exhaustive-search baseline.

## Limitations / notes

- The constant factor (`2*sqrt(N) + 3`) is not optimized; a tighter Shanks-style
  baby-step/giant-step variant (e.g. balancing baby/giant step counts more precisely)
  could shave off a small constant, but was not pursued further given the proof
  engineering cost.
- The bound is a genuine worst-case bound (holds for every secret `x` and the single
  seed), not merely an average, so it is a strictly stronger guarantee than the task
  requires.
- No `sorry`, no new axioms, no `native_decide`; only the standard trusted axioms
  (`propext`, `Classical.choice`, `Quot.sound`) used transitively by Mathlib appear in
  the dependency check.
