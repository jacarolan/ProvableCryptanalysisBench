"""Certified query complexity: exact worst-case costs of the reference attacks (upper bounds) and
generic lower bounds (see THEORY.md for proofs). All costs are in oracle queries, including the
final submission.
"""
from __future__ import annotations

import math

from .nt import ceil_div, ceil_sqrt


# ---------------------------------------------------------------------------- upper bounds
def bsgs_table_cost(m: int) -> int:
    """Baby steps G^j, j in [0, m): j = 1 is free (G itself), every other j costs one exp."""
    return m - (1 if m >= 2 else 0)


def bsgs_giant_cost(W: int, m: int) -> int:
    """Worst-case giant-step queries for one target: one exp(G, -m) plus ceil(W/m) - 1 muls."""
    steps = ceil_div(W, m)
    return steps if steps > 1 else 0  # (1 for the stride) + (steps - 1)


def bsgs_cost(W: int) -> int:
    m = ceil_sqrt(W)
    return bsgs_table_cost(m) + bsgs_giant_cost(W, m)


def ph_prime_power_cost(q: int, e: int) -> int:
    """Pohlig-Hellman for one prime power q^e || N, digit by digit, sharing one baby table.

    1 query for gamma = g^(N/q); table of size m = min(q, ceil(sqrt(e*q))); one stride exp;
    per digit: projection of the target (1 query for the first digit, 3 afterwards) and at most
    ceil(q/m) - 1 giant steps.
    """
    m = min(q, ceil_sqrt(e * q))
    steps = ceil_div(q, m)
    stride = 1 if steps > 1 else 0
    return 1 + bsgs_table_cost(m) + stride + e * (steps - 1) + 1 + 3 * (e - 1)


def ph_cost(factors: dict[int, int]) -> int:
    return sum(ph_prime_power_cost(q, e) for q, e in factors.items())


def cheon_cost(p: int, d: int) -> int:
    """Cheon's attack given g, g^x, g^(x^d), d | p-1 (exp charged 1 query).

    Step 1: x^d = xi^k0 with xi = zeta^d of order n1 = (p-1)/d; BSGS in the exponent:
            baby g^(xi^j), j in [0, m1) (j = 0 free), giant (g^(x^d))^(xi^(-i*m1)) (i = 0 free).
    Step 2: x = zeta^k0 * eta^l with eta of order d; baby g^(zeta^k0 * eta^v), v in [0, m2),
            giant (g^x)^(eta^(-u*m2)) (u = 0 free).
    """
    n1 = (p - 1) // d
    m1 = ceil_sqrt(n1)
    m2 = ceil_sqrt(d)
    return (m1 - 1) + (ceil_div(n1, m1) - 1) + m2 + (ceil_div(d, m2) - 1)


# ---------------------------------------------------------------------------- lower bounds
def lb_queries(M: int, k0: int = 2, delta: int = 1, eps: float = 0.5) -> int:
    """Smallest m with (C(m + k0, 2) * delta + 1) / M >= eps.

    Any generic algorithm making m queries succeeds with probability at most
    (C(m + k0, 2) * delta + 1) / M, where k0 = number of published elements, delta = max
    degree of the published exponent polynomials and M = the size of the unknown's range
    (see THEORY.md, Lemma 1). So reaching success probability eps needs at least this many.
    """
    target = (eps * M - 1) / delta
    if target <= 0:
        return 0
    # C(n, 2) >= target  <=>  n >= (1 + sqrt(1 + 8 target)) / 2
    n = math.ceil((1 + math.sqrt(1 + 8 * target)) / 2)
    while n > 1 and (n - 1) * (n - 2) // 2 >= target:
        n -= 1
    while n * (n - 1) // 2 < target:
        n += 1
    return max(0, n - k0)


def success_ub(m: int, M: int, k0: int = 2, delta: int = 1) -> float:
    """The generic success-probability bound itself, capped at 1."""
    return min(1.0, ((m + k0) * (m + k0 - 1) // 2 * delta + 1) / M)
