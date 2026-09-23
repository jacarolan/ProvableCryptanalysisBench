"""
Pohlig-Hellman attack against the generic-group discrete-log challenger.

Idea
----
The challenger publishes N (the order of the cyclic group G) in cleartext, so we can
factor N locally (cheap: N is ~2^58, sympy factors it instantly). For each prime power
q = p^e exactly dividing N we:

  1. Reduce to the order-q subgroup:      g_q = g^(N/q),  h_q = h^(N/q)
  2. Solve the discrete log of h_q to base g_q in that subgroup using the standard
     Pohlig-Hellman digit-by-digit lifting (HAC Algorithm 3.56), which at each of the
     e digits calls a baby-step/giant-step (BSGS) solver on a subgroup of prime order p.

Finally we CRT-combine the digit results x mod p^e across all prime power factors of N
to recover x mod N.

Every group operation (mul/inv/exp) costs one oracle query. All local bookkeeping
(building the baby-step table dict, comparing labels for equality, factoring N, CRT)
is free. Batching is used aggressively: baby steps are generated in one batch of
`exp` ops, and giant steps are generated as a chained batch of `mul` ops (each op
referencing the previous result via "$i"), in chunks so we can stop as soon as a
collision with the baby table is found instead of always paying for the full
2*sqrt(p) worst case.
"""
from __future__ import annotations

import math
from oracle_client import Oracle

MAX_BATCH = 200_000  # server-side cap on ops per request


