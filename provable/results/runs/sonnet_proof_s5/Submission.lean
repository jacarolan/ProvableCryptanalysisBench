import GGM.Certificate

/-! # Baby-step giant-step generic discrete-log attack

For prime order `p` set `m := Nat.sqrt p + 1`, so `p < m * m` (`Nat.lt_succ_sqrt`).
Every `x < p` can be written as `x = i + j * m` with `i = x % m < m` and `j = x / m < m`.

The attack:
1. Build `m` "baby" registers holding the constants `0, 1, …, m-1` (one `exp` query each).
2. Build one register holding `-m` (one more `exp` query).
3. Giant-step loop: starting from `y := h`, at each step compare `y` against every baby
   register (`eq` is free); a match with baby value `v` at step `j` means
   `x ≡ v + j*m (mod p)`, so we return the literal `v + j*m`. If nothing matches, replace
   `y` by `y + (-m)` (one `mul` query) and try the next `j`.

Since `x = i0 + j0*m` with `i0, j0 < m`, a match is guaranteed by step `j0 ≤ m-1`, i.e.
within `m` giant steps (the very first giant step, `j=0`, is free; the remaining `m-1`
steps each cost one `mul`).

Worst-case queries: `m` (babies) `+ 1` (the `-m` constant) `+ (m-1)` (giant-step
subtractions) `+ 1` (submission) `= 2*m + 1 = 2*sqrtOrder + 3`. This is an exact
worst-case bound (the attack is deterministic, `seeds = 1`), so
`expected_le_of_pointwise` applies directly. -/

namespace Submission
open GGM

/-- `m := Nat.sqrt p + 1`, chosen so that `p < (bsgsM p) * (bsgsM p)`. -/
def bsgsM (p : Nat) : Nat := Nat.sqrt p + 1

/-- Build `cnt` baby-step registers with values `start, start+1, …, start+cnt-1`
(each register `r` created will satisfy `env r = (v : ZMod p)` where `v` is its paired
label), then continue with `k`, handing it the (possibly shifted) index of the
constant-`1` register, the (possibly shifted) index of `h`, and the list of
`(value, register)` pairs built so far (older entries included, values unchanged). -/
def babies (cnt start : Nat) {n : Nat} (one h : Fin n) (bs : List (Nat × Fin n))
    (k : {n : Nat} → Fin n → Fin n → List (Nat × Fin n) → Program n) : Program n :=
  match cnt with
  | 0 => k one h bs
  | cnt + 1 =>
      .exp one (start : Int)
        (babies cnt (start + 1) one.succ h.succ
          ((start, (0 : Fin _)) :: bs.map (fun vr => (vr.1, vr.2.succ))) k)

/-- Test `y` for equality (for free) against every register in `l`, returning the paired
label on the first match, or falling through to `fallback` if none match. -/
def testChain {n : Nat} (y : Fin n) : List (Nat × Fin n) → Program n → Program n
  | [], fallback => fallback
  | (v, r) :: rest, fallback => .eq y r (.ret v) (testChain y rest fallback)

/-- The giant-step loop. `y` is the current candidate `h - j*m`, `negM` holds the
constant `-m`, `bs` is the (shifted) list of baby registers labelled `0, …, m-1`. -/
def giant (fuel j : Nat) {n : Nat} (y negM : Fin n) (bs : List (Nat × Fin n)) (m : Nat) :
    Program n :=
  match fuel with
  | 0 => testChain y (bs.map (fun vr => (vr.1 + j * m, vr.2))) (.ret 0)
  | fuel + 1 =>
      testChain y (bs.map (fun vr => (vr.1 + j * m, vr.2)))
        (.mul y negM
          (giant fuel (j + 1) (0 : Fin _) negM.succ
            (bs.map (fun vr => (vr.1, vr.2.succ))) m))

def program (p : Nat) : Program 2 :=
  babies (bsgsM p) 0 (0 : Fin 2) (1 : Fin 2) []
    (fun one h bs =>
      .exp one (-(bsgsM p : Int))
        (giant (bsgsM p - 1) 0 h.succ (0 : Fin _)
          (bs.map (fun vr => (vr.1, vr.2.succ))) (bsgsM p)))

def attack : Attack 1 := fun p _ => program p

/-! ## Cost lemmas -/

