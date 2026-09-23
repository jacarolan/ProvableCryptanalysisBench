"""
Discrete-log attack against the generic-group oracle.

Structure exploited
--------------------
The group order N is (with overwhelming probability, by the challenger's key
generation) a product of a handful of small-to-medium prime powers times one
huge prime factor: N = q_1 * q_2 * ... * q_r * P  with each q_i small enough
that a baby-step/giant-step (BSGS) discrete log inside the order-q_i subgroup
is cheap, and P so large that solving a DL there is infeasible.

Since x is guaranteed to lie in [0, 2^t), we don't need x mod N -- only
x mod L for some L = q_1*...*q_k that exceeds 2^t / (affordable BSGS range).
Standard Pohlig-Hellman recovers x mod each small q_i cheaply (projecting g
and h into the order-q_i subgroup via exponentiation by N/q_i, then BSGS of
size O(sqrt(q_i))). CRT combines these into x mod L. Then a *second* BSGS,
now only over the residual range ceil(2^t / L), recovers the missing high
part of x. Total cost is O(sum(sqrt(q_i)) + sqrt(2^t / L)), far below the
naive O(sqrt(2^t)) needed for a plain BSGS over the whole range, and well
within the oracle's query budget.

Everything here is pure stdlib -- no sympy/numpy -- since the grading run
only has attack.py + oracle_client.py available.
"""
from __future__ import annotations

import math
import os
import random
import sys

from oracle_client import Oracle, OracleError


# ---------------------------------------------------------------------------
# Number theory: primality testing + factorization (pure stdlib)
# ---------------------------------------------------------------------------

def is_probable_prime(n: int, rounds: int = 40) -> bool:
    if n < 2:
        return False
    small_primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37]
    for p in small_primes:
        if n == p:
            return True
        if n % p == 0:
            return False
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = random.randrange(2, n - 1)
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def pollard_rho(n: int) -> int:
    if n % 2 == 0:
        return 2
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


def full_factor(n: int, trial_bound: int = 200_000) -> dict[int, int]:
    """Return {prime: exponent} for n, using trial division then Pollard rho."""
    factors: dict[int, int] = {}
    m = n
    d = 2
    while d <= trial_bound and d * d <= m:
        while m % d == 0:
            factors[d] = factors.get(d, 0) + 1
            m //= d
        d += 1 if d == 2 else 2
    if m == 1:
        return factors

    stack = [m]
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


# ---------------------------------------------------------------------------
# CRT
# ---------------------------------------------------------------------------

