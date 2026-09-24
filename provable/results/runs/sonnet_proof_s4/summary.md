# Summary

## Attack

A baby-step giant-step (BSGS) discrete-log attack, certified for every prime
order `p` and every secret/seed.

Because registers in this model already carry discrete logs directly
(`initial` sets register 0 to `1` -- the log of `g` -- and register 1 to `x`
-- the log of `h`), every group operation the attack performs is literal
`ZMod p` arithmetic, so the whole correctness proof is elementary number
theory; no group-theoretic reasoning about `g`/`h` is needed.

Let `m = sqrt(p) + 1`, so `p < m * m`.

1. **Baby table** (`m` queries): compute `g^0, g^1, ..., g^(m-1)` via `m`
   calls to `exp`, tagging each new register with its exponent.
2. **Setup** (2 queries): compute `g^m` (`exp`) and its inverse `g^(-m)`
   (`inv`).
3. **Giant loop** (up to `m - 1` queries): starting from `y_0 = h`, at each
   step `j` compare `y_j` against every baby-table entry (`eq`, free); on a
   match with entry `i`, return `i + j*m`; otherwise advance
   `y_{j+1} = y_j * g^(-m)` (`mul`, 1 query) and continue.

Worst case this uses `m + 2 + (m - 1) = 2m + 1` group operations, plus the
one mandatory submission query, i.e. `2m + 2 = 2*sqrt(p) + 4` in the worst
case; the certified (safely rounded) bound is `2*sqrtOrder + 5`.

### Why any match is a correct match

Registers are `ZMod p` values, so `y_j` equals `x - j*m` and baby entry `i`
equals `i` (as `ZMod p` elements). An `eq` match at step `j` against entry
`i` means `i == x - j*m (mod p)`, i.e. `i + j*m == x (mod p)`, so
`(i + j*m) % p = x` because `0 <= x < p`. This holds for *any* match, not
just the "intended" one at `j = x / m, i = x % m` -- so the proof never
needs to reason about which match is found first, only that the intended
one (which always exists, since `x/m < m` follows from `p < m*m`) is
reached within the fuel budget.

## Bound and acceptance

Certified bound: `2 * sqrtOrder + 5` (a `Bound` expression evaluated
symbolically for every prime `p`, never executed). `check_submission.py`
reports `status: "accepted"`, with the certificate depending only on the
allowed axioms `[propext, Classical.choice, Quot.sound]`, and the exported
`GGM_CERT_JSON` bound matching `2*sqrtOrder + 5`.

This is roughly 2.1x the generic lower bound of `~0.94*sqrt(N)` -- much
tighter than the baseline exhaustive-search bound of `N + 1`, though not as
tight as an optimally-tuned BSGS/kangaroo variant could in principle
achieve (e.g. by using half-size baby tables and a distinguished-point
walk), which was not pursued here in the interest of keeping the Lean
proof tractable.

## Limitations / notes

- The proof is fully symbolic in `p` (via `Nat.sqrt`), so it scores at
  every requested security parameter from one certificate, as required.
- The attack is deterministic (`seeds := 1`); no randomness is used.
- No `sorry`, no new axioms, no `native_decide`.
- The `Nat.Prime p` hypothesis available in `Certificate.correct` is
  actually unused by the correctness proof: BSGS over the additive group
  `ZMod p`, as modeled here, works for *any* modulus `p > 0`, not just
  primes. (Only `p > 0`, needed for `ZMod p` casts, is used, and that
  already follows automatically since `Certificate` is only exercised at
  prime `p`.)
