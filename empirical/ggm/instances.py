"""Random generic-group discrete-log instances and the expected-query lower bound.

Instance for security parameter lam: N a uniformly random lam-bit prime, the cyclic group
Z_N = <g>, x uniform in [0, N), h = g^x. Budget B = 4 * (worst-case BSGS cost) so a runaway
attack is stopped, while any reasonable generic attack fits.

Lower bound (see README): any generic algorithm that makes at most m queries (including its
submission) succeeds with probability at most eps(m) = (C(m+2, 2) + 1) / N  [Shoup 1997;
k0 = 2 published elements g, h]. For an algorithm that always succeeds, with T its total
number of queries, Pr[T <= m] <= eps(m) (stop it after m queries), hence

    E[T] = sum_{m>=0} Pr[T > m] >= sum_{m>=0} max(0, 1 - eps(m))  ~  (2/3) sqrt(2N) ~ 0.943 sqrt(N).

`lb_expected` evaluates this sum exactly (hockey-stick identity).
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from fractions import Fraction

from .nt import ceil_div, ceil_sqrt, random_prime

BUDGET_FACTOR = 4


def bsgs_worst(N: int) -> int:
    """Worst-case queries of textbook BSGS (baby table incl. identity, stride, giant steps, submit)."""
    m = ceil_sqrt(N)
    return (m - 1) + ceil_div(N, m) + 1


def lb_expected(N: int) -> Fraction:
    """Exact value of sum_{m>=0} max(0, 1 - (C(m+2,2)+1)/N)."""
    # largest M with C(M+2, 2) + 1 < N, i.e. (M+2)(M+1)/2 <= N - 2
    M = max(0, math.isqrt(2 * N) - 2)
    while (M + 3) * (M + 2) // 2 <= N - 2:
        M += 1
    while M > 0 and (M + 2) * (M + 1) // 2 > N - 2:
        M -= 1
    if (M + 2) * (M + 1) // 2 > N - 2:
        return Fraction(0)
    # sum_{m=0}^{M} [1 - 1/N - C(m+2,2)/N] = (M+1)(N-1)/N - C(M+3,3)/N
    c3 = (M + 3) * (M + 2) * (M + 1) // 6
    return Fraction((M + 1) * (N - 1) - c3, N)


@dataclass
class Instance:
    lam: int
    N: int
    x: int
    budget: int
    lb_expected: float
    bsgs_worst: int

    def public_info(self) -> dict:
        return {"keygen": "N is a lam-bit prime; x is sampled uniformly at random from [0, N).",
                "params": {"lam": self.lam}}


def generate(lam: int, seed: bytes | int) -> Instance:
    if isinstance(seed, int):
        seed = seed.to_bytes(16, "big")
    rng = random.Random(hashlib.sha256(b"ggm-dl|%d|" % lam + seed).digest())
    N = random_prime(lam, rng)
    x = rng.randrange(N)
    w = bsgs_worst(N)
    return Instance(lam, N, x, BUDGET_FACTOR * w, float(lb_expected(N)), w)