theorem testChain_cost {n p : Nat} (y : Fin n) (l : List (Nat × Fin n)) (fallback : Program n)
    (env : Registers p n) :
    (run (testChain y l fallback) env).2 ≤ (run fallback env).2 := by
  induction l with
  | nil => simp [testChain]
  | cons hd tl ih =>
    obtain ⟨v, r⟩ := hd
    simp only [testChain, run]
    split
    · simp
    · exact ih

theorem giant_cost (fuel j : Nat) {n p : Nat} (y negM : Fin n) (bs : List (Nat × Fin n))
    (m : Nat) (env : Registers p n) :
    (run (giant fuel j y negM bs m) env).2 ≤ fuel := by
  induction fuel generalizing n y negM bs env j with
  | zero =>
    simp only [giant]
    have h1 := testChain_cost y (bs.map (fun vr => (vr.1 + j * m, vr.2))) (.ret 0) env
    simpa [run] using h1
  | succ fuel ih =>
    simp only [giant]
    have h1 := testChain_cost y (bs.map (fun vr => (vr.1 + j * m, vr.2)))
      (.mul y negM (giant fuel (j + 1) (0 : Fin _) negM.succ
        (bs.map (fun vr => (vr.1, vr.2.succ))) m)) env
    have h2 := ih (j + 1) (0 : Fin _) negM.succ (bs.map (fun vr => (vr.1, vr.2.succ)))
      (Fin.cons (env y + env negM) env)
    simp only [run] at h1
    omega

theorem babies_cost (cnt start : Nat) {n : Nat} (one h : Fin n) (bs : List (Nat × Fin n))
    (k : {n : Nat} → Fin n → Fin n → List (Nat × Fin n) → Program n)
    {p : Nat} (env : Registers p n) (B : Nat)
    (hk : ∀ {n' : Nat} (one' h' : Fin n') (bs' : List (Nat × Fin n')) (env' : Registers p n'),
        (run (k one' h' bs') env').2 ≤ B) :
    (run (babies cnt start one h bs k) env).2 ≤ cnt + B := by
  induction cnt generalizing start n one h bs env with
  | zero => simpa [babies] using hk one h bs env
  | succ cnt ih =>
    simp only [babies, run]
    have := ih (start + 1) one.succ h.succ
      ((start, (0 : Fin _)) :: bs.map (fun vr => (vr.1, vr.2.succ)))
      (Fin.cons ((start : Int) * env one) env)
    omega

/-! ## Correctness lemmas -/

theorem testChain_sound {n p : Nat} (y : Fin n) (env : Registers p n) (xz : ZMod p)
    (xval : Nat) (hxz : (xval : ZMod p) = xz) (hxval : xval < p)
    (l : List (Nat × Fin n)) (fallback : Program n)
    (hInv : ∀ v r, (v, r) ∈ l → env r = env y → (v : ZMod p) = xz) :
    (run (testChain y l fallback) env).1 % p = xval ∨
      run (testChain y l fallback) env = run fallback env := by
  induction l with
  | nil => right; rfl
  | cons hd tl ih =>
    obtain ⟨v, r⟩ := hd
    simp only [testChain, run]
    split
    next he =>
      left
      have hv : (v : ZMod p) = xz := hInv v r (List.mem_cons_self) he.symm
      have heqz : (v : ZMod p) = (xval : ZMod p) := hv.trans hxz.symm
      have hmodeq : v % p = xval % p := by
        have := congrArg ZMod.val heqz
        simpa [ZMod.val_natCast] using this
      simpa [Nat.mod_eq_of_lt hxval] using hmodeq
    next he =>
      exact ih (fun v r hm => hInv v r (List.mem_cons_of_mem _ hm))

theorem testChain_value {n p : Nat} (y : Fin n) (env : Registers p n) (xz : ZMod p)
    (xval : Nat) (hxz : (xval : ZMod p) = xz) (hxval : xval < p)
    (l : List (Nat × Fin n)) (fallback : Program n)
    (hInv : ∀ v r, (v, r) ∈ l → env r = env y → (v : ZMod p) = xz)
    (hex : ∃ v r, (v, r) ∈ l ∧ env r = env y) :
    (run (testChain y l fallback) env).1 % p = xval := by
  induction l with
  | nil => obtain ⟨v, r, hmem, _⟩ := hex; cases hmem
  | cons hd tl ih =>
    obtain ⟨v, r⟩ := hd
    simp only [testChain, run]
    split
    next he =>
      have hv : (v : ZMod p) = xz := hInv v r (List.mem_cons_self) he.symm
      have heqz : (v : ZMod p) = (xval : ZMod p) := hv.trans hxz.symm
      have hmodeq : v % p = xval % p := by
        have := congrArg ZMod.val heqz
        simpa [ZMod.val_natCast] using this
      simpa [Nat.mod_eq_of_lt hxval] using hmodeq
    next he =>
      apply ih (fun v r hm => hInv v r (List.mem_cons_of_mem _ hm))
      obtain ⟨v', r', hmem', heq'⟩ := hex
      simp only [List.mem_cons, Prod.mk.injEq] at hmem'
      rcases hmem' with ⟨rfl, rfl⟩ | hmem''
      · exact absurd heq'.symm he
      · exact ⟨v', r', hmem'', heq'⟩

