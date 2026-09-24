import GGM.Certificate

/-! Baby-step giant-step generic discrete-log attack.

Registers carry discrete logs directly (`initial` sets register 0 = 1, the
log of `g`, and register 1 = `x`, the log of `h`), so every group operation
is literal `ZMod p` arithmetic and the whole proof is elementary number
theory: no group-theoretic reasoning about `g` and `h` is needed.

Let `m = sqrt p + 1` (so `p < m * m`). We build a "baby" table of the `m`
values `0, 1, ..., m-1` (the logs of `g^0, ..., g^(m-1)`), then walk a
"giant" sequence `y_j = x - j*m` for `j = 0, ..., m-1`, comparing `y_j`
against every baby entry. Since `x = (x % m) + (x / m) * m` with
`x % m < m` and `x / m < m` (as `p < m * m`), the giant step `j = x / m`
is guaranteed to match baby entry `i = x % m`. Conversely *any* register
match, at any `j`, already certifies the answer: if `y_j = i` for baby
entry `i` then `i + j * m ≡ x (mod p)`, so `(i + j * m) % p = x` because
`x < p`. Correctness therefore never needs to reason about *which* match
is found first, only that some match exists within the fuel bound. -/
namespace Submission
open GGM

/-- Walk the baby table looking for a register equal to `y`; `cont` runs if
none of them match. A match at `(b, i)` answers `i + j * m`. -/
def checkBaby (m : Nat) {n : Nat} (baby : List (Fin n × Nat)) (y : Fin n) (j : Nat)
    (cont : Program n) : Program n :=
  match baby with
  | [] => cont
  | (b, i) :: rest => Program.eq y b (Program.ret (i + j * m)) (checkBaby m rest y j cont)

/-- Giant-step loop. `y` holds (as a register value) `x - j*m`, `ginv` holds
`-m`. Each round checks the baby table, then advances `y` by `ginv`. -/
def giantLoop (m : Nat) (fuel j : Nat) {n : Nat} (y ginv : Fin n)
    (baby : List (Fin n × Nat)) : Program n :=
  match fuel with
  | 0 => Program.ret 0
  | fuel + 1 =>
      checkBaby m baby y j
        (Program.mul y ginv
          (giantLoop m fuel (j + 1) (0 : Fin (n + 1)) ginv.succ
            (baby.map (fun q => (q.1.succ, q.2)))))

/-- After the baby table is built, compute `g^m`, its inverse, and start the
giant-step loop from `h`. `n` is explicit here so this can be used directly
as the continuation passed to `babyBuild`. -/
def gmStart (m : Nat) (n : Nat) (g h : Fin n) (baby : List (Fin n × Nat)) : Program n :=
  Program.exp g (m : Int)
    (Program.inv (0 : Fin (n + 1))
      (giantLoop m m 0 (h.succ.succ : Fin (n + 2)) (0 : Fin (n + 2))
        (baby.map (fun q => (q.1.succ.succ, q.2)))))

