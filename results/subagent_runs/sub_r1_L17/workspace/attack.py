"""
Pohlig-Hellman + Baby-Step Giant-Step attack against the generic-group DL oracle.

Strategy
--------
1. Read N, g, h from GET /instance (never hard-coded).
2. Factor N = prod p_i^e_i  (sympy.factorint; N is small enough, ~1e15-1e16,
   for this to be fast even when the largest prime factor is ~sqrt(N)).
3. For every prime power p^e dividing N:
     - Move to the order-p^e subgroup: g_i = g^(N/p^e), h_i = h^(N/p^e).
     - Recover x mod p^e with the standard p-adic lifting algorithm, using
       baby-step/giant-step (BSGS) to solve each order-p discrete log that
       shows up during the lifting.
4. Combine all the x mod p^e residues with CRT to get x mod N.
5. Submit x.

All group arithmetic is done through oracle ops (mul / inv / exp); every op
costs one query. Label equality (used to match baby/giant steps) is free.
"""
from __future__ import annotations

import sys
from math import gcd, isqrt

from sympy import factorint
from sympy.ntheory.modular import crt

from oracle_client import Oracle


class Group:
    """Thin helper that batches oracle ops and caches the identity label."""

    def __init__(self, oracle: Oracle):
        self.o = oracle
        self._identity = None

    def identity(self):
        if self._identity is None:
            self._identity = self.o.exp(self.o.instance["labels"]["g"], 0)
        return self._identity

    def exp(self, a, k):
        return self.o.exp(a, k)

    def mul(self, a, b):
        return self.o.mul(a, b)

    def inv(self, a):
        return self.o.inv(a)

    def batch(self, ops):
        return self.o.query(ops)


def bsgs_prime_order(grp: Group, base_label, target_label, p):
    """Solve target = base^x with base of (known) prime order p. Returns x in [0, p)."""
    if p == 1:
        return 0

    ident = grp.identity()
    if target_label == ident:
        return 0
    if target_label == base_label:
        return 1

    m = isqrt(p - 1) + 1  # ceil-ish sqrt

    # ---- baby steps: baby[j] = base^j for j = 0..m-1 ----
    baby = {ident: 0}
    ops = []
    cur_ref = None
    # build base^1, base^2, ... base^(m-1) via chained muls in one batch
    for j in range(1, m):
        if j == 1:
            ops.append(["mul", ident, base_label])
        else:
            ops.append(["mul", "$%d" % (j - 2), base_label])
    if ops:
        results = grp.batch(ops)
        for j in range(1, m):
            baby[results[j - 1]] = j

    # ---- giant steps: giant[i] = target * (base^-m)^i for i = 0..m-1 ----
    factor = grp.exp(base_label, -m)
    giant_ops = []
    for i in range(1, m):
        if i == 1:
            giant_ops.append(["mul", target_label, factor])
        else:
            giant_ops.append(["mul", "$%d" % (i - 2), factor])
    giant_labels = [target_label]
    if giant_ops:
        giant_labels += grp.batch(giant_ops)

    for i, lab in enumerate(giant_labels):
        if lab in baby:
            j = baby[lab]
            x = (i * m + j) % p
            return x
    raise RuntimeError("BSGS failed to find a match (unexpected)")


def dlog_prime_power(grp: Group, g_i, h_i, p, e):
    """Solve h_i = g_i^x mod (subgroup of order p^e) using p-adic lifting."""
    pe = p ** e
    if e == 1:
        return bsgs_prime_order(grp, g_i, h_i, p)

    # gamma has order p
    pe_1 = p ** (e - 1)
    gamma = grp.exp(g_i, pe_1)

    x = 0
    p_pow = 1  # p^k
    g_inv = None
    for k in range(e):
        # h_k = (h_i * g_i^{-x}) ^ (p^{e-1-k})
        if x == 0:
            reduced = h_i
        else:
            if g_inv is None:
                g_inv = grp.inv(g_i)
            g_neg_x = grp.exp(g_inv, x)
            reduced = grp.mul(h_i, g_neg_x)
        exp_pow = p ** (e - 1 - k)
        h_k = grp.exp(reduced, exp_pow) if exp_pow != 1 else reduced
        d_k = bsgs_prime_order(grp, gamma, h_k, p)
        x = x + d_k * p_pow
        p_pow *= p
    return x % pe


def solve(oracle: Oracle):
    inst = oracle.instance
    N = int(inst["N"])
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]

    grp = Group(oracle)

    factors = factorint(N)

    residues = []
    moduli = []
    for p, e in factors.items():
        pe = p ** e
        cofactor = N // pe
        g_i = grp.exp(g, cofactor)
        h_i = grp.exp(h, cofactor)
        x_i = dlog_prime_power(grp, g_i, h_i, p, e)
        residues.append(int(x_i))
        moduli.append(int(pe))

    x, mod = crt(moduli, residues)
    x = int(x) % N
    return x


def main():
    oracle = Oracle()
    x = solve(oracle)
    ok = oracle.submit(x)
    print(f"x = {x}")
    print(f"submit correct = {ok}")
    print(f"queries_used = {oracle.queries_used} / budget = {oracle.budget}")
    if not ok:
        print("FAILED", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
