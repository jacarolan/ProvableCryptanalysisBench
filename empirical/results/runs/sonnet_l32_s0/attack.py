"""Baby-step giant-step attack against the generic-group DLOG oracle.

The group is cyclic of prime order N (~32-bit). We cannot compute on labels
ourselves, but equal labels mean equal elements, so we can build a lookup
table of "baby step" labels g^0..g^(m-1) and then walk "giant steps"
h * (g^-m)^i, checking each against the table (standard BSGS), with
m = ceil(sqrt(N)). Total oracle queries are about 2*sqrt(N) in the worst
case, and fewer on average since we stop as soon as a match is found.
"""
from __future__ import annotations

import math
import sys

from oracle_client import Oracle, OracleError


def isqrt_ceil(n: int) -> int:
    r = math.isqrt(n)
    return r if r * r == n else r + 1


def solve(o: Oracle) -> int:
    inst = o.instance
    N = int(inst["N"])
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]

    m = isqrt_ceil(N)

    # --- Baby steps: g^0, g^1, ..., g^(m-1) in one batch ---
    # op0: g^0 (identity); op_i: $[i-1] * g  (i.e. g^i)
    ops = [["exp", g, 0]]
    for _ in range(m - 1):
        ops.append(["mul", "$%d" % (len(ops) - 1), g])
    baby_labels = o.query(ops)
    baby = {}
    for j, lab in enumerate(baby_labels):
        baby.setdefault(lab, j)  # elements are distinct in a prime-order group

    # i = 0 case: is h itself a baby step?
    if h in baby:
        x = baby[h]
        return x % N

    # factor = g^(-m)
    factor = o.exp(g, -m)

    # --- Giant steps: giant_i = h * factor^i for i = 1, 2, ... ---
    # Walk in chunks so we can stop as soon as we find a match (saves queries
    # on average), while keeping round trips low.
    i_max = m + 2  # small safety margin for rounding
    chunk = 4000
    prev_label = h
    i = 0
    while i < i_max:
        this_chunk = min(chunk, i_max - i)
        ops = [["mul", prev_label, factor]]
        for _ in range(this_chunk - 1):
            ops.append(["mul", "$%d" % (len(ops) - 1), factor])
        results = o.query(ops)
        for k, lab in enumerate(results):
            gi = i + k + 1  # this is giant step index i (1-based within full walk)
            if lab in baby:
                j = baby[lab]
                x = (j + gi * m) % N
                return x
        prev_label = results[-1]
        i += this_chunk

    raise RuntimeError("BSGS failed to find x within expected range")


def main():
    o = Oracle()
    x = solve(o)
    ok = o.submit(x)
    print(f"x = {x}")
    print(f"submit correct = {ok}")
    print(f"queries_used = {o.queries_used} / budget = {o.budget}")
    if not ok:
        print("FAILED", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
