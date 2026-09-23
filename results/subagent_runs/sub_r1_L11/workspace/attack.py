"""Pohlig-Hellman + batched BSGS attack on a generic-group discrete-log oracle.

Reads N, g, h from the live oracle at runtime, factors N (public, and in practice
smooth: a product of small-to-medium primes / prime powers), then for each prime-power
component p^e || N:
  - projects g, h into the order-(p^e) subgroup via exponentiation by N/p^e
  - recovers x mod p^e with the standard Pohlig-Hellman lifting, using a
    batched baby-step/giant-step (BSGS) discrete log in the order-p subgroup
    at each lifting level
Finally combines the per-prime-power residues with CRT to get x mod N, and submits.

All group arithmetic is done through the oracle (mul/inv/exp on opaque labels);
we never see or need actual group elements, only label equality.
"""
from __future__ import annotations

import math
from oracle_client import Oracle


def factor_n(n: int) -> dict[int, int]:
    """Trial-division factorization. N is assumed smooth enough (largest prime
    factor small enough for BSGS, i.e. its sqrt is a modest number of oracle
    queries) -- true for this benchmark's instances."""
    factors = {}
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors[d] = factors.get(d, 0) + 1
            n //= d
        d += 1 if d == 2 else 2
    if n > 1:
        factors[n] = factors.get(n, 0) + 1
    return factors


def bsgs_order_p(oracle: Oracle, base: str, target: str, p: int) -> int:
    """Discrete log of `target` base `base` in a subgroup of (known) prime order p.
    Returns d in [0, p) with target == base^d. Uses batched queries: one batch
    of m ops for baby steps, one exp for the giant-step factor, one batch of
    (m-1) ops for giant steps."""
    if p == 1:
        return 0
    m = math.isqrt(p - 1) + 1  # ceil(sqrt(p))

    # Baby steps: table[label(base^j)] = j, j = 0..m-1, built as one chained batch.
    ops = [["exp", base, 0]]
    for j in range(1, m):
        ops.append(["mul", f"${j - 1}", base])
    baby_labels = oracle.query(ops)
    table = {}
    for j, lab in enumerate(baby_labels):
        table.setdefault(lab, j)

    # i = 0 case: target itself might already be a baby step.
    if target in table:
        return table[target] % p

    # Giant steps: factor = base^-m, then target*factor^i for i = 1..m-1, chained.
    factor = oracle.exp(base, -m)
    ops2 = [["mul", target, factor]]
    for i in range(1, m - 1):
        ops2.append(["mul", f"${i - 1}", factor])
    if ops2:
        giant_labels = oracle.query(ops2)
        for i, lab in enumerate(giant_labels, start=1):
            if lab in table:
                j = table[lab]
                return (i * m + j) % p

    raise RuntimeError(f"BSGS failed to find discrete log mod {p}")


def pohlig_hellman_prime_power(oracle: Oracle, g: str, h: str, N: int, p: int, e: int) -> int:
    """Recover x mod p^e given g (order N) and h = g^x (order N), via the
    order-p^e projections g_n = g^(N/p^e), h_n = h^(N/p^e), using standard
    Pohlig-Hellman lifting through the e levels."""
    n = p ** e
    m_exp = N // n
    g_n = oracle.exp(g, m_exp)
    h_n = oracle.exp(h, m_exp)

    if e == 1:
        return bsgs_order_p(oracle, g_n, h_n, p)

    # gamma has order exactly p: gamma = g_n^(p^(e-1))
    gamma = oracle.exp(g_n, p ** (e - 1))

    x = 0
    # g_n^{-1}, used to build g_n^{-x} incrementally via exponentiation each round
    for k in range(e):
        if x == 0:
            gx_inv = oracle.exp(g_n, 0)  # identity
        else:
            gx_inv = oracle.exp(g_n, -x)
        temp = oracle.mul(h_n, gx_inv)  # h_n * g_n^{-x}
        power = p ** (e - 1 - k)
        h_k = oracle.exp(temp, power) if power != 1 else temp
        d_k = bsgs_order_p(oracle, gamma, h_k, p)
        x += d_k * (p ** k)
    return x % n


def crt_combine(residues: list[tuple[int, int]]) -> int:
    """Combine (r_i, m_i) pairs (pairwise coprime m_i) into x mod prod(m_i)."""
    x, m = 0, 1
    for r, mod in residues:
        # solve y = x + m*t == r (mod mod)
        g, a, _ = ext_gcd(m, mod)
        assert (r - x) % g == 0
        t = ((r - x) // g) * a % (mod // g)
        x = x + m * t
        m = m * mod // g
        x %= m
    return x % m


def ext_gcd(a: int, b: int):
    if b == 0:
        return a, 1, 0
    g, x1, y1 = ext_gcd(b, a % b)
    return g, y1, x1 - (a // b) * y1


def main():
    oracle = Oracle()
    inst = oracle.instance
    N = int(inst["N"])
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]

    factors = factor_n(N)

    residues = []
    for p, e in factors.items():
        r = pohlig_hellman_prime_power(oracle, g, h, N, p, e)
        residues.append((r, p ** e))

    x = crt_combine(residues)

    ok = oracle.submit(x)
    print(f"x = {x}")
    print(f"submit correct = {ok}")
    print(f"queries used = {oracle.queries_used} / budget {oracle.budget}")

    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