/-- Build the baby table `g^0, ..., g^(fuel-1)` (tagging each new register
with its exponent starting at `idx`), then hand off to `k`. -/
def babyBuild (fuel idx : Nat) {n : Nat} (g h : Fin n) (acc : List (Fin n × Nat))
    (k : (n' : Nat) → Fin n' → Fin n' → List (Fin n' × Nat) → Program n') : Program n :=
  match fuel with
  | 0 => k n g h acc
  | fuel + 1 =>
      Program.exp g (idx : Int)
        (babyBuild fuel (idx + 1) g.succ h.succ
          ((0, idx) :: acc.map (fun q => (q.1.succ, q.2))) k)

def buildAttack (p : Nat) : Program 2 :=
  babyBuild (p.sqrt + 1) 0 (0 : Fin 2) (1 : Fin 2) [] (gmStart (p.sqrt + 1))

def attack : Attack 1 := fun p _ => buildAttack p

/-! ### Cost bound -/

lemma checkBaby_cost {p m n : Nat} (baby : List (Fin n × Nat)) (y : Fin n) (j : Nat)
    (cont : Program n) (env : Registers p n) :
    (run (checkBaby m baby y j cont) env).2 ≤ (run cont env).2 := by
  induction baby with
  | nil => simp [checkBaby]
  | cons hd tl ih =>
    obtain ⟨b, i⟩ := hd
    simp only [checkBaby, run]
    split
    · simp
    · exact ih

lemma giantLoop_cost {p : Nat} (m fuel : Nat) :
    ∀ (j : Nat) {n : Nat} (y ginv : Fin n) (baby : List (Fin n × Nat)) (env : Registers p n),
    (run (giantLoop m fuel j y ginv baby) env).2 ≤ fuel := by
  induction fuel with
  | zero => intro j n y ginv baby env; simp [giantLoop, run]
  | succ fuel ih =>
    intro j n y ginv baby env
    simp only [giantLoop]
    have h1 := checkBaby_cost (p := p) (m := m) baby y j
      (Program.mul y ginv (giantLoop m fuel (j + 1) (0 : Fin (n + 1)) ginv.succ
        (baby.map (fun q => (q.1.succ, q.2))))) env
    have h2 := ih (j + 1) (0 : Fin (n + 1)) ginv.succ
      (baby.map (fun q => (q.1.succ, q.2))) (Fin.cons (env y + env ginv) env)
    simp only [run] at h1
    omega

lemma babyBuild_cost {p : Nat} (fuel : Nat) :
    ∀ (idx : Nat) {n : Nat} (g h : Fin n) (acc : List (Fin n × Nat)) (env : Registers p n)
    (k : (n' : Nat) → Fin n' → Fin n' → List (Fin n' × Nat) → Program n') (B : Nat),
    (∀ (n' : Nat) (g' h' : Fin n') (acc' : List (Fin n' × Nat)) (env' : Registers p n'),
      (run (k n' g' h' acc') env').2 ≤ B) →
    (run (babyBuild fuel idx g h acc k) env).2 ≤ fuel + B := by
  induction fuel with
  | zero => intro idx n g h acc env k B hk; simpa [babyBuild] using hk n g h acc env
  | succ fuel ih =>
    intro idx n g h acc env k B hk
    simp only [babyBuild, run]
    have := ih (idx + 1) g.succ h.succ ((0, idx) :: acc.map (fun q => (q.1.succ, q.2)))
      (Fin.cons (((idx : Int) : ZMod p) * env g) env) k B hk
    omega

lemma buildAttack_cost {p : Nat} (env : Registers p 2) :
    (run (buildAttack p) env).2 ≤ 2 * (p.sqrt + 1) + 2 := by
  unfold buildAttack
  have hk : ∀ (n' : Nat) (g' h' : Fin n') (acc' : List (Fin n' × Nat)) (env' : Registers p n'),
      (run (gmStart (p.sqrt + 1) n' g' h' acc') env').2 ≤ (p.sqrt + 1) + 2 := by
    intro n' g' h' acc' env'
    unfold gmStart
    simp only [run]
    have h1 :
        (run (giantLoop (p.sqrt + 1) (p.sqrt + 1) 0 (h'.succ.succ : Fin (n' + 2))
            (0 : Fin (n' + 2)) (acc'.map (fun q => (q.1.succ.succ, q.2))))
          (Fin.cons
              (-((Fin.cons ((((p.sqrt + 1 : Nat) : Int) : ZMod p) * env' g') env' :
                    Registers p (n' + 1)) 0))
              (Fin.cons ((((p.sqrt + 1 : Nat) : Int) : ZMod p) * env' g') env'))).2 ≤ p.sqrt + 1 :=
      giantLoop_cost (p := p) (p.sqrt + 1) (p.sqrt + 1) 0 _ _ _ _
    omega
  have := babyBuild_cost (p := p) (p.sqrt + 1) 0 (0 : Fin 2) (1 : Fin 2) [] env
    (gmStart (p.sqrt + 1)) (p.sqrt + 1 + 2) hk
  omega

/-! ### Correctness -/

lemma key_lemma {p : Nat} (x i j m : Nat) (hx : x < p)
    (heq : (i : ZMod p) = (x : ZMod p) - (j * m : ZMod p)) :
    (i + j * m) % p = x := by
  have hcast : ((i + j * m : Nat) : ZMod p) = (x : ZMod p) := by
    push_cast
    rw [heq]; ring
  have hmod : (i + j * m) % p = x % p := (ZMod.natCast_eq_natCast_iff _ _ _).mp hcast
  rwa [Nat.mod_eq_of_lt hx] at hmod

lemma checkBaby_hit {p m n : Nat} (baby : List (Fin n × Nat)) (y : Fin n) (j : Nat)
    (cont : Program n) (env : Registers p n) (x : Fin p)
    (hacc : ∀ b i, (b, i) ∈ baby → env b = (i : ZMod p))
    (hy : env y = (x.val : ZMod p) - (j * m : ZMod p))
    (hex : ∃ b i, (b, i) ∈ baby ∧ env b = env y) :
    (run (checkBaby m baby y j cont) env).1 % p = x.val := by
  induction baby with
  | nil => obtain ⟨b, i, hin, _⟩ := hex; simp at hin
  | cons hd tl ih =>
    obtain ⟨b0, i0⟩ := hd
    simp only [checkBaby, run]
    split
    · next heq =>
      have h1 : (i0 : ZMod p) = env y :=
        (heq.trans (hacc b0 i0 (List.mem_cons.mpr (Or.inl rfl)))).symm
      exact key_lemma x.val i0 j m x.isLt (h1.trans hy)
    · next hne =>
      apply ih (fun b i hin => hacc b i (List.mem_cons.mpr (Or.inr hin)))
      obtain ⟨b, i, hin, he⟩ := hex
      rw [List.mem_cons] at hin
      rcases hin with h | h
      · exfalso
        obtain ⟨hb, _⟩ := Prod.mk.injEq .. |>.mp h
        exact hne (hb ▸ he).symm
      · exact ⟨b, i, h, he⟩

lemma checkBaby_pass {p m n : Nat} (baby : List (Fin n × Nat)) (y : Fin n) (j : Nat)
    (cont : Program n) (env : Registers p n) (x : Fin p)
    (hacc : ∀ b i, (b, i) ∈ baby → env b = (i : ZMod p))
    (hy : env y = (x.val : ZMod p) - (j * m : ZMod p))
    (hcont : (run cont env).1 % p = x.val) :
    (run (checkBaby m baby y j cont) env).1 % p = x.val := by
  induction baby with
  | nil => simpa [checkBaby] using hcont
  | cons hd tl ih =>
    obtain ⟨b0, i0⟩ := hd
    simp only [checkBaby, run]
    split
    · next heq =>
      have h1 : (i0 : ZMod p) = env y :=
        (heq.trans (hacc b0 i0 (List.mem_cons.mpr (Or.inl rfl)))).symm
      exact key_lemma x.val i0 j m x.isLt (h1.trans hy)
    · next hne =>
      exact ih (fun b i hin => hacc b i (List.mem_cons.mpr (Or.inr hin)))

lemma giantLoop_correct {p : Nat} (m fuel : Nat) (hm : 0 < m) :
    ∀ (j : Nat) {n : Nat} (y ginv : Fin n) (baby : List (Fin n × Nat)) (env : Registers p n)
    (x : Fin p),
    (∀ b i, (b, i) ∈ baby → env b = (i : ZMod p)) →
    (∀ i, i < m → ∃ b, (b, i) ∈ baby) →
    env ginv = -(m : ZMod p) →
    env y = (x.val : ZMod p) - (j * m : ZMod p) →
    j ≤ x.val / m → x.val / m < j + fuel →
    (run (giantLoop m fuel j y ginv baby) env).1 % p = x.val := by
  induction fuel with
  | zero => intro j n y ginv baby env x _ _ _ _ hle hlt; omega
  | succ fuel ih =>
    intro j n y ginv baby env x hacc hfull hginv hy hle hlt
    simp only [giantLoop]
    rcases lt_or_eq_of_le hle with hlt2 | heq
    · -- j < x.val / m: no guarantee of a match yet, recurse via the fallback
      apply checkBaby_pass baby y j _ env x hacc hy
      have hy' : (Fin.cons (env y + env ginv) env : Registers p (n + 1)) (0 : Fin (n + 1))
          = (x.val : ZMod p) - ((j + 1 : Nat) : ZMod p) * (m : ZMod p) := by
        rw [Fin.cons_zero, hy, hginv]; push_cast; ring
      have hnext := ih (j + 1) (0 : Fin (n + 1)) ginv.succ
        (baby.map (fun q => (q.1.succ, q.2))) (Fin.cons (env y + env ginv) env) x
        (by
          intro b i hin
          simp only [List.mem_map] at hin
          obtain ⟨⟨b0, i0⟩, hin0, heq2⟩ := hin
          obtain ⟨hb, hi⟩ := Prod.mk.injEq .. |>.mp heq2
          rw [← hb, ← hi, Fin.cons_succ]; exact hacc b0 i0 hin0)
        (by
          intro i hi
          obtain ⟨b, hb⟩ := hfull i hi
          refine ⟨b.succ, ?_⟩
          simp only [List.mem_map]
          exact ⟨(b, i), hb, rfl⟩)
        (by rw [Fin.cons_succ]; exact hginv)
        hy' (by omega) (by omega)
      show (run (Program.mul y ginv (giantLoop m fuel (j + 1) (0 : Fin (n + 1)) ginv.succ
        (baby.map (fun q => (q.1.succ, q.2))))) env).1 % p = x.val
      simpa [run] using hnext
    · -- j = x.val / m: a match exists at the baby entry x.val % m
      obtain ⟨b, hin⟩ := hfull (x.val % m) (Nat.mod_lt _ hm)
      apply checkBaby_hit baby y j _ env x hacc hy
      refine ⟨b, x.val % m, hin, ?_⟩
      rw [hacc b _ hin, hy, heq]
      have hdm : x.val = x.val % m + m * (x.val / m) := (Nat.mod_add_div x.val m).symm
      have hcast : (x.val : ZMod p) =
          (x.val % m : ZMod p) + (m : ZMod p) * (x.val / m : ZMod p) := by
        have h := congrArg (fun t : ℕ => (t : ZMod p)) hdm
        push_cast at h
        exact h
      linear_combination -hcast

lemma babyBuild_correct {p : Nat} (fuel : Nat) :
    ∀ (idx : Nat) {n : Nat} (g h : Fin n) (acc : List (Fin n × Nat)) (env : Registers p n)
    (x : Fin p) (k : (n' : Nat) → Fin n' → Fin n' → List (Fin n' × Nat) → Program n'),
    env g = 1 → env h = (x.val : ZMod p) →
    (∀ b i, (b, i) ∈ acc → env b = (i : ZMod p)) →
    (∀ i, i < idx → ∃ b, (b, i) ∈ acc) →
    (∀ (n' : Nat) (g' h' : Fin n') (acc' : List (Fin n' × Nat)) (env' : Registers p n'),
        env' g' = 1 → env' h' = (x.val : ZMod p) →
        (∀ b i, (b, i) ∈ acc' → env' b = (i : ZMod p)) →
        (∀ i, i < idx + fuel → ∃ b, (b, i) ∈ acc') →
        (run (k n' g' h' acc') env').1 % p = x.val) →
    (run (babyBuild fuel idx g h acc k) env).1 % p = x.val := by
  induction fuel with
  | zero =>
    intro idx n g h acc env x k hg hh hacc hcov hk
    simpa [babyBuild] using hk n g h acc env hg hh hacc (by simpa using hcov)
  | succ fuel ih =>
    intro idx n g h acc env x k hg hh hacc hcov hk
    simp only [babyBuild, run]
    apply ih (idx + 1) g.succ h.succ ((0, idx) :: acc.map (fun q => (q.1.succ, q.2)))
      (Fin.cons (((idx : Int) : ZMod p) * env g) env) x k
    · rw [Fin.cons_succ]; exact hg
    · rw [Fin.cons_succ]; exact hh
    · intro b i hin
      rw [List.mem_cons] at hin
      rcases hin with hin | hin
      · obtain ⟨hb, hi⟩ := Prod.mk.injEq .. |>.mp hin
        rw [hb, hi, Fin.cons_zero, hg]; push_cast; ring
      · simp only [List.mem_map] at hin
        obtain ⟨⟨b0, i0⟩, hin0, heq⟩ := hin
        obtain ⟨hb, hi⟩ := Prod.mk.injEq .. |>.mp heq
        rw [← hb, ← hi, Fin.cons_succ]; exact hacc b0 i0 hin0
    · intro i hi
      rcases Nat.lt_succ_iff_lt_or_eq.mp hi with hi' | hi'
      · obtain ⟨b, hb⟩ := hcov i hi'
        refine ⟨b.succ, ?_⟩
        rw [List.mem_cons]
        right
        simp only [List.mem_map]
        exact ⟨(b, i), hb, rfl⟩
      · exact ⟨0, by rw [List.mem_cons]; left; simp [hi']⟩
    · intro n' g' h' acc' env' hg' hh' hacc' hcov'
      apply hk n' g' h' acc' env' hg' hh' hacc'
      intro i hi
      apply hcov'
      omega

lemma buildAttack_correct {p : Nat} (_hp : 0 < p) (x : Fin p) :
    (run (buildAttack p) (initial p x)).1 % p = x.val := by
  unfold buildAttack
  apply babyBuild_correct (p.sqrt + 1) 0 (0 : Fin 2) (1 : Fin 2) [] (initial p x) x
    (gmStart (p.sqrt + 1))
  · rfl
  · rfl
  · intro b i hin; simp at hin
  · intro i hi; omega
  · intro n' g' h' acc' env' hg' hh' hacc' hcov'
    unfold gmStart
    show (run (Program.inv (0 : Fin (n' + 1))
      (giantLoop (p.sqrt + 1) (p.sqrt + 1) 0 (h'.succ.succ : Fin (n' + 2)) (0 : Fin (n' + 2))
        (acc'.map (fun q => (q.1.succ.succ, q.2)))))
      (Fin.cons ((((p.sqrt + 1 : Nat) : Int) : ZMod p) * env' g') env')).1 % p = x.val
    show (run (giantLoop (p.sqrt + 1) (p.sqrt + 1) 0 (h'.succ.succ : Fin (n' + 2))
        (0 : Fin (n' + 2)) (acc'.map (fun q => (q.1.succ.succ, q.2))))
      (Fin.cons
          (-((Fin.cons ((((p.sqrt + 1 : Nat) : Int) : ZMod p) * env' g') env' :
                Registers p (n' + 1)) 0))
        (Fin.cons ((((p.sqrt + 1 : Nat) : Int) : ZMod p) * env' g') env'))).1 % p = x.val
    apply giantLoop_correct (p.sqrt + 1) (p.sqrt + 1) (Nat.succ_pos _) 0 (h'.succ.succ)
      (0 : Fin (n' + 2)) (acc'.map (fun q => (q.1.succ.succ, q.2)))
      (Fin.cons
          (-((Fin.cons ((((p.sqrt + 1 : Nat) : Int) : ZMod p) * env' g') env' :
                Registers p (n' + 1)) 0))
        (Fin.cons ((((p.sqrt + 1 : Nat) : Int) : ZMod p) * env' g') env')) x
    · intro b i hin
      simp only [List.mem_map] at hin
      obtain ⟨⟨b0, i0⟩, hin0, heq⟩ := hin
      obtain ⟨hb, hi⟩ := Prod.mk.injEq .. |>.mp heq
      rw [← hb, ← hi, Fin.cons_succ, Fin.cons_succ]; exact hacc' b0 i0 hin0
    · intro i hi
      obtain ⟨b, hb⟩ := hcov' i (by omega)
      refine ⟨b.succ.succ, ?_⟩
      simp only [List.mem_map]
      exact ⟨(b, i), hb, rfl⟩
    · rw [Fin.cons_zero, Fin.cons_zero, hg']
      push_cast; ring
    · rw [Fin.cons_succ, Fin.cons_succ, hh']
      simp
    · exact Nat.zero_le _
    · have h1 := Nat.lt_succ_sqrt p
      have h2 : x.val < (p.sqrt + 1) * (p.sqrt + 1) := lt_of_lt_of_le x.isLt h1.le
      have h3 : x.val / (p.sqrt + 1) < p.sqrt + 1 := by
        by_contra hcon
        push_neg at hcon
        have hd := Nat.div_add_mod x.val (p.sqrt + 1)
        have hmul := mul_le_mul_left' hcon (p.sqrt + 1)
        omega
      omega

def certificate : Certificate where
  seeds := 1
  seeds_pos := by decide
  attack := attack
  bound := .add (.mul (.constant 2) .sqrtOrder) (.constant 5)
  correct := by
    intro p hp s x
    exact buildAttack_correct hp.pos x
  expected_le := by
    intro p hp
    apply expected_le_of_pointwise attack hp.pos (by decide)
    intro s x
    have hc := buildAttack_cost (p := p) (initial p x)
    show (((run (buildAttack p) (initial p x)).2 + 1 : Nat) : Rat) ≤
      2 * (Nat.sqrt p : Rat) + 5
    have : (run (buildAttack p) (initial p x)).2 + 1 ≤ 2 * p.sqrt + 5 := by omega
    exact_mod_cast this

end Submission
