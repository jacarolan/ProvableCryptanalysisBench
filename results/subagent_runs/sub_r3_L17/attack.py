"""
Attack on the generic-group discrete-log challenger.

Structure exploited
--------------------
The group order N handed out by the challenger factors as

    N = (product of a handful of small primes)  *  (one large prime cofactor)

while the secret x is guaranteed to be much smaller than N (x < 2**t, with t
given in the instance parameters, e.g. t=52 while N is ~116 bits).

That combination lets us avoid ever touching the huge prime factor:

1.  Pohlig-Hellman on the *smooth* part of N (the small prime-power factors)
    recovers  r = x mod M  where M is the product of those small factors,
    at a cost of a handful of tiny baby-step/giant-step (BSGS) searches
    (sqrt(small prime) queries each).

2.  Because x < 2**t, write x = r + M*k with  0 <= k < ceil(2**t / M).
    Substituting into h = g^x gives

        (g^M)^k = h * g^(-r)

    which is a single discrete-log problem with a *much* smaller range
    (2**t / M instead of 2**t or N), solved with one BSGS costing about
    2*sqrt(2**t / M) queries.

Total query cost is therefore roughly 2*sqrt(2**t / M) plus the tiny cost of
step 1 -- far below a budget that would only tolerate O(sqrt(2**t)) naive
BSGS if M were 1.

The code never hard-codes N, t, or the labels: everything is read from
GET /instance at runtime, and the factorization / smooth-part selection is
computed on the fly so the same script works on any fresh instance "of the
same kind and size".
"""
from __future__ import annotations

import math
import sys
from math import isqrt

from oracle_client import Oracle, OracleError


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def trial_factor(n: int, limit: int = 2_000_000) -> tuple[dict[int, int], int]:
    """Factor out all prime powers with prime <= limit. Returns (factors, cofactor)."""
    factors: dict[int, int] = {}
    d = 2
    m = n
    while d <= limit and d * d <= m:
        while m % d == 0:
            factors[d] = factors.get(d, 0) + 1
            m //= d
        d += 1 if d == 2 else 2
    return factors, m


def pollard_rho(n: int) -> int:
    if n % 2 == 0:
        return 2
    if n % 3 == 0:
        return 3
    import random
    while True:
        c = random.randrange(1, n - 1)
        f = lambda x: (x * x + c) % n
        x = random.randrange(2, n - 1)
        y = x
        d = 1
        while d == 1:
            x = f(x)
            y = f(f(y))
            d = math.gcd(abs(x - y), n)
        if d != n:
            return d


