"""Baby-step giant-step attack against the generic-group DL oracle.

The challenger guarantees x is sampled uniformly from [0, 2^t) (t is published
in GET /instance under params.t). This is a much smaller search space than the
full group order N, so instead of a generic O(sqrt(N)) attack we run BSGS over
the *exponent* range [0, 2^t): with m = ceil(sqrt(2^t)) we get an O(m) = O(2^(t/2))
algorithm, using about 2*m oracle queries total (well under the 8192 budget for
t=20, m=1024 -> ~2049 queries).

All group arithmetic is done by the oracle; only opaque labels are compared
(label equality <=> group-element equality, and that comparison is free).
"""
from __future__ import annotations

import math

from oracle_client import Oracle, OracleError


def solve(o: Oracle) -> int:
    inst = o.instance
    N = int(inst["N"])
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]

    params = inst.get("params") or {}
    t = params.get("t")
    if t is None:
        # Fallback: no exponent bound published, treat whole group as the range.
        t = N.bit_length()
    t = int(t)

    upper = 1 << t  # x in [0, upper)
    m = int(math.isqrt(upper - 1)) + 1
    while m * m < upper:
        m += 1

    # --- Baby steps: baby[j] = g^j label, for j = 0 .. m-1 ---
    # One batch: first op computes identity (g^0), then chain multiplications
    # by g, each referencing the previous batch result.
    baby_ops = [["exp", g, 0]]
    for _ in range(1, m):
        baby_ops.append(["mul", f"${len(baby_ops) - 1}", g])
    baby_labels = o.query(baby_ops)

    baby = {}
    for j, lab in enumerate(baby_labels):
        baby.setdefault(lab, j)

    # --- factor = g^(-m) ---
    factor = o.exp(g, -m)

    # --- Giant steps: gs[i] = h * factor^i for i = 0 .. m-1 ---
    # gs[0] = h is free (no query). Chain the rest in one batch.
    if m > 1:
        giant_ops = [["mul", h, factor]]
        for _ in range(1, m - 1):
            giant_ops.append(["mul", f"${len(giant_ops) - 1}", factor])
        giant_labels = [h] + o.query(giant_ops)
    else:
        giant_labels = [h]

    for i, lab in enumerate(giant_labels):
        if lab in baby:
            j = baby[lab]
            x = (i * m + j) % N
            return x

    raise RuntimeError("BSGS failed to find a match; x may be outside the assumed range")


def main():
    o = Oracle()
    x = solve(o)
    ok = o.submit(x)
    print(f"x = {x}")
    print(f"submit correct = {ok}")
    print(f"queries_used = {o.queries_used} / budget = {o.budget}")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
