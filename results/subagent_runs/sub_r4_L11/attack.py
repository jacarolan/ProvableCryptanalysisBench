"""
Cheon's algorithm for the discrete-log-with-auxiliary-input problem.

Setup: G is a cyclic group of prime order N, generator g. We are given
  h   = g^x
  h_d = g^(x^d mod N)
with d | (N-1).  Let e = (N-1)/d.

The oracle only lets us combine group elements via mul/inv/exp with KNOWN
integer exponents, so starting from {g, h, h_d} the only exponents we can
ever reach (relative to g) are the linear forms a + b*x + c*x^d (mod N)
for integers a,b,c of our choosing.  We can never synthesize a genuine
power like x^2 or x^17 out of thin air -- so the attack must stay linear.

Step A (find x^d mod N as an explicit number, up to a size-e ambiguity):
  By Fermat, V := x^d mod N satisfies V^e = x^(d*e) = x^(N-1) = 1 (mod N),
  so V lies in the unique order-e subgroup H_e = <eta> of Z_N^*, i.e.
  V = eta^m for some unknown m in [0, e).  Since h_d = g^V, we search for
  m such that  g^(eta^m) == h_d,  which is a baby-step/giant-step search
  of size e (cost O(sqrt(e))): baby table g^(eta^m1), giant steps
  h_d^(inverse(eta^(m2*s))).  This determines V = eta^m as a concrete
  number -- no unknown exponents involved, just modular arithmetic once m
  is known.

Step B (recover x from V, up to a size-d ambiguity):
  V is a d-th power (V = x^d) and gcd(d,e) = 1 (checked at runtime), so
  the d-th power map is a bijection on H_e; hence
     V0 := V^(d^-1 mod e) mod N
  is a specific d-th root of V lying in H_e.  All d-th roots of V are
  V0 * zeta^i for i in [0,d), zeta a generator of the order-d subgroup of
  Z_N^*, and x is one of them.  A second baby-step/giant-step search
  (base = g^V0, computed with one query; target = h = g^x) of size d
  finds i, giving x = V0 * zeta^i mod N.

Total query cost ~ 2*sqrt(e) + 2*sqrt(d) + O(1), far below sqrt(N).
This is the classical Cheon attack for auxiliary input g^(x^d) with
d | N-1 (Cheon, "Discrete Logarithm Problems with Auxiliary Inputs").
"""
from __future__ import annotations

import math
import sys

from oracle_client import Oracle, OracleError


def trial_factor(n: int) -> dict[int, int]:
    f: dict[int, int] = {}
    d = 2
    while d * d <= n:
        while n % d == 0:
            f[d] = f.get(d, 0) + 1
            n //= d
        d += 1 if d == 2 else 2
    if n > 1:
        f[n] = f.get(n, 0) + 1
    return f


def find_generator_of_order(order: int, order_factors: dict[int, int], N: int) -> int:
    """Find an element of Z_N^* of exact multiplicative order `order`,
    given order | (N-1) and the prime factorization of `order`."""
    import random
    primes = list(order_factors.keys())
    while True:
        r = random.randrange(2, N - 1)
        cand = pow(r, (N - 1) // order, N)
        if cand == 1:
            continue
        ok = True
        for p in primes:
            if pow(cand, order // p, N) == 1:
                ok = False
                break
        if ok:
            return cand


class BSGS:
    """Batches the baby-step / giant-step search for k in [0,K) such that
    oracle.exp(base, pow(mult, k, N)) == target, using two batched queries
    (one for all baby steps, one for all giant steps)."""

    def __init__(self, oracle: Oracle, N: int):
        self.oracle = oracle
        self.N = N

    def solve(self, base: str, mult: int, K: int, target: str) -> int:
        N = self.N
        s = int(math.isqrt(K - 1)) + 1 if K > 1 else 1
        while s * s < K:
            s += 1
        ngiant = (K + s - 1) // s

        # baby steps: B[k1] = base^(mult^k1 mod N), k1 = 0..s-1
        baby_ops = []
        cur = 1
        exps = []
        for k1 in range(s):
            exps.append(cur)
            baby_ops.append(["exp", base, cur])
            cur = (cur * mult) % N
        baby_labels = self.oracle.query(baby_ops)
        table = {lab: k1 for k1, lab in enumerate(baby_labels)}

        # giant steps: G[k2] = target^(inverse(mult^(k2*s) mod N))
        step = pow(mult, s, N)
        giant_ops = []
        cur = 1  # mult^(k2*s) accumulator
        for k2 in range(ngiant):
            inv = pow(cur, -1, N)
            giant_ops.append(["exp", target, inv])
            cur = (cur * step) % N
        giant_labels = self.oracle.query(giant_ops)

        for k2, lab in enumerate(giant_labels):
            if lab in table:
                k1 = table[lab]
                k = k1 + k2 * s
                if k < K:
                    return k
        raise RuntimeError("BSGS: no collision found (unexpected)")


def solve(oracle: Oracle) -> int:
    inst = oracle.instance
    N = int(inst["N"])
    labels = inst["labels"]
    g, h = labels["g"], labels["h"]
    params = inst.get("params", {})
    if "d" in params:
        d = int(params["d"])
        h_d = labels.get("h_d")
    else:
        # fall back: find the aux label / d some other way
        d = int(inst["d"])
        h_d = labels["h_d"]
    assert h_d is not None, "instance did not publish h_d"

    assert (N - 1) % d == 0, "d does not divide N-1; assumptions violated"
    e = (N - 1) // d
    g0 = math.gcd(d, e)
    if g0 != 1:
        raise RuntimeError(f"gcd(d,e)={g0} != 1; this attack assumes coprimality")

    d_factors = trial_factor(d)
    e_factors = trial_factor(e)

    zeta = find_generator_of_order(d, d_factors, N)
    eta = find_generator_of_order(e, e_factors, N)

    bsgs = BSGS(oracle, N)

    # Step A: find m in [0,e) with g^(eta^m) == h_d  =>  V = x^d mod N = eta^m
    m = bsgs.solve(g, eta, e, h_d)
    V = pow(eta, m, N)

    # Step B: V0 is a d-th root of V lying in H_e; find i in [0,d) with
    # (g^V0)^(zeta^i) == h  =>  x = V0 * zeta^i mod N
    d_inv_mod_e = pow(d, -1, e)
    V0 = pow(V, d_inv_mod_e, N)
    base2 = oracle.exp(g, V0)
    i = bsgs.solve(base2, zeta, d, h)

    x = (V0 * pow(zeta, i, N)) % N
    return x


def main():
    oracle = Oracle()
    x = solve(oracle)
    ok = oracle.submit(x)
    print(f"x = {x}")
    print(f"submit correct = {ok}")
    print(f"queries_used = {oracle.queries_used} / budget = {oracle.budget}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
