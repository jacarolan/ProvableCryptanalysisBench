"""Cheon's algorithm attack on the generic-group DLOG-with-auxiliary-power oracle.

Structure exploited
--------------------
The challenger publishes a cyclic group of *prime* order N with generator g,
h = g^x, and h_d = g^(x^d mod N) for a public d that (in the observed
instance) divides N-1.  Because x has order dividing N-1 in Z_N^* (Fermat),
y := x^d mod N is a d-th power, hence y lies in the unique subgroup of
Z_N^* of order e := (N-1)/d.  That collapses the "search space" for y from
size N down to size e, and once y is known, x is one of only d candidate
d-th roots of y (they differ by a d-th root of unity).  This is exactly
Cheon's algorithm for the Strong-DH-style problem (weak case, d | N-1),
giving cost O(sqrt(e) + sqrt(d) + d) group operations instead of O(sqrt(N)).

All exponent-space arithmetic (finding generators of the order-e and
order-d subgroups of Z_N^*, factoring, modular inverses, root extraction)
is done locally in Python since N and d are public.  The oracle is only
used to *evaluate* g^(something) and compare opaque labels, exactly the
operations Cheon's algorithm needs (baby/giant steps via `exp`, equality
via label comparison).

Query cost: ~2*ceil(sqrt(e)) for the BSGS recovering y, plus d queries
for the final linear scan recovering x from its d candidates (that final
scan could be turned into an O(sqrt(d)) BSGS too, but since d is small
compared to the budget here a linear scan is simpler and still cheap).
"""
from __future__ import annotations

import random

import sympy
from sympy.ntheory.residue_ntheory import nthroot_mod

from oracle_client import Oracle


def _find_generator_of_order(N: int, order: int, cofactor_exponent: int, factors) -> int:
    """Return an element of Z_N^* with exact multiplicative order `order`.

    `cofactor_exponent` is such that raising a uniformly random unit to it
    lands in the subgroup of size `order` (i.e. cofactor_exponent =
    (N-1)//order). `factors` is the set of prime divisors of `order`.
    """
    while True:
        t = random.randrange(2, N - 1)
        cand = pow(t, cofactor_exponent, N)
        if cand == 1:
            continue
        if all(pow(cand, order // q, N) != 1 for q in factors):
            return cand


def cheon_recover_x(o: Oracle) -> int:
    inst = o.instance
    N = int(inst["N"])
    labels = inst["labels"]
    g, h, h_d = labels["g"], labels["h"], labels["h_d"]
    d = int(inst["params"]["d"])

    if (N - 1) % d != 0:
        raise RuntimeError("attack assumes d | N-1; unexpected instance parameters")
    e = (N - 1) // d

    d_factors = set(sympy.factorint(d).keys())
    e_factors = set(sympy.factorint(e).keys())

    # omega generates the order-e subgroup (contains y = x^d).
    omega = _find_generator_of_order(N, e, d, e_factors)
    # zeta generates the order-d subgroup (the ambiguity in d-th roots).
    zeta = _find_generator_of_order(N, d, e, d_factors)

    m = int(sympy.ceiling(sympy.sqrt(e)))

    # ---- Baby steps: table[label(g^(omega^k))] = k, for k = 0..m-1 ----
    baby = {}
    BATCH = 20000
    pw = 1
    powers = []
    for k in range(m):
        powers.append(pw)
        pw = (pw * omega) % N
    for start in range(0, m, BATCH):
        chunk = powers[start:start + BATCH]
        ops = [["exp", g, p] for p in chunk]
        results = o.query(ops)
        for k_off, lab in enumerate(results):
            baby[lab] = start + k_off

    # ---- Giant steps: C_i = h_d ^ (omega^-1)^(i*m); look for a baby match ----
    omega_inv = pow(omega, -1, N)
    step = pow(omega_inv, m, N)

    j = None
    cur_exp = 1  # step^0
    exps_batch = []
    i = 0
    while i < m and j is None:
        cnt = min(BATCH, m - i)
        ops = []
        exps_batch = []
        ce = cur_exp
        for _ in range(cnt):
            exps_batch.append(ce)
            ops.append(["exp", h_d, ce])
            ce = (ce * step) % N
        results = o.query(ops)
        for local_i, lab in enumerate(results):
            if lab in baby:
                k = baby[lab]
                gi = i + local_i
                j = (gi * m + k) % e
                break
        cur_exp = ce
        i += cnt

    if j is None:
        raise RuntimeError("BSGS failed to recover y = x^d; structural assumption may be wrong")

    y = pow(omega, j, N)

    # ---- Recover one d-th root x0 of y mod N (general nth-root extraction) ----
    x0 = nthroot_mod(y, d, N, all_roots=False)
    if x0 is None:
        raise RuntimeError("no d-th root found for y; unexpected instance")
    assert pow(x0, d, N) == y

    # ---- Determine which of the d candidates x0 * zeta^i equals x ----
    cur = x0
    candidates = []
    for _ in range(d):
        candidates.append(cur)
        cur = (cur * zeta) % N

    found_x = None
    for start in range(0, d, BATCH):
        chunk = candidates[start:start + BATCH]
        ops = [["exp", g, c] for c in chunk]
        results = o.query(ops)
        for off, lab in enumerate(results):
            if lab == h:
                found_x = chunk[off]
                break
        if found_x is not None:
            break

    if found_x is None:
        raise RuntimeError("failed to locate x among d-th root candidates")

    return found_x % N


def main():
    o = Oracle()
    x = cheon_recover_x(o)
    ok = o.submit(x)
    print(f"x = {x}")
    print(f"submit correct = {ok}")
    print(f"queries_used = {o.queries_used} / budget = {o.budget}")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
