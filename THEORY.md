# Theory: certified query complexity for the four rungs

This note fixes the model, proves the lower bound behind every rung, and gives the exact
worst-case cost of the reference attacks. Together these certify each instance's optimal cost
Q\* to within a factor of about 2.

## 1. The model

**Group.** The challenger's group is Z_N (additive), read as a cyclic group ⟨g⟩ of order N
with element e ↔ g^e. N is public.

**Encoding.** The adversary sees element e only as a label σ(e). σ is a keyed pseudorandom
permutation (a 4-round Luby–Rackoff Feistel network over BLAKE2b, 256-bit blocks) applied to
(e ‖ 0^128). Labels are injective. When a label is decoded, the zero padding is checked, so any
string the adversary did not receive is rejected except with probability 2^-128. We assume σ is
indistinguishable from a uniformly random injection (standard PRP security). This costs an
additive negligible term in every bound below, which we omit.

**Queries.** Each query returns the label of one new element:

| op | result | cost |
|---|---|---|
| `mul(a, b)` | σ(e_a + e_b) | 1 |
| `inv(a)` | σ(−e_a) | 1 |
| `exp(a, k)`, for any public integer k | σ(k·e_a) | 1 |
| `submit(x')` | whether x' = x | 1 |

Testing two labels for equality is free. Batching is allowed, and every op in a batch is
charged. A batch that would exceed the budget B is rejected. This is Maurer's generic model with
linear operations, and it matches Shoup's model up to how `exp` is charged.

**Why `exp` costs 1.** Every lower bound below counts the group elements the adversary obtains,
and each query yields at most one element, whichever operation produced it. Charging `exp` its
double-and-add cost (~1.5·log₂k multiplications) would leave every lower bound unchanged. It
would only multiply the upper bounds of exponentiation-heavy attacks (Pohlig–Hellman projections,
Cheon) by a log factor, so the bounds would no longer match. With unit cost they match to within
a constant.

**Polynomial view.** Each published element has an exponent that is a known polynomial in the
secret x: g ↔ 1, h ↔ X, h_d ↔ X^d. Every query takes Z-linear combinations of existing
exponents. So after m queries the adversary holds at most m + k₀ elements, where k₀ is the
number of published elements. Each element's exponent is a known polynomial
F ∈ span_Z{published polynomials}, evaluated at x.

## 2. The master lemma

> **Lemma 1.** Fix a set of k₀ published polynomials and a distribution of x. Suppose that for
> any two distinct formal combinations F ≠ G reachable by the adversary, one of the following
> holds:
> - (a) F(x) = G(x) is determined by information given to the adversary for free, or
> - (b) Pr_x[F(x) = G(x)] ≤ δ/M.
>
> Also suppose every value of x has probability at most 1/M given the free information. Then
> every generic algorithm making m queries, including submissions, succeeds with probability
> at most
>
> **ε(m) ≤ ( C(m + k₀, 2) · δ + 1 ) / M.**

*Proof sketch* (the standard Shoup/Maurer simulation). Run the adversary against a simulator
that treats x as a formal variable. The simulator answers equalities of type (a) correctly and
declares every type-(b) pair unequal. Its transcript is independent of x (given the free
information), so its final guess is right with probability at most 1/M.

The real game and the simulation diverge only if some type-(b) pair actually collides at the
real x. There are at most C(m + k₀, 2) pairs, each colliding with probability at most δ/M, and a
union bound finishes the proof. A submission is an equality test against h, so it is covered by
the same count. ∎

For success probability ½ this gives **Q\*_LB = min{ m : (C(m+k₀,2)·δ + 1)/M ≥ ½ } ≈ √(M/δ)**,
which `bounds.lb_queries` computes exactly.

## 3. The four rungs

Throughout, **Q\*_UB** is the exact worst-case query count of the reference attack
(`ggmbench/solvers.py`), including its one submission. `bounds.py` computes it in closed form,
and `scripts/verify_reference.py` checks every run against it. The budget is **B = 4·Q\*_UB**.

### Rung 1: smooth group order (Pohlig–Hellman + BSGS)

*Instance.* N = q·S. Here q is a prime of 2L−2 bits and S is a ~20-bit product of prime powers
below 100, so q ∥ N. The secret x is uniform in Z_N. Published: g, h.

