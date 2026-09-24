import GGM.Certificate

/-! A baby-step giant-step attack.  Registers are additive (`ZMod p`), so `g = 1`
and `h = x`.  We build `m := ⌊√p⌋ + 1` "baby" registers holding the values
`0, …, m-1` (via `exp g i`), then walk `m` "giant" registers holding
`x, x-m, x-2m, …` (via one `exp` for the constant `-m` and repeated `mul`),
comparing (for free) each giant register against every baby register.  Since
`x < p < m*m`, writing `x = i + j*m` with `i, j < m` (Euclidean division) gives a
match exactly at the `j`-th giant step against the `i`-th baby.  Total cost is
about `m` (babies) + `m` (giants) + 1 (submission) ≈ `2*sqrt p + 4`. -/
namespace Submission
open GGM

/-- Compare `giant` against every labeled register in `babies` (free), returning
`base + i` for the first `i` whose register matches, else falling through to `cont`. -/
def checkBabies {n : Nat} (giant : Fin n) (base : Nat) (babies : List (Fin n × Nat))
    (cont : Program n) : Program n :=
  match babies with
  | [] => cont
  | (b, i) :: bs => .eq giant b (.ret (base + i)) (checkBabies giant base bs cont)

/-- Giant-step loop.  At outer index `j`, `giant` should hold `x - j*m`, `step`
should hold `-m`, and `babies` should be `m` labeled registers holding `0,…,m-1`. -/
def giantLoop (m : Nat) (j rem : Nat) {n : Nat} (giant step : Fin n)
    (babies : List (Fin n × Nat)) : Program n :=
  match rem with
  | 0 => .ret 0
  | rem + 1 =>
      checkBabies giant (j * m) babies
        (.mul giant step
          (giantLoop m (j + 1) rem (0 : Fin (n + 1)) step.succ
            (babies.map fun q => (q.1.succ, q.2))))

/-- Baby-step phase: builds `m` registers holding `0,…,m-1`, then one register
holding `-m`, then hands off to the giant-step loop. -/
def buildBabies (m rem : Nat) {n : Nat} (g h : Fin n) (acc : List (Fin n × Nat)) :
    Program n :=
  match rem with
  | 0 =>
      .exp g (-(m : Int))
        (giantLoop m 0 m h.succ (0 : Fin (n + 1)) (acc.map fun q => (q.1.succ, q.2)))
  | rem + 1 =>
      .exp g ((m - 1 - rem : Nat) : Int)
        (buildBabies m rem g.succ h.succ ((0, m - 1 - rem) :: acc.map fun q => (q.1.succ, q.2)))

def attack : Attack 1 := fun p _ =>
  buildBabies (Nat.sqrt p + 1) (Nat.sqrt p + 1) (0 : Fin 2) (1 : Fin 2) []

/-! ## Cost lemmas -/

theorem checkBabies_cost {p n : Nat} (giant : Fin n) (base : Nat)
    (babies : List (Fin n × Nat)) (cont : Program n) (env : Registers p n) :
    (run (checkBabies giant base babies cont) env).2 ≤ (run cont env).2 := by
  induction babies with
  | nil => simp [checkBabies]
  | cons hd tl ih =>
      obtain ⟨b, i⟩ := hd
      simp only [checkBabies, run]
      split
      · simp
      · exact ih

theorem giantLoop_cost {p : Nat} (m : Nat) :
    ∀ (j rem : Nat) {n : Nat} (giant step : Fin n) (babies : List (Fin n × Nat))
      (env : Registers p n),
      (run (giantLoop m j rem giant step babies) env).2 ≤ rem := by
  intro j rem
  induction rem generalizing j with
  | zero =>
      intro n giant step babies env
      simp [giantLoop, run]
  | succ k ih =>
      intro n giant step babies env
      have h1 : (run (giantLoop m j (k + 1) giant step babies) env).2 ≤
          (run (.mul giant step
              (giantLoop m (j + 1) k (0 : Fin (n + 1)) step.succ
                (babies.map fun q => (q.1.succ, q.2)))) env).2 := by
        simp only [giantLoop]
        exact checkBabies_cost giant (j * m) babies _ env
      have h2 : (run (.mul giant step
              (giantLoop m (j + 1) k (0 : Fin (n + 1)) step.succ
                (babies.map fun q => (q.1.succ, q.2)))) env).2 =
          (run (giantLoop m (j + 1) k (0 : Fin (n + 1)) step.succ
              (babies.map fun q => (q.1.succ, q.2)))
            (Fin.cons (env giant + env step) env)).2 + 1 := by
        simp [run]
      have h3 := ih (j + 1) (0 : Fin (n + 1)) step.succ
        (babies.map fun q => (q.1.succ, q.2)) (Fin.cons (env giant + env step) env)
      omega

