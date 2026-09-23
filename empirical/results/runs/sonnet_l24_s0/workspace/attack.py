"""Baby-step giant-step attack against the generic-group DL oracle.

The challenger's group is cyclic of known order N (public), so a classic
Shanks BSGS recovers x with h = g^x using O(sqrt(N)) group operations,
each of which costs exactly one oracle query (mul/inv/exp all cost 1).

Let m = ceil(sqrt(N)) and write x = i + m*j with 0 <= i, j < m.
Then h * (g^-m)^j = g^i, so:
  - build the baby-step table {g^i : 0 <= i < m}          (m queries, batched)
  - compute factor = g^-m                                  (1 query, batched with the above)
  - walk giant steps h, h*factor, h*factor^2, ...           (m-1 queries, batched)
    until one matches a baby-step label; then x = i + m*j.

Total oracle cost is about 2*m + O(1) group-operation queries plus 1 submit,
i.e. ~2*sqrt(N) + O(1). For a 24-bit N (N < 2^24), m <= 4097, so the attack
uses at most roughly 8200 queries -- comfortably inside the stated budget of
32228 for the live instance (and any fresh same-size instance).
"""
from __future__ import annotations

import math
import sys

from oracle_client import Oracle, OracleError


def solve(o: Oracle) -> int:
    inst = o.instance
    N = int(inst["N"])
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]

    m = math.isqrt(N)
    if m * m < N:
        m += 1
    m = max(m, 1)

    # Batch 1: baby steps g^0 .. g^(m-1), plus factor = g^(-m).
    # op0 = exp(g, 0) -> g^0
    # op_i = mul($op_{i-1}, g) -> g^i   for i = 1..m-1
    # op_m = exp(g, -m) -> factor
    ops1 = [["exp", g, 0]]
    for i in range(1, m):
        ops1.append(["mul", f"${i - 1}", g])
    ops1.append(["exp", g, -m])

    res1 = o.query(ops1)
    baby = res1[:m]
    factor = res1[m]

    baby_index = {}
    for i, lab in enumerate(baby):
        # first occurrence wins (labels are unique per element, but be safe)
        baby_index.setdefault(lab, i)

    # Check j = 0 first (giant[0] = h) without spending a query.
    if h in baby_index:
        i = baby_index[h]
        x = i % N
        return x

    # Batch 2: giant steps h*factor, h*factor^2, ..., h*factor^(m-1)
    if m > 1:
        ops2 = [["mul", h, factor]]
        for j in range(2, m):
            ops2.append(["mul", f"${j - 2}", factor])
        res2 = o.query(ops2)
    else:
        res2 = []

    for idx, lab in enumerate(res2):
        j = idx + 1
        if lab in baby_index:
            i = baby_index[lab]
            x = (i + m * j) % N
            return x

    raise RuntimeError("BSGS failed to find a match; unexpected for a valid instance")


def main() -> int:
    o = Oracle()
    x = solve(o)
    ok = o.submit(x)
    print(f"N={o.instance['N']} x={x} correct={ok} "
          f"queries_used={o.queries_used} budget={o.budget}")
    if not ok:
        print("FAILED: submitted x was rejected", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