*Lower bound* (Shoup 1997, via Lemma 1). Give the adversary r = x mod S for free. Then
u = x mod q is uniform on Z_q, independent of r. By CRT, a + bx ≡ a' + b'x (mod N) holds exactly
when it holds mod S and mod q. The mod-S part is determined by r, which is type (a). The mod-q
part is (a−a') + (b−b')u ≡ 0 (mod q). This is either independent of u (when b ≡ b' mod q) or has
exactly one root u, which is type (b) with δ = 1.
**M = q, k₀ = 2, δ = 1 ⇒ Q\*_LB ≈ √q.**

*Upper bound.* Pohlig–Hellman over every q^e ∥ N. For each prime power: one projection
γ = g^(N/q), a shared baby table of size m = min(q, ⌈√(eq)⌉), one stride, and per digit one
target projection (1 query for the first digit, 3 afterwards) plus at most ⌈q/m⌉−1 giant steps.
**Q\*_UB = Σ_{q^e∥N} [2 + (m − [m≥2]) + [⌈q/m⌉>1] + e(⌈q/m⌉−1) + 3(e−1)] + 1 ≈ 2√q + O(bits(S)).**

### Rung 2: short exponent (interval BSGS)

*Instance.* N is a 128-bit prime, and x is uniform in [0, 2^t) with t = 2L−2. Published: g, h.

*Lower bound.* A nonzero linear polynomial mod a prime has at most one root, so a pair collides
for at most one of the 2^t possible values of x (δ = 1).
**M = 2^t ⇒ Q\*_LB ≈ 2^(t/2).**

*Upper bound.* BSGS on the interval: a table of ⌈√W⌉ baby steps and at most ⌈W/m⌉−1 giant
steps, with W = 2^t.
**Q\*_UB = m + ⌈W/m⌉ − 1 + 1 ≈ 2^(t/2+1).**

(A kangaroo attack has the same √W scaling with a larger constant in expectation. BSGS is used
because its worst case is exact.)

### Rung 3: smooth order and short exponent combined

*Instance.* N = S·P, where S is ~20-bit smooth as in rung 1 and P is a 96-bit prime. The secret
x is uniform in [0, 2^t) with t = (2L−3) + bits(S). Published: g, h.

*Lower bound.* Give r = x mod S for free. Then x = r + S·k, where k is uniform over
n_r ≥ ⌊2^t/S⌋ values, and n_r < P. For two elements a + bx and a' + b'x:
- If b ≢ b' (mod P), then (b−b')S is a unit mod P, so at most one k in range gives a collision
  (type (b)).
- If b ≡ b' (mod P), then (b−b')S ≡ 0 (mod N), so equality depends only on (a−a') + (b−b')r,
  which is known (type (a)).

**M = ⌊2^t/S⌋ ⇒ Q\*_LB ≈ √(2^t/S) ≈ 2^(L−1.5).**

*Upper bound.* Pohlig–Hellman over S gives r = x mod S. Three more queries give g^S and h·g^(−r).
Then BSGS runs over k ∈ [0, ⌈(2^t − r)/S⌉) in ⟨g^S⟩.
**Q\*_UB = PH(S) + 3 + BSGS(⌈2^t/S⌉) + 1.**

*Both structures are necessary.*
- Ignoring the smoothness, interval search over 2^t costs 2^(t/2+1). That is about 2^(bits(S)/2)
  ≈ 2^10 times Q\*, or about 2^8·B.
- Ignoring the interval, Pohlig–Hellman is blocked by the 96-bit prime P, which would cost
  about 2^49 queries.

### Rung 4: auxiliary input g^(x^d) with d | p−1 (Cheon)

*Instance.* p is prime, d is a 14-bit prime with d | p−1, and (p−1)/d ≈ (2^(L−1) − √d)². The
secret x is uniform in [1, p). Published: g, h = g^x, h_d = g^(x^d).

*Lower bound.* Reachable exponents are a + bX + cX^d, so any two distinct ones differ by a
nonzero polynomial of degree ≤ d. Such a polynomial has at most d roots in Z_p^*.
**M = p−1, k₀ = 3, δ = d ⇒ Q\*_LB ≈ √((p−1)/d).**

This is the bound Boneh and Boyen prove for q-SDH (J. Cryptology 2008): Ω(√(p/q)) for q < O(∛p).
Our setting has only the two powers x and x^d, and Lemma 1 proves the bound directly for all d.
Boneh and Boyen also point out that Cheon's algorithm matches it. That is the tightness we use.

*Upper bound* (Cheon, Eurocrypt 2006 / J. Cryptology 2010; Brown–Gallant 2004). Let ζ generate
F_p^*.
- Write x^d = ξ^(k₀) with ξ = ζ^d of order n₁ = (p−1)/d. Find k₀ by BSGS *in the exponent*: the
  baby table holds g^(ξ^j), and the giant steps are (h_d)^(ξ^(−i·m₁)). Each step is one `exp`.
- Then x = ζ^(k₀)·η^l, with η = ζ^(n₁) of order d. Find l the same way: the baby table holds
  g^(ζ^(k₀)·η^v), and the giant steps are h^(η^(−u·m₂)).

