"""
Attack on the generic-group interval-DLP challenger.

Setup (from TASK.md): G is cyclic of order N with generator g, h = g^x,
x sampled uniformly from [0, 2^t). N is public. The only oracle ops are
mul, inv, exp (any of which reveal nothing about elements beyond group
structure) plus label equality.

Because N (~115 bits) is much larger than 2^t (~45 bits), a naive BSGS/
kangaroo attack on the full interval would need about sqrt(2^t) ~ 2^22.5
queries, well over budget. But N in this key-generation scheme factors
as a handful of small primes times one large prime. That lets us:

  1. Use Pohlig-Hellman on each small prime-power factor q of N (cheap
     BSGS of cost ~2*sqrt(q) each) to learn r = x mod M, where
     M = product of the small factors used.
  2. Reduce the search: x = r + M*k with k in [0, K), K = ceil(2^t / M).
     Rewrite h*g^-r = (g^M)^k and BSGS-solve for k (cost ~2*sqrt(K)).

Total query cost is roughly 2*sum(sqrt(q_i)) + 2*sqrt(K), which for the
observed factor shapes is on the order of 10-15k queries -- comfortably
under the ~51k query budget, versus ~6M for a plain interval attack.
"""
from __future__ import annotations

import math
import sys

from oracle_client import Oracle, OracleError

try:
    import sympy
except ImportError:  # pragma: no cover
    sympy = None


def trial_factor(n: int, limit: int = 2_000_000) -> dict:
    """Factor out small primes up to `limit`; return {prime: exponent}."""
    factors = {}
    d = 2
    while d * d <= n and d <= limit:
        while n % d == 0:
            factors[d] = factors.get(d, 0) + 1
            n //= d
        d += 1 if d == 2 else 2
    return factors, n


