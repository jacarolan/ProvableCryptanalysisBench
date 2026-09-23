"""Pohlig-Hellman + baby-step-giant-step attack against the generic-group DLOG oracle.

Strategy
--------
The challenger publishes N (the order of the cyclic group G = <g>) and h = g^x.
We factor N into prime powers q_1, ..., q_k (coprime, product = N). For each
prime power q_i = p_i^{e_i} we project g and h into the unique subgroup of
order q_i:

    g_i = g^(N/q_i)      (has order exactly q_i, since g has order N)
    h_i = h^(N/q_i) = g_i^(x mod q_i)

and recover x_i = x mod q_i with baby-step-giant-step (BSGS) in that subgroup,
which costs O(sqrt(q_i)) oracle queries. Finally we combine the x_i via CRT to
get x mod N = x (since 0 <= x < N).

This works for *any* N of this shape (we never hard-code the factorization);
the only requirement is that every prime power factor of N be small enough
that BSGS's O(sqrt(q_i)) queries fit the budget - true here since the largest
factor observed is ~4.8e7 (sqrt ~ 6928), while the budget is tens of
thousands of queries.

Query cost: for each prime power factor q_i, BSGS uses about
2*ceil(sqrt(q_i)) + O(1) queries (baby steps + giant steps), plus 2 queries
to project g and h into the subgroup. Total is dominated by the largest
prime-power factor of N.
"""
from __future__ import annotations

import math
import os
import sys

import sympy

from oracle_client import Oracle, OracleError


def bsgs(o: Oracle, g: str, h: str, q: int) -> int:
    """Solve h = g^x for x in [0, q), where g has order exactly q (in G)."""
    if q == 1:
        return 0

    m = math.isqrt(q - 1) + 1  # m = ceil(sqrt(q))

    # Baby steps: table[label of g^j] = j, for j = 0 .. m-1.
    table: dict[str, int] = {}
    cur = o.exp(g, 0)  # identity
    table.setdefault(cur, 0)
    for j in range(1, m):
        cur = o.mul(cur, g)
        table.setdefault(cur, j)

    # Giant steps: look for h * (g^-m)^i in the baby-step table.
    g_minus_m = o.exp(g, -m)
    cur = h
    for i in range(0, m + 1):
        if cur in table:
            return (i * m + table[cur]) % q
        cur = o.mul(cur, g_minus_m)

    raise RuntimeError(f"bsgs failed to find discrete log mod {q}")


def crt_combine(moduli: list[int], residues: list[int]) -> int:
    x, m = 0, 1
    for qi, ri in zip(moduli, residues):
        # combine (x mod m) with (ri mod qi) via CRT, m and qi coprime
        lcm = m * qi // math.gcd(m, qi)
        diff = ri - x
        inv_m = pow(m, -1, qi)
        t = (diff * inv_m) % qi
        x = x + m * t
        m = lcm
        x %= m
    return x


def main() -> None:
    o = Oracle()
    N = int(o.instance["N"])
    g = o.instance["labels"]["g"]
    h = o.instance["labels"]["h"]

    factors = sympy.factorint(N)  # {p: e, ...}

    moduli: list[int] = []
    residues: list[int] = []
    for p, e in factors.items():
        q = p ** e
        n = N // q
        gi = o.exp(g, n)
        hi = o.exp(h, n)
        xi = bsgs(o, gi, hi, q)
        moduli.append(q)
        residues.append(xi)

    x = crt_combine(moduli, residues) % N

    ok = o.submit(x)
    print(f"submitted x={x} correct={ok} queries_used={o.queries_used} budget={o.budget}",
          file=sys.stderr)
    if not ok:
        raise SystemExit(f"submission rejected: x={x}")


if __name__ == "__main__":
    main()
