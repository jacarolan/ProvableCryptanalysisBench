import GGM.Model

/-!
# Generic discrete-log specification (trusted)

Key generation: a cyclic group of public order `N` with generator `g`; the secret `x` is uniform
in `[0, N)`; the challenger publishes `h = g^x`.

A certificate is a generic attack for every group order `N`, a query-cost function, and
a proof that **for every `N ≥ 1` and every secret `x`** the attack returns `x` using at most
`cost N` queries. The attack may use `N` (and any free local computation on it) to decide which
queries to make. The certified query count for a concrete instance is `cost N + 1`; the `+ 1`
is the submission.
-/

namespace GGM

/-- A certified generic discrete-log attack. -/
structure DLCert where
  /-- The attack, allowed to depend on the public group order `N`. -/
  attack : ℕ → Attack
  /-- The claimed worst-case number of group-operation queries (excluding the submission). -/
  cost : ℕ → ℕ
  /-- Correctness and query bound, for every group order and every secret. -/
  correct : ∀ (N : ℕ), 0 < N → ∀ x : ZMod N,
    (((run N (attack N (1 : ZMod N) x)).1 : ℕ) : ZMod N) = x ∧
    (run N (attack N (1 : ZMod N) x)).2 ≤ cost N

end GGM