def factorize(n: int) -> dict:
    """Full factorization of n, using sympy if available, else trial division
    plus a Pollard-rho fallback for the (presumably few, presumably one)
    remaining large cofactor(s)."""
    if sympy is not None:
        return dict(sympy.factorint(n))
    factors, rem = trial_factor(n)
    if rem > 1:
        # crude Pollard rho for whatever's left (should rarely trigger)
        stack = [rem]
        while stack:
            m = stack.pop()
            if m == 1:
                continue
            if is_probable_prime(m):
                factors[m] = factors.get(m, 0) + 1
                continue
            d = pollard_rho(m)
            stack.append(d)
            stack.append(m // d)
    return factors


def is_probable_prime(n: int) -> bool:
    if sympy is not None:
        return bool(sympy.isprime(n))
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    import random
    for _ in range(20):
        a = random.randrange(2, n - 1)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def pollard_rho(n: int) -> int:
    import random
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


def crt_pair(r1, m1, r2, m2):
    g, p, q = extended_gcd(m1, m2)
    assert g == 1
    lcm = m1 * m2
    x = (r1 + m1 * (p * (r2 - r1) % m2)) % lcm
    return x % lcm, lcm


def extended_gcd(a, b):
    old_r, r = a, b
    old_s, s = 1, 0
    old_t, t = 0, 1
    while r != 0:
        quot = old_r // r
        old_r, r = r, old_r - quot * r
        old_s, s = s, old_s - quot * s
        old_t, t = t, old_t - quot * t
    return old_r, old_s, old_t


class Group:
    """Thin helper batching oracle ops and tracking query usage."""

    def __init__(self, oracle: Oracle):
        self.o = oracle

    def exp(self, a, k):
        return self.o.query([["exp", a, int(k)]])[0]

    def mul(self, a, b):
        return self.o.query([["mul", a, b]])[0]

    def inv(self, a):
        return self.o.query([["inv", a]])[0]

    def batch(self, ops):
        return self.o.query(ops)


def bsgs(grp: Group, base_label: str, target_label: str, order: int) -> int:
    """Solve target = base^r for r in [0, order), base has exact order `order`."""
    if order == 1:
        return 0
    m = max(1, math.ceil(math.sqrt(order)))

    # Baby steps: base^0 .. base^(m-1), batched in one round trip.
    baby_ops = [["exp", base_label, j] for j in range(m)]
    baby_labels = grp.batch(baby_ops)
    table = {lab: j for j, lab in enumerate(baby_labels)}
    # base^0 is the identity; exp(base,0) already covers j=0 via the batch.

    # factor = base^(-m)
    factor = grp.exp(base_label, -m)

    if target_label in table:
        return table[target_label]

    # Giant steps: gamma_i = target * factor^i for i = 1..num_giants,
    # chained so each step is a 1-op batch entry: $0 = target*factor,
    # $1 = $0*factor, ...
    num_giants = math.ceil(order / m) + 1
    ops = []
    for i in range(num_giants):
        left = target_label if i == 0 else f"${i - 1}"
        ops.append(["mul", left, factor])
    gamma_labels = grp.batch(ops)
    for idx, lab in enumerate(gamma_labels):
        i = idx + 1
        if lab in table:
            j = table[lab]
            r = j + i * m
            return r % order
    raise RuntimeError(f"BSGS failed to find discrete log (order={order})")


def main():
    o = Oracle()
    N = int(o.instance["N"])
    g = o.instance["labels"]["g"]
    h = o.instance["labels"]["h"]
    t = int(o.instance["params"]["t"])
    budget = o.budget

    grp = Group(o)

    W = 1 << t  # x in [0, W)

    factors = factorize(N)
    prime_powers = sorted((p ** e for p, e in factors.items()), reverse=True)
    # Assume the largest factor is the "hard" cofactor; use the rest.
    usable = prime_powers[1:] if len(prime_powers) > 1 else []
    usable = [q for q in usable if q > 1]

    # Sort ascending, and only keep factors cheap enough to BSGS.
    usable.sort()

    r_mod = 0
    M = 1
    used_budget_estimate = 0

    for q in usable:
        cost_estimate = 2 * math.ceil(math.sqrt(q)) + 4
        # keep a safety margin; leave room for the final range BSGS
        if used_budget_estimate + cost_estimate > budget * 0.5:
            break
        g_i = grp.exp(g, N // q)
        h_i = grp.exp(h, N // q)
        r_i = bsgs(grp, g_i, h_i, q)
        r_mod, M = crt_pair(r_mod, M, r_i, q)
        used_budget_estimate += cost_estimate + 2

    if M <= 1:
        print("WARNING: no usable small factors found; attack may exceed budget",
              file=sys.stderr)

    # x = r_mod + M*k,  k in [0, K)
    K = (W - 1 - r_mod) // M + 1 if M <= W else 1
    K = max(K, 1)

    remaining = budget - o.queries_used
    est_final = 2 * math.ceil(math.sqrt(K)) + 8
    if est_final > remaining:
        print(f"WARNING: estimated final BSGS cost {est_final} exceeds remaining "
              f"budget {remaining} (K={K}); the small-factor coverage of N was "
              f"not enough for this instance -- aborting without submitting a "
              f"doomed guess.", file=sys.stderr)
        sys.exit(1)

    g2 = grp.exp(g, M)
    g_negr = grp.exp(g, -r_mod)
    h2 = grp.mul(h, g_negr)

    try:
        k = bsgs(grp, g2, h2, K)
    except OracleError as e:
        print(f"ERROR: final BSGS ran out of budget ({e}); "
              f"queries_used={o.queries_used}/{budget}", file=sys.stderr)
        sys.exit(1)

    x = r_mod + M * k
    x = x % N

    ok = o.submit(x)
    print(f"submitted x={x}, correct={ok}, queries_used={o.queries_used}/{budget}")
    if not ok:
        # Fallback: try a small local search around x in case of an off-by-one
        # in K/rounding (shouldn't normally trigger).
        for delta in range(-3, 4):
            if delta == 0:
                continue
            cand = (x + delta * M) % N
            if o.queries_used >= budget:
                break
            ok2 = o.submit(cand)
            print(f"retry x={cand}, correct={ok2}, queries_used={o.queries_used}/{budget}")
            if ok2:
                ok = True
                break
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
