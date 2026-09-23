"""
Attack for the generic-group DLP challenge (ggm-dl style).

Structure exploited:
  - N (the group order) factors as a product of several small prime-power
    factors (the "smooth part" m) times one huge prime factor.
  - x is guaranteed to lie in [0, 2^t) for a small t (t << log2(N)).
  - We first use Pohlig-Hellman on the smooth part m of N to recover
    x mod m very cheaply (tiny BSGS per small factor).
  - We then know x = x0 + m*y with y in [0, ceil(2^t / m)), a MUCH smaller
    range than the full group order. We solve for y with a plain
    baby-step/giant-step search in that bounded range, using g^m as the
    base. This costs about 2*sqrt(2^t / m) oracle queries, which is
    designed to fit comfortably inside the query budget.
  - Finally x = x0 + m*y is combined and submitted.

Only oracle queries are used to do group arithmetic; factorization of the
public N (not a secret) is done locally with sympy/trial division.
"""
from __future__ import annotations

import math
import sys

from oracle_client import Oracle, OracleError

try:
    import sympy

    def factorize(n: int) -> dict[int, int]:
        return dict(sympy.factorint(n))
except ImportError:
    def factorize(n: int) -> dict[int, int]:
        # Simple fallback trial-division + Pollard rho factorizer.
        import random

        def is_probable_prime(n):
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
            for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
                if a >= n:
                    continue
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

        def pollard_rho(n):
            if n % 2 == 0:
                return 2
            while True:
                c = random.randrange(1, n)
                f = lambda x: (x * x + c) % n
                x = y = random.randrange(2, n)
                d = 1
                while d == 1:
                    x = f(x)
                    y = f(f(y))
                    d = math.gcd(abs(x - y), n)
                if d != n:
                    return d

        def _factor(n, out):
            if n == 1:
                return
            if is_probable_prime(n):
                out[n] = out.get(n, 0) + 1
                return
            d = n
            while d == n:
                d = pollard_rho(n)
            _factor(d, out)
            _factor(n // d, out)

        out: dict[int, int] = {}
        # strip tiny primes first for speed
        for p in range(2, 100000):
            while n % p == 0:
                out[p] = out.get(p, 0) + 1
                n //= p
            if p * p > n:
                break
        if n > 1:
            _factor(n, out)
        return out


def crt(residues: list[tuple[int, int]]) -> tuple[int, int]:
    """Combine (r_i, m_i) with pairwise-coprime m_i into (r, M)."""
    r, m = 0, 1
    for ri, mi in residues:
        # solve x = r (mod m), x = ri (mod mi)
        g, p, q = ext_gcd(m, mi)
        assert g == 1
        lcm = m * mi
        x = (r + m * (p * ((ri - r) // g) % mi)) % lcm
        r, m = x % lcm, lcm
    return r, m


def ext_gcd(a: int, b: int) -> tuple[int, int, int]:
    if b == 0:
        return a, 1, 0
    g, x1, y1 = ext_gcd(b, a % b)
    return g, y1, x1 - (a // b) * y1


def small_factor_dlog(o: Oracle, g: str, h: str, N: int, n: int, cofactor: int) -> int:
    """
    Pohlig-Hellman step: recover x mod n (n a small prime power dividing N),
    given g of order N (so g^cofactor has order n) via brute force / BSGS.
    cofactor = N // n.
    """
    g_n = o.exp(g, cofactor)
    h_n = o.exp(h, cofactor)

    # brute force for very small n, BSGS otherwise
    if n <= 4096:
        # build table of g_n^0.. via incremental multiply (n queries worst case)
        cur = o.exp(g_n, 0)  # identity
        if cur == h_n:
            return 0
        for j in range(1, n):
            cur = o.mul(cur, g_n)
            if cur == h_n:
                return j
        raise RuntimeError("small_factor_dlog: not found (brute force)")
    else:
        B = int(math.isqrt(n)) + 1
        table = {}
        cur = o.exp(g_n, 0)
        table[cur] = 0
        for j in range(1, B):
            cur = o.mul(cur, g_n)
            table.setdefault(cur, j)
        # giant steps: h_n * (g_n^-B)^i
        g_n_negB = o.inv(o.exp(g_n, B))
        cur = h_n
        for i in range(0, B + 2):
            if cur in table:
                return (i * B + table[cur]) % n
            cur = o.mul(cur, g_n_negB)
        raise RuntimeError("small_factor_dlog: not found (BSGS)")


def bounded_bsgs(o: Oracle, base: str, target: str, Y: int) -> int:
    """
    Solve target = base^y for y in [0, Y) using baby-step/giant-step.
    Costs about 2*sqrt(Y) oracle queries.
    """
    if Y <= 1:
        return 0
    B = int(math.isqrt(Y)) + 1
    table = {}
    cur = o.exp(base, 0)  # identity
    table[cur] = 0
    for j in range(1, B):
        cur = o.mul(cur, base)
        table.setdefault(cur, j)

    base_negB = o.inv(o.exp(base, B))
    cur = target
    steps = Y // B + 2
    for i in range(0, steps + 1):
        if cur in table:
            y = i * B + table[cur]
            if 0 <= y < Y:
                return y
        cur = o.mul(cur, base_negB)
    raise RuntimeError("bounded_bsgs: y not found in range")


def main():
    o = Oracle()
    inst = o.instance
    N = int(inst["N"])
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]
    params = inst.get("params", {})
    t = int(params.get("t", N.bit_length()))

    fac = factorize(N)
    prime_powers = sorted((p ** e, p, e) for p, e in fac.items())

    # Pick a subset of small prime-power factors (smooth part) whose product
    # m keeps the residual search range Y = ceil(2^t / m) cheap, i.e. so that
    # ~2*sqrt(Y) fits well inside the budget. Greedily take smallest factors
    # first, stopping once the projected BSGS cost is small.
    budget = int(inst.get("budget", o.budget))
    safety = 0.5  # only use up to this fraction of budget for the main BSGS

    m = 1
    chosen = []
    for pe, p, e in prime_powers:
        # stop once adding more factors no longer helps (huge prime factor)
        Y_test = -(-(1 << t) // (m * pe))
        proj_cost = 2 * math.isqrt(Y_test) + 4 * len(chosen)
        if pe > (1 << t):
            # this factor alone exceeds the exponent range; no benefit, skip
            continue
        chosen.append((pe, p, e))
        m *= pe
        Y_now = -(-(1 << t) // m)
        if 2 * math.isqrt(Y_now) < budget * safety:
            # good enough; still keep adding small ones greedily to shrink further
            pass
        if m >= (1 << t):
            break

    # Recover x mod each chosen small prime power via Pohlig-Hellman.
    residues = []
    for pe, p, e in chosen:
        cofactor = N // pe
        r = small_factor_dlog(o, g, h, N, pe, cofactor)
        residues.append((r, pe))

    if residues:
        x0, m = crt(residues)
    else:
        x0, m = 0, 1

    Y = -(-(1 << t) // m)  # ceil(2^t / m)

    # h' = h * g^{-x0}; solve h' = (g^m)^y for y in [0, Y)
    g_x0 = o.exp(g, x0)
    g_x0_inv = o.inv(g_x0)
    h_prime = o.mul(h, g_x0_inv)
    g_m = o.exp(g, m)

    y = bounded_bsgs(o, g_m, h_prime, Y)

    x = x0 + m * y

    # sanity check locally before submitting (costs 2 queries)
    check = o.exp(g, x)
    if check != h:
        # Try full-range fallback search is infeasible; report diagnostic.
        raise RuntimeError(f"verification failed: g^x != h (x={x}, x0={x0}, m={m}, y={y}, Y={Y})")

    ok = o.submit(x)
    print(f"x = {x}")
    print(f"queries_used = {o.queries_used} / budget {o.budget}")
    print(f"submit correct = {ok}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
