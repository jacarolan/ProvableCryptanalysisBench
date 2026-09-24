import GGM.Model
import Mathlib.Algebra.BigOperators.Field
import Mathlib.Data.Nat.Prime.Basic
import Mathlib.Data.Nat.Sqrt
import Mathlib.Tactic

namespace GGM
open scoped BigOperators

/-- A small total expression language: evaluating a claimed bound never runs the attack. -/
inductive Bound where
  | constant : Nat → Bound
  | order : Bound
  | sqrtOrder : Bound
  | add : Bound → Bound → Bound
  | mul : Bound → Bound → Bound
  | div : Bound → Nat → Bound
  deriving Repr

def Bound.eval (p : Nat) : Bound → Rat
  | .constant k => k
  | .order => p
  | .sqrtOrder => Nat.sqrt p
  | .add a b => a.eval p + b.eval p
  | .mul a b => a.eval p * b.eval p
  | .div a k => a.eval p / k

/-- Exact mean over a uniform secret and independent uniform finite seed.
This is a specification, not an executable large-parameter benchmark. -/
def expectedQueries {seeds : Nat} (attack : Attack seeds) (p : Nat) : Rat :=
  (∑ s : Fin seeds, ∑ x : Fin p, (queries attack p s x : Rat)) / (p * seeds : Nat)

/-- A proof-bearing attack family for EVERY prime order and EVERY secret/seed.
Pointwise correctness prevents a low average obtained by failing on hard secrets.
No conjectured bound, sampled runtime, or Python implementation is certified here. -/
structure Certificate where
  seeds : Nat
  seeds_pos : 0 < seeds
  attack : Attack seeds
  bound : Bound
  correct : ∀ p, Nat.Prime p → ∀ (s : Fin seeds) (x : Fin p),
    (outcome attack p s x).1 % p = x.val
  expected_le : ∀ p, Nat.Prime p → expectedQueries attack p ≤ bound.eval p

theorem expected_le_of_pointwise {seeds p : Nat} (attack : Attack seeds)
    (hp : 0 < p) (hs : 0 < seeds) (b : Rat)
    (h : ∀ s x, (queries attack p s x : Rat) ≤ b) :
    expectedQueries attack p ≤ b := by
  unfold expectedQueries
  have hden : (0 : Rat) < (p * seeds : Nat) := by exact_mod_cast Nat.mul_pos hp hs
  apply (div_le_iff₀ hden).2
  calc
    (∑ s : Fin seeds, ∑ x : Fin p, (queries attack p s x : Rat))
        ≤ ∑ _s : Fin seeds, ∑ _x : Fin p, b := by
          apply Finset.sum_le_sum
          intro s _
          exact Finset.sum_le_sum (fun x _ => h s x)
    _ = b * (p * seeds : Nat) := by simp; ring

end GGM