def factor(n: int) -> dict[int, int]:
    """Trial-division / Pollard-rho factorization. n is small (<= ~2^64) for this task."""
    n = int(n)
    factors: dict[int, int] = {}

    def add(p):
        while n % p == 0:
            factors[p] = factors.get(p, 0) + 1
            n_holder[0] //= p

    n_holder = [n]

    # small primes by trial division
    d = 2
    m = n
    while d * d <= m and d < 100000:
        while m % d == 0:
            factors[d] = factors.get(d, 0) + 1
            m //= d
        d += 1 if d == 2 else 2

    if m == 1:
        return factors

    # Pollard's rho for the remaining (possibly large) cofactor
    def is_probable_prime(x: int) -> bool:
        if x < 2:
            return False
        for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
            if x % p == 0:
                return x == p
        d0 = x - 1
        r = 0
        while d0 % 2 == 0:
            d0 //= 2
            r += 1
        for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
            if a >= x:
                continue
            y = pow(a, d0, x)
            if y == 1 or y == x - 1:
                continue
            for _ in range(r - 1):
                y = pow(y, 2, x)
                if y == x - 1:
                    break
            else:
                return False
        return True

    def pollard_rho(x: int) -> int:
        if x % 2 == 0:
            return 2
        import random
        while True:
            c = random.randrange(1, x)
            f = lambda v: (v * v + c) % x
            a = b = random.randrange(2, x)
            d = 1
            while d == 1:
                a = f(a)
                b = f(f(b))
                d = math.gcd(abs(a - b), x)
            if d != x:
                return d

    def full_factor(x: int, out: dict[int, int]):
        if x == 1:
            return
        if is_probable_prime(x):
            out[x] = out.get(x, 0) + 1
            return
        d = pollard_rho(x)
        full_factor(d, out)
        full_factor(x // d, out)

    full_factor(m, factors)
    return factors


def crt(residues: list[tuple[int, int]]) -> int:
    """Combine [(r_i, m_i), ...] with pairwise-coprime m_i into x mod prod(m_i)."""
    x, m = 0, 1
    for r, mi in residues:
        # solve x + m*t = r (mod mi)
        g, inv, _ = ext_gcd(m, mi)
        t = ((r - x) // g * inv) % (mi // g)
        x = x + m * t
        m = m * mi // g
        x %= m
    return x % m


def ext_gcd(a: int, b: int):
    if b == 0:
        return a, 1, 0
    g, x1, y1 = ext_gcd(b, a % b)
    return g, y1, x1 - (a // b) * y1


def bsgs(oc: Oracle, gamma: str, h: str, p: int, identity: str) -> int:
    """Discrete log of h to base gamma in a (sub)group of prime order p. Returns d with gamma^d == h."""
    if p == 1:
        return 0
    if h == identity:
        return 0
    if gamma == h:
        return 1

    m = int(math.isqrt(p)) + 1

    # ---- baby steps: gamma^0 .. gamma^(m-1) ----
    baby: dict[str, int] = {}
    j = 0
    # j = 0 is the identity; we don't know identity label a priori for the reduced
    # subgroup element other than what's passed in, so compute it via exp(gamma, 0)
    # for correctness (cheap, batched with the rest).
    exps = list(range(0, m))
    idx = 0
    while idx < len(exps):
        chunk = exps[idx: idx + MAX_BATCH]
        ops = [["exp", gamma, k] for k in chunk]
        results = oc.query(ops)
        for k, lab in zip(chunk, results):
            if lab not in baby:
                baby[lab] = k
        idx += len(chunk)

    for lab, k in baby.items():
        if lab == h:
            return k

    # ---- giant steps: h * gamma^{-m*t}, t = 1, 2, ... ----
    gamma_inv_m = oc.query([["exp", gamma, -m]])[0]

    GIANT_CHUNK = 20000
    t = 0
    cur = h
    total_giants_needed = m + 2
    while t < total_giants_needed:
        chunk_size = min(GIANT_CHUNK, total_giants_needed - t)
        ops = []
        # first op of the chunk multiplies `cur` by gamma_inv_m; subsequent ops chain via $i
        ops.append(["mul", cur, gamma_inv_m])
        for i in range(1, chunk_size):
            ops.append(["mul", f"${i - 1}", gamma_inv_m])
        results = oc.query(ops)
        for i, lab in enumerate(results):
            tt = t + i + 1
            if lab in baby:
                return (tt * m + baby[lab]) % p
        cur = results[-1]
        t += chunk_size

    raise RuntimeError(f"bsgs failed to find discrete log mod {p}")


def pohlig_hellman_prime_power(oc: Oracle, g: str, h: str, N: int, p: int, e: int, identity: str) -> int:
    """Solve discrete log of h to base g within the order-p^e subgroup (g has order p^e)."""
    pe = p ** e
    n_div_pe = N // pe
    g_q = oc.query([["exp", g, n_div_pe]])[0] if n_div_pe != 1 else g
    h_q = oc.query([["exp", h, n_div_pe]])[0] if n_div_pe != 1 else h

    if e == 1:
        return bsgs(oc, g_q, h_q, p, identity)

    g1 = oc.query([["exp", g_q, p ** (e - 1)]])[0]  # order-p element

    x_val = 0
    p_pow = 1
    for i in range(e):
        if x_val == 0:
            hh = h_q
        else:
            g_inv_x = oc.query([["exp", g_q, -x_val]])[0]
            hh = oc.query([["mul", h_q, g_inv_x]])[0]
        exponent = p ** (e - 1 - i)
        h_i = oc.query([["exp", hh, exponent]])[0] if exponent != 1 else hh
        d_i = bsgs(oc, g1, h_i, p, identity)
        x_val += d_i * p_pow
        p_pow *= p
    return x_val


def main():
    oc = Oracle()
    N = int(oc.instance["N"])
    g = oc.instance["labels"]["g"]
    h = oc.instance["labels"]["h"]

    factors = factor(N)
    print("N =", N, "factors:", factors)

    # identity element label = g^0
    identity = oc.query([["exp", g, 0]])[0]

    residues = []
    for p, e in factors.items():
        q = p ** e
        x_q = pohlig_hellman_prime_power(oc, g, h, N, p, e, identity)
        residues.append((x_q, q))
        print(f"x mod {p}^{e} = {x_q}")

    x = crt(residues)
    print("recovered x =", x)
    print("queries used so far:", oc.queries_used, "/", oc.budget)

    ok = oc.submit(x)
    print("submit correct:", ok)
    if not ok:
        raise SystemExit("submission failed")


if __name__ == "__main__":
    main()
