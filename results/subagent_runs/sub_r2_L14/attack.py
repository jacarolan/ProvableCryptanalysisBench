"""Baby-step giant-step attack on the generic-group discrete-log challenger.

x is known to lie in [0, 2^t) for some small t (t=26 in the published example,
but this script reads t from GET /instance at runtime and never hard-codes it,
so it works against any fresh instance with the same kind of bound).

Let m = ceil(sqrt(2^t)) (chosen so m*m >= 2^t). Then any x in [0, 2^t) can be
written uniquely as x = j + m*i with 0 <= i, j < m.

  h = g^x = g^j * (g^m)^i   =>   h * (g^-m)^i = g^j

Baby steps: build a table label(g^j) -> j for j = 0..m-1, computed with a
running product (1 "exp" for g^0, then m-1 "mul"s), so this costs m queries.

Giant steps: compute u = g^-m (1 "exp"), then walk h, h*u, h*u^2, ... via a
running product (m-1 "mul"s, since h itself is already a known label), for m
queries total. At each giant step, if the current label matches an entry in
the baby-step table we recover x = j + m*i directly (labels are compared
locally -- for free -- since equal labels mean equal group elements).

Total oracle queries: ~2*m (+ a couple for setup, + 1 for the final submit).
For t=26, m = 2^13 = 8192, so about 16,385 queries -- well inside a 65536
query budget, independent of N's actual size (this is a generic-group BSGS,
its cost depends only on the exponent bound 2^t, not on N).
"""
from __future__ import annotations

import math
import sys

from oracle_client import Oracle, OracleError


def bsgs(o: Oracle, g: str, h: str, t: int) -> int:
    bound = 1 << t
    m = math.isqrt(bound - 1) + 1
    while m * m < bound:
        m += 1

    # --- baby steps: table of g^j for j = 0..m-1 -------------------------
    # ops: exp(g,0) then (m-1) muls, each referencing the previous result.
    baby_ops = [["exp", g, 0]]
    for _ in range(m - 1):
        baby_ops.append(["mul", "$" + str(len(baby_ops) - 1), g])
    baby_labels = o.query(baby_ops)

    table = {}
    for j, lab in enumerate(baby_labels):
        table.setdefault(lab, j)

    # --- giant steps: h, h*u, h*u^2, ... where u = g^-m -------------------
    giant_ops = [["exp", g, -m]]
    # results[0] = u. Then h_0 = h (no query needed), h_1 = mul(h, u), etc.
    for i in range(m - 1):
        prev = h if i == 0 else "$" + str(len(giant_ops) - 1)
        giant_ops.append(["mul", prev, "$0"])
    giant_results = o.query(giant_ops)
    u = giant_results[0]
    giant_labels = [h] + giant_results[1:]  # h_0, h_1, ..., h_{m-1}

    for i, lab in enumerate(giant_labels):
        if lab in table:
            j = table[lab]
            x = j + m * i
            if x < bound:
                return x
    raise RuntimeError("BSGS failed to find a match -- unexpected")


def main():
    o = Oracle()
    inst = o.instance
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]
    t = int(inst["params"]["t"])

    x = bsgs(o, g, h, t)

    ok = o.submit(x)
    print(f"x = {x}", file=sys.stderr)
    print(f"queries_used = {o.queries_used} / budget = {o.budget}", file=sys.stderr)
    print(f"submit correct = {ok}", file=sys.stderr)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
