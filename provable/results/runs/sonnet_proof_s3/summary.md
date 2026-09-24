# Baby-step giant-step attack, certified for every prime order

## Attack

Registers are elements of `(ZMod p, +)`, with `g = 1` and `h = x`. Let
`m = floor(sqrt p) + 1`.

1. **Baby steps.** Build `m` registers holding `0, 1, ..., m-1` via `exp g i` for
   `i = 0, ..., m-1` (`m` queries). Since `g` always holds `1`, `exp g i` computes
   exactly `i`.
2. **Giant steps.** Compute a register holding `-m` via one more `exp g (-m)`
   (1 query). Starting from `giant_0 = h` (= `x`, free), repeatedly multiply by
   the `-m` register to get `giant_{j+1} = giant_j - m` (up to `m-1` further
   queries).
3. **Matching.** At each giant step `j`, compare (for free, via `eq`) `giant_j`
   against every baby register. Writing `x = i + j*m` by Euclidean division
   (`i = x mod m < m`, `j = x div m < m`, valid because `x < p < m*m`), the
   match occurs exactly at `j = x div m`, `i = x mod m`, and the program
   returns the literal `j*m + i = x`.

Total group operations: `m` (babies) + `1` (the `-m` constant) + at most
`m - 1` (giant steps) `= 2m`, plus 1 for the final submission. Since
`m = floor(sqrt p) + 1`, this is `2*floor(sqrt p) + 3` group operations, i.e.
`2*floor(sqrt p) + 4` total queries in the worst case, certified pointwise
(hence also in expectation via `expected_le_of_pointwise`).

## Certified bound

`bound.eval p = 2 * sqrtOrder + 4`, i.e. about `2*sqrt(N)` queries -- well
below the naive `N+1` baseline and about `2/0.94 ~= 2.13x` the generic lower
bound `~0.94*sqrt(N)`.

`check.json` reports `"status": "accepted"` with this exact bound
(`{"op":"add","a":{"op":"mul","a":{"op":"constant","value":2},"b":{"op":"sqrtOrder"}},"b":{"op":"constant","value":4}}`),
using only the allowed axioms `propext`, `Classical.choice`, `Quot.sound`
(no `sorry`, no extra axioms, no `native_decide`).

## Correctness proof sketch

* `checkBabies` (free equality cascade over the `m` labeled baby registers)
  either returns early with the label of a match, or falls through unchanged
  in cost -- proved by `checkBabies_cost`/`checkBabies_correct`/`checkBabies_none`.
* `giantLoop` maintains the invariant that the `giant` register holds
  `x - j*m` (as a `Nat` difference, valid since `j*m <= x` is an invariant) and
  `step` holds `-m`; `giantLoop_correct` shows it terminates with the exact
  value `x` within `m` outer iterations, using that `m <= p` (so baby labels
  `0..m-1` are pairwise distinct mod `p`) and `p < m*m` (so every `x < p` has
  a valid `(i,j)` decomposition with `i, j < m`).
* `buildBabies_correct`/`buildBabies_cost` extend this through the baby-step
  construction phase by induction on the number of remaining babies to build,
  tracking that the accumulated labeled list is exactly `0, ..., (m - rem - 1)`.
* The two facts `m <= p` and `p < m*m` for `m = floor(sqrt p) + 1` come from
  Mathlib's `Nat.sqrt_lt_self` and `Nat.lt_succ_sqrt`.

## Limitations / notes

* The constant factor `2` (from doing baby steps and giant steps as two
  separate `O(sqrt p)` passes with no register reuse) is not optimized away;
  a more careful interleaving could in principle approach the
  `~0.94*sqrt(N)` lower bound more closely, but was not attempted here in the
  interest of keeping the register-index bookkeeping (and its Lean proof)
  tractable.
* The attack is deterministic (`seeds = 1`); no randomization is used.
* All reasoning is symbolic in `p`; the program itself is never evaluated at
  a concrete large `N` (its size is linear in `sqrt N`, which is already
  astronomically large for cryptographic parameters, but this never causes
  an issue since Lean only reasons about it via the recursion equations).
