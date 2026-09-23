"""Small, dependency-free number theory helpers (primality, factoring, CRT)."""
from __future__ import annotations

import math
import random

SMALL_PRIMES = [p for p in range(2, 1000) if all(p % q for q in range(2, int(p ** 0.5) + 1))]
_MR_BASES = SMALL_PRIMES[:24]


def is_prime(n: int) -> bool:
    """Miller-Rabin with the first 24 prime bases (deterministic far beyond 2^128 in practice;
    provably deterministic below 3.3e24)."""
    if n < 2:
        return False
    for p in SMALL_PRIMES[:30]:
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in _MR_BASES:
        y = pow(a, d, n)
        if y in (1, n - 1):
            continue
        for _ in range(s - 1):
            y = y * y % n
            if y == n - 1:
                break
        else:
            return False
    return True


def random_prime(bits: int, rng: random.Random) -> int:
    """Uniform-ish random prime with exactly `bits` bits."""
    assert bits >= 2
    while True:
        n = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if bits == 2:
            n = rng.choice([2, 3])
        if is_prime(n):
            return n


def _pollard_rho(n: int, rng: random.Random) -> int:
    if n % 2 == 0:
        return 2
    while True:
        x = rng.randrange(2, n)
        y, c, d = x, rng.randrange(1, n), 1
        while d == 1:
            x = (x * x + c) % n
            y = (y * y + c) % n
            y = (y * y + c) % n
            d = math.gcd(abs(x - y), n)
        if d != n:
            return d


def factorize(n: int, rng: random.Random | None = None) -> dict[int, int]:
    """Full factorization {prime: exponent}. Fine for n up to ~2^100 with small cofactors."""
    rng = rng or random.Random(0)
    out: dict[int, int] = {}
    for p in SMALL_PRIMES:
        while n % p == 0:
            out[p] = out.get(p, 0) + 1
            n //= p
    stack = [n] if n > 1 else []
    while stack:
        m = stack.pop()
        if is_prime(m):
            out[m] = out.get(m, 0) + 1
            continue
        d = _pollard_rho(m, rng)
        stack += [d, m // d]
    return dict(sorted(out.items()))


def crt(residues: list[int], moduli: list[int]) -> int:
    x, m = 0, 1
    for r, n in zip(residues, moduli):
        # solve x' = x mod m, x' = r mod n
        t = ((r - x) * pow(m, -1, n)) % n
        x += m * t
        m *= n
    return x % m


def primitive_root(p: int, factors_pm1: dict[int, int] | None = None) -> int:
    factors_pm1 = factors_pm1 or factorize(p - 1)
    for z in range(2, p):
        if all(pow(z, (p - 1) // q, p) != 1 for q in factors_pm1):
            return z
    raise ValueError("no primitive root")


def ceil_sqrt(n: int) -> int:
    r = math.isqrt(n)
    return r if r * r == n else r + 1


def ceil_div(a: int, b: int) -> int:
    return -(-a // b)
