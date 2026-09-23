"""Pohlig-Hellman + baby-step/giant-step attack on a generic-group DLP oracle.

Reads N, g, h from GET /instance at runtime. Factors N (Pollard rho + Miller-Rabin),
then for each prime power p^e || N solves the discrete log modulo p^e using BSGS in
the order-p subgroup (with digit-by-digit Hensel lifting when e > 1), and finally
combines the residues with CRT to recover x mod N.

All group arithmetic is done exclusively through the oracle's mul/inv/exp ops;
label equality (a free, local string comparison) is used to detect matches.
"""
from __future__ import annotations

import math
import os
import random
import sys

from oracle_client import Oracle, OracleError


def is_probable_prime(n: int, k: int = 25) -> bool:
    if n < 2:
        return False
    small_primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]
    for p in small_primes:
        if n % p == 0:
            return n == p
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
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


def pollard_rho(n: int) -> int:
    if n % 2 == 0:
        return 2
    while True:
        x = random.randrange(2, n - 1)
        y = x
        c = random.randrange(1, n - 1)
        d = 1
        while d == 1:
            x = (x * x + c) % n
            y = (y * y + c) % n
            y = (y * y + c) % n
            d = math.gcd(abs(x - y), n)
        if d != n:
            return d


def factor(n: int, out: dict | None = None) -> dict:
    if out is None:
        out = {}
    if n == 1:
        return out
    if is_probable_prime(n):
        out[n] = out.get(n, 0) + 1
        return out
    d = n
    while d == n:
        d = pollard_rho(n)
    factor(d, out)
    factor(n // d, out)
    return out


def crt(residues):
    """residues: list of (r_i, m_i) with pairwise coprime m_i. Returns x mod prod(m_i)."""
    x, M = 0, 1
    for r, m in residues:
        r %= m
        # x_new ≡ x (mod M), x_new ≡ r (mod m)
        inv_M = pow(M % m, -1, m)
        t = ((r - x) * inv_M) % m
        x = x + M * t
        M *= m
    return x % M


def build_baby_table(o: Oracle, gamma: str, idn: str, B: int) -> dict:
    """table[label] = j such that gamma^j == label, for j in [0, B)."""
    table = {idn: 0}
    if B <= 1:
        return table
    table[gamma] = 1
    if B - 1 <= 1:
        return table
    # Chain multiplications in one batched request: $0 = gamma^2, $1 = gamma^3, ...
    ops = [["mul", gamma, gamma]]
    for i in range(1, B - 2):
        ops.append(["mul", f"${i - 1}", gamma])
    res = o.query(ops)
    for idx, lab in enumerate(res):
        table[lab] = idx + 2
    return table


def bsgs_in_subgroup(o: Oracle, gamma: str, giant_stride: str, target: str, table: dict, B: int, p: int) -> int:
    """Find d in [0, p) with gamma^d == target, using precomputed baby table (size B)
    and giant_stride = gamma^{-B}."""
    j = 0
    cur = target
    max_j = p // B + 2
    while True:
        if cur in table:
            return (table[cur] + j * B) % p
        j += 1
        if j > max_j:
            raise RuntimeError("BSGS failed to find discrete log in subgroup")
        cur = o.mul(cur, giant_stride)


def solve_prime_power(o: Oracle, g: str, h: str, N: int, idn: str, p: int, e: int) -> tuple[int, int]:
    pe = p ** e
    m = N // pe
    g1 = o.exp(g, m)
    h1 = o.exp(h, m)
    gamma = o.exp(g1, p ** (e - 1)) if e > 1 else g1

    B = int(math.isqrt(p)) + 1
    table = build_baby_table(o, gamma, idn, B)
    giant_stride = o.exp(gamma, -B)

    x_p = 0
    h_cur = h1
    for i in range(e):
        rem = e - 1 - i
        hi = o.exp(h_cur, p ** rem) if rem > 0 else h_cur
        d_i = bsgs_in_subgroup(o, gamma, giant_stride, hi, table, B, p)
        x_p += d_i * (p ** i)
        if i < e - 1:
            corr = o.exp(g1, -d_i * (p ** i))
            h_cur = o.mul(h_cur, corr)
    return x_p, pe


def main():
    o = Oracle()
    N = int(o.instance["N"])
    labels = o.instance["labels"]
    g, h = labels["g"], labels["h"]

    fac = factor(N)

    idn = o.exp(g, 0)

    residues = []
    for p, e in fac.items():
        x_p, pe = solve_prime_power(o, g, h, N, idn, p, e)
        residues.append((x_p, pe))

    x = crt(residues) % N

    ok = o.submit(x)
    print(f"factorization: {fac}")
    print(f"x = {x}")
    print(f"submit correct: {ok}")
    print(f"queries_used = {o.queries_used} / budget = {o.budget}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