theorem buildBabies_cost {p : Nat} (m : Nat) :
    ∀ (rem : Nat) {n : Nat} (g h : Fin n) (acc : List (Fin n × Nat)) (env : Registers p n),
      (run (buildBabies m rem g h acc) env).2 ≤ rem + m + 1 := by
  intro rem
  induction rem with
  | zero =>
      intro n g h acc env
      simp only [buildBabies, run]
      push_cast
      have := giantLoop_cost m 0 m h.succ (0 : Fin (n + 1))
        (acc.map fun q => (q.1.succ, q.2))
        (Fin.cons (-(m : ZMod p) * env g) env)
      omega
  | succ k ih =>
      intro n g h acc env
      simp only [buildBabies, run]
      have := ih g.succ h.succ ((0, m - 1 - k) :: acc.map fun q => (q.1.succ, q.2))
        (Fin.cons (((m - 1 - k : Nat) : Int) * env g : ZMod p) env)
      omega

/-! ## Shifting labeled register lists preserves their properties. -/

theorem babies_shift_lt {n m : Nat} (babies : List (Fin n × Nat))
    (hlt : ∀ b i, (b, i) ∈ babies → i < m) :
    ∀ b i, (b, i) ∈ (babies.map fun q => (q.1.succ, q.2)) → i < m := by
  intro b i hbi
  obtain ⟨⟨b0, i0⟩, hmem, heq⟩ := List.mem_map.mp hbi
  injection heq with h1 h2
  rw [← h2]
  exact hlt b0 i0 hmem

theorem babies_shift_val {p n : Nat} (v : ZMod p) (env : Registers p n)
    (babies : List (Fin n × Nat))
    (hval : ∀ b i, (b, i) ∈ babies → env b = (i : ZMod p)) :
    ∀ b i, (b, i) ∈ (babies.map fun q => (q.1.succ, q.2)) →
      (Fin.cons v env : Registers p (n + 1)) b = (i : ZMod p) := by
  intro b i hbi
  obtain ⟨⟨b0, i0⟩, hmem, heq⟩ := List.mem_map.mp hbi
  injection heq with h1 h2
  rw [← h1, ← h2, Fin.cons_succ]
  exact hval b0 i0 hmem

theorem babies_shift_tot {n m : Nat} (babies : List (Fin n × Nat))
    (htot : ∀ i, i < m → ∃ b, (b, i) ∈ babies) :
    ∀ i, i < m → ∃ b, (b, i) ∈ (babies.map fun q => (q.1.succ, q.2)) := by
  intro i hi
  obtain ⟨b, hb⟩ := htot i hi
  exact ⟨b.succ, List.mem_map.mpr ⟨(b, i), hb, rfl⟩⟩

/-! ## Correctness lemmas -/

theorem checkBabies_none {p n : Nat} (giant : Fin n) (base : Nat) (env : Registers p n) :
    ∀ (babies : List (Fin n × Nat)) (cont : Program n),
      (∀ b i, (b, i) ∈ babies → env giant ≠ env b) →
      run (checkBabies giant base babies cont) env = run cont env := by
  intro babies
  induction babies with
  | nil => intro cont _; simp [checkBabies]
  | cons hd tl ih =>
      intro cont hne
      obtain ⟨b, i⟩ := hd
      have h1 : env giant ≠ env b := hne b i (List.mem_cons.mpr (Or.inl rfl))
      simp only [checkBabies, run, if_neg h1]
      exact ih cont (fun b' i' hb' => hne b' i' (List.mem_cons.mpr (Or.inr hb')))

