import Mathlib.Data.ZMod.Basic
import Mathlib.Data.Fin.VecNotation

/-! Register-machine syntax for generic-group attacks. Programs never receive the
semantic values of handles. Only an explicit equality instruction can branch on them.
The newest oracle result is register 0; old registers are shifted by one.
Local computation and equality are free. Each mul/inv/exp costs one query.
-/
namespace GGM

inductive Program : Nat → Type where
  | ret {n : Nat} : Nat → Program n
  | mul {n : Nat} : Fin n → Fin n → Program (n + 1) → Program n
  | inv {n : Nat} : Fin n → Program (n + 1) → Program n
  | exp {n : Nat} : Fin n → Int → Program (n + 1) → Program n
  | eq {n : Nat} : Fin n → Fin n → Program n → Program n → Program n

abbrev Registers (p n : Nat) := Fin n → ZMod p

def run {p n : Nat} : Program n → Registers p n → Nat × Nat
  | .ret a, _ => (a, 0)
  | .mul a b next, env =>
      let r := run next (Fin.cons (env a + env b) env)
      (r.1, r.2 + 1)
  | .inv a next, env =>
      let r := run next (Fin.cons (-env a) env)
      (r.1, r.2 + 1)
  | .exp a k next, env =>
      let r := run next (Fin.cons ((k : ZMod p) * env a) env)
      (r.1, r.2 + 1)
  | .eq a b yes no, env => if env a = env b then run yes env else run no env

def initial (p : Nat) (x : Fin p) : Registers p 2 := ![1, (x.val : ZMod p)]

/-- Public order and public random seed may determine a program, never the secret. -/
abbrev Attack (seeds : Nat) := Nat → Fin seeds → Program 2

def outcome {seeds : Nat} (attack : Attack seeds) (p : Nat) (s : Fin seeds)
    (x : Fin p) : Nat × Nat := run (attack p s) (initial p x)

/-- Includes one final submission, matching the empirical cost convention. -/
def queries {seeds : Nat} (attack : Attack seeds) (p : Nat) (s : Fin seeds)
    (x : Fin p) : Nat := (outcome attack p s x).2 + 1

end GGM