**Q\*_UB = (m₁−1) + (⌈n₁/m₁⌉−1) + m₂ + (⌈d/m₂⌉−1) + 1 ≈ 2√(p/d) + 2√d.**

Since d ≈ 2^14 ≪ √p, the √(p/d) term dominates and UB/LB → 2. In the op-only model both steps
pick up a log p factor, which is why Cheon's paper states Õ(·).

*Why rung 4 starts at L = 11.* Cheon saves at most a factor p^(1/4), so the naive cost √p is at
most (Q\*)². At Q\* = 2^8 there is no parameter choice that keeps the naive attack well above the
budget while d ≪ √p. From L = 11 upward, naive BSGS costs 2^4.4–2^6.6 times the budget.

## 4. Verified ladders

`python scripts/verify_reference.py --seeds 3` generates 3 instances per (rung, level). It runs
the reference attack through the real oracle and checks two things: the attack succeeds with at
most Q\*_UB queries, and naive BSGS over the whole group costs far more than the budget. The
table below is filled in from `results/reference_verification.json` (see `results/ladder.md`).

| rung | L | log2 Q*_LB | log2 Q*_UB | log2 B | log2 naive | UB/LB | reference used / Q*_UB (max) | all solved |
|---|---|---|---|---|---|---|---|---|
| 1 | 8 | 6.7 | 8.1 | 10.1 | 17.8 | 2.48–2.61 | 0.97 | True |
| 1 | 11 | 9.9 | 10.9 | 12.9 | 21.0 | 2.06–2.07 | 1.00 | True |
| 1 | 14 | 12.9 | 13.9 | 15.9 | 23.9 | 2.01–2.01 | 1.00 | True |
| 1 | 17 | 15.8 | 16.8 | 18.8 | 26.8 | 2.00–2.00 | 1.00 | True |
| 1 | 20 | 18.8 | 19.8 | 21.8 | 29.8 | 2.00–2.00 | 0.97 | True |
| 2 | 8 | 7.0 | 8.0 | 10.0 | 64.7 | 2.02–2.02 | 1.00 | True |
| 2 | 11 | 10.0 | 11.0 | 13.0 | 64.9 | 2.00–2.00 | 0.97 | True |
| 2 | 14 | 13.0 | 14.0 | 16.0 | 64.8 | 2.00–2.00 | 1.00 | True |
| 2 | 17 | 16.0 | 17.0 | 19.0 | 64.7 | 2.00–2.00 | 1.00 | True |
| 2 | 20 | 19.0 | 20.0 | 22.0 | 64.8 | 2.00–2.00 | 0.94 | True |
| 3 | 8 | 6.7 | 8.1 | 10.1 | 17.7 | 2.47–2.62 | 1.00 | True |
| 3 | 11 | 9.7 | 10.8 | 12.8 | 20.8 | 2.07–2.08 | 1.00 | True |
| 3 | 14 | 12.7 | 13.7 | 15.7 | 23.8 | 2.01–2.01 | 0.82 | True |
| 3 | 17 | 15.8 | 16.8 | 18.8 | 26.5 | 2.00–2.00 | 0.83 | True |
| 3 | 20 | 18.7 | 19.7 | 21.7 | 29.7 | 2.00–2.00 | 1.00 | True |
| 4 | 11 | 9.9 | 11.0 | 13.0 | 17.6 | 2.18–2.26 | 0.98 | True |
| 4 | 14 | 12.9 | 13.9 | 15.9 | 20.6 | 2.02–2.03 | 0.94 | True |
| 4 | 17 | 15.9 | 16.9 | 18.9 | 23.8 | 2.00–2.00 | 1.00 | True |
| 4 | 20 | 18.8 | 19.8 | 21.8 | 26.5 | 2.00–2.00 | 0.62 | True |

## 5. What "certified" means here, and what it does not mean

- **Certified:** no generic algorithm reaches success probability ½ with fewer than Q\*_LB
  queries, and an explicit algorithm always succeeds within Q\*_UB. Across all instances,
  Q\*_UB/Q\*_LB is between 2.0 and 2.7. Because the harness *is* the generic group, the bounds
  are theorems about the task itself. There is no unintended shortcut, and no scaling bug can
  make an instance easier than claimed.
- **Assumptions:** the label map is a secure PRP, and the challenger's memory is not readable
  from the sandbox (process isolation only; see the README).
- **Not certified:** the constant factor between Q\*_LB and Q\*_UB. We normalise efficiency by
  Q\*_UB, which is achievable. So an efficiency below 0 is possible (average-case luck, or a
  better constant than the BSGS worst case). Going far below the band is improbable: by
  Lemma 1, succeeding with m ≪ Q\*_LB queries happens with probability about (m/Q\*_LB)²/2.