theorem checkBabies_correct {p n : Nat} (giant : Fin n) (base : Nat) (env : Registers p n) :
    ∀ (babies : List (Fin n × Nat)) (cont : Program n) (i0 : Nat),
      (∀ b i, (b, i) ∈ babies → i < p) →
      (∀ b i, (b, i) ∈ babies → env b = (i : ZMod p)) →
      (∃ b, (b, i0) ∈ babies) →
      i0 < p →
      env giant = (i0 : ZMod p) →
      (run (checkBabies giant base babies cont) env).1 = base + i0 := by
  intro babies
  induction babies with
  | nil => intro cont i0 _ _ hex _ _; obtain ⟨b, hb⟩ := hex; cases hb
  | cons hd tl ih =>
      intro cont i0 hlt hval hex hi0p hgiant
      obtain ⟨b, i⟩ := hd
      have hib : i < p := hlt b i (List.mem_cons.mpr (Or.inl rfl))
      have hvalb : env b = (i : ZMod p) := hval b i (List.mem_cons.mpr (Or.inl rfl))
      by_cases hcase : i = i0
      · have heq : env giant = env b := by rw [hgiant, hvalb, hcase]
        simp only [checkBabies, run, if_pos heq]
        omega
      · have hne : env giant ≠ env b := by
          rw [hvalb, hgiant]
          intro hcontra
          apply hcase
          have h1 := congrArg ZMod.val hcontra
          rw [ZMod.val_cast_of_lt hi0p, ZMod.val_cast_of_lt hib] at h1
          omega
        have hex' : ∃ b', (b', i0) ∈ tl := by
          obtain ⟨b'', hb''⟩ := hex
          rcases List.mem_cons.mp hb'' with heq2 | hin2
          · injection heq2 with e1 e2
            exact absurd e2.symm hcase
          · exact ⟨b'', hin2⟩
        simp only [checkBabies, run, if_neg hne]
        exact ih cont i0
          (fun b' i' hb' => hlt b' i' (List.mem_cons.mpr (Or.inr hb')))
          (fun b' i' hb' => hval b' i' (List.mem_cons.mpr (Or.inr hb')))
          hex' hi0p hgiant

theorem giantLoop_correct {p : Nat} (m : Nat) (_hm : 0 < m) (hmp : m ≤ p) :
    ∀ (j rem : Nat) {n : Nat} (giant step : Fin n) (babies : List (Fin n × Nat))
      (env : Registers p n) (x : Nat),
      x < p →
      j * m ≤ x →
      x < j * m + rem * m →
      env giant = ((x - j * m : Nat) : ZMod p) →
      env step = -(m : ZMod p) →
      (∀ b i, (b, i) ∈ babies → i < m) →
      (∀ b i, (b, i) ∈ babies → env b = (i : ZMod p)) →
      (∀ i, i < m → ∃ b, (b, i) ∈ babies) →
      (run (giantLoop m j rem giant step babies) env).1 = x := by
  intro j rem
  induction rem generalizing j with
  | zero =>
      intro n giant step babies env x hxp hlow hfuel _ _ _ _ _
      omega
  | succ k ih =>
      intro n giant step babies env x hxp hlow hfuel hgiant hstep hlt hval htot
      have hexp1 : (j + 1) * m = j * m + m := by ring
      have hexp2 : (k + 1) * m = k * m + m := by ring
      by_cases hcase : x < j * m + m
      · have hi0m : x - j * m < m := by omega
        obtain ⟨b0, hb0⟩ := htot (x - j * m) hi0m
        simp only [giantLoop]
        have hres := checkBabies_correct giant (j * m) env babies
          (.mul giant step
            (giantLoop m (j + 1) k (0 : Fin (n + 1)) step.succ
              (babies.map fun q => (q.1.succ, q.2))))
          (x - j * m) (fun b i hbi => lt_of_lt_of_le (hlt b i hbi) hmp) hval ⟨b0, hb0⟩
          (lt_of_lt_of_le hi0m hmp) hgiant
        rw [hres]
        omega
      · push_neg at hcase
        have hne : ∀ b i, (b, i) ∈ babies → env giant ≠ env b := by
          intro b i hbi hcontra
          have hib : i < m := hlt b i hbi
          have hvalb : env b = (i : ZMod p) := hval b i hbi
          rw [hvalb, hgiant] at hcontra
          have h1 := congrArg ZMod.val hcontra
          rw [ZMod.val_cast_of_lt (show x - j * m < p by omega),
              ZMod.val_cast_of_lt (lt_of_lt_of_le hib hmp)] at h1
          omega
        simp only [giantLoop]
        rw [checkBabies_none giant (j * m) env babies _ hne]
        have hgiant2 : (Fin.cons (env giant + env step) env : Registers p (n + 1))
            (0 : Fin (n + 1)) = ((x - (j + 1) * m : Nat) : ZMod p) := by
          rw [Fin.cons_zero, hgiant, hstep]
          have hr : x - j * m = (x - (j + 1) * m) + m := by omega
          rw [hr]
          push_cast
          ring
        have hstep2 : (Fin.cons (env giant + env step) env : Registers p (n + 1))
            (step.succ) = -(m : ZMod p) := by
          rw [Fin.cons_succ, hstep]
        have h3 := ih (j + 1) (0 : Fin (n + 1)) step.succ
          (babies.map fun q => (q.1.succ, q.2)) (Fin.cons (env giant + env step) env) x
          hxp (by omega) (by omega) hgiant2 hstep2
          (babies_shift_lt babies hlt)
          (by
            intro b i hbi
            obtain ⟨⟨b0, i0⟩, hmem, heq⟩ := List.mem_map.mp hbi
            injection heq with e1 e2
            rw [← e1, ← e2, Fin.cons_succ]
            exact hval b0 i0 hmem)
          (babies_shift_tot babies htot)
        simp only [run]
        exact h3