/-- Main giant-step correctness: from step `j` with `fuel` steps remaining, provided the
true quotient `j0` (with `x = i0 + j0*m`, `i0, j0 < m`) lies in `[j, j+fuel]`, the loop
returns a literal that is `x` mod `p`. -/
theorem giant_sound (fuel j m i0 j0 : Nat) {n p : Nat} (y negM : Fin n) (bs : List (Nat × Fin n))
    (env : Registers p n) (xz : ZMod p) (xval : Nat)
    (hxz : (xval : ZMod p) = xz) (hxval : xval < p)
    (hxeq : xval = i0 + j0 * m) (hi0 : i0 < m)
    (hjle : j ≤ j0) (hfuel : j0 ≤ j + fuel)
    (hy : env y = xz - ((j * m : Nat) : ZMod p))
    (hnegM : env negM = -(m : ZMod p))
    (hbs : ∀ v r, (v, r) ∈ bs → env r = (v : ZMod p))
    (hcompl : ∀ v, v < m → ∃ r, (v, r) ∈ bs) :
    (run (giant fuel j y negM bs m) env).1 % p = xval := by
  induction fuel generalizing n y negM bs env j with
  | zero =>
    have hje : j = j0 := by omega
    subst hje
    obtain ⟨r0, hr0⟩ := hcompl i0 hi0
    have hInv : ∀ v r, (v, r) ∈ bs.map (fun vr => (vr.1 + j * m, vr.2)) →
        env r = env y → (v : ZMod p) = xz := by
      intro v r hmem hmatch
      simp only [List.mem_map, Prod.exists] at hmem
      obtain ⟨ov, r', hmemorig, heq⟩ := hmem
      simp only [Prod.mk.injEq] at heq
      obtain ⟨hveq, hreq⟩ := heq
      subst hveq; subst hreq
      have hor : env r' = (ov : ZMod p) := hbs ov r' hmemorig
      rw [hor, hy] at hmatch
      have hz : xz = (ov : ZMod p) + ((j * m : Nat) : ZMod p) := by
        rw [hmatch]; ring
      rw [hz]; push_cast; ring
    have hex : ∃ v r, (v, r) ∈ bs.map (fun vr => (vr.1 + j * m, vr.2)) ∧ env r = env y := by
      refine ⟨i0 + j * m, r0, ?_, ?_⟩
      · exact List.mem_map.mpr ⟨(i0, r0), hr0, rfl⟩
      · rw [hbs i0 r0 hr0, hy]
        have hz : xz = (i0 : ZMod p) + ((j * m : Nat) : ZMod p) := by
          rw [← hxz, hxeq]; push_cast; ring
        rw [hz]; ring
    show (run (testChain y (bs.map (fun vr => (vr.1 + j * m, vr.2))) (.ret 0)) env).1 % p = xval
    exact testChain_value y env xz xval hxz hxval _ _ hInv hex
  | succ fuel ih =>
    by_cases hje : j = j0
    · subst hje
      obtain ⟨r0, hr0⟩ := hcompl i0 hi0
      have hInv : ∀ v r, (v, r) ∈ bs.map (fun vr => (vr.1 + j * m, vr.2)) →
          env r = env y → (v : ZMod p) = xz := by
        intro v r hmem hmatch
        simp only [List.mem_map, Prod.exists] at hmem
        obtain ⟨ov, r', hmemorig, heq⟩ := hmem
        simp only [Prod.mk.injEq] at heq
        obtain ⟨hveq, hreq⟩ := heq
        subst hveq; subst hreq
        have hor : env r' = (ov : ZMod p) := hbs ov r' hmemorig
        rw [hor, hy] at hmatch
        have hz : xz = (ov : ZMod p) + ((j * m : Nat) : ZMod p) := by
          rw [hmatch]; ring
        rw [hz]; push_cast; ring
      have hex : ∃ v r, (v, r) ∈ bs.map (fun vr => (vr.1 + j * m, vr.2)) ∧ env r = env y := by
        refine ⟨i0 + j * m, r0, ?_, ?_⟩
        · exact List.mem_map.mpr ⟨(i0, r0), hr0, rfl⟩
        · rw [hbs i0 r0 hr0, hy]
          have hz : xz = (i0 : ZMod p) + ((j * m : Nat) : ZMod p) := by
            rw [← hxz, hxeq]; push_cast; ring
          rw [hz]; ring
      show (run (testChain y (bs.map (fun vr => (vr.1 + j * m, vr.2)))
        (.mul y negM (giant fuel (j + 1) (0 : Fin _) negM.succ
          (bs.map (fun vr => (vr.1, vr.2.succ))) m))) env).1 % p = xval
      exact testChain_value y env xz xval hxz hxval _ _ hInv hex
    · have hjlt : j < j0 := lt_of_le_of_ne hjle hje
      have hInv : ∀ v r, (v, r) ∈ bs.map (fun vr => (vr.1 + j * m, vr.2)) →
          env r = env y → (v : ZMod p) = xz := by
        intro v r hmem hmatch
        simp only [List.mem_map, Prod.exists] at hmem
        obtain ⟨ov, r', hmemorig, heq⟩ := hmem
        simp only [Prod.mk.injEq] at heq
        obtain ⟨hveq, hreq⟩ := heq
        subst hveq; subst hreq
        have hor : env r' = (ov : ZMod p) := hbs ov r' hmemorig
        rw [hor, hy] at hmatch
        have hz : xz = (ov : ZMod p) + ((j * m : Nat) : ZMod p) := by
          rw [hmatch]; ring
        rw [hz]; push_cast; ring
      have hsound := testChain_sound y env xz xval hxz hxval
        (bs.map (fun vr => (vr.1 + j * m, vr.2)))
        (.mul y negM (giant fuel (j + 1) (0 : Fin _) negM.succ
          (bs.map (fun vr => (vr.1, vr.2.succ))) m)) hInv
      rcases hsound with hcorrect | hfall
      · show (run (testChain y (bs.map (fun vr => (vr.1 + j * m, vr.2)))
          (.mul y negM (giant fuel (j + 1) (0 : Fin _) negM.succ
            (bs.map (fun vr => (vr.1, vr.2.succ))) m))) env).1 % p = xval
        exact hcorrect
      · set env2 : Registers p (n + 1) := Fin.cons (env y + env negM) env with henv2
        have hy' : env2 (0 : Fin (n + 1)) = xz - (((j + 1) * m : Nat) : ZMod p) := by
          simp only [henv2, Fin.cons_zero, hy, hnegM]
          push_cast; ring
        have hnegM' : env2 negM.succ = -(m : ZMod p) := by
          simp [henv2, Fin.cons_succ, hnegM]
        have hbs' : ∀ (v : Nat) (r : Fin (n + 1)), (v, r) ∈ bs.map (fun vr => (vr.1, vr.2.succ)) →
            env2 r = (v : ZMod p) := by
          intro v r hmem
          simp only [List.mem_map, Prod.exists] at hmem
          obtain ⟨ov, r', hmemorig, heq⟩ := hmem
          simp only [Prod.mk.injEq] at heq
          obtain ⟨hveq, hreq⟩ := heq
          subst hveq; subst hreq
          simp [henv2, Fin.cons_succ, hbs ov r' hmemorig]
        have hcompl' : ∀ v, v < m → ∃ r, (v, r) ∈ bs.map (fun vr => (vr.1, vr.2.succ)) := by
          intro v hv
          obtain ⟨r, hr⟩ := hcompl v hv
          exact ⟨r.succ, List.mem_map.mpr ⟨(v, r), hr, rfl⟩⟩
        have hrec := ih (j + 1) (0 : Fin _) negM.succ (bs.map (fun vr => (vr.1, vr.2.succ)))
          env2 (by omega) (by omega) hy' hnegM' hbs' hcompl'
        show (run (testChain y (bs.map (fun vr => (vr.1 + j * m, vr.2)))
          (.mul y negM (giant fuel (j + 1) (0 : Fin _) negM.succ
            (bs.map (fun vr => (vr.1, vr.2.succ))) m))) env).1 % p = xval
        rw [hfall]
        simpa [run] using hrec

theorem babies_correct (cnt start : Nat) {n p : Nat} (one h : Fin n) (bs : List (Nat × Fin n))
    (env : Registers p n) (valH : ZMod p) (xval : Nat)
    (hone : env one = 1) (hh : env h = valH)
    (hbs : ∀ v r, (v, r) ∈ bs → env r = (v : ZMod p))
    (hcompl : ∀ v, v < start → ∃ r, (v, r) ∈ bs)
    (k : {n' : Nat} → Fin n' → Fin n' → List (Nat × Fin n') → Program n')
    (hk : ∀ {n' : Nat} (one' h' : Fin n') (bs' : List (Nat × Fin n')) (env' : Registers p n'),
        env' one' = 1 → env' h' = valH →
        (∀ v r, (v, r) ∈ bs' → env' r = (v : ZMod p)) →
        (∀ v, v < start + cnt → ∃ r, (v, r) ∈ bs') →
        (run (k one' h' bs') env').1 % p = xval) :
    (run (babies cnt start one h bs k) env).1 % p = xval := by
  induction cnt generalizing start n one h bs env with
  | zero => exact hk one h bs env hone hh hbs hcompl
  | succ cnt ih =>
    simp only [babies, run]
    apply ih (start + 1) one.succ h.succ
      ((start, (0 : Fin _)) :: bs.map (fun vr => (vr.1, vr.2.succ)))
      (Fin.cons ((start : Int) * env one) env)
    · simp [Fin.cons_succ, hone]
    · simp [Fin.cons_succ, hh]
    · intro v r hmem
      simp only [List.mem_cons, Prod.mk.injEq] at hmem
      rcases hmem with ⟨rfl, rfl⟩ | hmem'
      · simp only [Fin.cons_zero]
        push_cast; rw [hone]; ring
      · simp only [List.mem_map, Prod.exists] at hmem'
        obtain ⟨ov, r', hmemorig, heq⟩ := hmem'
        simp only [Prod.mk.injEq] at heq
        obtain ⟨hveq, hreq⟩ := heq
        subst hveq; subst hreq
        simp [Fin.cons_succ, hbs ov r' hmemorig]
    · intro v hv
      have hv' : v ≤ start := Nat.lt_succ_iff.mp hv
      rcases hv'.lt_or_eq with hlt | heq
      · obtain ⟨r, hr⟩ := hcompl v hlt
        exact ⟨r.succ, List.mem_cons_of_mem _ (List.mem_map.mpr ⟨(v, r), hr, rfl⟩)⟩
      · subst heq
        exact ⟨0, List.mem_cons_self⟩
    · intro n'' one'' h'' bs'' env'' hone'' hh'' hbs'' hcompl2
      refine hk one'' h'' bs'' env'' hone'' hh'' hbs'' ?_
      intro v hv
      exact hcompl2 v (by omega)

/-! ## Assembling the attack -/

theorem program_correct (p : Nat) (hp : Nat.Prime p) (x : Fin p) :
    (run (program p) (initial p x)).1 % p = x.val := by
  obtain ⟨m, hmdef⟩ : ∃ m, m = bsgsM p := ⟨bsgsM p, rfl⟩
  have hm_pos : 0 < m := by rw [hmdef]; exact Nat.succ_pos _
  have hm_lt : p < m * m := by
    rw [hmdef]
    have h := Nat.lt_succ_sqrt p
    simpa [bsgsM, Nat.succ_eq_add_one] using h
  have hm_le : m ≤ p := by
    rw [hmdef]
    have h1 : 1 < p := hp.one_lt
    have h2 := Nat.sqrt_lt_self h1
    simp only [bsgsM]; omega
  obtain ⟨j0, hj0def⟩ : ∃ j0, j0 = x.val / m := ⟨x.val / m, rfl⟩
  obtain ⟨i0, hi0def⟩ : ∃ i0, i0 = x.val % m := ⟨x.val % m, rfl⟩
  have hxeq : x.val = i0 + j0 * m := by
    have h := Nat.div_add_mod x.val m
    rw [Nat.mul_comm] at h
    rw [← hj0def, ← hi0def] at h
    omega
  have hi0 : i0 < m := by rw [hi0def]; exact Nat.mod_lt x.val (by omega)
  have hj0 : j0 < m := by
    by_contra hc
    push_neg at hc
    have e1 : m * m ≤ j0 * m := Nat.mul_le_mul hc (le_refl m)
    have e2 : j0 * m ≤ x.val := by omega
    omega
  show (run (program p) (initial p x)).1 % p = x.val
  unfold program
  rw [← hmdef]
  refine babies_correct m 0 (0 : Fin 2) (1 : Fin 2) [] (initial p x) (x.val : ZMod p) x.val
    rfl rfl (by simp) (fun v hv => absurd hv (Nat.not_lt_zero v)) _ ?_
  intro n' one' h' bs' env' hone' hh' hbs' hcompl'
  have hcompl'' : ∀ v, v < m → ∃ r, (v, r) ∈ bs' := by simpa using hcompl'
  show (run (.exp one' (-(m : Int)) (giant (m - 1) 0 h'.succ (0 : Fin _)
    (bs'.map (fun vr => (vr.1, vr.2.succ))) m)) env').1 % p = x.val
  simp only [run]
  refine giant_sound (m - 1) 0 m i0 j0 h'.succ (0 : Fin _) (bs'.map (fun vr => (vr.1, vr.2.succ)))
    _ (x.val : ZMod p) x.val rfl x.isLt hxeq hi0
    (Nat.zero_le _) (by omega) ?_ ?_ ?_ ?_
  · simp [Fin.cons_succ, hh']
  · simp only [Fin.cons_zero, hone', mul_one]
    push_cast; ring
  · intro v r hmem
    simp only [List.mem_map, Prod.exists] at hmem
    obtain ⟨ov, r', hmemorig, heq⟩ := hmem
    simp only [Prod.mk.injEq] at heq
    obtain ⟨hveq, hreq⟩ := heq
    subst hveq; subst hreq
    simp [Fin.cons_succ, hbs' ov r' hmemorig]
  · intro v hv
    obtain ⟨r, hr⟩ := hcompl'' v hv
    exact ⟨r.succ, List.mem_map.mpr ⟨(v, r), hr, rfl⟩⟩

theorem program_cost (p : Nat) (x : Fin p) :
    (run (program p) (initial p x)).2 + 1 ≤ 2 * bsgsM p + 1 := by
  have hm_pos : 0 < bsgsM p := Nat.succ_pos _
  have hk : ∀ {n' : Nat} (one' h' : Fin n') (bs' : List (Nat × Fin n')) (env' : Registers p n'),
      (run (.exp one' (-(bsgsM p : Int)) (giant (bsgsM p - 1) 0 h'.succ (0 : Fin _)
        (bs'.map (fun vr => (vr.1, vr.2.succ))) (bsgsM p))) env').2 ≤ bsgsM p := by
    intro n' one' h' bs' env'
    simp only [run]
    refine le_trans (Nat.add_le_add_right (giant_cost (bsgsM p - 1) 0 h'.succ (0 : Fin _)
      (bs'.map (fun vr => (vr.1, vr.2.succ))) (bsgsM p) _) 1) (by omega)
  have hb := babies_cost (bsgsM p) 0 (0 : Fin 2) (1 : Fin 2) [] _ (initial p x) (bsgsM p) hk
  have : (run (program p) (initial p x)).2 = (run (babies (bsgsM p) 0 (0 : Fin 2) (1 : Fin 2) []
      (fun one h bs => .exp one (-(bsgsM p : Int)) (giant (bsgsM p - 1) 0 h.succ (0 : Fin _)
        (bs.map (fun vr => (vr.1, vr.2.succ))) (bsgsM p)))) (initial p x)).2 := rfl
  omega

def certificate : Certificate where
  seeds := 1
  seeds_pos := by decide
  attack := attack
  bound := .add (.mul (.constant 2) .sqrtOrder) (.constant 3)
  correct := by
    intro p hp s x
    exact program_correct p hp x
  expected_le := by
    intro p hp
    apply expected_le_of_pointwise attack hp.pos (by decide)
    intro s x
    have h := program_cost p x
    have hqueries : queries attack p s x = (run (program p) (initial p x)).2 + 1 := rfl
    show (queries attack p s x : Rat) ≤
      (Bound.add (Bound.mul (Bound.constant 2) Bound.sqrtOrder) (Bound.constant 3)).eval p
    have heval : (Bound.add (Bound.mul (Bound.constant 2) Bound.sqrtOrder) (Bound.constant 3)).eval p
        = 2 * (bsgsM p : Rat) + 1 := by
      simp only [Bound.eval, bsgsM]
      push_cast; ring
    rw [heval, hqueries]
    exact_mod_cast h

end Submission
