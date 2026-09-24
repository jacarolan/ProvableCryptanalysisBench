import Mathlib.Data.ZMod.Basic

/-!
# The generic group model (trusted core)

A generic algorithm is a program over an *abstract* handle type `H`. It can only:

* create a new group element from existing ones: `mul a b` (a·b), `inv a` (a⁻¹) or
  `exp a k` (a^k for a public integer k). Each costs **one query**;
* test two handles for equality (`eq`), which is **free** (labels are compared locally);
* return a result.

An attack is polymorphic in `H` (`Attack` below), so it can never inspect a group element:
genericity holds by parametricity. `run N` interprets a program in the cyclic group of order
`N`, written additively as `ZMod N` (g ↦ 1, g^x ↦ x), and returns its result together with the
number of queries made. Submitting the answer costs one more query, added in the
specification.

This file, together with the specification in `GGM/DL.lean`, is the trusted base. Everything else in
a certificate is checked by Lean's kernel.
-/

namespace GGM

/-- A generic program with handle type `H` and result type `α`. -/
inductive Prog (H : Type) (α : Type) : Type where
  | ret : α → Prog H α
  | mul : H → H → (H → Prog H α) → Prog H α
  | inv : H → (H → Prog H α) → Prog H α
  | exp : H → ℤ → (H → Prog H α) → Prog H α
  | eq : H → H → (Bool → Prog H α) → Prog H α

namespace Prog

variable {H α β : Type}

/-- Sequencing of generic programs. -/
def bind : Prog H α → (α → Prog H β) → Prog H β
  | ret a, f => f a
  | mul a b k, f => mul a b (fun c => bind (k c) f)
  | inv a k, f => inv a (fun c => bind (k c) f)
  | exp a n k, f => exp a n (fun c => bind (k c) f)
  | eq a b k, f => eq a b (fun t => bind (k t) f)

instance : Monad (Prog H) where
  pure := ret
  bind := bind

/-- `a * b` as a one-query program. -/
def mulM (a b : H) : Prog H H := mul a b ret
/-- `a⁻¹` as a one-query program. -/
def invM (a : H) : Prog H H := inv a ret
/-- `a ^ k` as a one-query program. -/
def expM (a : H) (k : ℤ) : Prog H H := exp a k ret
/-- Free equality test of two handles. -/
def eqM (a b : H) : Prog H Bool := eq a b ret

end Prog

/-- A generic discrete-log attack: given handles for `g` and `h = g^x`, output a candidate `x`. -/
abbrev Attack : Type 1 := ∀ {H : Type}, H → H → Prog H ℕ

/-- Semantics in the cyclic group of order `N` (as `ZMod N`, g ↦ 1): result and query count. -/
def run (N : ℕ) {α : Type} : Prog (ZMod N) α → α × ℕ
  | .ret a => (a, 0)
  | .mul a b k => ((run N (k (a + b))).1, (run N (k (a + b))).2 + 1)
  | .inv a k => ((run N (k (-a))).1, (run N (k (-a))).2 + 1)
  | .exp a n k => ((run N (k ((n : ZMod N) * a))).1, (run N (k ((n : ZMod N) * a))).2 + 1)
  | .eq a b k => run N (k (decide (a = b)))

section lemmas
/-! Convenience lemmas (kernel-checked; not part of the trusted base). -/

variable {N : ℕ} {α β : Type}

@[simp] theorem run_ret (a : α) : run N (Prog.ret a : Prog (ZMod N) α) = (a, 0) := rfl

@[simp] theorem run_pure (a : α) : run N (pure a : Prog (ZMod N) α) = (a, 0) := rfl

@[simp] theorem run_mul (a b : ZMod N) (k : ZMod N → Prog (ZMod N) α) :
    run N (Prog.mul a b k) = ((run N (k (a + b))).1, (run N (k (a + b))).2 + 1) := rfl

@[simp] theorem run_inv (a : ZMod N) (k : ZMod N → Prog (ZMod N) α) :
    run N (Prog.inv a k) = ((run N (k (-a))).1, (run N (k (-a))).2 + 1) := rfl

@[simp] theorem run_exp (a : ZMod N) (n : ℤ) (k : ZMod N → Prog (ZMod N) α) :
    run N (Prog.exp a n k) =
      ((run N (k ((n : ZMod N) * a))).1, (run N (k ((n : ZMod N) * a))).2 + 1) := rfl

@[simp] theorem run_eq (a b : ZMod N) (k : Bool → Prog (ZMod N) α) :
    run N (Prog.eq a b k) = run N (k (decide (a = b))) := rfl

/-- Running a sequenced program: results thread through, query counts add. -/
theorem run_bind (p : Prog (ZMod N) α) (f : α → Prog (ZMod N) β) :
    run N (Prog.bind p f) =
      ((run N (f (run N p).1)).1, (run N p).2 + (run N (f (run N p).1)).2) := by
  induction p with
  | ret a => simp [Prog.bind]
  | mul a b k ih => simp [Prog.bind, ih]; omega
  | inv a k ih => simp [Prog.bind, ih]; omega
  | exp a n k ih => simp [Prog.bind, ih]; omega
  | eq a b k ih => simp [Prog.bind, ih]

@[simp] theorem run_bind' (p : Prog (ZMod N) α) (f : α → Prog (ZMod N) β) :
    run N (p >>= f) =
      ((run N (f (run N p).1)).1, (run N p).2 + (run N (f (run N p).1)).2) :=
  run_bind p f

@[simp] theorem run_mulM (a b : ZMod N) : run N (Prog.mulM a b) = (a + b, 1) := rfl
@[simp] theorem run_invM (a : ZMod N) : run N (Prog.invM a) = (-a, 1) := rfl
@[simp] theorem run_expM (a : ZMod N) (k : ℤ) : run N (Prog.expM a k) = ((k : ZMod N) * a, 1) := rfl
@[simp] theorem run_eqM (a b : ZMod N) : run N (Prog.eqM a b) = (decide (a = b), 0) := rfl

end lemmas

end GGM