theorem buildBabies_correct {p : Nat} (_hp1 : 1 < p) (m : Nat) (hm : 0 < m) (hmp : m ≤ p)
    (hbound : p < m * m) :
    ∀ (rem : Nat) {n : Nat} (g h : Fin n) (acc : List (Fin n × Nat)) (env : Registers p n)
      (x : Nat),
      rem ≤ m →
      x < p →
      env g = 1 →
      env h = (x : ZMod p) →
      (∀ b i, (b, i) ∈ acc → i < m) →
      (∀ b i, (b, i) ∈ acc → env b = (i : ZMod p)) →
      (∀ i, i < m - rem → ∃ b, (b, i) ∈ acc) →
      (run (buildBabies m rem g h acc) env).1 = x := by
  intro rem
  induction rem with
  | zero =>
      intro n g h acc env x _ hxp hg hh hlt hval htot
      simp only [buildBabies, run]
      push_cast
      rw [hg, mul_one]
      have h0 : (0 : Nat) * m = 0 := by ring
      have hgiant0 : (Fin.cons (-(m : ZMod p)) env : Registers p (n + 1)) (h.succ) =
          ((x - 0 * m : Nat) : ZMod p) := by
        rw [h0, Nat.sub_zero, Fin.cons_succ, hh]
      have hstep0 : (Fin.cons (-(m : ZMod p)) env : Registers p (n + 1))
          (0 : Fin (n + 1)) = -(m : ZMod p) := by
        rw [Fin.cons_zero]
      have hm0 : m - 0 = m := by omega
      exact giantLoop_correct m hm hmp 0 m h.succ (0 : Fin (n + 1))
        (acc.map fun q => (q.1.succ, q.2)) (Fin.cons (-(m : ZMod p)) env) x
        hxp (by omega) (by omega) hgiant0 hstep0
        (babies_shift_lt acc hlt)
        (by
          intro b i hbi
          obtain ⟨⟨b0, i0⟩, hmem, heq⟩ := List.mem_map.mp hbi
          injection heq with e1 e2
          rw [← e1, ← e2, Fin.cons_succ]
          exact hval b0 i0 hmem)
        (babies_shift_tot acc (by rw [hm0] at htot; exact htot))
  | succ k ih =>
      intro n g h acc env x hremm hxp hg hh hlt hval htot
      simp only [buildBabies, run]
      have hg2 : (Fin.cons (((m - 1 - k : Nat) : Int) * env g : ZMod p) env
          : Registers p (n + 1)) g.succ = 1 := by
        rw [Fin.cons_succ]; exact hg
      have hh2 : (Fin.cons (((m - 1 - k : Nat) : Int) * env g : ZMod p) env
          : Registers p (n + 1)) h.succ = (x : ZMod p) := by
        rw [Fin.cons_succ]; exact hh
      have hhead : (Fin.cons (((m - 1 - k : Nat) : Int) * env g : ZMod p) env
          : Registers p (n + 1)) (0 : Fin (n + 1)) = ((m - 1 - k : Nat) : ZMod p) := by
        rw [Fin.cons_zero, hg]; push_cast; ring
      have hlt2 : ∀ b i, (b, i) ∈ ((0, m - 1 - k) :: acc.map fun q => (q.1.succ, q.2)) →
          i < m := by
        intro b i hbi
        rcases List.mem_cons.mp hbi with heq | hin
        · injection heq with e1 e2; omega
        · exact babies_shift_lt acc hlt b i hin
      have hval2 : ∀ b i, (b, i) ∈ ((0, m - 1 - k) :: acc.map fun q => (q.1.succ, q.2)) →
          (Fin.cons (((m - 1 - k : Nat) : Int) * env g : ZMod p) env
            : Registers p (n + 1)) b = (i : ZMod p) := by
        intro b i hbi
        rcases List.mem_cons.mp hbi with heq | hin
        · injection heq with e1 e2; rw [e1, e2]; exact hhead
        · obtain ⟨⟨b0, i0⟩, hmem, heq2⟩ := List.mem_map.mp hin
          injection heq2 with e1 e2
          rw [← e1, ← e2, Fin.cons_succ]
          exact hval b0 i0 hmem
      have htot2 : ∀ i, i < m - k → ∃ b,
          (b, i) ∈ ((0, m - 1 - k) :: acc.map fun q => (q.1.succ, q.2)) := by
        intro i hi
        by_cases hcase : i = m - 1 - k
        · exact ⟨0, List.mem_cons.mpr (Or.inl (by rw [hcase]))⟩
        · have hi' : i < m - (k + 1) := by omega
          obtain ⟨b, hb⟩ := htot i hi'
          exact ⟨b.succ, List.mem_cons.mpr (Or.inr (List.mem_map.mpr ⟨(b, i), hb, rfl⟩))⟩
      exact ih g.succ h.succ ((0, m - 1 - k) :: acc.map fun q => (q.1.succ, q.2))
        (Fin.cons (((m - 1 - k : Nat) : Int) * env g : ZMod p) env) x
        (by omega) hxp hg2 hh2 hlt2 hval2 htot2

