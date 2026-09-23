"""Attack for the generic-group DL challenge (rung ggm-dl-3).

Structure exploited
--------------------
The group has order N which factors as a handful of small primes (or small
prime powers) times one very large prime cofactor:

    N = q_1 * q_2 * ... * q_k * P        (q_i small, P huge, ~2^90+)

The secret x is sampled from [0, 2^t) with t small (e.g. 33 bits), i.e. x is
*much* smaller than N. That means:

  1. We can run classic Pohlig-Hellman restricted to the smooth part
     M = q_1 * ... * q_k (ignoring the huge cofactor P entirely -- we never
     need x mod P because x < 2^t << P already determines x mod P = x).
     This recovers r = x mod M using O(sum_i sqrt(q_i)) oracle queries.

  2. Once r = x mod M is known, every candidate for x has the form
     x = r + M*k for some small k in [0, ceil(2^t / M)). We then run a
     single baby-step giant-step search for k against the *shifted*
     instance  G' = g^M,  H' = h * g^-r  (so H' = G'^k). This costs
     O(sqrt(2^t / M)) queries.

Total query cost is therefore roughly
    2 * sum_i sqrt(q_i)  +  2 * sqrt(2^t / M)
which for the observed factorization (small primes ~2,43,67,79 and t=33)
is a few hundred queries -- comfortably inside the 1024 query budget,
whereas a plain BSGS/kangaroo over the full 2^33 range would need
~2*sqrt(2^33) ~ 185000 queries.

Nothing about N, the labels, x, or the specific small primes is hardcoded:
everything is read from GET /instance and re-derived every run so the same
script works against fresh instances of "the same kind and size".
"""
from __future__ import annotations

import math
from oracle_client import Oracle, OracleError


def isqrt_ceil(n: int) -> int:
    r = math.isqrt(n)
    return r if r * r == n else r + 1


class BatchedGroup:
    """Thin helper around an Oracle that counts/limits queries and gives a
    convenient interface for group ops, all backed by real oracle queries."""

    def __init__(self, oracle):
        self.o = oracle

    def exp(self, a, k):
        return self.o.exp(a, int(k))

    def mul(self, a, b):
        return self.o.mul(a, b)

    def inv(self, a):
        return self.o.inv(a)

    def exp_many(self, a, ks):
        """Batch a^k for many k against a fixed base label a. Returns list."""
        ops = [["exp", a, str(int(k))] for k in ks]
        return self.o.query(ops)

    def remaining(self):
        return self.o.budget - self.o.queries_used


