"""Baby-step giant-step attack on a generic-group discrete-log challenger.

G is cyclic of prime order N (~20 bits, so N < 2^20 ~ 1.05e6). The oracle only
lets us combine labelled group elements (mul / inv / exp); labels reveal
nothing, but equal labels mean equal elements, so we can do all the bookkeeping
(hash tables, comparisons) locally for free and only spend queries on the
actual group operations.

Standard BSGS: choose m = ceil(sqrt(N)). Build the baby-step table
{g^i : i = 0..m-1}. Then walk giant steps h * (g^-m)^j for j = 0..m-1 until we
hit a label that's in the baby-step table; then x = i + j*m (mod N).

Query cost: m ops to build the baby-step table (via one batched request, using
"$k" back-references to chain g^0 -> g^1 -> ... -> g^{m-1} with a single mul
each), 2 ops to get g^-1 and then g^-m, and up to m-1 ops for the giant-step
chain (h, h*g^-m, h*g^-2m, ... also chained via "$k" back-references in one
request). Total <= 2*m + 1 ~= 2*sqrt(N) + 1 group-op queries, plus 1 query for
the final submit. For a 20-bit N (~1.05e6) that's roughly 2100-2200 queries,
comfortably inside the stated 6604-query budget, in only 3 HTTP round trips.
"""
from __future__ import annotations

import math
import sys

from oracle_client import Oracle, OracleError


def bsgs(o: Oracle, g: str, h: str, N: int) -> int:
    m = math.isqrt(N - 1) + 1  # ceil(sqrt(N)) for N >= 1

    # --- Baby steps: g^0, g^1, ..., g^{m-1}, built as one chained batch. ---
    baby_ops = [["exp", g, 0]]
    for i in range(1, m):
        baby_ops.append(["mul", f"${i - 1}", g])
    baby_labels = o.query(baby_ops)

    baby_table = {}
    for i, lab in enumerate(baby_labels):
        baby_table.setdefault(lab, i)  # keep smallest i (shouldn't collide anyway)

    # x = 0 case: h itself might already be in the baby table (j = 0).
    if h in baby_table:
        return baby_table[h] % N

    # --- g^{-m}, then giant steps h, h*g^-m, h*g^-2m, ... chained. ---
    setup_ops = [["inv", g], ["exp", "$0", m]]
    setup = o.query(setup_ops)
    g_neg_m = setup[1]

    giant_ops = [["mul", h, g_neg_m]]
    for j in range(2, m):
        giant_ops.append(["mul", f"${j - 2}", g_neg_m])
    giant_labels = o.query(giant_ops)

    for j_idx, lab in enumerate(giant_labels):
        j = j_idx + 1
        if lab in baby_table:
            i = baby_table[lab]
            return (i + j * m) % N

    raise RuntimeError("BSGS failed to find a collision — unexpected for a valid DL instance")


def main():
    o = Oracle()
    inst = o.instance
    N = int(inst["N"])
    g = inst["labels"]["g"]
    h = inst["labels"]["h"]

    x = bsgs(o, g, h, N)

    ok = o.submit(x)
    print(f"N={N} x={x} correct={ok} queries_used={o.queries_used} budget={o.budget}", file=sys.stderr)
    if not ok:
        raise SystemExit(f"submit failed: x={x} was rejected")
    print(x)


if __name__ == "__main__":
    main()