/-! ## The certificate -/

def certificate : Certificate where
  seeds := 1
  seeds_pos := by decide
  attack := attack
  bound := .add (.mul (.constant 2) .sqrtOrder) (.constant 4)
  correct := by
    intro p hp s x
    have hp1 : 1 < p := hp.one_lt
    have hm : 0 < Nat.sqrt p + 1 := Nat.succ_pos _
    have hmp : Nat.sqrt p + 1 ≤ p := by
      have h := Nat.sqrt_lt_self hp1
      omega
    have hbound : p < (Nat.sqrt p + 1) * (Nat.sqrt p + 1) := by
      have h := Nat.lt_succ_sqrt p
      simpa [Nat.succ_eq_add_one] using h
    have hres : (run (attack p s) (initial p x)).1 = x.val := by
      unfold attack
      exact buildBabies_correct hp1 (Nat.sqrt p + 1) hm hmp hbound
        (Nat.sqrt p + 1) (0 : Fin 2) (1 : Fin 2) [] (initial p x) x.val
        (le_refl _) x.isLt rfl rfl
        (fun b i hi => by simp at hi)
        (fun b i hi => by simp at hi)
        (fun i hi => absurd hi (by omega))
    show (run (attack p s) (initial p x)).1 % p = x.val
    rw [hres]
    exact Nat.mod_eq_of_lt x.isLt
  expected_le := by
    intro p hp
    apply expected_le_of_pointwise attack hp.pos (by decide)
    intro s x
    have hc := buildBabies_cost (Nat.sqrt p + 1) (Nat.sqrt p + 1) (0 : Fin 2) (1 : Fin 2)
      ([] : List (Fin 2 × Nat)) (initial p x)
    have hnat : (outcome attack p s x).2 + 1 ≤ 2 * Nat.sqrt p + 4 := by
      show (run (attack p s) (initial p x)).2 + 1 ≤ 2 * Nat.sqrt p + 4
      unfold attack
      omega
    have hq : (queries attack p s x : Rat) ≤ ((2 * Nat.sqrt p + 4 : Nat) : Rat) := by
      show (((outcome attack p s x).2 + 1 : Nat) : Rat) ≤ _
      exact_mod_cast hnat
    simpa [Bound.eval] using hq

end Submission