def bsgs(grp: BatchedGroup, base_label, target_label, order: int, identity_label=None):
    """Find e in [0, order) with base^e == target, via baby-step/giant-step.

    Uses batched 'exp' queries for baby steps and a chained batch of 'mul'
    queries (via $i references) for giant steps, so the whole search is a
    small, fixed number of HTTP round trips.
    """
    order = int(order)
    if order <= 1:
        return 0

    m = isqrt_ceil(order)

    # Baby steps: base^0 .. base^(m-1)  (batched into one call)
    baby_labels = grp.exp_many(base_label, range(m))
    baby = {lab: j for j, lab in enumerate(baby_labels)}
    if target_label in baby:
        return baby[target_label]

    # factor = base^(-m)
    factor = grp.exp(base_label, -m)

    # Giant steps: target, target*factor, target*factor^2, ... chained in one batch
    max_i = (order // m) + 2
    ops = []
    ops.append(["mul", target_label, factor])  # $0 = target*factor^1
    for i in range(1, max_i):
        ops.append(["mul", f"${i - 1}", factor])  # $i = target*factor^(i+1)
    results = grp.o.query(ops)

    cur = target_label
    if cur in baby:
        return baby[cur]
    for i, lab in enumerate(results):
        if lab in baby:
            e = (i + 1) * m + baby[lab]
            if e < order:
                return e
        cur = lab
    raise RuntimeError("bsgs: discrete log not found in expected range")


def factor_smooth_part(N: int, limit: int):
    """Trial-divide N by all primes up to `limit`. Returns (factors dict
    {prime: exponent}, cofactor) where cofactor has no factors <= limit."""
    factors = {}
    n = N
    d = 2
    while d <= limit and d * d <= n:
        while n % d == 0:
            factors[d] = factors.get(d, 0) + 1
            n //= d
        d += 1 if d == 2 else 2
    return factors, n


def pohlig_hellman_prime_power(grp: BatchedGroup, g_label, h_label, N: int, p: int, e: int):
    """Solve for r in [0, p**e) with h = g^r, where g is known to have order
    N (so we reduce to the order-p^e subgroup internally). Returns r."""
    q = p ** e
    N_over_q = N // q
    gq = grp.exp(g_label, N_over_q)
    hq = grp.exp(h_label, N_over_q)

    if e == 1:
        return bsgs(grp, gq, hq, p)

    gamma = grp.exp(gq, p ** (e - 1))
    x_val = 0
    for i in range(e):
        ginv = grp.exp(gq, -x_val) if x_val != 0 else grp.exp(gq, 0)
        hi_temp = grp.mul(hq, ginv)
        hi = grp.exp(hi_temp, p ** (e - 1 - i))
        di = bsgs(grp, gamma, hi, p)
        x_val += di * (p ** i)
    return x_val % q


def crt_combine(residues):
    """residues: list of (r_i, m_i) pairwise coprime. Returns (R, M) with
    R mod M matching all residues."""
    R, M = 0, 1
    for r, m in residues:
        # solve R + M*t = r (mod m)
        g = math.gcd(M, m)
        assert g == 1, "moduli must be pairwise coprime"
        inv = pow(M % m, -1, m)
        t = ((r - R) * inv) % m
        R = R + M * t
        M = M * m
        R %= M
    return R, M


def main():
    o = Oracle()
    inst = o.instance
    N = int(inst["N"])
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]
    t = int(inst.get("params", {}).get("t", 33))
    budget = o.budget

    grp = BatchedGroup(o)

    # 1) find the smooth part of N. Grow the trial-division limit until we
    #    have enough smooth-part coverage that the leftover BSGS range is
    #    affordable, or until further growth stops helping.
    limit = 2000
    best = None
    while True:
        factors, cof = factor_smooth_part(N, limit)
        M = 1
        for p, e in factors.items():
            M *= p ** e
        rng = -(-(1 << t) // M)  # ceil(2**t / M)
        # rough query cost estimate
        small_cost = sum(4 + 2 * e * isqrt_ceil(p) for p, e in factors.items())
        main_cost = 2 * isqrt_ceil(rng) + 10
        total_cost = small_cost + main_cost + 20
        best = (factors, M, rng, total_cost)
        if total_cost <= budget * 0.85 or limit >= 5_000_000:
            break
        limit *= 5

    factors, M, rng, est_cost = best
    if est_cost > budget:
        raise RuntimeError(f"estimated cost {est_cost} exceeds budget {budget}; "
                            f"factors found: {factors}")

    # 2) Pohlig-Hellman on each small prime-power factor -> x mod M
    residues = []
    for p, e in factors.items():
        r = pohlig_hellman_prime_power(grp, g, h, N, p, e)
        residues.append((r, p ** e))

    if residues:
        r, M_check = crt_combine(residues)
        assert M_check == M
    else:
        r, M = 0, 1

    # 3) BSGS on the shifted problem to find k in [0, rng): h = g^r * (g^M)^k
    Gp = grp.exp(g, M)
    g_minus_r = grp.exp(g, -r) if r != 0 else grp.exp(g, 0)
    Hp = grp.mul(h, g_minus_r)

    k = bsgs(grp, Gp, Hp, rng)

    x = r + M * k

    ok = o.submit(x)
    print(f"N={N} t={t} budget={budget} queries_used={o.queries_used}")
    print(f"small factors={factors} M={M} range={rng}")
    print(f"recovered x={x} submit correct={ok}")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