def crt_combine(residues: list[tuple[int, int]]) -> tuple[int, int]:
    """Combine [(r_i, m_i)] (pairwise coprime m_i) into (r, m)."""
    r, m = 0, 1
    for ri, mi in residues:
        # solve y*m ≡ (ri - r) (mod mi)
        g, p, _ = ext_gcd(m, mi)
        assert (ri - r) % g == 0
        lcm = m // g * mi
        tmp = (ri - r) // g % (mi // g)
        y = (p * tmp) % (mi // g)
        r = r + m * y
        m = lcm
        r %= m
    return r, m


def ext_gcd(a: int, b: int) -> tuple[int, int, int]:
    old_r, r = a, b
    old_s, s = 1, 0
    old_t, t = 0, 1
    while r != 0:
        q = old_r // r
        old_r, r = r, old_r - q * r
        old_s, s = s, old_s - q * s
        old_t, t = t, old_t - q * t
    return old_r, old_s, old_t


# ---------------------------------------------------------------------------
# Oracle-backed BSGS: solve k in [0, n) with target = base^k
# ---------------------------------------------------------------------------

def bsgs_oracle_chained(o: Oracle, base: str, target: str, n: int, chunk: int = 1000) -> int:
    """BSGS with batched, chained baby/giant steps to minimize round trips."""
    if n <= 1:
        return 0
    m = math.isqrt(n - 1) + 1

    table: dict[str, int] = {}
    last_label = None
    produced = 0
    while produced < m:
        take = min(chunk, m - produced)
        ops = []
        if last_label is None:
            ops.append(["exp", base, 0])
            for _ in range(take - 1):
                ops.append(["mul", "$" + str(len(ops) - 1), base])
        else:
            ops.append(["mul", last_label, base])
            for _ in range(take - 1):
                ops.append(["mul", "$" + str(len(ops) - 1), base])
        results = o.query(ops)
        for lab in results:
            if lab not in table:
                table[lab] = produced
            produced += 1
        last_label = results[-1]

    if target in table:
        return table[target]

    # factor = base^{-m}
    factor = o.query([["exp", base, -m]])[0]

    steps_needed = n // m + 2
    cur = target
    done = 0
    while done < steps_needed:
        take = min(chunk, steps_needed - done)
        ops = [["mul", cur, factor]]
        for _ in range(take - 1):
            ops.append(["mul", "$" + str(len(ops) - 1), factor])
        results = o.query(ops)
        for j, lab in enumerate(results, start=1):
            if lab in table:
                return (done + j) * m + table[lab]
        cur = results[-1]
        done += take

    raise ValueError("BSGS failed to find discrete log in range")


# ---------------------------------------------------------------------------
# Main attack
# ---------------------------------------------------------------------------

def main() -> None:
    o = Oracle()
    inst = o.instance
    N = int(inst["N"])
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]
    params = inst.get("params", {}) or {}
    t = int(params.get("t", 40))

    print(f"[attack] N={N} (bits={N.bit_length()}), t={t}, budget={o.budget}",
          file=sys.stderr)

    factors = full_factor(N)
    fac_list = sorted(p ** e for p, e in factors.items())
    print(f"[attack] factorization prime-powers: {fac_list}", file=sys.stderr)

    target_bound = 1 << t
    remaining_range = target_bound

    used_factors: list[int] = []
    residues: list[tuple[int, int]] = []

    for q in fac_list:
        if q > remaining_range:
            # No benefit: solving DL here costs sqrt(q) > sqrt(remaining_range).
            continue
        budget_left = o.budget - o.queries_used
        projected_cost = 2 * math.isqrt(q) + 10
        if projected_cost > budget_left - 500:  # keep a safety margin
            break

        cofactor = N // q
        gq, hq = o.query([["exp", g, cofactor], ["exp", h, cofactor]])
        kq = bsgs_oracle_chained(o, gq, hq, q)
        used_factors.append(q)
        residues.append((kq, q))
        remaining_range = (target_bound - 1) // (
            _prod(used_factors)
        ) + 2
        print(f"[attack] solved x mod {q} = {kq}; remaining_range ~ {remaining_range}",
              file=sys.stderr)

    if residues:
        x0, L = crt_combine(residues)
    else:
        x0, L = 0, 1

    print(f"[attack] x0={x0} mod L={L}", file=sys.stderr)

    final_range = (target_bound - 1 - x0) // L + 2
    print(f"[attack] final BSGS range = {final_range} "
          f"(budget left = {o.budget - o.queries_used})", file=sys.stderr)

    if final_range <= 1:
        x = x0
    else:
        G, Hx0 = o.query([["exp", g, L], ["exp", g, x0]])
        Hx0_inv = o.inv(Hx0)
        Hp = o.mul(h, Hx0_inv)
        k = bsgs_oracle_chained(o, G, Hp, final_range)
        x = x0 + L * k

    x %= N
    print(f"[attack] recovered x = {x}; queries_used={o.queries_used}/{o.budget}",
          file=sys.stderr)

    ok = o.submit(x)
    print(f"[attack] submit -> correct={ok}, queries_used={o.queries_used}/{o.budget}",
          file=sys.stderr)
    if not ok:
        sys.exit(1)


def _prod(xs: list[int]) -> int:
    p = 1
    for v in xs:
        p *= v
    return p


if __name__ == "__main__":
    main()