def full_factor(n: int, limit: int = 2_000_000) -> dict[int, int]:
    """Full factorization: small trial division, then Pollard rho for the rest."""
    factors, m = trial_factor(n, limit)
    stack = [m] if m > 1 else []
    while stack:
        cur = stack.pop()
        if cur == 1:
            continue
        if is_probable_prime(cur):
            factors[cur] = factors.get(cur, 0) + 1
            continue
        d = pollard_rho(cur)
        stack.append(d)
        stack.append(cur // d)
    return factors


def is_probable_prime(n: int, k: int = 40) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    import random
    for _ in range(k):
        a = random.randrange(2, n - 1)
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


# ---------------------------------------------------------------------------
# oracle-backed group arithmetic helpers
# ---------------------------------------------------------------------------

class Group:
    def __init__(self, oracle: Oracle):
        self.o = oracle
        self.queries = 0

    def query(self, ops):
        r = self.o.query(ops)
        self.queries += len(ops)
        return r

    def exp(self, a, k):
        return self.query([["exp", a, int(k)]])[0]

    def mul(self, a, b):
        return self.query([["mul", a, b]])[0]

    def inv(self, a):
        return self.query([["inv", a]])[0]


def bsgs_fixed(grp: Group, g_label: str, h_label: str, n: int) -> int | None:
    """Correct, careful BSGS implementation (0 <= x < n, g^x = h)."""
    if n <= 1:
        return 0
    m = isqrt(n - 1) + 1

    # --- baby steps ---
    ops = [["exp", g_label, 0]]
    for j in range(1, m):
        ops.append(["mul", f"${j - 1}", g_label])
    baby = grp.query(ops)
    baby_index = {}
    for j, lab in enumerate(baby):
        if lab not in baby_index:
            baby_index[lab] = j

    if h_label in baby_index:
        return baby_index[h_label]

    # --- giant steps ---
    # factor = g^{-m}; giant_1 = h * factor; giant_i = giant_{i-1} * factor
    ops2 = [["exp", g_label, -m]]          # $0 = g^{-m}
    ops2.append(["mul", h_label, "$0"])    # $1 = h * g^{-m}
    for i in range(2, m + 1):
        ops2.append(["mul", f"${i - 1}", "$0"])  # $i = giant_{i-1} * $0
    res = grp.query(ops2)
    # res[0] is $0 = g^{-m} (not a giant step); res[i] for i=1..m is giant step i.
    for i in range(1, m + 1):
        lab = res[i]
        if lab in baby_index:
            j = baby_index[lab]
            return j + m * i
    return None


def dlog_prime_power(grp: Group, g_label: str, h_label: str, p: int, e: int, order_hint: int | None = None) -> int:
    """Discrete log of h base g, where g is known to have order exactly p**e."""
    q = p ** e
    g_inv = grp.inv(g_label)
    h_i = h_label
    x = 0
    gamma = grp.exp(g_label, p ** (e - 1)) if e > 1 else g_label  # order-p element

    for i in range(e):
        exponent = p ** (e - 1 - i)
        target = grp.exp(h_i, exponent) if exponent != 1 else h_i
        x_i = bsgs_fixed(grp, gamma, target, p)
        if x_i is None:
            raise RuntimeError(f"failed to solve digit {i} for prime {p}^{e}")
        x += x_i * (p ** i)
        if x_i != 0 and i != e - 1:
            corr = grp.exp(g_inv, x_i * (p ** i))
            h_i = grp.mul(h_i, corr)
    return x % q


def crt(residues: list[tuple[int, int]]) -> tuple[int, int]:
    """Combine list of (r_i, m_i) with coprime m_i into (r, M)."""
    r, M = 0, 1
    for ri, mi in residues:
        # solve x = r (mod M), x = ri (mod mi)
        g, p_, q_ = ext_gcd(M, mi)
        assert (ri - r) % g == 0
        lcm = M // g * mi
        tmp = (ri - r) // g % (mi // g)
        x = (r + M * (tmp * p_ % (mi // g))) % lcm
        r, M = x, lcm
    return r % M, M


def ext_gcd(a: int, b: int) -> tuple[int, int, int]:
    if b == 0:
        return a, 1, 0
    g, x1, y1 = ext_gcd(b, a % b)
    return g, y1, x1 - (a // b) * y1


# ---------------------------------------------------------------------------
# main attack
# ---------------------------------------------------------------------------

def main():
    o = Oracle()
    inst = o.instance
    N = int(inst["N"])
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]
    params = inst.get("params", {}) or {}
    t = int(params.get("t", N.bit_length()))
    bound = 1 << t  # x in [0, bound)

    grp = Group(o)

    print(f"N={N} ({N.bit_length()} bits), t={t}, budget={o.budget}", file=sys.stderr)

    # 1. factor N (small trial division should find the smooth part quickly;
    #    fall back to Pollard rho for anything trial division misses).
    factors = full_factor(N, limit=2_000_000)
    print(f"factors: {factors}", file=sys.stderr)

    # 2. choose the "smooth part": every prime power factor whose individual
    #    BSGS cost (~sqrt(p^e)) is affordable. Anything left out (typically a
    #    single huge prime cofactor) is absorbed into the final search range.
    PER_FACTOR_BUDGET = 200_000  # sqrt(p^e) must be <= this to include it
    items = sorted(factors.items())
    residues = []
    M = 1
    for p, e in items:
        q = p ** e
        if isqrt(q) + 1 > PER_FACTOR_BUDGET:
            continue  # too expensive / this is the "hard" cofactor -> skip
        exp_val = N // q
        g_q = grp.exp(g, exp_val)
        h_q = grp.exp(h, exp_val)
        xi = dlog_prime_power(grp, g_q, h_q, p, e)
        residues.append((xi, q))
        M *= q
        print(f"  solved digit for {p}^{e}: x = {xi} (mod {q})  [queries so far: {grp.queries}]",
              file=sys.stderr)

    if residues:
        r, M = crt(residues)
    else:
        r, M = 0, 1

    print(f"r = x mod {M} = {r}   (queries so far: {grp.queries})", file=sys.stderr)

    # 3. final range reduction: x = r + M*k, 0 <= k < k_bound
    k_bound = (bound + M - 1) // M if M > 0 else bound
    k_bound = max(k_bound, 1)
    print(f"k_bound = {k_bound}  (need ~{2 * (isqrt(k_bound - 1) + 1)} queries for final BSGS)",
          file=sys.stderr)

    if M == 1:
        # no smooth part found at all; just do a direct BSGS on x itself.
        x = bsgs_fixed(grp, g, h, bound)
        if x is None:
            raise RuntimeError("direct BSGS failed to find x")
    else:
        g_neg_r = grp.exp(g, -r)
        H = grp.mul(h, g_neg_r)
        G = grp.exp(g, M)
        k = bsgs_fixed(grp, G, H, k_bound)
        if k is None:
            raise RuntimeError("final BSGS failed to find k")
        x = r + M * k

    x %= N
    print(f"recovered x = {x}   (total queries: {grp.queries})", file=sys.stderr)

    ok = o.submit(x)
    print(f"submit -> correct={ok}, queries_used={o.queries_used}/{o.budget}", file=sys.stderr)
    if not ok:
        raise SystemExit("submission was rejected as incorrect")


if __name__ == "__main__":
    main()
