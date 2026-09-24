import GGM.Certificate

/-! A deliberately simple fully proved baseline: exhaustive search, not a
claimed square-root attack. This demonstrates the submission contract. -/
namespace Submission
open GGM

def scan (fuel start : Nat) {n : Nat} (g h : Fin n) : Program n :=
  match fuel with
  | 0 => .ret 0
  | fuel + 1 => .exp g (start : Int)
      (.eq 0 h.succ (.ret start) (scan fuel (start + 1) g.succ h.succ))

theorem scan_cost (fuel start : Nat) {p n : Nat} (g h : Fin n) (env : Registers p n) :
    (run (scan fuel start g h) env).2 ≤ fuel := by
  induction fuel generalizing start n with
  | zero => simp [scan, run]
  | succ fuel ih =>
    simp only [scan, run]
    split
    · simp
    · have hi := ih (start + 1) g.succ h.succ
          (Fin.cons (((start : Int) : ZMod p) * env g) env)
      omega

theorem scan_correct (fuel start : Nat) {p n : Nat} (g h : Fin n)
    (env : Registers p n) (x : Fin p) (hg : env g = 1) (hh : env h = (x.val : ZMod p))
    (lo : start ≤ x.val) (hi : x.val < start + fuel) :
    (run (scan fuel start g h) env).1 % p = x.val := by
  induction fuel generalizing start n with
  | zero => omega
  | succ fuel ih =>
    simp only [scan, run]
    split
    next he =>
      simp only [Fin.cons_zero, Fin.cons_succ, hg, hh, mul_one, Int.cast_natCast] at he
      have hv := congrArg ZMod.val he
      simp only [ZMod.val_natCast] at hv
      simpa [Nat.mod_eq_of_lt x.isLt] using hv
    next he =>
      apply ih (start + 1) g.succ h.succ
        (Fin.cons (((start : Int) : ZMod p) * env g) env)
      · simpa using hg
      · simpa using hh
      · have hne : start ≠ x.val := by
          intro hx
          apply he
          simp [hg, hh, hx]
        omega
      · omega

def attack : Attack 1 := fun p _ => scan p 0 0 1

def certificate : Certificate where
  seeds := 1
  seeds_pos := by decide
  attack := attack
  bound := .add .order (.constant 1)
  correct := by
    intro p hp s x
    apply scan_correct p 0 0 1 (initial p x) x
    · rfl
    · rfl
    · omega
    · omega
  expected_le := by
    intro p hp
    apply expected_le_of_pointwise attack hp.pos (by decide)
    intro s x
    have hc := scan_cost p 0 (0 : Fin 2) 1 (initial p x)
    change (((run (scan p 0 0 1) (initial p x)).2 + 1 : Nat) : Rat) ≤ (p : Rat) + 1
    exact_mod_cast Nat.add_le_add_right hc 1

end Submission
